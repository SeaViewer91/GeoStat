from __future__ import annotations

from pathlib import Path

import pyarrow as pa
from conftest import make_grid
from fastapi.testclient import TestClient


def test_health_needs_no_token(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_datasets_require_token(client: TestClient) -> None:
    assert client.get("/datasets").status_code == 401
    bad = {"Authorization": "Bearer wrong"}
    assert client.get("/datasets", headers=bad).status_code == 401


def test_open_shapefile(client: TestClient, auth: dict, grid_shp_cp949: Path) -> None:
    r = client.post("/datasets/open", json={"path": str(grid_shp_cp949)}, headers=auth)
    assert r.status_code == 200, r.text
    info = r.json()
    assert info["n_rows"] == 20
    assert info["geometry_type"] == "polygon"
    assert info["encoding"] == "CP949"
    assert info["crs"]["epsg"] == 5186
    minx, miny, maxx, maxy = info["bounds_wgs84"]
    # EPSG:5186 서울 부근 좌표가 경위도로 변환돼야 함
    assert 126 < minx < maxx < 128 and 37 < miny < maxy < 38
    kinds = {c["name"]: c["kind"] for c in info["columns"]}
    assert kinds == {"이름": "string", "값": "numeric", "정수": "numeric"}


def test_geometry_is_geoarrow_stream(client: TestClient, auth: dict, grid_gpkg: Path) -> None:
    ds = client.post("/datasets/open", json={"path": str(grid_gpkg)}, headers=auth).json()
    r = client.get(f"/datasets/{ds['id']}/geometry", headers=auth)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/vnd.apache.arrow.stream"
    table = pa.ipc.open_stream(r.content).read_all()
    assert table.num_rows == 20
    field = table.schema.field("geometry")
    # 단일 Polygon만 있으면 polygon, MultiPolygon이 섞이면 multipolygon으로 승격됨
    assert field.metadata[b"ARROW:extension:name"] == b"geoarrow.polygon"
    # 첫 좌표가 경위도 범위여야 함
    first = table.column("geometry")[0].as_py()[0][0]
    assert 126 < first[0] < 128 and 37 < first[1] < 38


def test_rows_paging(client: TestClient, auth: dict, grid_gpkg: Path) -> None:
    ds = client.post("/datasets/open", json={"path": str(grid_gpkg)}, headers=auth).json()
    r = client.get(f"/datasets/{ds['id']}/rows", params={"offset": 5, "limit": 3}, headers=auth)
    body = r.json()
    assert body["total"] == 20
    assert body["columns"] == ["이름", "값", "정수"]
    assert body["rows"][0] == ["격자_0100", 1.0, 5]


def test_missing_crs_then_assign(client: TestClient, auth: dict, tmp_path: Path) -> None:
    path = tmp_path / "nocrs.shp"
    make_grid(crs=None).to_file(path, encoding="UTF-8", engine="pyogrio")
    ds = client.post("/datasets/open", json={"path": str(path)}, headers=auth).json()
    assert ds["crs"] is None and ds["bounds_wgs84"] is None

    r = client.get(f"/datasets/{ds['id']}/geometry", headers=auth)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "crs_missing"

    r = client.put(f"/datasets/{ds['id']}/crs", json={"epsg": 5186}, headers=auth)
    assert r.status_code == 200 and r.json()["crs"]["epsg"] == 5186
    assert client.get(f"/datasets/{ds['id']}/geometry", headers=auth).status_code == 200


def test_missing_file_gives_readable_error(client: TestClient, auth: dict) -> None:
    r = client.post("/datasets/open", json={"path": "/no/such/file.shp"}, headers=auth)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "file_not_found"


def test_unknown_dataset_is_404(client: TestClient, auth: dict) -> None:
    r = client.get("/datasets/nope", headers=auth)
    assert r.status_code == 404
