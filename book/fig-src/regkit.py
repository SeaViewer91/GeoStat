"""6부(공간 회귀) 그림에서 함께 쓰는 도구.

- 행정동 자료와 8강의 변수(출동률, 고령비율, 온도편차, 로그밀도c)
- 퀸 인접 공간가중치(행 표준화, 앱과 같은 방식)
- 연습용 모의 자료 practice/hanbit_dong_sim.gpkg 만들기와 읽기
- GeoStat 엔진의 회귀(regression.prepare/run)를 그대로 부르는 함수 (앱과 같은 수치)

연습용 모의 자료의 규칙(공개함, 24~27강에서 정답으로 씀)
    xb = 5 + 0.3 × 고령비율 + 1.5 × 온도편차,  ε ~ N(0, 1.5²) (세 변수에 같은 ε)
    Y_독립 = xb + ε
    Y_시차 = (I − 0.5W)⁻¹ (xb + ε)          공간시차 과정, ρ = 0.5
    Y_오차 = xb + (I − 0.5W)⁻¹ ε            공간오차 과정, λ = 0.5
    W는 퀸 인접을 행 표준화한 것. Y는 소수 셋째 자리로 반올림해 저장함

28강에서 더한 변수 (공간 이질성, ε는 따로 뽑음)
    X_km, Y_km = 행정동 중심점 좌표(km, EPSG:5186)
    Y_체제 = 5 + 0.3 × 고령비율 + b2 × 온도편차 + ε,  b2 = 2.0 (다솜구), 1.0 (나머지 구)
    Y_변이 = 5 + 0.3 × 고령비율 + b2(u, v) × 온도편차 + ε,
             b2(u, v) = 0.8 + 1.4 × exp(−d² / (2 × 6²)),  d = 중심점과 (34, 455) km 사이 거리(km)
"""
import os
import warnings
import zlib

import geopandas as gpd
import numpy as np

from geostat_engine.analysis import aggregate as agg
from geostat_engine.analysis import regression as rg
from geostat_engine.analysis import weights as gw
from geostat_engine.analysis import zonal

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
PRACTICE = os.path.join(DATA, "practice")
SIM_PATH = os.path.join(PRACTICE, "hanbit_dong_sim.gpkg")
LST = os.path.join(DATA, "hanbit_lst.tif")
BASE_SEED = 20260930
TRUE = {"b0": 5.0, "b1": 0.3, "b2": 1.5, "sigma": 1.5, "rho": 0.5, "lam": 0.5}


def rng(name):
    return np.random.default_rng([BASE_SEED, zlib.crc32(name.encode("utf-8"))])


def load_dong():
    """8강과 같은 방법으로 만든 행정동 변수"""
    dong = gpd.read_file(os.path.join(DATA, "hanbit_dong.gpkg"))
    ev = gpd.read_file(os.path.join(DATA, "hanbit_events.gpkg"))
    dong["PT_CNT"] = np.asarray(agg.aggregate(dong, ev, stats=[], count=True, density=False).columns["CNT"])
    pl = zonal.prepare(dong, type("R", (), {"path": LST, "info": {"count": 1, "crs": "EPSG:5186"}})(), {"stats": ["mean"], "band": 1})
    dong["ZS_MEAN"] = zonal.run(pl, lambda *_: None)["columns"]["MEAN"]
    dong["출동률"] = dong["PT_CNT"] / dong["인구"] * 10000
    dong["고령비율"] = dong["고령인구"] / dong["인구"] * 100
    dong["온도편차"] = dong["ZS_MEAN"] - 30
    dong["로그밀도c"] = np.log(dong["인구"] / dong["면적_km2"]) - 8
    return dong


def queen(gdf):
    W, _ = gw.build(gdf, {"type": "queen"})
    W.transform = "r"
    return W


def dense(W):
    return W.full()[0]


def make_sim(dong, W):
    """연습용 모의 자료를 만들어 저장하고 돌려줌"""
    n = len(dong)
    Wd = dense(W)
    I = np.eye(n)
    x1 = dong["고령비율"].to_numpy()
    x2 = dong["온도편차"].to_numpy()
    xb = TRUE["b0"] + TRUE["b1"] * x1 + TRUE["b2"] * x2
    e = TRUE["sigma"] * rng("sim_reg").standard_normal(n)
    sim = dong[["동코드", "구", "동이름", "인구", "고령인구", "면적_km2", "고령비율", "온도편차", "geometry"]].copy()
    sim["Y_독립"] = np.round(xb + e, 3)
    sim["Y_시차"] = np.round(np.linalg.solve(I - TRUE["rho"] * Wd, xb + e), 3)
    sim["Y_오차"] = np.round(xb + np.linalg.solve(I - TRUE["lam"] * Wd, e), 3)
    cent = dong.geometry.centroid
    sim["X_km"] = np.round(cent.x.to_numpy() / 1000, 3)
    sim["Y_km"] = np.round(cent.y.to_numpy() / 1000, 3)
    sim["Y_체제"] = np.round(TRUE["b0"] + TRUE["b1"] * x1 + regime_b2(dong) * x2 + TRUE["sigma"] * rng("sim_regime").standard_normal(n), 3)
    sim["Y_변이"] = np.round(TRUE["b0"] + TRUE["b1"] * x1 + vary_b2(sim["X_km"].to_numpy(), sim["Y_km"].to_numpy()) * x2
                           + TRUE["sigma"] * rng("sim_vary").standard_normal(n), 3)
    os.makedirs(PRACTICE, exist_ok=True)
    if os.path.exists(SIM_PATH):
        os.remove(SIM_PATH)
    sim.to_file(SIM_PATH, layer="hanbit_dong_sim", driver="GPKG")
    return sim


def regime_b2(gdf):
    """Y_체제의 참 온도편차 계수: 다솜구 2.0, 나머지 1.0"""
    return np.where(gdf["구"].to_numpy() == "다솜구", 2.0, 1.0)


def vary_b2(xk, yk):
    """Y_변이의 참 온도편차 계수: (34, 455) km 둘레에서 2.2까지 커지는 매끈한 언덕"""
    d2 = (np.asarray(xk) - 34.0) ** 2 + (np.asarray(yk) - 455.0) ** 2
    return 0.8 + 1.4 * np.exp(-d2 / (2 * 6.0 ** 2))


def load_sim():
    return gpd.read_file(SIM_PATH)


def fit(gdf, model, y, xs, W=None):
    """GeoStat 엔진의 회귀 (앱과 같은 계산). 보고서 dict를 돌려줌"""
    payload = rg.prepare(gdf, {"model": model, "y": y, "x": xs}, W, None)
    out = rg.run(payload, lambda *a: None)
    return out["report"], out["columns"]


def summ(rep):
    return dict(rep["summary"])


def coefs(rep):
    return {c["name"]: c for c in rep["coefficients"]}


def diags(rep):
    return {d["name"]: d for d in rep["diagnostics"]}


def true_effects(Wd, rho, beta):
    """공간시차 과정의 참 직접·간접·총 효과"""
    n = len(Wd)
    S = np.linalg.inv(np.eye(n) - rho * Wd)
    d = np.trace(S) / n
    t = S.sum() / n
    return beta * d, beta * (t - d), beta * t


def app_num(v, digits=4):
    """앱 결과 카드의 숫자 표시(ReportCard.num)를 흉내 냄: 유효숫자 4자리, 0.001보다 작으면 지수 표기"""
    if v is None:
        return "–"
    v = float(v)
    if v == int(v) and abs(v) < 1e12:
        return f"{int(v):,}"
    if v != 0 and abs(v) < 1e-3:
        m, e = f"{v:.2e}".split("e")
        return f"{m}e{int(e)}"
    r = float(f"{v:.{digits}g}")
    s = f"{r:,.6f}".rstrip("0").rstrip(".")
    return s


def app_p(p):
    return "<0.001" if p is not None and p < 0.001 else (f"{p:.3f}" if p is not None else "–")
