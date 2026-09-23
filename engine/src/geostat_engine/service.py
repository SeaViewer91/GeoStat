"""데이터셋 열기·변경 공통 로직. API와 프로젝트 재생(열기)이 함께 씀."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pyproj import CRS

from geostat_engine.analysis.fields import evaluate, validate_name
from geostat_engine.errors import EngineError
from geostat_engine.io.table import is_table, read_table_points
from geostat_engine.io.vector import read_vector
from geostat_engine.state import AppState, Dataset, DerivedField


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
    if name not in {f.name for f in ds.fields}:
        raise EngineError("not_derived", f"계산 필드만 삭제할 수 있음: {name}")
    ds.gdf = ds.gdf.drop(columns=[name])
    ds.fields = [f for f in ds.fields if f.name != name]
