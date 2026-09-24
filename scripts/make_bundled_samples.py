"""앱에 넣는 샘플 데이터를 만드는 스크립트 (engine/src/geostat_engine/samples/).

  georgia.gpkg      조지아주 카운티 교육 수준 (GWR 교과서 예제, UTM 17N 좌표계 지정)
  nc_sids.gpkg      노스캐롤라이나 영아 돌연사(SIDS) (ESDA 고전 예제, 경위도 좌표계 지정)
  seoul_grid.shp    서울 부근 가상 격자 (cp949 DBF, .cpg 없음 → 한글 인코딩 자동 판별 확인용)
  terrain.tif       서울 부근 가상 지형 래스터 (존 통계·격자 집계 연습용)

원본 셰이프파일에는 좌표계 정보가 없어 문헌에 적힌 좌표계를 지정해 GeoPackage로 저장함.
실행: cd engine && uv run python ../scripts/make_bundled_samples.py
"""

from __future__ import annotations

import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import shapely
from rasterio.transform import from_origin

warnings.simplefilter("ignore")
import libpysal  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "engine" / "src" / "geostat_engine" / "samples"
rng = np.random.default_rng(2026)


def smooth(ny: int, nx: int, sigma: float) -> np.ndarray:
    noise = rng.standard_normal((ny, nx))
    ky = np.fft.fftfreq(ny)[:, None]
    kx = np.fft.fftfreq(nx)[None, :]
    kernel = np.exp(-2 * (np.pi * sigma) ** 2 * (kx**2 + ky**2))
    f = np.real(np.fft.ifft2(np.fft.fft2(noise) * kernel))
    return (f - f.mean()) / f.std()


def georgia() -> None:
    gdf = gpd.read_file(libpysal.examples.get_path("G_utm.shp")).set_crs(26917)
    keep = ["AreaKey", "Latitude", "Longitud", "TotPop90", "PctRural", "PctBach", "PctEld",
            "PctFB", "PctPov", "PctBlack", "geometry"]
    gdf[[c for c in keep if c in gdf.columns]].to_file(OUT / "georgia.gpkg", layer="georgia", engine="pyogrio")


def nc_sids() -> None:
    gdf = gpd.read_file(libpysal.examples.get_path("sids2.shp")).set_crs(4267).to_crs(4326)
    gdf.to_file(OUT / "nc_sids.gpkg", layer="nc_sids", engine="pyogrio")


def seoul_grid() -> None:
    nx = ny = 30
    field = smooth(ny, nx, 3).ravel()
    ii, jj = np.meshgrid(np.arange(nx), np.arange(ny))
    x0 = 190_000 + ii.ravel() * 500.0
    y0 = 545_000 + jj.ravel() * 500.0
    n = nx * ny
    gdf = gpd.GeoDataFrame(
        {
            "격자ID": [f"G{i:04d}" for i in range(n)],
            "인구": np.round(5000 + 1500 * field + rng.normal(0, 300, n)).astype(int),
            "소득": np.round(300 + 40 * field + rng.normal(0, 15, n), 1),
            "녹지율": np.clip(np.round(30 - 12 * field + rng.normal(0, 5, n), 1), 0, 100),
            "구분": np.where(field > 0, "도심", "외곽"),
        },
        geometry=shapely.box(x0, y0, x0 + 500, y0 + 500),
        crs=5186,
    )
    path = OUT / "seoul_grid.shp"
    gdf.to_file(path, encoding="CP949", engine="pyogrio")
    path.with_suffix(".cpg").unlink(missing_ok=True)


def terrain() -> None:
    n = 800
    base = smooth(n, n, 40) * 120 + smooth(n, n, 8) * 25 + 180
    yy, xx = np.mgrid[0:n, 0:n]
    base += 150 * np.exp(-(((xx - 520) / 160) ** 2 + ((yy - 260) / 140) ** 2))  # 산
    base = np.maximum(base, 0).astype("float32")
    with rasterio.open(
        OUT / "terrain.tif", "w", driver="GTiff", width=n, height=n, count=1, dtype="float32",
        crs="EPSG:5186", transform=from_origin(188_000, 562_000, 25, 25), nodata=-9999,
        compress="deflate", predictor=3, tiled=True,
    ) as dst:
        dst.write(base, 1)
        dst.set_band_description(1, "고도 (가상, m)")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for fn in (georgia, nc_sids, seoul_grid, terrain):
        fn()
    for p in sorted(OUT.iterdir()):
        print(f"{p.name:<22}{p.stat().st_size / 1024:8.0f} KB")
