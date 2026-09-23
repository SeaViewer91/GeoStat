"""데이터셋 내보내기 (계산 필드 포함)."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyproj import CRS

from geostat_engine.errors import EngineError

DRIVERS = {
    ".gpkg": "GPKG",
    ".shp": "ESRI Shapefile",
    ".geojson": "GeoJSON",
    ".json": "GeoJSON",
    ".fgb": "FlatGeobuf",
    ".csv": "CSV",
}

# shapefile 필드 이름 최대 바이트 수 (DBF 규격)
_SHP_FIELD_BYTES = 10


def export_dataset(
    gdf: gpd.GeoDataFrame,
    path: str | Path,
    epsg: int | None = None,
    encoding: str | None = None,
    layer: str | None = None,
) -> dict:
    """파일로 저장하고 경고 목록을 반환함. 형식은 확장자로 결정함."""
    path = Path(path).expanduser()
    ext = path.suffix.lower()
    if ext not in DRIVERS:
        raise EngineError(
            "unsupported_format", f"지원하지 않는 저장 형식: {ext or '(확장자 없음)'}"
        )
    if not path.parent.exists():
        raise EngineError("folder_not_found", f"폴더가 없음: {path.parent}")

    warnings: list[str] = []
    out = gdf
    if epsg is not None:
        try:
            target = CRS.from_epsg(epsg)
        except Exception as exc:
            raise EngineError("invalid_crs", f"알 수 없는 EPSG 코드: {epsg}") from exc
        if out.crs is None:
            raise EngineError(
                "crs_missing", "원본 좌표계가 없어 변환할 수 없음. 먼저 좌표계를 지정해야 함"
            )
        out = out.to_crs(target)
    elif ext in {".geojson", ".json"} and out.crs is not None and out.crs.to_epsg() != 4326:
        # GeoJSON 표준(RFC 7946)은 WGS84만 허용하므로 자동 변환함
        out = out.to_crs(4326)
        warnings.append("GeoJSON 표준에 맞춰 WGS84(EPSG:4326)로 변환해 저장함")

    try:
        if ext == ".csv":
            _write_csv(out, path)
        elif ext == ".shp":
            enc = (encoding or "UTF-8").upper()
            warnings += _shapefile_name_warnings(out, enc)
            out.to_file(path, driver="ESRI Shapefile", engine="pyogrio", encoding=enc)
        else:
            kwargs = {"driver": DRIVERS[ext], "engine": "pyogrio"}
            if ext == ".gpkg":
                kwargs["layer"] = layer or path.stem
            out.to_file(path, **kwargs)
    except EngineError:
        raise
    except Exception as exc:
        raise EngineError("write_failed", f"저장하지 못함: {exc}") from exc

    return {"path": str(path), "format": DRIVERS[ext], "n_rows": len(out), "warnings": warnings}


def _write_csv(gdf: gpd.GeoDataFrame, path: Path) -> None:
    frame = pd.DataFrame(gdf.drop(columns=gdf.geometry.name))
    geom = gdf.geometry
    if len(geom) and (geom.geom_type.dropna() == "Point").all():
        # 점 레이어는 좌표를 X·Y 열로 함께 저장함
        frame["X"] = geom.x
        frame["Y"] = geom.y
    # 엑셀에서 한글이 깨지지 않도록 BOM을 붙임
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def _shapefile_name_warnings(gdf: gpd.GeoDataFrame, encoding: str) -> list[str]:
    long_names = []
    for col in gdf.columns:
        if col == gdf.geometry.name:
            continue
        try:
            n_bytes = len(str(col).encode(encoding))
        except (LookupError, UnicodeEncodeError):
            n_bytes = len(str(col).encode("utf-8"))
        if n_bytes > _SHP_FIELD_BYTES:
            long_names.append(str(col))
    if not long_names:
        return []
    names = ", ".join(long_names)
    return [
        f"shapefile 필드 이름은 {_SHP_FIELD_BYTES}바이트까지라 잘릴 수 있음: {names} "
        + "(이름을 보존하려면 GeoPackage로 저장하는 것이 좋음)"
    ]
