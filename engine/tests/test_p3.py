"""P3 기능: 회귀 분석(OLS·공간시차·공간오차·GWR·MGWR), 작업 진행·취소, 결과 보존."""

from __future__ import annotations

import base64
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


@pytest.fixture
def columbus(tmp_path: Path) -> Path:
    """프로젝트 캐시 테스트가 원본 폴더를 건드리지 않도록 복사해서 씀."""
    for f in COLUMBUS.parent.glob("columbus.*"):
        shutil.copy(f, tmp_path / f.name)
    return tmp_path / "columbus.shp"


def _open(client: TestClient, auth: dict, path: Path) -> dict:
    r = client.post("/datasets/open", json={"path": str(path)}, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def _queen(client, auth, ds_id) -> str:
    return client.post(f"/datasets/{ds_id}/weights", json={"type": "queen"}, headers=auth).json()[
        "id"
    ]


def _wait(client, auth, job_id: str, timeout: float = 180) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        job = client.get(f"/jobs/{job_id}", headers=auth).json()
        if job["status"] != "running":
            return job
        time.sleep(0.2)
    raise AssertionError("작업이 제한 시간 안에 끝나지 않음")


def _run(client, auth, ds_id, **spec) -> dict:
    r = client.post(f"/datasets/{ds_id}/regression", json=spec, headers=auth)
    assert r.status_code == 200, r.text
    job = _wait(client, auth, r.json()["id"])
    assert job["status"] == "done", job
    return job["result"]


def _summary(report: dict) -> dict:
    return {label: value for label, value in report["summary"]}


def _diag(report: dict, name: str) -> dict:
    return next(d for d in report["diagnostics"] if d["name"] == name)


def test_ols_matches_geoda_columbus(client, auth, columbus) -> None:
    """GeoDa 참조값 (Anselin, GeoDa Workbook): HOVAL ~ INC + CRIME, Queen 가중치."""
    ds = _open(client, auth, columbus)
    wid = _queen(client, auth, ds["id"])
    res = _run(client, auth, ds["id"], model="ols", y="HOVAL", x=["INC", "CRIME"], weights_id=wid)
    rep = res["analysis"]["report"]
    coefs = {c["name"]: c["coef"] for c in rep["coefficients"]}
    assert coefs["CONSTANT"] == pytest.approx(46.4282, abs=1e-3)
    assert coefs["INC"] == pytest.approx(0.62898, abs=1e-4)
    assert coefs["CRIME"] == pytest.approx(-0.48489, abs=1e-4)
    assert _summary(rep)["R²"] == pytest.approx(0.349514, abs=1e-5)
    assert _diag(rep, "잔차 Moran's I")["value"] == pytest.approx(0.171310, abs=1e-5)
    assert _diag(rep, "LM (error)")["value"] == pytest.approx(3.0971, abs=1e-3)
    assert res["analysis"]["outputs"] == ["OLS_PRED", "OLS_RESID"]
    names = [c["name"] for c in res["info"]["columns"]]
    assert {"OLS_PRED", "OLS_RESID"} <= set(names)


@pytest.mark.parametrize(
    ("model", "param", "value"),
    [("lag", "ρ (공간시차 계수)", 0.174847), ("error", "λ (공간오차 계수)", 0.357823)],
)
def test_spatial_lag_and_error(client, auth, columbus, model, param, value) -> None:
    ds = _open(client, auth, columbus)
    wid = _queen(client, auth, ds["id"])
    res = _run(client, auth, ds["id"], model=model, y="HOVAL", x=["INC", "CRIME"], weights_id=wid)
    rep = res["analysis"]["report"]
    assert _summary(rep)[param] == pytest.approx(value, abs=1e-4)
    assert rep["stat_label"] == "z"
    assert _diag(rep, "우도비 검정 (vs OLS)")["value"] > 0
    prefix = "LAG" if model == "lag" else "ERR"
    assert res["analysis"]["outputs"] == [f"{prefix}_PRED", f"{prefix}_RESID"]


def test_gwr_columbus(client, auth, columbus) -> None:
    ds = _open(client, auth, columbus)
    res = _run(client, auth, ds["id"], model="gwr", y="HOVAL", x=["INC", "CRIME"])
    rep = res["analysis"]["report"]
    assert rep["local"][0]["bandwidth"] == pytest.approx(48.0)
    assert _summary(rep)["R²"] == pytest.approx(0.42613, abs=1e-4)
    outs = res["analysis"]["outputs"]
    for key in ("B_CONST", "T_INC", "SIG_CRIME", "R2", "PRED", "RESID"):
        assert f"GWR_{key}" in outs

    # 유의성 마스크: SIG=0인 피처는 '유의하지 않음' 계급으로 빠짐
    body = client.post(
        f"/datasets/{ds['id']}/classify",
        json={"column": "GWR_B_INC", "method": "quantile", "k": 4, "mask": "GWR_SIG_INC"},
        headers=auth,
    ).json()
    assert body["labels"][-1] == "유의하지 않음"
    assert body["colors"][:-1] == [None] * 4 and body["colors"][-1]
    classes = np.frombuffer(base64.b64decode(body["classes"]), dtype="<i2")
    assert (
        int((classes == 4).sum())
        == body["counts"][-1]
        == 49 - rep["local"][1]["pct_significant"] * 49 / 100
    )


def test_mgwr_reports_progress_and_bandwidths(client, auth, columbus) -> None:
    ds = _open(client, auth, columbus)
    r = client.post(
        f"/datasets/{ds['id']}/regression",
        json={"model": "mgwr", "y": "HOVAL", "x": ["INC", "CRIME"]},
        headers=auth,
    )
    job_id = r.json()["id"]
    messages = set()
    t0 = time.time()
    while time.time() - t0 < 180:
        job = client.get(f"/jobs/{job_id}", headers=auth).json()
        messages.add(job["message"])
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job["status"] == "done", job
    rep = job["result"]["analysis"]["report"]
    assert [row["bandwidth"] for row in rep["local"]] == [46.0, 48.0, 46.0]
    assert any("반복" in m for m in messages)


def test_input_validation(client, auth, columbus) -> None:
    ds = _open(client, auth, columbus)
    url = f"/datasets/{ds['id']}/regression"
    r = client.post(url, json={"model": "lag", "y": "HOVAL", "x": ["INC"]}, headers=auth)
    assert r.json()["error"]["code"] == "weights_required"
    r = client.post(url, json={"model": "ols", "y": "HOVAL", "x": ["HOVAL"]}, headers=auth)
    assert r.json()["error"]["code"] == "invalid_variables"
    client.post(
        f"/datasets/{ds['id']}/fields",
        json={"name": "INC2", "expression": "`INC` * 2"},
        headers=auth,
    )
    r = client.post(url, json={"model": "ols", "y": "HOVAL", "x": ["INC", "INC2"]}, headers=auth)
    assert r.json()["error"]["code"] == "collinear"


def test_cancel_job(client, auth, columbus) -> None:
    ds = _open(client, auth, columbus)
    r = client.post(
        f"/datasets/{ds['id']}/regression",
        json={"model": "mgwr", "y": "HOVAL", "x": ["INC", "CRIME"]},
        headers=auth,
    )
    job = client.delete(f"/jobs/{r.json()['id']}", headers=auth).json()
    assert job["status"] == "cancelled"
    time.sleep(1)
    info = client.get(f"/datasets/{ds['id']}", headers=auth).json()
    assert not any(c["name"].startswith("MGWR_") for c in info["columns"])


def test_project_restores_regression_from_cache(client, auth, columbus, tmp_path) -> None:
    ds = _open(client, auth, columbus)
    wid = _queen(client, auth, ds["id"])
    _run(client, auth, ds["id"], model="ols", y="HOVAL", x=["INC", "CRIME"], weights_id=wid)
    _run(client, auth, ds["id"], model="gwr", y="HOVAL", x=["INC", "CRIME"])
    analyses = client.get(f"/datasets/{ds['id']}/analyses", headers=auth).json()
    assert [a["params"]["model"] for a in analyses] == ["ols", "gwr"]

    report_path = tmp_path / "gwr.txt"
    client.post(
        f"/datasets/{ds['id']}/analyses/{analyses[1]['id']}/report",
        json={"path": str(report_path)},
        headers=auth,
    )
    text = report_path.read_text(encoding="utf-8")
    assert "지리가중회귀" in text and "지역 계수 요약" in text

    proj = tmp_path / "p.gstproj"
    client.post(
        "/project/save", json={"path": str(proj), "datasets": [{"id": ds["id"]}]}, headers=auth
    )
    assert (tmp_path / "p.gstcache" / "dataset0.parquet").exists()
    saved = json.loads(proj.read_text(encoding="utf-8"))
    assert saved["datasets"][0]["analyses"][1]["report"]["model"] == "gwr"

    opened = client.post("/project/open", json={"path": str(proj)}, headers=auth).json()[
        "datasets"
    ][0]
    assert opened["warnings"] == []  # 캐시로 복원해 다시 계산하지 않음
    new_id = opened["info"]["id"]
    restored = client.get(f"/datasets/{new_id}/analyses", headers=auth).json()
    assert restored[1]["report"]["local"][0]["bandwidth"] == pytest.approx(48.0)

    # 캐시가 없으면 다시 계산함
    shutil.rmtree(tmp_path / "p.gstcache")
    opened = client.post("/project/open", json={"path": str(proj)}, headers=auth).json()[
        "datasets"
    ][0]
    assert any("다시 계산" in w for w in opened["warnings"])
    assert "GWR_B_INC" in [c["name"] for c in opened["info"]["columns"]]


def test_gwr_small_dataset_uses_interval_search(client, auth, tmp_path) -> None:
    """관측치가 mgwr 기본 최소 대역폭(40+2k)보다 적어도 GWR·MGWR이 동작해야 함."""
    import geopandas as gpd
    from shapely.geometry import box

    cells = [
        box(i * 1000, j * 1000, (i + 1) * 1000, (j + 1) * 1000) for j in range(6) for i in range(6)
    ]
    gdf = gpd.GeoDataFrame(
        {"y": [float(v % 7) + v * 0.1 for v in range(36)], "x": [float(v % 6) for v in range(36)]},
        geometry=cells,
        crs=5186,
    )
    path = tmp_path / "small.gpkg"
    gdf.to_file(path)
    ds = _open(client, auth, path)
    for model in ("gwr", "mgwr"):
        res = _run(client, auth, ds["id"], model=model, y="y", x=["x"])
        bws = [r["bandwidth"] for r in res["analysis"]["report"]["local"]]
        assert all(3 <= b <= 35 for b in bws), bws

    gdf.iloc[:15].to_file(tmp_path / "tiny.gpkg")
    tiny = _open(client, auth, tmp_path / "tiny.gpkg")
    r = client.post(
        f"/datasets/{tiny['id']}/regression",
        json={"model": "gwr", "y": "y", "x": ["x"]},
        headers=auth,
    )
    assert r.json()["error"]["code"] == "too_few"


def test_mask_with_no_significant_features(client, auth, columbus) -> None:
    ds = _open(client, auth, columbus)
    client.post(
        f"/datasets/{ds['id']}/fields",
        json={"name": "zero", "expression": "`INC` * 0"},
        headers=auth,
    )
    body = client.post(
        f"/datasets/{ds['id']}/classify",
        json={"column": "INC", "method": "quantile", "mask": "zero"},
        headers=auth,
    ).json()
    assert body["labels"] == ["유의하지 않음"] and body["counts"] == [49]


# ---- P3 보완: GM 추정, 강건 표준오차, 효과 분해, 모형 비교 지표 ------------------------


def _spreg_data():
    import spreg

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        db = libpysal.io.open(str(COLUMBUS.with_suffix(".dbf")))
        y = np.array(db.by_col("HOVAL")).reshape(-1, 1)
        X = np.column_stack([db.by_col("INC"), db.by_col("CRIME")])
        w = libpysal.weights.Queen.from_shapefile(str(COLUMBUS))
    w.transform = "r"
    return spreg, y, X, w


@pytest.mark.parametrize("model", ["lag_gm", "error_gm"])
def test_gm_models_match_spreg(client, auth, columbus, model) -> None:
    spreg, y, X, w = _spreg_data()
    ref = spreg.GM_Lag(y, X, w=w) if model == "lag_gm" else spreg.GM_Error_Het(y, X, w)
    ds = _open(client, auth, columbus)
    wid = _queen(client, auth, ds["id"])
    res = _run(client, auth, ds["id"], model=model, y="HOVAL", x=["INC", "CRIME"], weights_id=wid)
    rep = res["analysis"]["report"]
    coefs = [c["coef"] for c in rep["coefficients"]]
    assert coefs == pytest.approx(np.ravel(ref.betas).tolist(), rel=1e-6)
    assert rep["fit"]["loglik"] is None and rep["fit"]["aicc"] is None
    assert rep["fit"]["r2"] == pytest.approx(ref.pr2)
    assert rep["fit"]["moran_i"] is not None
    prefix = "LAGGM" if model == "lag_gm" else "ERRGM"
    assert res["analysis"]["outputs"] == [f"{prefix}_PRED", f"{prefix}_RESID"]
    if model == "lag_gm":
        assert _diag(rep, "Anselin-Kelejian (잔차 공간 의존성)")["p"] is not None
        assert rep["impacts"]["rows"][0]["name"] == "INC"


def test_lag_impacts_decomposition(client, auth, columbus) -> None:
    """총 효과 = β/(1-ρ), 직접 + 간접 = 총 효과."""
    ds = _open(client, auth, columbus)
    wid = _queen(client, auth, ds["id"])
    res = _run(client, auth, ds["id"], model="lag", y="HOVAL", x=["INC", "CRIME"], weights_id=wid)
    rep = res["analysis"]["report"]
    rho = _summary(rep)["ρ (공간시차 계수)"]
    betas = {c["name"]: c["coef"] for c in rep["coefficients"]}
    for row in rep["impacts"]["rows"]:
        assert row["total"] == pytest.approx(betas[row["name"]] / (1 - rho), rel=1e-6)
        assert row["direct"] + row["indirect"] == pytest.approx(row["total"], rel=1e-9)
        assert abs(row["direct"]) > abs(betas[row["name"]])  # 되먹임 효과로 직접 효과가 β보다 큼


def test_ols_white_robust_se(client, auth, columbus) -> None:
    spreg, y, X, _w = _spreg_data()
    ref = spreg.OLS(y, X, robust="white")
    ds = _open(client, auth, columbus)
    res = _run(client, auth, ds["id"], model="ols", y="HOVAL", x=["INC", "CRIME"], robust="white")
    rep = res["analysis"]["report"]
    assert [c["se"] for c in rep["coefficients"]] == pytest.approx(np.ravel(ref.std_err).tolist())
    assert _summary(rep)["표준오차"] == "White 이분산 강건"
    assert "White 강건" in res["analysis"]["description"]


def test_fit_metrics_are_comparable(client, auth, columbus) -> None:
    """모형 비교표 지표: AICc는 mgwr 방식(σ² 포함)이고, 가중치가 있으면 모든 모형에 잔차 Moran's I가 붙음."""
    from mgwr.diagnostics import get_AICc
    from spglm.glm import GLM

    _spreg, y, X, _w = _spreg_data()
    ds = _open(client, auth, columbus)
    wid = _queen(client, auth, ds["id"])
    fits = {}
    for model in ("ols", "lag", "gwr", "mgwr"):
        res = _run(
            client, auth, ds["id"], model=model, y="HOVAL", x=["INC", "CRIME"], weights_id=wid
        )
        fits[model] = res["analysis"]["report"]["fit"]
    # OLS AICc = mgwr가 GWR 요약에 쓰는 전역 회귀 AICc
    assert fits["ols"]["aicc"] == pytest.approx(get_AICc(GLM(y, X).fit()), rel=1e-9)
    assert fits["ols"]["moran_i"] == pytest.approx(0.171310, abs=1e-5)
    for f in fits.values():
        assert f["moran_i"] is not None and 0 < f["moran_p"] <= 1
    # MGWR은 원래 척도로 환산하므로 GWR·OLS와 같은 크기의 AICc를 가짐 (표준화 척도면 100 안팎)
    assert abs(fits["mgwr"]["aicc"] - fits["gwr"]["aicc"]) < 20
    assert fits["gwr"]["r2"] > fits["ols"]["r2"]


def test_zero_centered_classification(client, auth, columbus) -> None:
    ds = _open(client, auth, columbus)
    client.post(
        f"/datasets/{ds['id']}/fields",
        json={"name": "dev", "expression": "`HOVAL` - `HOVAL`.mean()"},
        headers=auth,
    )
    body = client.post(
        f"/datasets/{ds['id']}/classify",
        json={"column": "dev", "method": "zero_centered", "k": 6},
        headers=auth,
    ).json()
    assert len(body["labels"]) == len(body["colors"]) == 6
    assert sum(body["counts"]) == 49
    neg = [i for i, label in enumerate(body["labels"]) if label.endswith("0 미만")]
    assert len(neg) == 1
    # 음수 계급은 파랑 계열, 양수 계급은 빨강 계열
    blue = int(body["colors"][0][1:3], 16) < int(body["colors"][0][5:7], 16)
    red = int(body["colors"][-1][1:3], 16) > int(body["colors"][-1][5:7], 16)
    assert blue and red
    classes = np.frombuffer(base64.b64decode(body["classes"]), dtype="<i2")
    _spreg, y, _X, _w = _spreg_data()
    values = np.ravel(y) - y.mean()
    assert ((classes <= neg[0]) == (values < 0)).all()
