from __future__ import annotations

from pathlib import Path

from geostat_engine.io.encoding import resolve_shapefile_encoding
from geostat_engine.io.vector import read_vector


def test_cp949_without_cpg_is_detected(grid_shp_cp949: Path) -> None:
    assert not grid_shp_cp949.with_suffix(".cpg").exists()
    assert resolve_shapefile_encoding(grid_shp_cp949) == "CP949"


def test_utf8_without_cpg_is_detected(grid_shp_utf8_nocpg: Path) -> None:
    assert resolve_shapefile_encoding(grid_shp_utf8_nocpg) == "UTF-8"


def test_cpg_takes_precedence(grid_shp_cp949: Path) -> None:
    grid_shp_cp949.with_suffix(".cpg").write_text("949")
    assert resolve_shapefile_encoding(grid_shp_cp949) == "CP949"


def test_read_vector_decodes_korean_attributes(grid_shp_cp949: Path) -> None:
    result = read_vector(grid_shp_cp949)
    assert result.encoding == "CP949"
    # 컬럼명과 값 모두 한글이 깨지지 않아야 함
    assert "이름" in result.gdf.columns
    assert result.gdf["이름"].iloc[0] == "격자_0000"
