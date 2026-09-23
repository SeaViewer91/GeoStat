"""지도 표시용 GeoArrow 직렬화.

프론트엔드(deck.gl GeoArrow 레이어)는 WGS84 경위도와 interleaved 좌표(xy xy …)를 기대함.
GeoJSON 대신 Arrow IPC 스트림으로 보내 수십만 피처도 파싱 없이 GPU 버퍼로 넘김.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pyarrow as pa
import shapely

from geostat_engine.errors import EngineError

ARROW_STREAM_MEDIA_TYPE = "application/vnd.apache.arrow.stream"

# 한 레이어에 섞여도 하나의 GeoArrow 타입으로 승격 가능한 조합
_FAMILIES = {
    "Point": "point",
    "MultiPoint": "point",
    "LineString": "line",
    "MultiLineString": "line",
    "LinearRing": "line",
    "Polygon": "polygon",
    "MultiPolygon": "polygon",
}

_EMPTY_BY_FAMILY = {
    "point": "MULTIPOINT EMPTY",
    "line": "MULTILINESTRING EMPTY",
    "polygon": "MULTIPOLYGON EMPTY",
}


def geometry_family(gdf: gpd.GeoDataFrame) -> str:
    """레이어의 지오메트리 계열(point/line/polygon)을 반환함."""
    types = set(gdf.geometry.dropna().geom_type.unique())
    types.discard(None)
    families = {_FAMILIES.get(t, "other") for t in types}
    if not families:
        raise EngineError("empty_geometry", "유효한 지오메트리가 없음")
    if len(families) > 1 or "other" in families:
        raise EngineError(
            "mixed_geometry",
            f"점·선·면이 섞였거나 지원하지 않는 지오메트리가 있음: {sorted(types)}",
        )
    return families.pop()


def to_display_crs(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """지도 표시용으로 EPSG:4326 변환함. 원본은 건드리지 않음."""
    if gdf.crs is None:
        minx, miny, maxx, maxy = gdf.total_bounds
        if -180 <= minx <= maxx <= 180 and -90 <= miny <= maxy <= 90:
            # 좌표 범위가 경위도로 보이면 WGS84로 간주함
            return gdf.set_crs(4326, allow_override=True)
        raise EngineError(
            "crs_missing",
            "좌표계 정보(.prj)가 없어 지도에 표시할 수 없음. 좌표계를 지정해야 함",
        )
    if gdf.crs.to_epsg() == 4326:
        return gdf
    return gdf.to_crs(4326)


def geometry_to_ipc(display_gdf: gpd.GeoDataFrame) -> bytes:
    """지오메트리와 중심점을 GeoArrow(interleaved) Arrow IPC 스트림으로 직렬화함.

    열 구성: geometry(GeoArrow), cx·cy(중심점 경위도, 올가미 선택용. 빈 도형은 NaN)
    행 순서는 원본 데이터셋과 동일함. 행 번호가 곧 피처 ID이며 선택 상태 동기화에 쓰임.
    """
    family = geometry_family(display_gdf)
    geom = display_gdf.geometry.values
    missing = shapely.is_missing(geom) | shapely.is_empty(geom)
    if missing.any():
        # null이 있으면 일부 렌더러가 버퍼 오프셋을 잘못 계산하므로 빈 도형으로 채움
        geom = geom.copy()
        geom[missing] = shapely.from_wkt(_EMPTY_BY_FAMILY[family])

    frame = gpd.GeoDataFrame(geometry=gpd.GeoSeries(geom, crs=display_gdf.crs))
    table = pa.table(
        frame.to_arrow(index=False, geometry_encoding="geoarrow", interleaved=True, include_z=False)
    )
    # GeoDa처럼 올가미 선택은 중심점 기준으로 판정함 (표시용 WGS84 좌표에서 계산)
    centroids = np.asarray(shapely.centroid(geom))
    cx = np.full(len(centroids), np.nan)
    cy = np.full(len(centroids), np.nan)
    ok = ~shapely.is_empty(centroids)  # 빈 도형의 중심점은 좌표를 꺼낼 수 없음
    cx[ok] = shapely.get_x(centroids[ok])
    cy[ok] = shapely.get_y(centroids[ok])
    table = table.append_column("cx", pa.array(cx, pa.float64()))
    table = table.append_column("cy", pa.array(cy, pa.float64()))
    # pandas 메타데이터는 JS에서 쓰지 않으므로 제거함 (지오메트리 필드의 확장 메타데이터는 유지)
    table = table.replace_schema_metadata(None)
    return _write_stream(table)


def _write_stream(table: pa.Table) -> bytes:
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    return sink.getvalue().to_pybytes()
