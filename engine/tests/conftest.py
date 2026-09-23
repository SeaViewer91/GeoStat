from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box

from geostat_engine.server import create_app

TOKEN = "test-token"


def make_grid(nx: int = 5, ny: int = 4, crs: int | None = 5186) -> gpd.GeoDataFrame:
    """한글 속성을 가진 격자 폴리곤을 만듦. 좌표는 EPSG:5186 서울 부근임."""
    x0, y0, size = 195_000.0, 545_000.0, 1_000.0
    geoms, names, values = [], [], []
    for j in range(ny):
        for i in range(nx):
            geoms.append(
                box(x0 + i * size, y0 + j * size, x0 + (i + 1) * size, y0 + (j + 1) * size)
            )
            names.append(f"격자_{j:02d}{i:02d}")
            values.append(float(i + j))
    return gpd.GeoDataFrame(
        {"이름": names, "값": values, "정수": np.arange(len(geoms))}, geometry=geoms, crs=crs
    )


@pytest.fixture
def grid_shp_cp949(tmp_path: Path) -> Path:
    """.cpg 없는 cp949 shapefile (국내 자료에서 흔한 형태)."""
    path = tmp_path / "grid_cp949.shp"
    make_grid().to_file(path, encoding="CP949", engine="pyogrio")
    path.with_suffix(".cpg").unlink(missing_ok=True)
    return path


@pytest.fixture
def grid_shp_utf8_nocpg(tmp_path: Path) -> Path:
    path = tmp_path / "grid_utf8.shp"
    make_grid().to_file(path, encoding="UTF-8", engine="pyogrio")
    path.with_suffix(".cpg").unlink(missing_ok=True)
    return path


@pytest.fixture
def grid_gpkg(tmp_path: Path) -> Path:
    path = tmp_path / "grid.gpkg"
    make_grid().to_file(path, layer="grid", engine="pyogrio")
    return path


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(token=TOKEN))


@pytest.fixture
def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}
