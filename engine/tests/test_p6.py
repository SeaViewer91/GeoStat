"""P6 기능: 샘플 데이터, 조건 선택, 지도 이미지 저장."""

from __future__ import annotations

import base64
from pathlib import Path

import numpy as np

from geostat_engine.io.raster import encode_png


def test_samples_copy_and_open(client, auth, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GEOSTAT_SAMPLE_DIR", str(tmp_path / "samples"))
    samples = client.get("/files/samples", headers=auth).json()
    assert [s["id"] for s in samples] == ["georgia", "nc_sids", "seoul_grid", "terrain"]

    path = client.post("/files/samples/georgia/copy", headers=auth).json()["path"]
    assert Path(path).parent == tmp_path / "samples"
    info = client.post("/datasets/open", json={"path": path}, headers=auth).json()
    assert info["n_rows"] == 159 and info["crs"]["epsg"] == 26917

    shp = client.post("/files/samples/seoul_grid/copy", headers=auth).json()["path"]
    assert (tmp_path / "samples" / "seoul_grid.dbf").exists()  # 부속 파일도 함께 복사함
    info = client.post("/datasets/open", json={"path": shp}, headers=auth).json()
    assert info["encoding"] == "CP949" and "인구" in [c["name"] for c in info["columns"]]

    tif = client.post("/files/samples/terrain/copy", headers=auth).json()["path"]
    r = client.post("/rasters/open", json={"path": tif}, headers=auth).json()
    assert r["crs"] == "EPSG:5186" and r["band_names"] == ["고도 (가상, m)"]

    missing = client.post("/files/samples/nope/copy", headers=auth)
    assert missing.status_code == 404


def test_query_selection(client, auth, grid_gpkg) -> None:
    ds = client.post("/datasets/open", json={"path": str(grid_gpkg)}, headers=auth).json()
    url = f"/datasets/{ds['id']}/query"
    r = client.post(url, json={"expression": "`값` >= 5 and `정수` < 15"}, headers=auth).json()
    ids = np.frombuffer(base64.b64decode(r["ids"]), dtype="<u4")
    # make_grid: 값 = i + j (5×4 격자), 정수 = 행 번호
    values = np.array([i + j for j in range(4) for i in range(5)])
    expected = np.flatnonzero((values >= 5) & (np.arange(20) < 15))
    assert r["count"] == len(expected) and (ids == expected).all()

    r = client.post(url, json={"expression": "`이름` == '격자_0000'"}, headers=auth).json()
    assert r["count"] == 1
    bad = client.post(url, json={"expression": "`값` + 1"}, headers=auth).json()
    assert bad["error"]["code"] == "invalid_expression"
    bad = client.post(url, json={"expression": "__import__('os')"}, headers=auth).json()
    assert bad["error"]["code"] == "invalid_expression"


def test_save_image(client, auth, tmp_path) -> None:
    png = encode_png(np.zeros((4, 4, 4), dtype=np.uint8))
    body = {"path": str(tmp_path / "map"), "data": base64.b64encode(png).decode()}
    r = client.post("/files/save-image", json=body, headers=auth).json()
    assert r["path"].endswith("map.png") and Path(r["path"]).read_bytes() == png
    body["data"] = base64.b64encode(b"not png").decode()
    assert (
        client.post("/files/save-image", json=body, headers=auth).json()["error"]["code"]
        == "invalid_image"
    )


def test_georgia_sample_matches_mgwr_reference(client, auth, tmp_path, monkeypatch) -> None:
    """mgwr 문서의 조지아 예제: PctBach ~ PctRural + PctFB + PctBlack, 적응 bisquare → 대역폭 117, R² 0.678."""
    import time

    monkeypatch.setenv("GEOSTAT_SAMPLE_DIR", str(tmp_path))
    path = client.post("/files/samples/georgia/copy", headers=auth).json()["path"]
    ds = client.post("/datasets/open", json={"path": path}, headers=auth).json()
    spec = {"model": "gwr", "y": "PctBach", "x": ["PctRural", "PctFB", "PctBlack"]}
    job = client.post(f"/datasets/{ds['id']}/regression", json=spec, headers=auth).json()
    t0 = time.time()
    while job["status"] == "running" and time.time() - t0 < 120:
        time.sleep(0.2)
        job = client.get(f"/jobs/{job['id']}", headers=auth).json()
    rep = job["result"]["analysis"]["report"]
    assert rep["local"][0]["bandwidth"] == 117.0
    assert abs(rep["fit"]["r2"] - 0.6778) < 1e-3
