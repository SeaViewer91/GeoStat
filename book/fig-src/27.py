"""27강 그림과 본문 수치.

- 27-esf.svg : 위: 퀸 인접의 고유벡터 지도 네 개(Moran 계수 순). 아래: Y_오차의 참 공간 오차와 고유벡터 공간 필터가 찾은 성분
- 27-weights.svg : 공간가중치 여섯 가지로 추정한 공간시차·공간오차 모형의 로그우도와 ρ·λ (연습용 모의 자료, 참 W는 퀸 인접)

계수 자료 모형(포아송·음이항)은 numpy·scipy로 직접 적합함(statsmodels와 같은 식).

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/27.py
"""
import contextlib
import io
import os
import sys
import warnings

import numpy as np
from scipy import optimize, special, stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import MapFrame, draw, outline  # noqa: E402
from plotkit import Axes  # noqa: E402
from regkit import TRUE, dense, load_dong, load_sim, queen  # noqa: E402
from svglib import Svg  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
XN = ["고령비율", "온도편차"]


def moran(e, W):
    """행 표준화 W에서 Moran's I와 정규 근사 z (esda와 같음)"""
    from esda import Moran

    m = Moran(np.asarray(e, float), W, permutations=0)
    return m.I, m.z_norm, m.p_norm


# ---------------------------------------------------------------- 계수 자료
def poisson(X, y, off):
    b = np.zeros(X.shape[1])
    b[0] = np.log(y.sum() / np.exp(off).sum())
    for _ in range(100):
        mu = np.exp(X @ b + off)
        z = X @ b + (y - mu) / mu
        nb = np.linalg.solve(X.T @ (X * mu[:, None]), X.T @ (mu * z))
        if np.max(np.abs(nb - b)) < 1e-12:
            b = nb
            break
        b = nb
    mu = np.exp(X @ b + off)
    se = np.sqrt(np.diag(np.linalg.inv(X.T @ (X * mu[:, None]))))
    ll = np.sum(y * np.log(mu) - mu - special.gammaln(y + 1))
    return b, se, mu, ll


def negbin(X, y, off, b0):
    def nll(p):
        b, a = p[:-1], np.exp(p[-1])
        mu = np.exp(X @ b + off)
        r = 1 / a
        return -np.sum(special.gammaln(y + r) - special.gammaln(r) - special.gammaln(y + 1) + r * np.log(r / (r + mu)) + y * np.log(mu / (r + mu)))

    res = optimize.minimize(nll, np.r_[b0, np.log(0.1)], method="BFGS", options={"gtol": 1e-8})
    # 표준오차: 수치 헤시안
    k = len(res.x)
    h = 1e-4
    Hm = np.zeros((k, k))
    for i in range(k):
        for j in range(k):
            ei, ej = np.eye(k)[i] * h, np.eye(k)[j] * h
            Hm[i, j] = (nll(res.x + ei + ej) - nll(res.x + ei - ej) - nll(res.x - ei + ej) + nll(res.x - ei - ej)) / (4 * h * h)
    se = np.sqrt(np.diag(np.linalg.inv(Hm)))
    b, a = res.x[:-1], np.exp(res.x[-1])
    mu = np.exp(X @ b + off)
    return b, se, a, mu, -res.fun


def counts(dong, W):
    n = len(dong)
    y = dong["PT_CNT"].to_numpy(float)
    off = np.log(dong["인구"].to_numpy(float))
    X3 = np.c_[np.ones(n), dong[XN].to_numpy()]
    X1 = X3[:, :2]
    print(f"[1] 출동 건수: 평균 {y.mean():.2f}, 분산 {y.var(ddof=1):.2f}, 0건인 동 {int((y == 0).sum())}개")
    out = {}
    for name, X in (("M1", X1), ("M3", X3)):
        b, se, mu, ll = poisson(X, y, off)
        pr = (y - mu) / np.sqrt(mu)
        disp = np.sum(pr ** 2) / (n - X.shape[1])
        I, z, p = moran(pr, W)
        print(f"  포아송 {name}: 계수 {np.round(b, 4).tolist()}, 표준오차 {np.round(se, 4).tolist()}, 로그우도 {ll:.3f}, 분산 비 {disp:.3f}, 피어슨 잔차 I {I:.4f} (z {z:.2f}, p {p:.3f})")
        print(f"    exp(계수): {np.round(np.exp(b[1:]), 4).tolist()}")
        nb, nse, a, nmu, nll_ = negbin(X, y, off, b)
        npr = (y - nmu) / np.sqrt(nmu + a * nmu ** 2)
        I2, z2, p2 = moran(npr, W)
        lr = 2 * (nll_ - ll)
        print(f"  음이항 {name}: 계수 {np.round(nb, 4).tolist()}, 표준오차 {np.round(nse[:-1], 4).tolist()}, α {a:.4f}, 로그우도 {nll_:.3f}, "
              f"포아송 대비 우도비 {lr:.3f} (p 경계 보정 {0.5 * stats.chi2.sf(lr, 1):.4f}), 피어슨 잔차 I {I2:.4f} (z {z2:.2f}, p {p2:.3f})")
        out[name] = (b, se, mu, pr)
    # M3 피어슨 잔차의 공간 의존: 다른 가중치에서도
    from esda import Moran
    from libpysal import weights as lw

    cent = np.c_[dong.geometry.centroid.x, dong.geometry.centroid.y]
    alts = {"KNN 4": lw.KNN.from_array(cent, k=4), "KNN 6": lw.KNN.from_array(cent, k=6), "KNN 8": lw.KNN.from_array(cent, k=8),
            "거리 3 km": lw.DistanceBand.from_array(cent, threshold=3000, binary=True),
            "역거리 5 km": lw.DistanceBand.from_array(cent, threshold=5000, binary=False, alpha=-1)}
    pr3 = out["M3"][3]
    for k, w in alts.items():
        w.transform = "r"
        m = Moran(pr3, w, permutations=0)
        print(f"  포아송 M3 피어슨 잔차, {k}: I {m.I:.4f} (정규 근사 p {m.p_norm:.3f})")
    return y, off, X1, X3, out


# ---------------------------------------------------------------- 고유벡터 공간 필터
def eigvecs(gdf):
    W = queen(gdf)
    C = (dense(W) > 0).astype(float)
    n = len(C)
    M = np.eye(n) - np.ones((n, n)) / n
    vals, vecs = np.linalg.eigh(M @ C @ M)
    o = np.argsort(vals)[::-1]
    vals, vecs = vals[o], vecs[:, o]
    mc = n / C.sum() * vals
    cand = np.where(mc / mc[0] >= 0.25)[0]
    return vecs, mc, cand


def esf_select(y, X, W, vecs, cand, fitfun, alpha=0.10):
    """잔차 Moran's I의 |z|를 가장 줄이는 고유벡터를 하나씩 더함. 잔차 I가 유의하지 않으면(정규 근사 p > alpha) 멈춤"""
    sel = []
    while True:
        Z = np.c_[X, vecs[:, sel]] if sel else X
        e = fitfun(Z)
        I, z, p = moran(e, W)
        if p > alpha or len(sel) >= len(cand):
            return sel, Z, I, z, p
        best = None
        for j in cand:
            if j in sel:
                continue
            I2, z2, _ = moran(fitfun(np.c_[Z, vecs[:, j]]), W)
            if best is None or abs(z2) < best[0]:
                best = (abs(z2), j)
        sel.append(int(best[1]))


def esf(sim, W, vecs, mc, cand):
    n = len(sim)
    X = np.c_[np.ones(n), sim[XN].to_numpy()]
    print(f"[2] 고유벡터: Moran 계수 최대 {mc[0]:.3f}, 최소 {mc[-1]:.3f}; 후보(MC/MC_max ≥ 0.25) {len(cand)}개; 처음 다섯 {np.round(mc[:5], 3).tolist()}")
    res = {}
    for yv in ("Y_독립", "Y_시차", "Y_오차"):
        y = sim[yv].to_numpy()

        def fitols(Z, y=y):
            return y - Z @ np.linalg.lstsq(Z, y, rcond=None)[0]

        I0, z0, p0 = moran(fitols(X), W)
        sel, Z, I, z, p = esf_select(y, X, W, vecs, cand, fitols)
        b = np.linalg.lstsq(Z, y, rcond=None)[0]
        e = y - Z @ b
        s2 = e @ e / (n - Z.shape[1])
        se = np.sqrt(np.diag(s2 * np.linalg.inv(Z.T @ Z)))
        r2 = 1 - e @ e / np.sum((y - y.mean()) ** 2)
        print(f"  {yv}: OLS 잔차 I {I0:.4f} (p {p0:.4f}) → 고유벡터 {len(sel)}개 {[s + 1 for s in sel]} 뒤 잔차 I {I:.4f} (p {p:.3f}); "
              f"계수 {np.round(b[:3], 4).tolist()}, 표준오차 {np.round(se[:3], 4).tolist()}, R² {r2:.4f}")
        res[yv] = (sel, b, Z)
    # 참 공간 오차와 비교 (Y_오차)
    sel, b, Z = res["Y_오차"]
    comp = Z[:, 3:] @ b[3:]
    xb = TRUE["b0"] + TRUE["b1"] * sim["고령비율"].to_numpy() + TRUE["b2"] * sim["온도편차"].to_numpy()
    u_true = sim["Y_오차"].to_numpy() - xb
    print(f"  Y_오차의 필터 성분과 참 공간 오차의 상관 {np.corrcoef(comp, u_true)[0, 1]:.3f} (참 오차의 표준편차 {u_true.std(ddof=1):.3f}, 필터 성분 {comp.std(ddof=1):.3f})")
    # 모의 실험: 공간오차 과정에서 ESF와 SEM의 온도편차 계수
    return res, comp, u_true


def esf_mc(sim, W, vecs, cand, R=300):
    import spreg

    from regkit import rng

    n = len(sim)
    X = np.c_[np.ones(n), sim[XN].to_numpy()]
    Wd = dense(W)
    A = np.linalg.inv(np.eye(n) - TRUE["lam"] * Wd)
    xb = X @ np.array([TRUE["b0"], TRUE["b1"], TRUE["b2"]])
    r = rng("sim_mc_27")
    rows = []
    for _ in range(R):
        y = xb + A @ (TRUE["sigma"] * r.standard_normal(n))

        def fitols(Z, y=y):
            return y - Z @ np.linalg.lstsq(Z, y, rcond=None)[0]

        sel, Z, I, z, p = esf_select(y, X, W, vecs, cand, fitols)
        b = np.linalg.lstsq(Z, y, rcond=None)[0]
        e = y - Z @ b
        se = np.sqrt(np.diag(e @ e / (n - Z.shape[1]) * np.linalg.inv(Z.T @ Z)))
        bo = np.linalg.lstsq(X, y, rcond=None)[0]
        eo = y - X @ bo
        seo = np.sqrt(np.diag(eo @ eo / (n - 3) * np.linalg.inv(X.T @ X)))
        with contextlib.redirect_stdout(io.StringIO()):
            m = spreg.ML_Error(y[:, None], X[:, 1:], W)
        bs, ses = np.ravel(m.betas), np.ravel(m.std_err)
        rows.append((bo[2], seo[2], b[2], se[2], bs[2], ses[2], len(sel)))
    a = np.array(rows)
    print(f"[3] 모의 실험 (공간오차 과정 λ 0.5, 실현값 {R}개, 온도편차 참값 1.5)")
    for nm, j in (("OLS", 0), ("ESF", 2), ("SEM(ML)", 4)):
        cover = np.mean(np.abs(a[:, j] - 1.5) <= 1.96 * a[:, j + 1])
        print(f"  {nm}: 평균 {a[:, j].mean():.3f}, 실제 표준편차 {a[:, j].std(ddof=1):.4f}, 보고 표준오차 평균 {a[:, j + 1].mean():.4f}, 95% 포함률 {cover:.3f}")
    print(f"  ESF가 고른 고유벡터 수: 평균 {a[:, 6].mean():.1f}, 범위 {int(a[:, 6].min())}~{int(a[:, 6].max())}")


def esf_counts(dong, W, y, off, X1, X3, vecs, cand):
    def fitp(Z):
        b, se, mu, ll = poisson(Z, y, off)
        return (y - mu) / np.sqrt(mu)

    sel, Z, I, z, p = esf_select(y, X1, W, vecs, cand, fitp)
    b, se, mu, ll = poisson(Z, y, off)
    comp = Z[:, 2:] @ b[2:]
    r = np.corrcoef(comp, dong["온도편차"].to_numpy())[0, 1]
    print(f"[4] 포아송 M1(고령비율만) + 고유벡터 {len(sel)}개 {[s + 1 for s in sel]}: 고령비율 {b[1]:.4f} (표준오차 {se[1]:.4f}), 잔차 I {I:.4f} (p {p:.3f}); "
          f"필터 성분과 온도편차의 상관 {r:.3f}")


def fixed_effects(sim, dong, W):
    print("[5] 구 고정효과 (구 더미 4개)")
    for gdf, yv in ((sim, "Y_오차"), (sim, "Y_시차"), (dong, "출동률")):
        n = len(gdf)
        G = gdf["구"].astype("category")
        D = np.c_[[(G == g).astype(float) for g in G.cat.categories[1:]]].T
        X = np.c_[np.ones(n), gdf[XN].to_numpy()]
        y = gdf[yv].to_numpy()
        for name, Z in (("구 없음", X), ("구 더미", np.c_[X, D])):
            b = np.linalg.lstsq(Z, y, rcond=None)[0]
            e = y - Z @ b
            I, z, p = moran(e, W if gdf is sim else queen(dong))
            se = np.sqrt(np.diag(e @ e / (n - Z.shape[1]) * np.linalg.inv(Z.T @ Z)))
            print(f"  {yv} {name}: 온도편차 {b[2]:.4f} (표준오차 {se[2]:.4f}), 잔차 I {I:.4f} (p {p:.3f})")


def weights_sens(sim):
    import spreg
    from libpysal import weights as lw

    n = len(sim)
    X = sim[XN].to_numpy()
    cent = np.c_[sim.geometry.centroid.x, sim.geometry.centroid.y]
    Ws = {"퀸 인접": queen(sim)}
    for k in (4, 6, 8):
        Ws[f"KNN {k}"] = lw.KNN.from_array(cent, k=k)
    Ws["거리 3 km"] = lw.DistanceBand.from_array(cent, threshold=3000, binary=True)
    Ws["역거리 5 km"] = lw.DistanceBand.from_array(cent, threshold=5000, binary=False, alpha=-1)
    rook = lw.Rook.from_dataframe(sim, use_index=True)
    same = all(set(rook.neighbors[i]) == set(Ws["퀸 인접"].neighbors[i]) for i in range(n))
    print(f"[6] 가중치 민감도 (룩 인접은 퀸 인접과 이웃이 모두 같음: {same}; 최소 연결 거리 {lw.min_threshold_distance(cent):.0f} m)")
    res = {}
    for k, w in Ws.items():
        w.transform = "r"
        card = np.array(list(w.cardinalities.values()))
        for yv in ("Y_시차", "Y_오차"):
            y = sim[[yv]].to_numpy()
            with contextlib.redirect_stdout(io.StringIO()):
                lag = spreg.ML_Lag(y, X, w, name_x=XN, spat_impacts=None)
                err = spreg.ML_Error(y, X, w, name_x=XN)
                o = spreg.OLS(y, X, w=w, spat_diag=True)
            rho = lag.rho.item()
            b = np.ravel(lag.betas)
            lam = np.ravel(err.betas)[-1]
            res[(k, yv)] = dict(rho=rho, lam=lam, ll_lag=lag.logll, ll_err=err.logll, total=b[2] / (1 - rho), be=np.ravel(err.betas)[2],
                                p=(o.lm_lag[1], o.lm_error[1], o.rlm_lag[1], o.rlm_error[1]))
            q = res[(k, yv)]
            print(f"  {k} (이웃 평균 {card.mean():.2f}) {yv}: 시차 ρ {rho:.3f}, 로그우도 {lag.logll:.2f}, 온도편차 총 효과 {q['total']:.3f} | 오차 λ {lam:.3f}, 로그우도 {err.logll:.2f}, "
                  f"온도편차 {q['be']:.3f} | LM p {', '.join(f'{v:.3g}' for v in q['p'])}")
    return Ws, res


# ---------------------------------------------------------------- 그림
def fig_esf(sim, vecs, mc, comp, u_true):
    W_, H = 720, 470
    s = Svg(W_, H, "위: 퀸 인접 가중치에서 뽑은 고유벡터(지도 패턴) 네 개. Moran 계수(MC)가 큰 1번은 도시를 둘로 나누는 큰 무늬이고, 번호가 커질수록 무늬가 잘아짐. "
                   f"아래: 연습용 자료 Y_오차의 참 공간 오차(왼쪽)와, 고유벡터 공간 필터가 고른 고유벡터들의 합(오른쪽). 상관 {np.corrcoef(comp, u_true)[0, 1]:.2f}로 큰 무늬를 잡아냄. 범례는 아래 두 지도의 값이고, 위 네 지도는 고유벡터마다 최댓값 기준으로 칠했음")
    mw = 165
    for k, j in enumerate((0, 1, 9, 29)):
        v = vecs[:, j]
        lim = np.abs(v).max()
        bins = np.array([-0.6, -0.2, 0, 0.2, 0.6]) * lim
        cls = [f"d{int(np.digitize(t, bins))}" for t in v]
        fr = MapFrame(sim.total_bounds, 12 + k * (mw + 12), 34, mw)
        draw(s, fr, sim.geometry, cls, width=0.2)
        outline(s, fr, sim.union_all(), cls="s-mu", width=0.6)
        s.text(fr.x + mw / 2, 24, f"고유벡터 {j + 1} (MC {mc[j]:.2f})", size=11, weight="600")
    mw2 = 300
    y0 = 200
    lim = max(np.abs(u_true).max(), np.abs(comp).max())
    bins = np.array([-2.0, -0.7, 0, 0.7, 2.0])
    for k, (v, title) in enumerate(((u_true, "참 공간 오차 (I − 0.5W)⁻¹ε"), (comp, "고유벡터 필터 성분"))):
        cls = [f"d{int(np.digitize(t, bins))}" for t in v]
        fr = MapFrame(sim.total_bounds, 40 + k * (mw2 + 40), y0 + 22, mw2)
        draw(s, fr, sim.geometry, cls, width=0.3)
        outline(s, fr, sim.union_all(), cls="s-mu", width=0.8)
        s.text(fr.x + mw2 / 2, y0 + 12, title, size=12, weight="600")
    x = 140
    for c, lab in (("d0", "< −2"), ("d1", "−2~−0.7"), ("d2", "−0.7~0"), ("d3", "0~0.7"), ("d4", "0.7~2"), ("d5", "> 2")):
        s.rect(x, H - 24, 12, 12, cls=f"s-mu {c}", width=0.5)
        s.text(x + 16, H - 14, lab, size=10, anchor="start")
        x += 30 + len(lab) * 7
    s.save(os.path.join(OUT, "27-esf.svg"))


def fig_weights(res, Ws):
    names = list(Ws.keys())
    W_, H = 720, 300
    s = Svg(W_, H, "공간가중치 여섯 가지로 적합한 결과(연습용 모의 자료, 참 가중치는 퀸 인접). 왼쪽: Y_시차의 공간시차 모형과 Y_오차의 공간오차 모형의 로그우도(가장 큰 값과의 차이). "
                   "두 변수 모두 참 가중치에서 로그우도가 가장 큼. 오른쪽: 추정한 ρ(Y_시차)와 λ(Y_오차). 참값은 둘 다 0.5인데, 가중치에 따라 ρ는 0.43~0.50, λ는 0.44~0.57로 달라짐")
    ax = Axes(s, 120, 40, 220, 200, (-9, 0.6), (-0.5, len(names) - 0.5))
    s.text(230, 22, "로그우도 − 최댓값", size=12, weight="600")
    m1 = max(res[(k, "Y_시차")]["ll_lag"] for k in names)
    m2 = max(res[(k, "Y_오차")]["ll_err"] for k in names)
    for i, k in enumerate(names):
        yy = float(ax.Y(len(names) - 1 - i))
        s.text(float(ax.X(-9)) - 8, yy + 4, k, size=11, anchor="end")
        s.circle(float(ax.X(res[(k, "Y_시차")]["ll_lag"] - m1)), yy - 4, 5, cls="s-bg f-bd", width=1)
        s.circle(float(ax.X(res[(k, "Y_오차")]["ll_err"] - m2)), yy + 4, 5, cls="s-bg f-ac", width=1)
    ax.xaxis(ticks=[-8, -6, -4, -2, 0])
    ax2 = Axes(s, 450, 40, 240, 200, (0.3, 0.8), (-0.5, len(names) - 0.5))
    s.text(570, 22, "추정한 ρ와 λ", size=12, weight="600")
    for i, k in enumerate(names):
        yy = float(ax2.Y(len(names) - 1 - i))
        s.circle(float(ax2.X(res[(k, "Y_시차")]["rho"])), yy - 4, 5, cls="s-bg f-bd", width=1)
        s.circle(float(ax2.X(res[(k, "Y_오차")]["lam"])), yy + 4, 5, cls="s-bg f-ac", width=1)
    ax2.vline(0.5, cls="s-mu", width=1, dash="3 3")
    ax2.xaxis(ticks=[0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
    for x, c, lab in ((200, "f-bd", "Y_시차 · 공간시차 모형 (ρ)"), (430, "f-ac", "Y_오차 · 공간오차 모형 (λ)")):
        s.circle(x, H - 18, 5, cls=f"s-bg {c}", width=1)
        s.text(x + 10, H - 14, lab, size=10, anchor="start")
    s.save(os.path.join(OUT, "27-weights.svg"))


def app_runs(sim):
    """앱의 공간가중치(엔진 weights.build)로 공간시차 모형을 돌린 값 (해 보기용)"""
    from geostat_engine.analysis import weights as gw

    from regkit import app_num, coefs, fit

    print("[7] 앱 해 보기: Y_시차 공간시차 모형(ML)")
    for label, spec in (("퀸", {"type": "queen"}), ("KNN 6", {"type": "knn", "k": 6}), ("거리 3000", {"type": "distance", "threshold": 3000}),
                        ("역거리 5000", {"type": "distance", "threshold": 5000, "inverse": True, "power": 1})):
        W, desc = gw.build(sim, spec)
        card = np.array(list(W.cardinalities.values()))
        rep, _ = fit(sim, "lag", "Y_시차", XN, W)
        c = coefs(rep)
        tot = next(r for r in rep["impacts"]["rows"] if r["name"] == "온도편차")["total"]
        print(f"  {label} ({desc}; 평균 {card.mean():.2f} · 최소 {card.min()} · 최대 {card.max()}): ρ {app_num(c['ρ (W_y)']['coef'])}, 온도편차 총 효과 {app_num(tot)}, "
              f"AICc {app_num(rep['fit']['aicc'], 6)}, 로그우도 {app_num(rep['fit']['loglik'], 6)}")


if __name__ == "__main__":
    dong = load_dong()
    Wn = queen(dong)
    y, off, X1, X3, cnt = counts(dong, Wn)
    sim = load_sim()
    W = queen(sim)
    vecs, mc, cand = eigvecs(sim)
    res, comp, u_true = esf(sim, W, vecs, mc, cand)
    esf_counts(dong, Wn, y, off, X1, X3, vecs, cand)
    esf_mc(sim, W, vecs, cand)
    fixed_effects(sim, dong, W)
    Ws, wres = weights_sens(sim)
    app_runs(sim)
    fig_esf(sim, vecs, mc, comp, u_true)
    fig_weights(wres, Ws)
