"""데이터셋 열기·변경 공통 로직. API와 프로젝트 재생(열기)이 함께 씀."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
    x = _column(ds, params["column"])
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
        "gi_star": "Gi*",
        "local_geary": "Local Geary",
    }[method]
    var = params["column"] + (f" × {params['column_y']}" if y is not None else "")
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
