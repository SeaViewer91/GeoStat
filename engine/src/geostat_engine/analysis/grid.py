"""격자(피시넷) 만들기. 래스터나 점 자료를 격자로 집계해 ESDA에 쓰는 흐름의 첫 단계임.

정사각형과 육각형을 지원함. 경위도 자료는 UTM으로 바꿔 m 단위로 만듦.
"""

from __future__ import annotations

import math
from typing import Any

import geopandas as gpd
import numpy as np
import shapely
from pyproj import CRS

from geostat_engine.errors import EngineError

# 만들 수 있는 최대 셀 수 (메모리·지도 표시 한계)
MAX_CELLS = 1_000_000


def metric_crs(crs: CRS | None, bounds_wgs84: tuple[float, float, float, float] | None) -> CRS:
    """m 단위 좌표계. 이미 투영 좌표계면 그대로, 경위도면 가운데 지점의 UTM 구역을 씀."""
    if crs is None:
        raise EngineError("missing_crs", "좌표계가 없는 자료로는 격자를 만들 수 없음")
    if not crs.is_geographic:
        return crs
    if bounds_wgs84 is None:
        raise EngineError("missing_crs", "범위를 알 수 없음")
    lon = (bounds_wgs84[0] + bounds_wgs84[2]) / 2
    lat = (bounds_wgs84[1] + bounds_wgs84[3]) / 2
    zone = int((lon + 180) // 6) + 1
    return CRS.from_epsg((32600 if lat >= 0 else 32700) + zone)


def make_grid(
    bounds: tuple[float, float, float, float],
    crs: CRS,
    cell_size: float,
    shape: str = "square",
    clip: Any | None = None,
) -> gpd.GeoDataFrame:
    """범위를 덮는 격자를 만듦. clip(같은 좌표계의 지오메트리)을 주면 겹치는 셀만 남김."""
    if cell_size <= 0:
        raise EngineError("invalid_cell_size", "셀 크기는 0보다 커야 함")
    xmin, ymin, xmax, ymax = bounds
    w, h = xmax - xmin, ymax - ymin
    if shape == "square":
        nx, ny = math.ceil(w / cell_size), math.ceil(h / cell_size)
        _check(nx * ny)
        ii, jj = np.meshgrid(np.arange(nx), np.arange(ny))
        x0 = xmin + ii.ravel() * cell_size
        y0 = ymax - (jj.ravel() + 1) * cell_size  # 위쪽 줄부터 번호를 매김
        geoms = shapely.box(x0, y0, x0 + cell_size, y0 + cell_size)
        rows, cols = jj.ravel(), ii.ravel()
    elif shape == "hexagon":
        # cell_size = 육각형 한 변 길이 (꼭짓점이 위아래인 뾰족 방향)
        r = cell_size
        dx, dy = math.sqrt(3) * r, 1.5 * r
        nx, ny = math.ceil(w / dx) + 1, math.ceil(h / dy) + 1
        _check(nx * ny)
        ii, jj = np.meshgrid(np.arange(nx), np.arange(ny))
        cx = xmin + ii.ravel() * dx + (jj.ravel() % 2) * dx / 2
        cy = ymax - jj.ravel() * dy
        angles = np.deg2rad(np.arange(6) * 60 + 30)
        ring = np.stack(
            [cx[:, None] + r * np.cos(angles), cy[:, None] + r * np.sin(angles)], axis=2
        )
        geoms = shapely.polygons(ring)
        rows, cols = jj.ravel(), ii.ravel()
    else:
        raise EngineError("invalid_shape", f"알 수 없는 격자 모양: {shape}")

    if clip is not None:
        keep = shapely.intersects(geoms, clip)
        geoms, rows, cols = geoms[keep], rows[keep], cols[keep]
        if len(geoms) == 0:
            raise EngineError("empty_grid", "자르기 범위와 겹치는 셀이 없음")
    return gpd.GeoDataFrame(
        {
            "GRID_ID": np.arange(1, len(geoms) + 1, dtype="int64"),
            "ROW": rows.astype("int32"),
            "COL": cols.astype("int32"),
        },
        geometry=geoms,
        crs=crs,
    )


def _check(n: int) -> None:
    if n > MAX_CELLS:
        raise EngineError(
            "too_many_cells",
            f"셀이 {n:,}개로 너무 많음 (최대 {MAX_CELLS:,}개). 셀 크기를 키워야 함",
        )
