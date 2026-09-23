"""벡터 파일 읽기."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pyogrio

from geostat_engine.errors import EngineError
from geostat_engine.io.encoding import resolve_shapefile_encoding

log = logging.getLogger(__name__)

# GDAL로 읽을 수 있으면 대부분 동작하지만, UI 파일 선택창에 노출할 확장자만 명시함
SUPPORTED_EXTENSIONS = {".shp", ".gpkg", ".geojson", ".json", ".fgb", ".kml", ".gml"}


@dataclass
class VectorReadResult:
    gdf: gpd.GeoDataFrame
    layer: str | None
    layers: list[str]
    encoding: str | None


def list_layers(path: Path) -> list[str]:
    try:
        return [str(row[0]) for row in pyogrio.list_layers(path)]
    except Exception as exc:  # GDAL 예외 종류가 다양해 포괄적으로 처리함
        raise EngineError("unreadable_file", f"파일을 읽을 수 없음: {exc}") from exc


def read_vector(
    path: str | Path,
    layer: str | None = None,
    encoding: str | None = None,
) -> VectorReadResult:
    path = Path(path).expanduser()
    if not path.exists():
        raise EngineError("file_not_found", f"파일이 없음: {path}")

    layers = list_layers(path)
    if not layers:
        raise EngineError("no_layers", "공간 레이어가 없음")
    if layer is None:
        layer = layers[0]
    elif layer not in layers:
        raise EngineError("layer_not_found", f"레이어가 없음: {layer}", layers=layers)

    if encoding is None and path.suffix.lower() == ".shp":
        encoding = resolve_shapefile_encoding(path)
        log.info("shapefile 인코딩 판별 결과: %s (%s)", encoding or "GDAL 기본값", path.name)

    try:
        gdf = _read(path, layer, encoding, use_arrow=True)
    except Exception as exc:  # noqa: BLE001 - 드라이버별 예외가 제각각임
        # Arrow 경로가 실패하는 드라이버·인코딩 조합이 있어 일반 경로로 한 번 더 시도함
        log.warning("Arrow 읽기 실패, 일반 모드로 재시도함: %s", exc)
        try:
            gdf = _read(path, layer, encoding, use_arrow=False)
        except Exception as exc2:
            raise EngineError("read_failed", f"데이터를 읽지 못함: {exc2}") from exc2

    if gdf.geometry.name is None or len(gdf.columns) == 0:
        raise EngineError("no_geometry", "지오메트리 열이 없음")

    gdf = gdf.reset_index(drop=True)
    return VectorReadResult(gdf=gdf, layer=layer, layers=layers, encoding=encoding)


def _read(path: Path, layer: str, encoding: str | None, use_arrow: bool) -> gpd.GeoDataFrame:
    kwargs: dict = {"layer": layer, "use_arrow": use_arrow}
    if encoding:
        kwargs["encoding"] = encoding
    return pyogrio.read_dataframe(path, **kwargs)
