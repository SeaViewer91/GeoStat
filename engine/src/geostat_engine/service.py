"""데이터셋 열기·변경 공통 로직. API와 프로젝트 재생(열기)이 함께 씀."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from pyproj import CRS

from geostat_engine.analysis import esda_ops
from geostat_engine.analysis import weights as weights_mod
from geostat_engine.analysis.fields import evaluate, validate_name
from geostat_engine.errors import EngineError
from geostat_engine.io.table import is_table, read_table_points
from geostat_engine.io.vector import read_vector
from geostat_engine.state import AnalysisRecord, AppState, Dataset, DerivedField, WeightsEntry

# GeoDa 기본 난수 시드와 같게 둠 (같은 설정이면 같은 결과가 나오도록)
DEFAULT_SEED = 123456789


def open_source(
    state: AppState,
    path: str | Path,
    layer: str | None = None,
    encoding: str | None = None,
    table: dict[str, Any] | None = None,
    name: str | None = None,
) -> Dataset:
    """벡터 파일 또는 좌표 열이 있는 표를 열어 세션에 등록함."""
    path = Path(path).expanduser()
    if is_table(path):
        if not table or not table.get("x") or not table.get("y") or not table.get("epsg"):
            raise EngineError(
                "table_options_required", "표 파일은 X·Y 좌표 열과 좌표계(EPSG)를 지정해야 함"
            )
        gdf, enc, sheet = read_table_points(
            path,
            x=table["x"],
            y=table["y"],
            epsg=int(table["epsg"]),
            encoding=encoding,
            sheet=table.get("sheet"),
        )
        return state.add(
            {
                "name": name or path.stem,
                "path": path,
                "layer": None,
                "encoding": enc,
                "gdf": gdf,
                "layers": [],
                "table": {**table, "sheet": sheet},
            }
        )

    result = read_vector(path, layer=layer, encoding=encoding)
    default_name = path.stem if len(result.layers) <= 1 else f"{path.stem}:{result.layer}"
    return state.add(
        {
            "name": name or default_name,
            "path": path,
            "layer": result.layer,
            "encoding": result.encoding,
            "gdf": result.gdf,
            "layers": result.layers,
        }
    )


def assign_crs(ds: Dataset, epsg: int) -> None:
    """좌표 변환 없이 좌표계 정보만 지정함 (.prj가 없거나 잘못된 경우)."""
    try:
        crs = CRS.from_epsg(epsg)
    except Exception as exc:
        raise EngineError("invalid_crs", f"알 수 없는 EPSG 코드: {epsg}") from exc
    ds.gdf = ds.gdf.set_crs(crs, allow_override=True)
    ds.crs_override = epsg
    ds.invalidate_display()


def set_field(ds: Dataset, name: str, expression: str) -> str:
    """계산 필드를 추가하거나(같은 이름의 계산 필드면) 다시 계산함."""
    derived = {f.name for f in ds.fields}
    name = validate_name(ds.gdf, name, derived)
    values = evaluate(ds.gdf, expression)
    ds.gdf[name] = values.to_numpy()
    ds.fields = [f for f in ds.fields if f.name != name] + [DerivedField(name, expression)]
    return name


def remove_field(ds: Dataset, name: str) -> None:
    """계산 필드를 지움. 분석 결과 열이면 그 분석의 결과 열 전체를 지움."""
    record = next((a for a in ds.analyses if name in a.outputs), None)
    if record is not None:
        ds.gdf = ds.gdf.drop(columns=[c for c in record.outputs if c in ds.gdf.columns])
        ds.analyses = [a for a in ds.analyses if a is not record]
        return
    if name not in {f.name for f in ds.fields}:
        raise EngineError("not_derived", f"계산 필드나 분석 결과 열만 삭제할 수 있음: {name}")
    ds.gdf = ds.gdf.drop(columns=[name])
    ds.fields = [f for f in ds.fields if f.name != name]


# ---- 공간가중치 ---------------------------------------------------------------


def create_weights(
    ds: Dataset,
    spec: dict[str, Any],
    name: str | None = None,
    weights_id: str | None = None,
    base_dir: Path | None = None,
) -> WeightsEntry:
    w, desc = weights_mod.build(ds.gdf, spec, base_dir=base_dir)
    wid = weights_id or _next_id("w", ds.weights.keys())
    entry = WeightsEntry(
        id=wid,
        name=(name or "").strip() or _default_weights_name(spec),
        spec=spec,
        description=desc,
        w=w,
        summary=weights_mod.summarize(w),
    )
    ds.weights[wid] = entry
    return entry


def _default_weights_name(spec: dict[str, Any]) -> str:
    kind = spec.get("type")
    if kind in ("queen", "rook"):
        return f"{kind}{int(spec.get('order', 1))}"
    if kind == "knn":
        return f"knn{int(spec.get('k', 6))}"
    if kind == "distance":
        t = spec.get("threshold")
        return f"dist{int(t) if t else ''}"
    if kind == "kernel":
        return f"kernel_{spec.get('function', 'triangular')}"
    return Path(str(spec.get("path", "weights"))).stem


def _next_id(prefix: str, existing) -> str:
    used = set(existing)
    i = 1
    while f"{prefix}{i}" in used:
        i += 1
    return f"{prefix}{i}"


def remove_weights(ds: Dataset, weights_id: str) -> None:
    entry = ds.get_weights(weights_id)
    users = [a for a in ds.analyses if a.params.get("weights_id") == weights_id]
    if users:
        cols = ", ".join(a.outputs[0].rsplit("_", 1)[0] for a in users)
        raise EngineError(
            "weights_in_use",
            f"'{entry.name}' 가중치로 만든 분석 결과({cols})가 있음. 결과 열을 먼저 삭제해야 함",
        )
    del ds.weights[weights_id]


# ---- 국지 공간통계 (결과를 열로 저장) --------------------------------------------


def run_local(ds: Dataset, params: dict[str, Any], record_id: str | None = None) -> AnalysisRecord:
    method = params["method"]
    entry = ds.get_weights(params["weights_id"])
    x = variable(ds, params["column"], params.get("column_base"))
    if method == "lisa_eb":
        if not params.get("rate_base"):
            raise EngineError("missing_base", "EB 비율 LISA는 분모 변수를 골라야 함")
        y = _column(ds, params["rate_base"])
    else:
        y = _column(ds, params["column_y"]) if params.get("column_y") else None
    result = esda_ops.local(
        method,
        x,
        entry.w,
        permutations=int(params.get("permutations", 999)),
        seed=params.get("seed", DEFAULT_SEED),
        alpha=float(params.get("alpha", 0.05)),
        correction=params.get("correction", "none"),
        y=y,
    )
    prefix = (params.get("prefix") or esda_ops.LOCAL_DEFAULT_PREFIX[method]).strip()
    s_stat, s_cl, s_p = esda_ops.LOCAL_SUFFIXES[method]
    outputs = [f"{prefix}_{s_stat}", f"{prefix}_{s_cl}", f"{prefix}_{s_p}"]

    # 같은 접두어의 이전 분석은 대체함. 원본 열과 이름이 겹치면 거부함
    previous = [a for a in ds.analyses if set(a.outputs) & set(outputs)]
    owned = {c for a in previous for c in a.outputs}
    for col in outputs:
        if col in ds.gdf.columns and col not in owned:
            raise EngineError("name_exists", f"이미 있는 열 이름임: {col}. 다른 접두어를 써야 함")
    for a in previous:
        remove_field(ds, a.outputs[0])

    ds.gdf[outputs[0]] = result.stat
    ds.gdf[outputs[1]] = result.cluster
    ds.gdf[outputs[2]] = result.p

    label = {
        "lisa": "LISA",
        "lisa_bv": "이변량 LISA",
        "lisa_eb": "EB 비율 LISA",
        "gi_star": "Gi*",
        "local_geary": "Local Geary",
    }[method]
    var = str(x.name)
    if method == "lisa_eb":
        var = f"{var} / {params['rate_base']}"
    elif y is not None:
        var += f" × {params['column_y']}"
    correction = {"none": "", "fdr": ", FDR", "bonferroni": ", Bonferroni"}[result.correction]
    record = AnalysisRecord(
        id=record_id or _next_id("a", [a.id for a in ds.analyses]),
        method=method,
        params={**params, "prefix": prefix, "seed": params.get("seed", DEFAULT_SEED)},
        outputs=outputs,
        description=(
            f"{label}({var}, W={entry.name}, 순열 {result.permutations}, "
            f"α={result.alpha:g}{correction})"
        ),
    )
    record.summary = {
        "threshold": result.threshold,
        "counts": result.counts,
        "n_islands": result.n_islands,
    }
    ds.analyses.append(record)
    return record


def _column(ds: Dataset, name: str):
    if name not in ds.gdf.columns or name == ds.gdf.geometry.name:
        raise EngineError("column_not_found", f"열이 없음: {name}")
    return ds.gdf[name]


def variable(ds: Dataset, name: str, base: str | None = None):
    """분석 변수. base가 있으면 차분(name − base, 시공간 차분 Moran·LISA용)을 돌려줌."""
    import pandas as pd

    x = _column(ds, name)
    if not base:
        return x
    b = _column(ds, base)
    for s in (x, b):
        if not pd.api.types.is_numeric_dtype(s) or pd.api.types.is_bool_dtype(s):
            raise EngineError("not_numeric", f"숫자 열이 아님: {s.name}")
    diff = x.astype("float64") - b.astype("float64")
    diff.name = f"{name}−{base}"
    return diff


# ---- 회귀 분석 (결과를 열로 저장) -------------------------------------------------


def prepare_regression(ds: Dataset, spec: dict[str, Any]) -> dict[str, Any]:
    """작업 프로세스로 보낼 계산 입력을 만듦. 입력 검사 오류는 여기서 바로 알려줌."""
    from geostat_engine.analysis import regression

    weights = ds.get_weights(spec["weights_id"]).w if spec.get("weights_id") else None
    coords = None
    if spec.get("model") in ("gwr", "mgwr"):
        coords, _note = weights_mod._metric_points(ds.gdf)
    return regression.prepare(ds.gdf, spec, weights, coords)


def _attach_columns(ds: Dataset, prefix: str, result_columns: dict[str, Any]) -> list[str]:
    """작업 결과 열을 <접두어>_<키> 이름으로 붙임. 같은 열을 쓰던 이전 분석은 대체함."""
    columns = {f"{prefix}_{key}": np.asarray(values) for key, values in result_columns.items()}
    for values in columns.values():
        if len(values) != len(ds.gdf):
            raise EngineError(
                "row_mismatch", "결과 행 수가 데이터와 다름. 데이터가 바뀌었을 수 있음"
            )

    previous = [a for a in ds.analyses if set(a.outputs) & set(columns)]
    owned = {c for a in previous for c in a.outputs}
    for col in columns:
        if col in ds.gdf.columns and col not in owned:
            raise EngineError("name_exists", f"이미 있는 열 이름임: {col}. 다른 접두어를 써야 함")
    for a in previous:
        remove_field(ds, a.outputs[0])
    for col, values in columns.items():
        ds.gdf[col] = values
    return list(columns)


def apply_regression(
    ds: Dataset, spec: dict[str, Any], result: dict[str, Any], record_id: str | None = None
) -> AnalysisRecord:
    """계산 결과 열을 데이터셋에 붙이고 분석 기록을 남김. 같은 접두어의 이전 결과는 대체함."""
    from geostat_engine.analysis import regression

    model = spec["model"]
    prefix = (spec.get("prefix") or regression.DEFAULT_PREFIX[model]).strip()
    outputs = _attach_columns(ds, prefix, result["columns"])

    report = result["report"]
    weights_name = (
        ds.weights[spec["weights_id"]].name if spec.get("weights_id") in ds.weights else None
    )
    desc = f"{report['title']}: {spec['y']} ~ {' + '.join(spec['x'])}"
    if weights_name:
        desc += f" (W={weights_name})"
    if spec.get("robust") == "white":
        desc += " [White 강건 표준오차]"
    record = AnalysisRecord(
        id=record_id or _next_id("a", [a.id for a in ds.analyses]),
        method="regression",
        params={**spec, "prefix": prefix},
        outputs=outputs,
        description=desc,
        summary={"report": report},
    )
    ds.analyses.append(record)
    return record


def run_regression_sync(
    ds: Dataset, spec: dict[str, Any], record_id: str | None = None
) -> AnalysisRecord:
    """작업 프로세스 없이 바로 계산함 (프로젝트 다시 열기·테스트용)."""
    from geostat_engine.analysis import regression

    payload = prepare_regression(ds, spec)
    result = regression.run(payload, lambda _p, _m: None)
    return apply_regression(ds, spec, result, record_id=record_id)


# ---- 군집 분석 (결과를 열로 저장) ------------------------------------------------


def prepare_cluster(ds: Dataset, spec: dict[str, Any]) -> dict[str, Any]:
    from geostat_engine.analysis import cluster

    weights = ds.get_weights(spec["weights_id"]).w if spec.get("weights_id") else None
    return cluster.prepare(ds.gdf, {**spec, "seed": spec.get("seed", DEFAULT_SEED)}, weights)


def apply_cluster(
    ds: Dataset, spec: dict[str, Any], result: dict[str, Any], record_id: str | None = None
) -> AnalysisRecord:
    from geostat_engine.analysis import cluster

    method = spec["method"]
    prefix = (spec.get("prefix") or cluster.DEFAULT_PREFIX[method]).strip()
    outputs = _attach_columns(ds, prefix, result["columns"])
    report = result["report"]
    weights_name = (
        ds.weights[spec["weights_id"]].name if spec.get("weights_id") in ds.weights else None
    )
    desc = f"{report['title']}: {', '.join(spec['variables'])} → {report['k']}개 군집"
    if weights_name:
        desc += f" (W={weights_name})"
    record = AnalysisRecord(
        id=record_id or _next_id("a", [a.id for a in ds.analyses]),
        method="cluster",
        params={**spec, "prefix": prefix, "seed": spec.get("seed", DEFAULT_SEED)},
        outputs=outputs,
        description=desc,
        summary={"report": report},
    )
    ds.analyses.append(record)
    return record


def run_cluster_sync(
    ds: Dataset, spec: dict[str, Any], record_id: str | None = None
) -> AnalysisRecord:
    """작업 프로세스 없이 바로 계산함 (프로젝트 다시 열기·테스트용)."""
    from geostat_engine.analysis import cluster

    payload = prepare_cluster(ds, spec)
    result = cluster.run(payload, lambda _p, _m: None)
    return apply_cluster(ds, spec, result, record_id=record_id)


# ---- 래스터·존 통계·격자 ---------------------------------------------------------


def open_raster(state: AppState, path: str | Path, name: str | None = None):
    from geostat_engine.io import raster as raster_io

    path = Path(path).expanduser()
    if not path.exists():
        raise EngineError("file_not_found", f"파일이 없음: {path}")
    info = raster_io.describe(path)
    return state.add_raster(name or path.stem, path, info)


def prepare_zonal(state: AppState, ds: Dataset, spec: dict[str, Any]) -> dict[str, Any]:
    from geostat_engine.analysis import zonal

    raster = state.get_raster(spec["raster_id"])
    return zonal.prepare(ds.gdf, raster, spec)


def apply_zonal(
    ds: Dataset,
    spec: dict[str, Any],
    result: dict[str, Any],
    record_id: str | None = None,
) -> AnalysisRecord:
    from geostat_engine.analysis import zonal

    prefix = (spec.get("prefix") or "ZS").strip()
    outputs = _attach_columns(ds, prefix, result["columns"])
    labels = ", ".join(zonal.STATS[s][2] for s in spec["stats"])
    desc = f"존 통계: {spec.get('raster_name', '래스터')} 밴드 {spec.get('band', 1)} ({labels})"
    record = AnalysisRecord(
        id=record_id or _next_id("a", [a.id for a in ds.analyses]),
        method="zonal",
        params={**spec, "prefix": prefix},
        outputs=outputs,
        description=desc,
        summary=dict(result.get("summary", {})),
    )
    ds.analyses.append(record)
    return record


def run_zonal_sync(
    ds: Dataset, spec: dict[str, Any], record_id: str | None = None
) -> AnalysisRecord:
    """프로젝트 다시 열기용: 원본 래스터 경로로 바로 다시 계산함."""
    from geostat_engine.analysis import zonal
    from geostat_engine.io import raster as raster_io
    from geostat_engine.state import RasterEntry

    path = Path(spec["raster_path"])
    if not path.exists():
        raise EngineError("source_missing", f"래스터 파일을 찾을 수 없음: {path}")
    entry = RasterEntry(id="tmp", name=path.stem, path=path, info=raster_io.describe(path))
    payload = zonal.prepare(ds.gdf, entry, spec)
    result = zonal.run(payload, lambda _p, _m: None)
    return apply_zonal(ds, spec, result, record_id=record_id)


def make_fishnet(state: AppState, spec: dict[str, Any]) -> Dataset:
    """자료 범위를 덮는 격자를 만들어 GeoPackage로 저장하고 새 데이터셋으로 엶."""
    from pyproj import CRS

    from geostat_engine.analysis import grid

    out = Path(spec["path"]).expanduser()
    if out.suffix.lower() != ".gpkg":
        out = out.with_suffix(".gpkg")
    if not out.parent.exists():
        raise EngineError("folder_not_found", f"폴더가 없음: {out.parent}")
    clip = None
    if spec.get("raster_id"):
        raster = state.get_raster(spec["raster_id"])
        src_crs = CRS.from_user_input(raster.info["crs"])
        target = grid.metric_crs(src_crs, tuple(raster.info["bounds_wgs84"]))
        import geopandas as gpd
        from shapely.geometry import box

        footprint = gpd.GeoSeries([box(*raster.info["bounds"])], crs=src_crs).to_crs(target)
        bounds = tuple(footprint.total_bounds)
        clip = footprint.iloc[0] if src_crs != target else None
        source_name = raster.name
    else:
        ds = state.get(spec["dataset_id"])
        if ds.gdf.crs is None:
            raise EngineError("missing_crs", "좌표계가 없는 자료로는 격자를 만들 수 없음")
        wgs = tuple(ds.gdf.total_bounds) if ds.gdf.crs.is_geographic else None
        target = grid.metric_crs(ds.gdf.crs, wgs)
        geoms = ds.gdf.geometry.to_crs(target)
        bounds = tuple(geoms.total_bounds)
        if spec.get("clip", True) and set(ds.gdf.geom_type.dropna()) <= {"Polygon", "MultiPolygon"}:
            import shapely

            clip = shapely.union_all(shapely.make_valid(geoms.values))
        source_name = ds.name
    gdf = grid.make_grid(
        bounds, target, float(spec["cell_size"]), shape=spec.get("shape", "square"), clip=clip
    )
    try:
        gdf.to_file(out, layer="grid", engine="pyogrio")
    except Exception as exc:
        raise EngineError("write_failed", f"격자를 저장하지 못함: {exc}") from exc
    size = f"{float(spec['cell_size']):g}m"
    kind = "육각" if spec.get("shape") == "hexagon" else "격자"
    return open_source(state, out, name=spec.get("name") or f"{source_name}_{kind}{size}")


# ---- 점 집계 (공간 결합) -----------------------------------------------------------


def run_aggregate(
    ds: Dataset,
    source: Dataset,
    params: dict[str, Any],
    record_id: str | None = None,
) -> AnalysisRecord:
    """source 피처를 ds 폴리곤에 모아 개수·합계 등을 열로 붙임."""
    from geostat_engine.analysis import aggregate

    if source is ds:
        raise EngineError("same_dataset", "집계할 점 레이어와 대상 폴리곤 레이어가 같음")
    result = aggregate.aggregate(
        ds.gdf,
        source.gdf,
        stats=list(params.get("stats", [])),
        count=bool(params.get("count", True)),
        density=bool(params.get("density", False)),
    )
    prefix = (params.get("prefix") or "PT").strip()
    outputs = _attach_columns(ds, prefix, result.columns)
    stored = {
        **params,
        "prefix": prefix,
        "source_name": source.name,
        # 프로젝트를 다시 열 때 캐시가 없으면 원본을 다시 읽어 계산함
        "source": {**source.source_spec(), "crs_override": source.crs_override},
    }
    stored.pop("source_id", None)
    record = AnalysisRecord(
        id=record_id or _next_id("a", [a.id for a in ds.analyses]),
        method="aggregate",
        params=stored,
        outputs=outputs,
        description=aggregate.describe(params, source.name),
        summary={
            "n_source": result.n_source,
            "n_matched": result.n_matched,
            "n_empty": result.n_empty,
            "notes": result.notes,
        },
    )
    ds.analyses.append(record)
    return record


def apply_aggregate_cached(
    ds: Dataset, params: dict[str, Any], cached: dict[str, Any], record_id: str | None = None
) -> AnalysisRecord:
    """프로젝트 캐시에서 읽은 집계 결과 열을 그대로 붙임."""
    from geostat_engine.analysis import aggregate

    prefix = params.get("prefix", "PT")
    columns = {c[len(prefix) + 1 :]: v for c, v in cached.items()}
    outputs = _attach_columns(ds, prefix, columns)
    record = AnalysisRecord(
        id=record_id or _next_id("a", [a.id for a in ds.analyses]),
        method="aggregate",
        params=params,
        outputs=outputs,
        description=aggregate.describe(params, params.get("source_name", "")),
    )
    ds.analyses.append(record)
    return record


def rerun_aggregate(ds: Dataset, params: dict[str, Any], record_id: str | None = None):
    """프로젝트 다시 열기용: 기록된 원본 경로를 다시 읽어 집계함."""
    src = params.get("source") or {}
    tmp = AppState()
    source = open_source(
        tmp,
        src.get("path", ""),
        layer=src.get("layer"),
        encoding=src.get("encoding"),
        table=src.get("table"),
        name=params.get("source_name"),
    )
    if src.get("crs_override"):
        assign_crs(source, int(src["crs_override"]))
    return run_aggregate(ds, source, params, record_id=record_id)


# ---- 비율·EB 평활 ---------------------------------------------------------------


def run_rate(ds: Dataset, params: dict[str, Any], record_id: str | None = None) -> AnalysisRecord:
    from geostat_engine.analysis import rates

    method = params["method"]
    w = ds.get_weights(params["weights_id"]).w if params.get("weights_id") else None
    multiplier = float(params.get("multiplier") or 1.0)
    values = rates.compute(
        method,
        _column(ds, params["event"]),
        _column(ds, params["base"]),
        w=w if method in rates.NEEDS_WEIGHTS else None,
        multiplier=1.0 if method == "excess_risk" else multiplier,
    )
    name = (params.get("name") or rates.DEFAULT_NAME[method]).strip()
    if not name:
        raise EngineError("invalid_name", "결과 열 이름이 필요함")
    previous = [a for a in ds.analyses if name in a.outputs]
    if name in ds.gdf.columns and not previous:
        raise EngineError("name_exists", f"이미 있는 열 이름임: {name}")
    for a in previous:
        remove_field(ds, a.outputs[0])
    ds.gdf[name] = values
    desc = f"{rates.LABELS[method]}: {params['event']} / {params['base']}"
    if method != "excess_risk" and multiplier != 1:
        desc += f" × {multiplier:g}"
    if w is not None and method in rates.NEEDS_WEIGHTS:
        desc += f" (W={ds.get_weights(params['weights_id']).name})"
    finite = values[np.isfinite(values)]
    record = AnalysisRecord(
        id=record_id or _next_id("a", [a.id for a in ds.analyses]),
        method="rate",
        params={**params, "name": name},
        outputs=[name],
        description=desc,
        summary={
            "min": float(finite.min()) if finite.size else None,
            "max": float(finite.max()) if finite.size else None,
            "mean": float(finite.mean()) if finite.size else None,
        },
    )
    ds.analyses.append(record)
    return record


# ---- 시공간 ------------------------------------------------------------------


def set_time_groups(ds: Dataset, groups: list[dict[str, Any]]) -> None:
    from geostat_engine.analysis import timeseries
    from geostat_engine.state import TimeGroup

    checked = [timeseries.check_group(ds.gdf, g) for g in groups]
    names = [g["name"] for g in checked]
    if len(set(names)) != len(names):
        raise EngineError("invalid_group", "시간 변수 묶음 이름이 겹침")
    ds.time_groups = [TimeGroup(g["name"], g["columns"], g["labels"]) for g in checked]


def get_time_group(ds: Dataset, name: str):
    for g in ds.time_groups:
        if g.name == name:
            return g
    raise EngineError("group_not_found", f"시간 변수 묶음이 없음: {name}")


def moran_series(ds: Dataset, params: dict[str, Any]) -> dict[str, Any]:
    """기간별 전역 Moran's I 추이."""
    group = get_time_group(ds, params["group"])
    entry = ds.get_weights(params["weights_id"])
    rows = []
    for col, label in zip(group.columns, group.labels, strict=True):
        r = esda_ops.moran(
            _column(ds, col), entry.w, int(params.get("permutations", 999)), DEFAULT_SEED
        )
        rows.append(
            {
                "label": label,
                "column": col,
                "I": r.I,
                "z_sim": r.z_sim,
                "p_sim": r.p_sim,
                "mean": float(np.nanmean(ds.gdf[col].to_numpy(dtype="float64", na_value=np.nan))),
            }
        )
    return {"group": group.name, "weights": entry.name, "rows": rows}


def run_lisa_time(
    ds: Dataset, params: dict[str, Any], record_id: str | None = None
) -> AnalysisRecord:
    """기간마다 LISA를 계산해 군집 코드 열을 붙이고 군집 전이표를 만듦."""
    from geostat_engine.analysis import timeseries

    group = get_time_group(ds, params["group"])
    entry = ds.get_weights(params["weights_id"])
    prefix = (params.get("prefix") or "TLISA").strip()
    columns: dict[str, np.ndarray] = {}
    clusters = []
    for col, label in zip(group.columns, group.labels, strict=True):
        r = esda_ops.local(
            "lisa",
            _column(ds, col),
            entry.w,
            permutations=int(params.get("permutations", 999)),
            seed=params.get("seed", DEFAULT_SEED),
            alpha=float(params.get("alpha", 0.05)),
            correction=params.get("correction", "none"),
        )
        columns[f"{label}_CL"] = r.cluster
        clusters.append(r.cluster)
    report = timeseries.transitions(clusters, group.labels)
    columns["CHG"] = report.pop("changes")
    outputs = _attach_columns(ds, prefix, columns)
    corr = {"none": "", "fdr": ", FDR", "bonferroni": ", Bonferroni"}[
        params.get("correction", "none")
    ]
    report.update(
        {
            "title": f"기간별 LISA: {group.name}",
            "group": group.name,
            "weights": entry.name,
            "n": len(ds.gdf),
            "alpha": float(params.get("alpha", 0.05)),
        }
    )
    record = AnalysisRecord(
        id=record_id or _next_id("a", [a.id for a in ds.analyses]),
        method="lisa_time",
        params={**params, "prefix": prefix, "seed": params.get("seed", DEFAULT_SEED)},
        outputs=outputs,
        description=(
            f"기간별 LISA({group.name}, {len(group.columns)}기간, W={entry.name}, "
            f"α={float(params.get('alpha', 0.05)):g}{corr})"
        ),
        summary={"report": report},
    )
    ds.analyses.append(record)
    return record


def _write_new_dataset(state: AppState, gdf, spec: dict[str, Any], default_name: str) -> Dataset:
    out = Path(spec["path"]).expanduser()
    if out.suffix.lower() != ".gpkg":
        out = out.with_suffix(".gpkg")
    if not out.parent.exists():
        raise EngineError("folder_not_found", f"폴더가 없음: {out.parent}")
    try:
        gdf.to_file(out, layer=out.stem, engine="pyogrio")
    except Exception as exc:
        raise EngineError("write_failed", f"자료를 저장하지 못함: {exc}") from exc
    return open_source(state, out, name=spec.get("name") or default_name)


def pivot_dataset(state: AppState, spec: dict[str, Any]) -> tuple[Dataset, list[str]]:
    """긴 형태 자료를 넓은 형태로 바꿔 GeoPackage로 저장하고 새 데이터셋으로 엶."""
    from geostat_engine.analysis import timeseries

    src = state.get(spec["dataset_id"])
    gdf, groups, notes = timeseries.pivot_long(
        src.gdf, spec["id_column"], spec["time_column"], list(spec["value_columns"])
    )
    ds = _write_new_dataset(state, gdf, spec, f"{src.name}_기간별")
    set_time_groups(ds, groups)
    return ds, notes


def merge_dataset(state: AppState, spec: dict[str, Any]) -> tuple[Dataset, list[str]]:
    """기간별로 나뉜 자료를 공통 ID로 이어 붙여 GeoPackage로 저장하고 새 데이터셋으로 엶."""
    from geostat_engine.analysis import timeseries

    parts = [(state.get(p["dataset_id"]).gdf, p["id_column"], p["label"]) for p in spec["parts"]]
    base = state.get(spec["parts"][0]["dataset_id"])
    gdf, groups, notes = timeseries.merge_periods(parts, list(spec["value_columns"]))
    ds = _write_new_dataset(state, gdf, spec, f"{base.name}_기간별")
    set_time_groups(ds, groups)
    return ds, notes
