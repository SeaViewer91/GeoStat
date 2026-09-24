"""P2 기능: 공간가중치, 전역·국지 공간자기상관, 차트용 열 데이터."""

from __future__ import annotations

import base64
import json
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pyarrow as pa
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import libpysal

COLUMBUS = Path(libpysal.examples.get_path("columbus.shp"))


def _open(client: TestClient, auth: dict, path: Path) -> dict:
    r = client.post("/datasets/open", json={"path": str(path)}, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def _weights(client, auth, ds_id, **spec) -> dict:
    r = client.post(f"/datasets/{ds_id}/weights", json=spec, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def _f64(b64: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(b64), dtype="<f8")


def _u32(ids) -> str:
    return base64.b64encode(np.asarray(ids, dtype="<u4").tobytes()).decode()


@pytest.fixture
def lattice(tmp_path: Path) -> Path:
    """10×10 격자. 왼쪽 절반은 값이 높고 오른쪽 절반은 낮아 뚜렷한 공간 군집이 있음."""
    geoms, values, binary = [], [], []
    rng = np.random.default_rng(0)
    for j in range(10):
        for i in range(10):
            geoms.append(
                box(200000 + i * 1000, 550000 + j * 1000, 201000 + i * 1000, 551000 + j * 1000)
            )
            values.append((10.0 if i < 5 else 0.0) + rng.normal(0, 1))
            binary.append(1 if i < 5 else 0)
    path = tmp_path / "lattice.gpkg"
    gpd.GeoDataFrame({"v": values, "b": binary}, geometry=geoms, crs=5186).to_file(path)
    return path


# ---- 공간가중치 ---------------------------------------------------------------


def test_contiguity_weights_summary(client, auth, lattice) -> None:
    ds = _open(client, auth, lattice)
    queen = _weights(client, auth, ds["id"], type="queen")
    s = queen["summary"]
    assert (s["n"], s["min_neighbors"], s["max_neighbors"], s["n_islands"]) == (100, 3, 8, 0)
    # 모서리 4개(3), 가장자리 32개(5), 내부 64개(8)
    assert {h["neighbors"]: h["count"] for h in s["histogram"]} == {3: 4, 5: 32, 8: 64}
    assert queen["name"] == "queen1"

    rook2 = _weights(client, auth, ds["id"], type="rook", order=2, include_lower=True)
    assert rook2["summary"]["max_neighbors"] == 12  # 1차 4 + 2차 8
    listed = client.get(f"/datasets/{ds['id']}/weights", headers=auth).json()
    assert [w["id"] for w in listed] == [queen["id"], rook2["id"]]


def test_distance_knn_kernel(client, auth, lattice) -> None:
    ds = _open(client, auth, lattice)
    t = client.get(f"/datasets/{ds['id']}/weights-threshold", headers=auth).json()
    assert t["threshold"] == pytest.approx(1000.0)
    dist = _weights(client, auth, ds["id"], type="distance")  # 임계값 생략 → 최소 거리
    assert dist["summary"]["min_neighbors"] >= 1
    knn = _weights(client, auth, ds["id"], type="knn", k=4)
    assert knn["summary"]["min_neighbors"] == knn["summary"]["max_neighbors"] == 4
    kern = _weights(client, auth, ds["id"], type="kernel", function="gaussian", k=6)
    assert kern["summary"]["n"] == 100


def test_contiguity_rejects_points(client, auth, tmp_path) -> None:
    path = tmp_path / "pts.gpkg"
    gpd.GeoDataFrame(
        {"a": [1, 2, 3]}, geometry=gpd.points_from_xy([0, 1, 2], [0, 1, 2]), crs=5186
    ).to_file(path)
    ds = _open(client, auth, path)
    r = client.post(f"/datasets/{ds['id']}/weights", json={"type": "queen"}, headers=auth)
    assert r.json()["error"]["code"] == "contiguity_needs_polygons"
    # 경위도 점은 UTM으로 변환해 거리를 계산함
    path2 = tmp_path / "ll.gpkg"
    gpd.GeoDataFrame(
        {"a": [1, 2, 3]}, geometry=gpd.points_from_xy([127, 127.01, 127.02], [37, 37, 37]), crs=4326
    ).to_file(path2)
    ds2 = _open(client, auth, path2)
    t = client.get(f"/datasets/{ds2['id']}/weights-threshold", headers=auth).json()
    assert 800 < t["threshold"] < 1000 and "UTM" in t["note"]


def test_islands_detected(client, auth, tmp_path) -> None:
    path = tmp_path / "island.gpkg"
    geoms = [box(0, 0, 1, 1), box(1, 0, 2, 1), box(10, 10, 11, 11)]
    gpd.GeoDataFrame({"v": [1.0, 2.0, 3.0]}, geometry=geoms, crs=5186).to_file(path)
    ds = _open(client, auth, path)
    s = _weights(client, auth, ds["id"], type="queen")["summary"]
    assert s["n_islands"] == 1 and s["islands"] == [2]


def test_gal_roundtrip_and_neighbors(client, auth, lattice, tmp_path) -> None:
    ds = _open(client, auth, lattice)
    queen = _weights(client, auth, ds["id"], type="queen")
    gal = tmp_path / "q.gal"
    r = client.post(
        f"/datasets/{ds['id']}/weights/{queen['id']}/save", json={"path": str(gal)}, headers=auth
    )
    assert r.status_code == 200, r.text
    lines = gal.read_text().splitlines()
    assert lines[0].split()[-1] == "100"
    assert lines[1].split() == ["1", "3"]  # ID는 1부터 씀 (GeoDa 관례)
    loaded = client.post(
        f"/datasets/{ds['id']}/weights/load", json={"path": str(gal)}, headers=auth
    ).json()
    assert loaded["summary"]["histogram"] == queen["summary"]["histogram"]

    knn = _weights(client, auth, ds["id"], type="knn", k=4)
    gwt = tmp_path / "k.gwt"
    r = client.post(
        f"/datasets/{ds['id']}/weights/{knn['id']}/save", json={"path": str(gwt)}, headers=auth
    )
    assert r.status_code == 200, r.text
    back = client.post(f"/datasets/{ds['id']}/weights/load", json={"path": str(gwt)}, headers=auth)
    assert back.status_code == 200, back.text
    assert back.json()["summary"]["mean_neighbors"] == 4

    # 0번(왼쪽 아래 모서리)의 이웃은 1, 10, 11
    r = client.post(
        f"/datasets/{ds['id']}/weights/{queen['id']}/neighbors",
        json={"ids": _u32([0])},
        headers=auth,
    ).json()
    ids = np.frombuffer(base64.b64decode(r["ids"]), dtype="<u4").tolist()
    assert ids == [1, 10, 11]


# ---- 전역 공간자기상관 ------------------------------------------------------------


def test_moran_matches_geoda_columbus(client, auth) -> None:
    """GeoDa 참조값: Columbus CRIME, Queen 인접 → Moran's I = 0.500189, E[I] = -0.0208."""
    ds = _open(client, auth, COLUMBUS)
    queen = _weights(client, auth, ds["id"], type="queen")
    r = client.post(
        f"/datasets/{ds['id']}/esda/moran",
        json={"column": "CRIME", "weights_id": queen["id"], "permutations": 999},
        headers=auth,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["I"] == pytest.approx(0.500189, abs=1e-6)
    assert body["expected"] == pytest.approx(-1 / 48)
    assert body["p_sim"] <= 0.002
    z, lag = _f64(body["z"]), _f64(body["lag"])
    assert z.size == lag.size == 49
    # Moran 산점도의 기울기가 I와 같아야 함 (행 표준화 가중치)
    slope = np.polyfit(z, lag, 1)[0]
    assert slope == pytest.approx(body["I"], rel=1e-6)
    assert sum(body["sim_hist"]["counts"]) == 999


def test_bivariate_moran_and_join_count(client, auth, lattice) -> None:
    ds = _open(client, auth, lattice)
    queen = _weights(client, auth, ds["id"], type="queen")
    url = f"/datasets/{ds['id']}/esda"
    bv = client.post(
        f"{url}/moran",
        json={"column": "v", "column_y": "b", "weights_id": queen["id"]},
        headers=auth,
    ).json()
    assert bv["I"] > 0.5 and bv["column_y"] == "b"
    jc = client.post(
        f"{url}/joincount", json={"column": "b", "weights_id": queen["id"]}, headers=auth
    ).json()
    assert jc["bb"] > jc["mean_bb"] and jc["p_sim_bb"] <= 0.01
    r = client.post(
        f"{url}/joincount", json={"column": "v", "weights_id": queen["id"]}, headers=auth
    )
    assert r.json()["error"]["code"] == "not_binary"


# ---- 국지 공간통계 ------------------------------------------------------------


@pytest.mark.parametrize("method", ["lisa", "gi_star", "local_geary"])
def test_local_statistics(client, auth, lattice, method) -> None:
    ds = _open(client, auth, lattice)
    queen = _weights(client, auth, ds["id"], type="queen")
    r = client.post(
        f"/datasets/{ds['id']}/esda/local",
        json={"method": method, "column": "v", "weights_id": queen["id"], "permutations": 499},
        headers=auth,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    _stat_col, cl_col, p_col = body["outputs"]
    cols = {c["name"]: c for c in body["info"]["columns"]}
    assert cols[cl_col]["origin"] == "analysis" and cols[cl_col]["derived"]
    assert sum(body["counts"].values()) == 100
    # 뚜렷한 군집이 있으므로 유의한 피처가 있어야 함
    assert sum(v for k, v in body["counts"].items() if k != "0") > 10

    cm = client.post(
        f"/datasets/{ds['id']}/classify",
        json={"column": cl_col, "method": body["cluster_method"]},
        headers=auth,
    ).json()
    assert cm["colors"] and len(cm["colors"]) == len(cm["labels"])
    sig = client.post(
        f"/datasets/{ds['id']}/classify",
        json={"column": p_col, "method": "significance"},
        headers=auth,
    ).json()
    assert sig["labels"][-1] == "유의하지 않음"


def test_lisa_cluster_codes_and_corrections(client, auth, lattice) -> None:
    ds = _open(client, auth, lattice)
    queen = _weights(client, auth, ds["id"], type="queen")
    url = f"/datasets/{ds['id']}/esda/local"
    base = {"method": "lisa", "column": "v", "weights_id": queen["id"], "permutations": 999}
    plain = client.post(url, json=base, headers=auth).json()
    # 왼쪽(높음)은 High-High(1), 오른쪽(낮음)은 Low-Low(2)만 나와야 함
    assert set(plain["counts"]) <= {"0", "1", "2"}
    bonf = client.post(
        url, json={**base, "correction": "bonferroni", "prefix": "LB"}, headers=auth
    ).json()
    assert bonf["threshold"] == pytest.approx(0.05 / 100)
    assert bonf["counts"].get("0", 0) >= plain["counts"].get("0", 0)
    # 같은 접두어로 다시 돌리면 이전 결과를 대체함
    again = client.post(url, json=base, headers=auth).json()
    names = [c["name"] for c in again["info"]["columns"]]
    assert names.count("LISA_CL") == 1
    # 가중치를 쓰는 분석이 있으면 가중치를 지울 수 없음
    r = client.delete(f"/datasets/{ds['id']}/weights/{queen['id']}", headers=auth)
    assert r.json()["error"]["code"] == "weights_in_use"
    # 결과 열 하나를 지우면 그 분석의 열이 모두 지워짐
    info = client.delete(f"/datasets/{ds['id']}/fields/LISA_P", headers=auth).json()
    assert not {"LISA_I", "LISA_CL", "LISA_P"} & {c["name"] for c in info["columns"]}


def test_local_rejects_missing_values(client, auth, tmp_path) -> None:
    path = tmp_path / "nan.gpkg"
    geoms = [box(i, 0, i + 1, 1) for i in range(4)]
    gpd.GeoDataFrame({"v": [1.0, None, 3.0, 4.0]}, geometry=geoms, crs=5186).to_file(path)
    ds = _open(client, auth, path)
    queen = _weights(client, auth, ds["id"], type="queen")
    r = client.post(
        f"/datasets/{ds['id']}/esda/local",
        json={"method": "lisa", "column": "v", "weights_id": queen["id"]},
        headers=auth,
    )
    assert r.json()["error"]["code"] == "missing_values"


def test_project_replays_weights_and_lisa(client, auth, lattice, tmp_path) -> None:
    ds = _open(client, auth, lattice)
    queen = _weights(client, auth, ds["id"], type="queen")
    client.post(
        f"/datasets/{ds['id']}/fields", json={"name": "v2", "expression": "`v` * 2"}, headers=auth
    )
    first = client.post(
        f"/datasets/{ds['id']}/esda/local",
        json={"method": "lisa", "column": "v2", "weights_id": queen["id"], "permutations": 199},
        headers=auth,
    ).json()
    before = client.post(f"/datasets/{ds['id']}/columns", json={"names": ["LISA_P"]}, headers=auth)

    proj = tmp_path / "p.gstproj"
    client.post(
        "/project/save", json={"path": str(proj), "datasets": [{"id": ds["id"]}]}, headers=auth
    )
    saved = json.loads(proj.read_text(encoding="utf-8"))["datasets"][0]
    assert saved["weights"][0]["spec"]["type"] == "queen"
    assert saved["analyses"][0]["outputs"] == first["outputs"]

    opened = client.post("/project/open", json={"path": str(proj)}, headers=auth).json()[
        "datasets"
    ][0]
    assert opened["warnings"] == []
    new_id = opened["info"]["id"]
    after = client.post(f"/datasets/{new_id}/columns", json={"names": ["LISA_P"]}, headers=auth)
    # 같은 난수 시드라 p값이 똑같이 재현돼야 함
    p0 = pa.ipc.open_stream(before.content).read_all().column("LISA_P").to_numpy()
    p1 = pa.ipc.open_stream(after.content).read_all().column("LISA_P").to_numpy()
    np.testing.assert_array_equal(p0, p1)
    assert client.get(f"/datasets/{new_id}/weights", headers=auth).json()[0]["id"] == queen["id"]


def test_columns_endpoint(client, auth, lattice) -> None:
    ds = _open(client, auth, lattice)
    r = client.post(f"/datasets/{ds['id']}/columns", json={"names": ["v", "b"]}, headers=auth)
    table = pa.ipc.open_stream(r.content).read_all()
    assert table.column_names == ["v", "b"] and table.num_rows == 100
    assert table.schema.field("b").type == pa.float64()
