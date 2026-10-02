"""부록 E 수치: 같은 자료에서 도구마다 결과가 달라지는 관례를 한빛시 자료로 확인함.

1. 이웃 수 k의 기본값(GeoDa 4, libpysal 2, spdep 1, GeoStat 6)에 따른 Moran's I
2. 같은 999번 순열이라도 시드에 따라 달라지는 유사 p
3. 유사 p의 두 계산식 (M + 1)/(R + 1)과 max(M, 1)/(R + 1)
4. 국지 Moran의 분모 n − 1 대 n
5. Gi*의 이진 가중치 대 행 표준화, 해석적 z 대 순열 p
6. 공간 회귀 AIC의 모수 수 세는 법
7. EB 평활에서 동 사이 분산 추정값이 음수일 때

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/E.py
"""
import contextlib
import io
import os
import sys
import warnings

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from regkit import load_dong, queen  # noqa: E402

warnings.filterwarnings("ignore")

import esda  # noqa: E402
import libpysal  # noqa: E402
import spreg  # noqa: E402

SEED = 123456789


def knn_defaults(d):
    print("[1] k-최근린 이웃 수에 따른 출동률의 Moran's I (행 표준화, 순열 999, 시드 123456789)")
    pts = np.c_[d.geometry.centroid.x, d.geometry.centroid.y]
    y = d["출동률"].to_numpy()
    for k, who in [(1, "spdep knearneigh 기본"), (2, "libpysal KNN 기본"), (4, "GeoDa 기본"), (6, "GeoStat 기본")]:
        w = libpysal.weights.KNN.from_array(pts, k=k)
        w.transform = "r"
        np.random.seed(SEED)
        m = esda.Moran(y, w, permutations=999)
        print(f"  k = {k} ({who}): I = {m.I:.4f}, 유사 p = {m.p_sim:.3f}, 정규 근사 z = {m.z_norm:.2f}")
    w = queen(d)
    np.random.seed(SEED)
    m = esda.Moran(y, w, permutations=999)
    print(f"  (참고) 퀸 인접: I = {m.I:.4f}, 유사 p = {m.p_sim:.3f}")


def seeds(d):
    w = queen(d)
    y = d["출동률"].to_numpy()
    ps = []
    for s in range(1, 101):
        np.random.seed(s)
        ps.append(esda.Moran(y, w, permutations=999).p_sim)
    ps = np.array(ps)
    print(f"[2] 출동률의 Moran's I, 순열 999번을 시드 1~100으로 되풀이: 유사 p 최소 {ps.min():.3f}, 최대 {ps.max():.3f}, "
          f"평균 {ps.mean():.4f}, 표준편차 {ps.std():.4f} (이항 근사 √(p(1 − p)/999) = {np.sqrt(ps.mean() * (1 - ps.mean()) / 999):.4f})")


def pformula(d):
    w = queen(d)
    y = d["출동률"].to_numpy()
    np.random.seed(SEED)
    m = esda.Moran(y, w, permutations=999)
    M = int(np.sum(m.sim >= m.I))
    print(f"[3] 출동률 Moran's I = {m.I:.4f}, 순열 999번 가운데 관측값 이상 M = {M}")
    print(f"  esda·GeoDa (M + 1)/(R + 1) = {(M + 1) / 1000:.3f} (esda p_sim {m.p_sim:.3f}), spdep moran.mc max(M, 1)/(R + 1) = {max(M, 1) / 1000:.3f}")


def lisa_scale(d):
    w = queen(d)
    y = d["고령비율"].to_numpy()
    n = len(y)
    lm = esda.Moran_Local(y, w, permutations=999, seed=SEED, n_jobs=1)
    g = esda.Moran(y, w, permutations=0)
    Is = lm.Is
    In = Is * n / (n - 1)
    print(f"[4] 고령비율 LISA: 분모 n − 1(GeoDa·esda·GeoStat, spdep mlvar=FALSE) 최대 I_i = {Is.max():.4f}, "
          f"분모 n(spdep localmoran 기본 mlvar=TRUE) = {In.max():.4f}, 비 {n / (n - 1):.4f}")
    print(f"  ΣI_i: n − 1 방식 {Is.sum():.2f} = (n − 1)·I = {(n - 1) * g.I:.2f}, n 방식 {In.sum():.2f} = n·I = {n * g.I:.2f}")


def gistar(d):
    y = d["출동률"].to_numpy()
    W, _ = __import__("geostat_engine.analysis.weights", fromlist=["build"]).build(d, {"type": "queen"})
    gb = esda.G_Local(y, W, transform="B", star=True, permutations=999, seed=SEED, n_jobs=1)
    gr = esda.G_Local(y, W, transform="R", star=True, permutations=999, seed=SEED, n_jobs=1)
    zb, zr = gb.Zs, gr.Zs
    print(f"[5] 출동률 Gi* (퀸, 자기 포함): 이진 z와 행 표준화 z의 최대 차이 {np.max(np.abs(zb - zr)):.3f}, 상관 {np.corrcoef(zb, zr)[0, 1]:.4f}")
    print(f"  |z| > 1.96인 동: 이진 {np.sum(np.abs(zb) > 1.96)}개, 행 표준화 {np.sum(np.abs(zr) > 1.96)}개")
    print(f"  순열 유사 p가 같은 동 {np.sum(np.isclose(gb.p_sim, gr.p_sim))}/{len(y)}개")
    print(f"  p_sim < 0.05인 동 {np.sum(gb.p_sim < 0.05)}개, 정규 근사 p_z_sim < 0.05인 동 {np.sum(gb.p_z_sim < 0.05)}개")


def aic(d):
    w = queen(d)
    y = d[["출동률"]].to_numpy()
    X = d[["온도편차", "고령비율"]].to_numpy()
    ols = spreg.OLS(y, X, w=w, name_y="출동률", name_x=["온도편차", "고령비율"])
    with contextlib.redirect_stdout(io.StringIO()):
        lag = spreg.ML_Lag(y, X, w=w)
        err = spreg.ML_Error(y, X, w=w)
    print("[6] 출동률 ~ 온도편차 + 고령비율의 AIC (k: β 3개)")
    for name, m, extra in [("OLS", ols, 0), ("공간시차", lag, 1), ("공간오차", err, 1)]:
        ll = float(m.logll)
        a_sp = float(m.aic)
        a_r = -2 * ll + 2 * (3 + 1 + extra)
        print(f"  {name}: log L = {ll:.3f}, spreg AIC = {a_sp:.3f} (k = {(a_sp + 2 * ll) / 2:.0f}), σ²와 공간 계수를 모두 센 AIC = {a_r:.3f}")


def columbus():
    import libpysal.examples as ex
    db = libpysal.io.open(ex.get_path("columbus.dbf"))
    y = np.array(db.by_col("CRIME")).reshape(-1, 1)
    X = np.c_[db.by_col("INC"), db.by_col("HOVAL")]
    w = libpysal.io.open(ex.get_path("columbus.gal")).read()
    w.transform = "r"
    ols = spreg.OLS(y, X)
    with contextlib.redirect_stdout(io.StringIO()):
        lag = spreg.ML_Lag(y, X, w=w)
        err = spreg.ML_Error(y, X, w=w)
    print("[6b] Columbus CRIME ~ INC + HOVAL (columbus.gal, 행 표준화)")
    for name, m, extra in [("OLS", ols, 0), ("공간시차", lag, 1), ("공간오차", err, 1)]:
        ll = float(m.logll)
        print(f"  {name}: log L = {ll:.3f}, spreg AIC = {float(m.aic):.3f}, σ²와 공간 계수를 모두 센 AIC = {-2 * ll + 2 * (3 + 1 + extra):.3f}")
    print(f"  공간시차 ρ = {float(lag.rho):.4f}, 공간오차 λ = {float(err.lam):.4f}")


def eb_hanbit(d):
    e = d["PT_CNT"].to_numpy(float)
    n = d["인구"].to_numpy(float)
    r = e / n
    b = e.sum() / n.sum()
    s2 = np.sum(n * (r - b) ** 2) / n.sum()
    print(f"[7b] 한빛시 출동: α̂ = {s2 - b / n.mean():.3e} (양수라 자르기 여부와 무관)")


def eb_negative():
    from esda import smoothing
    e = np.array([1, 2, 5, 9, 31.0])
    n = np.array([100, 200, 500, 1000, 3000.0])
    r = e / n
    b = e.sum() / n.sum()
    s2 = np.sum(n * (r - b) ** 2) / n.sum()
    a = s2 - b / n.mean()
    eb = smoothing.Empirical_Bayes(e.reshape(-1, 1), n.reshape(-1, 1)).r.ravel()
    ac = max(a, 0.0)
    clamp = (ac / (ac + b / n)) * r + (1 - ac / (ac + b / n)) * b
    print("[7] 비율이 포아송 잡음으로 기대되는 것보다도 고른 다섯 지역: 건수", e.astype(int).tolist(), "인구", n.astype(int).tolist())
    print(f"  전체 비율 β̂ = {b * 1e4:.2f}(1만 명당), 가중 분산 s² = {s2:.3e}, α̂ = s² − β̂/n̄ = {a:.3e} (음수)")
    print(f"  원비율(1만 명당) {np.round(r * 1e4, 2).tolist()}")
    print(f"  esda Empirical_Bayes(자르지 않음) {np.round(eb * 1e4, 2).tolist()}")
    print(f"  α̂를 0으로 자름(GeoDa, spdep EBest) {np.round(clamp * 1e4, 2).tolist()}")


if __name__ == "__main__":
    d = load_dong()
    knn_defaults(d)
    seeds(d)
    pformula(d)
    lisa_scale(d)
    gistar(d)
    aic(d)
    columbus()
    eb_negative()
    eb_hanbit(d)
    import mgwr
    print(f"[버전] esda {esda.__version__}, libpysal {libpysal.__version__}, spreg {spreg.__version__}, mgwr {mgwr.__version__}, numpy {np.__version__}")
