"""개발·성능 검증용 샘플 데이터 생성 스크립트.

생성 위치: 저장소 루트의 data/local/ (git에 포함되지 않음)
  - seoul_grid_cp949.shp : 40×40 격자, EPSG:5186, .cpg 없는 cp949 DBF (한글 인코딩 판별 확인용)
  - perf_grid_200k.gpkg  : 400×500 격자(20만 개), EPSG:5179 (렌더링·선택 성능 확인용)

값은 공간 자기상관이 있도록 가우시안 평활한 잡음으로 만듦 (Moran's I 확인용).

실행: cd engine && uv run python ../scripts/make_sample_data.py
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely

OUT = Path(__file__).resolve().parents[1] / "data" / "local"
rng = np.random.default_rng(42)


def smooth_field(ny: int, nx: int, sigma: float) -> np.ndarray:
    """FFT 가우시안 평활로 공간 자기상관이 있는 값을 만듦. 평균 0, 표준편차 1로 정규화함."""
    noise = rng.standard_normal((ny, nx))
    ky = np.fft.fftfreq(ny)[:, None]
    kx = np.fft.fftfreq(nx)[None, :]
    kernel = np.exp(-2 * (np.pi * sigma) ** 2 * (kx**2 + ky**2))
    field = np.real(np.fft.ifft2(np.fft.fft2(noise) * kernel))
    return (field - field.mean()) / field.std()


def grid(nx: int, ny: int, x0: float, y0: float, size: float) -> np.ndarray:
    """행 우선(아래→위, 왼→오른쪽) 순서의 정사각 격자 폴리곤 배열을 만듦."""
    ii, jj = np.meshgrid(np.arange(nx), np.arange(ny))
    xmin = (x0 + ii * size).ravel()
    ymin = (y0 + jj * size).ravel()
    return shapely.box(xmin, ymin, xmin + size, ymin + size)


def make_seoul_grid() -> Path:
    nx = ny = 40
    field = smooth_field(ny, nx, sigma=4).ravel()
    n = nx * ny
    gdf = gpd.GeoDataFrame(
        {
            "격자ID": [f"G{i:04d}" for i in range(n)],
            "인구": np.round(5000 + 1500 * field + rng.normal(0, 300, n)).astype(int),
            "소득": np.round(300 + 40 * field + rng.normal(0, 15, n), 1),
            "구분": np.where(field > 0, "도심", "외곽"),
        },
        geometry=grid(nx, ny, 190_000.0, 540_000.0, 500.0),
        crs=5186,
    )
    path = OUT / "seoul_grid_cp949.shp"
    gdf.to_file(path, encoding="CP949", engine="pyogrio")
    path.with_suffix(".cpg").unlink(missing_ok=True)  # 국내 자료처럼 .cpg 없는 상태로 만듦
    return path


def make_perf_grid() -> Path:
    nx, ny = 500, 400
    field = smooth_field(ny, nx, sigma=12).ravel()
    gdf = gpd.GeoDataFrame(
        {"value": np.round(field, 4), "rank": np.argsort(np.argsort(field))},
        geometry=grid(nx, ny, 900_000.0, 1_700_000.0, 400.0),
        crs=5179,
    )
    path = OUT / "perf_grid_200k.gpkg"
    path.unlink(missing_ok=True)
    gdf.to_file(path, layer="grid", engine="pyogrio")
    return path


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for fn in (make_seoul_grid, make_perf_grid):
        p = fn()
        print(f"생성함: {p.relative_to(OUT.parents[1])}")
