"""P4 기능: 공간군집화(SKATER, Max-p, AZP, Region K-Means, Ward)와 비공간 군집화."""

from __future__ import annotations

import json
import shutil
import time
import warnings
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import libpysal

COLUMBUS = Path(libpysal.examples.get_path("columbus.shp"))
VARS = ["CRIME", "INC", "HOVAL"]


@pytest.fixture
def columbus(tmp_path: Path) -> Path:
    for f in COLUMBUS.parent.glob("columbus.*"):
        shutil.copy(f, tmp_path / f.name)
    return tmp_path / "columbus.shp"


def _open(client: TestClient, auth: dict, path: Path) -> dict:
    r = client.post("/datasets/open", json={"path": str(path)}, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def _weights(client, auth, ds_id, **spec) -> str:
    r = client.post(f"/datasets/{ds_id}/weights", json=spec or {"type": "queen"}, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _run(client, auth, ds_id, **spec) -> dict:
    r = client.post(f"/datasets/{ds_id}/cluster", json=spec, headers=auth)
    assert r.status_code == 200, r.text
    job_id = r.json()["id"]
    t0 = time.time()
    while time.time() - t0 < 180:
        job = client.get(f"/jobs/{job_id}", headers=auth).json()
        if job["status"] != "running":
            break
        time.sleep(0.2)
    assert job["status"] == "done", job
    return job["result"]


def _labels(client, auth, ds_id, column) -> np.ndarray:
    import pyarrow as pa

    r = client.post(f"/datasets/{ds_id}/columns", json={"names": [column]}, headers=auth)
    assert r.status_code == 200, r.text
    table = pa.ipc.open_stream(r.content).read_all()
    return table.column(column).to_numpy()


@pytest.mark.parametrize(
    "method", ["skater", "azp", "region_kmeans", "ward_spatial", "kmeans", "hierarchical"]
)
def test_cluster_methods(client, auth, columbus, method) -> None:
    ds = _open(client, auth, columbus)
    wid = _weights(client, auth, ds["id"])
    res = _run(client, auth, ds["id"], method=method, variables=VARS, n_clusters=5, weights_id=wid)
    rep = res["analysis"]["report"]
    prefix = {
        "skater": "SKATER",
        "azp": "AZP",
        "region_kmeans": "RKM",
        "ward_spatial": "WARDSP",
        "kmeans": "KMEANS",
        "hierarchical": "HCLUST",
    }[method]
    assert res["analysis"]["outputs"] == [f"{prefix}_GRP"]
    assert rep["k"] == 5 and sum(c["size"] for c in rep["clusters"]) == 49
    sizes = [c["size"] for c in rep["clusters"]]
    assert sizes == sorted(sizes, reverse=True)  # 크기 순으로 번호를 매김
    assert 0 < rep["ratio"] < 1
    # 군집 내 SS 합 + 군집 간 SS = 전체 SS
    summary = {k: v for k, v in rep["summary"]}
    assert summary["군집 내 제곱합"] + summary["군집 간 제곱합"] == pytest.approx(
        summary["전체 제곱합"]
    )
    assert summary["전체 제곱합"] == pytest.approx(49 * 3)  # 표준화했으므로 n × 변수 수
    if method in ("skater", "azp", "region_kmeans", "ward_spatial"):
        # 공간 제약 군집은 모든 군집이 한 덩어리여야 함
        assert all(c["fragments"] == 1 for c in rep["clusters"]), rep["clusters"]
    labels = _labels(client, auth, ds["id"], f"{prefix}_GRP")
    assert set(np.unique(labels)) == {1, 2, 3, 4, 5}


def test_kmeans_matches_sklearn_ratio(client, auth, columbus) -> None:
    from sklearn.cluster import KMeans

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        db = libpysal.io.open(str(COLUMBUS.with_suffix(".dbf")))
        X = np.column_stack([db.by_col(v) for v in VARS])
    Z = (X - X.mean(axis=0)) / X.std(axis=0)
    km = KMeans(n_clusters=4, n_init=50, random_state=123456789).fit(Z)
    expected = 1 - km.inertia_ / (Z**2).sum()
    ds = _open(client, auth, columbus)
    res = _run(client, auth, ds["id"], method="kmeans", variables=VARS, n_clusters=4)
    assert res["analysis"]["report"]["ratio"] == pytest.approx(expected, rel=1e-9)
    # 가중치가 없으면 조각 수는 계산하지 않음
    assert res["analysis"]["report"]["clusters"][0]["fragments"] is None


def test_maxp_threshold(client, auth, columbus) -> None:
    ds = _open(client, auth, columbus)
    wid = _weights(client, auth, ds["id"])
    res = _run(client, auth, ds["id"], method="maxp", variables=VARS, weights_id=wid, threshold=8)
    rep = res["analysis"]["report"]
    assert all(c["size"] >= 8 for c in rep["clusters"])
    assert rep["k"] >= 2

    # 임계값 열: 지역별 면적 합이 기준 이상
    res = _run(
        client,
        auth,
        ds["id"],
        method="maxp",
        variables=VARS,
        weights_id=wid,
        threshold_column="AREA",
        threshold=1.5,
        prefix="MPA",
    )
    labels = _labels(client, auth, ds["id"], "MPA_GRP")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        area = np.array(libpysal.io.open(str(COLUMBUS.with_suffix(".dbf"))).by_col("AREA"))
    for c in np.unique(labels):
        assert area[labels == c].sum() >= 1.5


def test_cluster_validation(client, auth, columbus) -> None:
    ds = _open(client, auth, columbus)
    url = f"/datasets/{ds['id']}/cluster"
    r = client.post(url, json={"method": "skater", "variables": VARS}, headers=auth)
    assert r.json()["error"]["code"] == "weights_required"
    r = client.post(
        url, json={"method": "kmeans", "variables": VARS, "n_clusters": 60}, headers=auth
    )
    assert r.json()["error"]["code"] == "invalid_k"
    # 거리 기준이 짧아 여러 조각으로 나뉜 가중치: AZP는 거부, SKATER는 경고와 함께 실행
    wid = _weights(client, auth, ds["id"], type="distance", threshold=0.6)
    r = client.post(url, json={"method": "azp", "variables": VARS, "weights_id": wid}, headers=auth)
    assert r.json()["error"]["code"] == "disconnected"
    res = _run(client, auth, ds["id"], method="skater", variables=VARS, weights_id=wid)
    assert any("조각" in n for n in res["analysis"]["report"]["notes"])


def test_cluster_project_and_report(client, auth, columbus, tmp_path) -> None:
    ds = _open(client, auth, columbus)
    wid = _weights(client, auth, ds["id"])
    res = _run(client, auth, ds["id"], method="azp", variables=VARS, weights_id=wid)
    aid = res["analysis"]["id"]
    before = _labels(client, auth, ds["id"], "AZP_GRP")

    report_path = tmp_path / "azp.txt"
    client.post(
        f"/datasets/{ds['id']}/analyses/{aid}/report",
        json={"path": str(report_path)},
        headers=auth,
    )
    text = report_path.read_text(encoding="utf-8")
    assert "군집 분석 보고서" in text and "군집별 요약" in text

    proj = tmp_path / "c.gstproj"
    client.post(
        "/project/save", json={"path": str(proj), "datasets": [{"id": ds["id"]}]}, headers=auth
    )
    saved = json.loads(proj.read_text(encoding="utf-8"))
    assert saved["datasets"][0]["analyses"][0]["method"] == "cluster"
    opened = client.post("/project/open", json={"path": str(proj)}, headers=auth).json()
    entry = opened["datasets"][0]
    assert entry["warnings"] == []
    after = _labels(client, auth, entry["info"]["id"], "AZP_GRP")
    assert (before == after).all()

    # 캐시가 없으면 같은 시드로 다시 계산해 같은 결과를 냄
    shutil.rmtree(tmp_path / "c.gstcache")
    opened = client.post("/project/open", json={"path": str(proj)}, headers=auth).json()
    entry = opened["datasets"][0]
    assert any("다시 계산" in w for w in entry["warnings"])
    assert (_labels(client, auth, entry["info"]["id"], "AZP_GRP") == before).all()


def test_spopt_region_without_matplotlib() -> None:
    """앱 번들은 matplotlib을 빼므로, 없어도 spopt 지역화 모듈을 불러올 수 있어야 함."""
    import subprocess
    import sys

    code = """
import builtins
real = builtins.__import__
def blocked(name, *a, **k):
    if name.startswith("matplotlib"):
        raise ModuleNotFoundError("No module named 'matplotlib'")
    return real(name, *a, **k)
builtins.__import__ = blocked
from geostat_engine.analysis.cluster import _spopt_region
assert hasattr(_spopt_region(), "Skater")
"""
    subprocess.run([sys.executable, "-c", code], check=True, timeout=120)
