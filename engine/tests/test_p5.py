"""P5 기능: 래스터 열기·타일, 오버뷰, 존 통계, 격자 만들기, 프로젝트 보존."""

from __future__ import annotations

import json
import shutil
import struct
import time
import zlib
from pathlib import Path

import numpy as np
import pytest
import rasterio
from conftest import make_grid
from rasterio.transform import from_origin

# make_grid()와 같은 범위(195,000~200,000 / 545,000~549,000, EPSG:5186)를 10 m 셀로 덮는 래스터
X0, Y0, RES = 195_000.0, 549_000.0, 10.0
NX, NY = 500, 400


def _write_raster(path: Path, count: int = 1, crs: int | None = 5186) -> np.ndarray:
    cols = np.tile(np.arange(NX, dtype="float32"), (NY, 1))  # 값 = 열 번호
    data = np.stack([cols + 1000 * b for b in range(count)])
    data[0, :5, :5] = -9999  # 왼쪽 위 모서리는 값 없음
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=NX,
        height=NY,
        count=count,
        dtype="float32",
        crs=f"EPSG:{crs}" if crs else None,
        transform=from_origin(X0, Y0, RES, RES),
        nodata=-9999,
    ) as dst:
        dst.write(data)
    return data


@pytest.fixture
def dem(tmp_path: Path) -> Path:
    path = tmp_path / "dem.tif"
    _write_raster(path)
    return path


def _open_raster(client, auth, path: Path) -> dict:
    r = client.post("/rasters/open", json={"path": str(path)}, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def _png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", data[16:24])
    return w, h


def _png_alpha(data: bytes) -> np.ndarray:
    """직접 만든 PNG(필터 0, RGBA)의 알파 채널."""
    w, h = _png_size(data)
    idat = data.index(b"IDAT")
    length = struct.unpack(">I", data[idat - 4 : idat])[0]
    raw = np.frombuffer(zlib.decompress(data[idat + 4 : idat + 4 + length]), np.uint8)
    return raw.reshape(h, w * 4 + 1)[:, 1:].reshape(h, w, 4)[..., 3]


def _lonlat_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    import math

    n = 2**z
    return int((lon + 180) / 360 * n), int(
        (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    )


def test_open_raster_and_tiles(client, auth, dem) -> None:
    r = client.post("/files/inspect", json={"path": str(dem)}, headers=auth).json()
    assert r["kind"] == "raster"
    info = _open_raster(client, auth, dem)
    assert (info["width"], info["height"], info["count"]) == (NX, NY, 1)
    assert info["crs"] == "EPSG:5186" and info["nodata"] == -9999
    assert info["stats"][0]["min"] == pytest.approx(0, abs=2)
    assert info["stats"][0]["max"] == pytest.approx(NX - 1, abs=2)
    assert not info["needs_overviews"] and not info["categorical"]
    west, south, east, north = info["bounds_wgs84"]
    assert 126 < west < east < 128 and 37 < south < north < 38

    z = 14
    x, y = _lonlat_tile((west + east) / 2, (south + north) / 2, z)
    url = f"/rasters/{info['id']}/tiles/{z}/{x}/{y}.png"
    res = client.get(url, params={"vmin": "0", "vmax": "499", "colormap": "terrain"}, headers=auth)
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"
    assert _png_size(res.content) == (256, 256)
    assert _png_alpha(res.content).max() == 255

    # 래스터 밖 타일은 내용 없음(204)
    far = client.get(
        f"/rasters/{info['id']}/tiles/{z}/0/0.png", params={"vmin": "0", "vmax": "1"}, headers=auth
    )
    assert far.status_code == 204
    bad = client.get(url, params={"vmin": "0", "vmax": "1", "bands": "2"}, headers=auth)
    assert bad.json()["error"]["code"] == "invalid_band"
    # 토큰 없이는 거부
    assert client.get(url, params={"vmin": "0", "vmax": "1"}).status_code == 401


def test_rgb_tile_and_overviews(client, auth, tmp_path) -> None:
    path = tmp_path / "rgb.tif"
    _write_raster(path, count=3)
    info = _open_raster(client, auth, path)
    west, south, east, north = info["bounds_wgs84"]
    x, y = _lonlat_tile((west + east) / 2, (south + north) / 2, 13)
    res = client.get(
        f"/rasters/{info['id']}/tiles/13/{x}/{y}.png",
        params={"bands": "1,2,3", "vmin": "0,1000,2000", "vmax": "499,1499,2499"},
        headers=auth,
    )
    assert res.status_code == 200
    before = path.read_bytes()
    r = client.post(f"/rasters/{info['id']}/overviews", headers=auth).json()
    assert r["overviews"] == [2]  # 500 px → 256 px 이상인 단계까지만
    assert path.with_suffix(".tif.ovr").exists()
    assert path.read_bytes() == before  # 원본은 그대로


def test_raster_without_crs(client, auth, tmp_path) -> None:
    path = tmp_path / "nocrs.tif"
    _write_raster(path, crs=None)
    r = client.post("/rasters/open", json={"path": str(path)}, headers=auth)
    assert r.json()["error"]["code"] == "raster_no_crs"


def _wait(client, auth, job_id: str) -> dict:
    t0 = time.time()
    while time.time() - t0 < 120:
        job = client.get(f"/jobs/{job_id}", headers=auth).json()
        if job["status"] != "running":
            return job
        time.sleep(0.2)
    raise AssertionError("작업 시간 초과")


def _zonal(client, auth, ds_id, raster_id, **extra) -> dict:
    r = client.post(
        f"/datasets/{ds_id}/zonal", json={"raster_id": raster_id, **extra}, headers=auth
    )
    assert r.status_code == 200, r.text
    job = _wait(client, auth, r.json()["id"])
    assert job["status"] == "done", job
    return job["result"]


def _column(client, auth, ds_id, name) -> np.ndarray:
    import pyarrow as pa

    r = client.post(f"/datasets/{ds_id}/columns", json={"names": [name]}, headers=auth)
    return pa.ipc.open_stream(r.content).read_all().column(name).to_numpy()


def test_zonal_stats(client, auth, dem, grid_gpkg) -> None:
    raster = _open_raster(client, auth, dem)
    ds = client.post("/datasets/open", json={"path": str(grid_gpkg)}, headers=auth).json()
    res = _zonal(client, auth, ds["id"], raster["id"], stats=["mean", "min", "max", "count"])
    assert res["analysis"]["outputs"] == ["ZS_MEAN", "ZS_MIN", "ZS_MAX", "ZS_COUNT"]
    assert res["analysis"]["method"] == "zonal" and res["analysis"]["report"] is None
    mean = _column(client, auth, ds["id"], "ZS_MEAN")
    count = _column(client, auth, ds["id"], "ZS_COUNT")
    # 격자 i열(1 km)은 래스터 열 100i ~ 100i+99를 덮으므로 평균은 100i + 49.5
    cols = np.tile(np.arange(5), 4)
    expected = 100 * cols + 49.5
    # 셀 하나(1 km²)는 10 m 셀 10,000개. 왼쪽 위 격자만 값 없는 셀 25개(열 0~4)가 빠짐
    top_left = 15  # make_grid는 아래 줄부터 번호를 매김 → 마지막 줄의 첫 셀
    expected[top_left] = (100 * 4950 - 5 * 10) / (10_000 - 25)
    assert np.allclose(mean, expected), mean
    assert count[top_left] == pytest.approx(10_000 - 25)
    assert np.allclose(np.delete(count, top_left), 10_000)

    # 경위도 자료도 래스터 좌표계로 바꿔서 계산함
    geo = tmp_geo = grid_gpkg.with_name("grid_4326.gpkg")
    make_grid().to_crs(4326).to_file(tmp_geo, layer="grid", engine="pyogrio")
    ds2 = client.post("/datasets/open", json={"path": str(geo)}, headers=auth).json()
    _zonal(client, auth, ds2["id"], raster["id"], stats=["mean"], prefix="DEM")
    assert np.allclose(_column(client, auth, ds2["id"], "DEM_MEAN"), expected, atol=1)


def test_zonal_validation(client, auth, dem, tmp_path) -> None:
    raster = _open_raster(client, auth, dem)
    pts = tmp_path / "pts.gpkg"
    make_grid().set_geometry(make_grid().centroid).to_file(pts, engine="pyogrio")
    ds = client.post("/datasets/open", json={"path": str(pts)}, headers=auth).json()
    r = client.post(
        f"/datasets/{ds['id']}/zonal", json={"raster_id": raster["id"]}, headers=auth
    ).json()
    assert r["error"]["code"] == "not_polygon"


def test_fishnet(client, auth, dem, grid_gpkg, tmp_path) -> None:
    ds = client.post("/datasets/open", json={"path": str(grid_gpkg)}, headers=auth).json()
    out = tmp_path / "fish.gpkg"
    info = client.post(
        "/grid/fishnet",
        json={"dataset_id": ds["id"], "cell_size": 500, "path": str(out)},
        headers=auth,
    ).json()
    assert info["n_rows"] == 10 * 8 and out.exists()
    assert info["crs"]["epsg"] == 5186
    hexes = client.post(
        "/grid/fishnet",
        json={
            "dataset_id": ds["id"],
            "cell_size": 300,
            "shape": "hexagon",
            "path": str(out.with_name("hex")),
        },
        headers=auth,
    ).json()
    assert hexes["n_rows"] > 0 and hexes["geometry_type"] == "polygon"

    raster = _open_raster(client, auth, dem)
    info = client.post(
        "/grid/fishnet",
        json={"raster_id": raster["id"], "cell_size": 1000, "path": str(tmp_path / "r.gpkg")},
        headers=auth,
    ).json()
    assert info["n_rows"] == 20
    too_many = client.post(
        "/grid/fishnet",
        json={"raster_id": raster["id"], "cell_size": 1, "path": str(tmp_path / "x.gpkg")},
        headers=auth,
    ).json()
    assert too_many["error"]["code"] == "too_many_cells"


def test_project_keeps_raster_and_zonal(client, auth, dem, grid_gpkg, tmp_path) -> None:
    raster = _open_raster(client, auth, dem)
    ds = client.post("/datasets/open", json={"path": str(grid_gpkg)}, headers=auth).json()
    _zonal(client, auth, ds["id"], raster["id"], stats=["mean"])
    before = _column(client, auth, ds["id"], "ZS_MEAN")
    proj = tmp_path / "p.gstproj"
    client.post(
        "/project/save",
        json={
            "path": str(proj),
            "datasets": [{"id": ds["id"]}],
            "rasters": [{"id": raster["id"], "ui": {"colormap": "terrain"}}],
        },
        headers=auth,
    )
    saved = json.loads(proj.read_text(encoding="utf-8"))
    assert saved["rasters"][0]["path"] == "dem.tif"

    opened = client.post("/project/open", json={"path": str(proj)}, headers=auth).json()
    assert opened["rasters"][0]["info"]["name"] == "dem"
    assert opened["rasters"][0]["ui"] == {"colormap": "terrain"}
    entry = opened["datasets"][0]
    assert entry["warnings"] == []
    assert np.allclose(_column(client, auth, entry["info"]["id"], "ZS_MEAN"), before)

    shutil.rmtree(tmp_path / "p.gstcache")
    opened = client.post("/project/open", json={"path": str(proj)}, headers=auth).json()
    entry = opened["datasets"][0]
    assert any("다시 계산" in w for w in entry["warnings"])
    assert np.allclose(_column(client, auth, entry["info"]["id"], "ZS_MEAN"), before)
