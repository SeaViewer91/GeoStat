"""28강 그림과 본문 수치.

- 28-regime.svg : Y_체제. 다솜구와 나머지 구의 온도편차 기울기(전역 OLS 하나 대 체제별)
- 28-vary.svg : Y_변이. 참 온도편차 계수 지도와 확장법(1차·2차 좌표 다항식)으로 추정한 계수 지도
- 28-confuse.svg : 모의 실험. 이질성 검정(체제 Chow, 확장법)과 의존성 검정(LM)이 서로의 과정에서 얼마나 자주 유의하게 나오는지

연습용 모의 자료의 규칙은 regkit.py 머리말에 있음(Y_체제, Y_변이는 28강에서 더함).
앱 해 보기 수치는 GeoStat 엔진(계산 필드 fields.evaluate, 회귀 regression.prepare/run)으로 계산함.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/28.py
"""
import contextlib
import io
import os
import sys
import warnings

import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import MapFrame, colorbar, draw, outline  # noqa: E402
from plotkit import Axes  # noqa: E402
from regkit import TRUE, app_num, app_p, coefs, dense, diags, fit, load_dong, load_sim, queen, regime_b2, rng, summ, vary_b2  # noqa: E402
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import fields  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
XN = ["고령비율", "온도편차"]
X0, Y0 = 38.0, 454.0  # 확장법에서 좌표를 빼는 기준(km)


def quiet(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


# ---------------------------------------------------------------- 손계산
def hand():
    print("[손계산] 두 집단, x = 1, 2, 3, 4. A의 y = (2, 3, 5, 6), B의 y = (1, 3, 6, 8)")
    x = np.array([1, 2, 3, 4.0])
    ya = np.array([2, 3, 5, 6.0])
    yb = np.array([1, 3, 6, 8.0])

    def ols(x, y):
        X = np.c_[np.ones(len(x)), x]
        b = np.linalg.lstsq(X, y, rcond=None)[0]
        e = y - X @ b
        return b, e @ e

    ba, ra = ols(x, ya)
    bb, rb = ols(x, yb)
    bp, rp = ols(np.r_[x, x], np.r_[ya, yb])
    k, n = 2, 8
    F = ((rp - (ra + rb)) / k) / ((ra + rb) / (n - 2 * k))
    print(f"  A: 절편 {ba[0]:.3f}, 기울기 {ba[1]:.3f}, RSS {ra:.3f} | B: 절편 {bb[0]:.3f}, 기울기 {bb[1]:.3f}, RSS {rb:.3f}")
    print(f"  합친 회귀: 절편 {bp[0]:.3f}, 기울기 {bp[1]:.3f}, RSS {rp:.3f}")
    print(f"  Chow F = (({rp:.3f} − {ra + rb:.3f}) / {k}) / ({ra + rb:.3f} / {n - 2 * k}) = {F:.3f}, p = {stats.f.sf(F, k, n - 2 * k):.4f}")


# ---------------------------------------------------------------- 본문 수치
def chow_summary(name, m):
    j = m.chow.joint
    regi = [(round(a, 3), round(b, 4)) for a, b in m.chow.regi]
    return f"{name}: 전체 {j[0]:.3f} (p {j[1]:.4f}), 변수별(상수, 고령비율, 온도편차) {regi}"


def numbers():
    import spreg

    sim = load_sim()
    W = queen(sim)
    X = sim[XN].to_numpy()
    gu = sim["구"].tolist()
    da = np.where(sim["구"] == "다솜구", "다솜구", "나머지").tolist()
    xc = sim["X_km"].to_numpy() - X0
    yc = sim["Y_km"].to_numpy() - Y0
    b_reg = regime_b2(sim)
    b_var = vary_b2(sim["X_km"], sim["Y_km"])
    print(f"[0] 참 계수: Y_체제 다솜구 {b_reg[sim['구'] == '다솜구'][0]}, 나머지 {b_reg[sim['구'] != '다솜구'][0]} (다솜구 {int((sim['구'] == '다솜구').sum())}개 동); "
          f"Y_변이 {b_var.min():.3f}~{b_var.max():.3f} (평균 {b_var.mean():.3f})")
    out = {}
    for yv in ("Y_독립", "Y_시차", "Y_오차", "Y_체제", "Y_변이"):
        y = sim[[yv]].to_numpy()
        o = quiet(spreg.OLS, y, X, w=W, spat_diag=True, moran=True, name_x=XN)
        r5 = quiet(spreg.OLS_Regimes, y, X, gu, name_x=XN)
        r2 = quiet(spreg.OLS_Regimes, y, X, da, name_x=XN)
        cl = quiet(spreg.OLS, y, np.c_[X, X[:, 1] * xc, X[:, 1] * yc])
        cq = quiet(spreg.OLS, y, np.c_[X, X[:, 1] * xc, X[:, 1] * yc, X[:, 1] * xc ** 2, X[:, 1] * yc ** 2, X[:, 1] * xc * yc])
        Fl = ((o.utu - cl.utu) / 2) / (cl.utu / (len(y) - 5))
        Fq = ((o.utu - cq.utu) / 5) / (cq.utu / (len(y) - 8))
        print(f"[1] {yv}: OLS {np.round(o.betas.ravel(), 4).tolist()}, R² {o.r2:.4f}, 잔차 I {o.moran_res[0]:.4f} (p {o.moran_res[2]:.4f}), "
              f"LM-lag p {o.lm_lag[1]:.4f}, LM-error p {o.lm_error[1]:.4f}, Robust lag p {o.rlm_lag[1]:.4f}, Robust error p {o.rlm_error[1]:.4f}")
        print("    " + chow_summary("Chow 구 5개", r5))
        print("    " + chow_summary("Chow 다솜구 대 나머지", r2) + f", 계수 {np.round(r2.betas.ravel(), 4).tolist()} {r2.name_x}")
        print(f"    확장법 1차: {np.round(cl.betas.ravel(), 4).tolist()}, p {[round(p, 4) for _, p in cl.t_stat]}, F {Fl:.3f} (p {stats.f.sf(Fl, 2, len(y) - 5):.4f}), "
              f"R² {cl.r2:.4f}; 2차: F {Fq:.3f} (p {stats.f.sf(Fq, 5, len(y) - 8):.4f}), R² {cq.r2:.4f}")
        out[yv] = (o, r5, r2, cl, cq)
    # 계수 지도 오차
    for nm, m, terms in (("1차", out["Y_변이"][3], 2), ("2차", out["Y_변이"][4], 5)):
        b = m.betas.ravel()
        est = b[2] + b[3] * xc + b[4] * yc + (b[5] * xc ** 2 + b[6] * yc ** 2 + b[7] * xc * yc if terms == 5 else 0)
        print(f"    Y_변이 확장법 {nm}: 추정 계수 {est.min():.3f}~{est.max():.3f}, 참 계수와의 상관 {np.corrcoef(est, b_var)[0, 1]:.3f}, RMSE {np.sqrt(np.mean((est - b_var) ** 2)):.3f}")
    # 공간 체제 + 공간오차/시차 (Anselin 1990의 공간 Chow)
    print("[2] 공간 의존을 함께 넣은 체제 모형 (구 5개)")
    for yv in ("Y_오차", "Y_시차", "Y_체제", "Y_변이"):
        y = sim[[yv]].to_numpy()
        e = quiet(spreg.ML_Error_Regimes, y, X, gu, w=W, name_x=XN)
        lg = quiet(spreg.ML_Lag_Regimes, y, X, gu, w=W, name_x=XN, spat_impacts=None)
        print(f"  {yv}: 공간오차 체제 λ {e.betas.ravel()[-1]:.3f}, Chow {e.chow.joint[0]:.3f} (p {e.chow.joint[1]:.4f}) | 공간시차 체제 ρ {lg.betas.ravel()[-1]:.3f}, Chow {lg.chow.joint[0]:.3f} (p {lg.chow.joint[1]:.4f})")
    # 출동률
    dong = load_dong()
    Wn = queen(dong)
    y = dong[["출동률"]].to_numpy()
    Xd = dong[XN].to_numpy()
    xd = dong.geometry.centroid.x.to_numpy() / 1000 - X0
    yd = dong.geometry.centroid.y.to_numpy() / 1000 - Y0
    o = quiet(spreg.OLS, y, Xd, name_x=XN)
    r5 = quiet(spreg.OLS_Regimes, y, Xd, dong["구"].tolist(), name_x=XN)
    cl = quiet(spreg.OLS, y, np.c_[Xd, Xd[:, 1] * xd, Xd[:, 1] * yd])
    Fl = ((o.utu - cl.utu) / 2) / (cl.utu / (len(y) - 5))
    print("[3] 출동률(8강 M3): " + chow_summary("Chow 구 5개", r5))
    nm = r5.name_x
    b = r5.betas.ravel()
    print("    구별 온도편차 계수: " + ", ".join(f"{nm[i].split('_')[0]} {b[i]:.3f}" for i in range(len(b)) if nm[i].endswith("온도편차")))
    print(f"    확장법 1차: {np.round(cl.betas.ravel(), 4).tolist()}, p {[round(p, 3) for _, p in cl.t_stat]}, F {Fl:.3f} (p {stats.f.sf(Fl, 2, len(y) - 5):.4f})")
    return sim, W, out


def app_steps(sim, W):
    """앱 해 보기: 계산 필드와 OLS (엔진과 같은 계산)"""
    s = sim.copy()
    for name, expr in (("다솜", '(`구` == "다솜구") * 1'), ("다솜_온도", "`다솜` * `온도편차`"),
                       ("온도_x", "`온도편차` * (`X_km` - 38)"), ("온도_y", "`온도편차` * (`Y_km` - 454)")):
        s[name] = fields.evaluate(s, expr)
    print("[4] 앱 해 보기")
    for label, y, xs in (("전역", "Y_체제", XN), ("체제", "Y_체제", XN + ["다솜", "다솜_온도"]),
                         ("전역", "Y_변이", XN), ("확장법", "Y_변이", XN + ["온도_x", "온도_y"])):
        rep, _ = fit(s, "ols", y, xs, W)
        c, d, sm = coefs(rep), diags(rep), summ(rep)
        print(f"  {y} {label}: " + ", ".join(f"{k} {app_num(v['coef'])} (p {app_p(v['p'])})" for k, v in c.items()))
        mi = d["잔차 Moran's I"]
        print(f"     R² {app_num(sm['R²'])}, AICc {app_num(rep['fit']['aicc'], 6)}, 잔차 I {app_num(mi['value'])} (p {app_p(mi['p'])}), 안내: {rep['notes'][-1]}")


# ---------------------------------------------------------------- 모의 실험
def simulate(sim, W, R=1000):
    n = len(sim)
    Wd = dense(W)
    x1 = sim["고령비율"].to_numpy()
    x2 = sim["온도편차"].to_numpy()
    X = np.c_[np.ones(n), x1, x2]
    xc = sim["X_km"].to_numpy() - X0
    yc = sim["Y_km"].to_numpy() - Y0
    Xc = np.c_[X, x2 * xc, x2 * yc]
    G = sim["구"].astype("category")
    D = np.c_[[(G == g).astype(float) for g in G.cat.categories]].T  # 구 5개
    Xr = np.hstack([D * X[:, [j]] for j in range(3)])  # 구별 상수·기울기
    A = np.linalg.inv(np.eye(n) - 0.5 * Wd)
    xb = TRUE["b0"] + TRUE["b1"] * x1 + TRUE["b2"] * x2
    dgps = {
        "독립": lambda e: xb + e,
        "공간시차 ρ 0.5": lambda e: A @ (xb + e),
        "공간오차 λ 0.5": lambda e: xb + A @ e,
        "체제 (다솜구)": lambda e: TRUE["b0"] + TRUE["b1"] * x1 + regime_b2(sim) * x2 + e,
        "매끈한 변이": lambda e: TRUE["b0"] + TRUE["b1"] * x1 + vary_b2(sim["X_km"], sim["Y_km"]) * x2 + e,
    }
    T = np.trace(Wd.T @ Wd + Wd @ Wd)

    def rss(Z, Y):
        B = np.linalg.lstsq(Z, Y, rcond=None)[0]
        E = Y - Z @ B
        return (E * E).sum(0), E

    r = rng("sim_mc_28")
    res = {}
    for name, f in dgps.items():
        E0 = TRUE["sigma"] * r.standard_normal((n, R))
        Y = np.column_stack([f(E0[:, k]) for k in range(R)])
        r0, E = rss(X, Y)
        rc, _ = rss(Xc, Y)
        rr, _ = rss(Xr, Y)
        Fc = ((r0 - rc) / 2) / (rc / (n - Xc.shape[1]))
        Fr = ((r0 - rr) / (Xr.shape[1] - 3)) / (rr / (n - Xr.shape[1]))
        s2 = r0 / n
        lm_err = ((E * (Wd @ E)).sum(0) / s2) ** 2 / T
        rej = dict(chow=np.mean(stats.f.sf(Fr, Xr.shape[1] - 3, n - Xr.shape[1]) <= 0.05),
                   casetti=np.mean(stats.f.sf(Fc, 2, n - Xc.shape[1]) <= 0.05),
                   lmerr=np.mean(stats.chi2.sf(lm_err, 1) <= 0.05))
        res[name] = rej
    print(f"[5] 모의 실험 (실현값 {R}개, 유의수준 5%에서 기각한 비율)")
    for k, v in res.items():
        print(f"  {k}: 구 체제 Chow {v['chow']:.3f}, 확장법 1차 F {v['casetti']:.3f}, LM-error {v['lmerr']:.3f}")
    return res


# ---------------------------------------------------------------- 그림
def fig_regime(sim, out):
    o, r5, r2, cl, cq = out["Y_체제"]
    b = r2.betas.ravel()
    nm = r2.name_x
    get = lambda reg, v: b[nm.index(f"{reg}_{v}")]  # noqa: E731
    da = (sim["구"] == "다솜구").to_numpy()
    y = sim["Y_체제"].to_numpy()
    x1 = sim["고령비율"].to_numpy()
    x2 = sim["온도편차"].to_numpy()
    part = y - o.betas.ravel()[1] * x1  # 고령비율 몫을 뺀 값
    W_, H = 720, 300
    s = Svg(W_, H, f"Y_체제에서 고령비율의 몫을 뺀 값과 온도편차. 주황 점은 다솜구, 회색 점은 나머지 구. 회색 점선은 도시 전체에 하나의 기울기를 맞춘 OLS({o.betas.ravel()[2]:.2f}), "
                   f"실선은 체제마다 따로 맞춘 기울기(다솜구 {get('다솜구', '온도편차'):.2f}, 나머지 {get('나머지', '온도편차'):.2f}). 참 기울기는 2.0과 1.0임. "
                   "전역 기울기는 대부분을 차지하는 나머지 구의 관계에 끌려, 다솜구의 강한 관계를 숨김")
    ax = Axes(s, 70, 30, 380, 220, (-4.5, 6.2), (-2, 20))
    for xx, yy, d in zip(x2, part, da):
        s.circle(float(ax.X(xx)), float(ax.Y(yy)), 3.2, cls="s-bg " + ("f-bd" if d else "f-mu"), width=0.5)
    xs = np.array([-4.5, 6.2])
    bo = o.betas.ravel()
    ax.curve(xs, bo[0] + bo[2] * xs, cls="s-mu", width=1.6, dash="5 3")
    for reg, cls, sel in (("다솜구", "s-bd", da), ("나머지", "s-fg", ~da)):
        c0 = get(reg, "CONSTANT") + get(reg, "고령비율") * x1[sel].mean() - bo[1] * x1[sel].mean()
        lo, hi = x2[sel].min(), x2[sel].max()
        ax.curve(np.array([lo, hi]), c0 + get(reg, "온도편차") * np.array([lo, hi]), cls=cls, width=2)
    ax.xaxis(ticks=[-4, -2, 0, 2, 4, 6], label="온도편차 (℃)")
    ax.yaxis(ticks=[0, 5, 10, 15, 20], label="Y_체제 − 고령비율 몫")
    fr = MapFrame(sim.total_bounds, 490, 50, 210)
    draw(s, fr, sim.geometry, ["q3" if d else "q0" for d in da], width=0.3)
    outline(s, fr, sim.union_all(), cls="s-mu", width=0.8)
    s.text(fr.x + 105, 36, "체제: 다솜구(주황)와 나머지", size=11, weight="600")
    s.save(os.path.join(OUT, "28-regime.svg"))


def fig_vary(sim, out):
    xc = sim["X_km"].to_numpy() - X0
    yc = sim["Y_km"].to_numpy() - Y0
    true = vary_b2(sim["X_km"], sim["Y_km"])
    _, _, _, cl, cq = out["Y_변이"]
    bl, bq = cl.betas.ravel(), cq.betas.ravel()
    lin = bl[2] + bl[3] * xc + bl[4] * yc
    quad = bq[2] + bq[3] * xc + bq[4] * yc + bq[5] * xc ** 2 + bq[6] * yc ** 2 + bq[7] * xc * yc
    W_, H = 720, 260
    s = Svg(W_, H, f"Y_변이의 온도편차 계수. 왼쪽: 참 계수(가람·누리·라온구가 만나는 도시 서쪽 가운데에서 2.2까지 높고 바깥으로 0.8까지 낮아짐). 가운데: 좌표의 1차식으로 넓힌 확장법의 추정(참값과 상관 "
                   f"{np.corrcoef(lin, true)[0, 1]:.2f}). 기울어진 평면이라 언덕을 그리지 못함. 오른쪽: 2차식으로 넓힌 추정(상관 {np.corrcoef(quad, true)[0, 1]:.2f}). "
                   "확장법은 미리 정한 식의 모양만큼만 변이를 잡음")
    mw = 220
    lo, hi = 0.6, 2.4
    bins = np.linspace(lo, hi, 6)[1:-1]
    for k, (v, title) in enumerate(((true, "참 계수"), (lin, "확장법 1차"), (quad, "확장법 2차"))):
        cls = [f"q{int(np.digitize(t, bins))}" for t in v]
        fr = MapFrame(sim.total_bounds, 15 + k * (mw + 14), 36, mw)
        draw(s, fr, sim.geometry, cls, width=0.3)
        outline(s, fr, sim.union_all(), cls="s-mu", width=0.8)
        s.text(fr.x + mw / 2, 24, title, size=12, weight="600")
    x = 170
    labs = ["< 0.96", "0.96~1.32", "1.32~1.68", "1.68~2.04", "≥ 2.04"]
    for k, lab in enumerate(labs):
        s.rect(x, H - 22, 12, 12, cls=f"s-mu q{k}", width=0.5)
        s.text(x + 16, H - 12, lab, size=10, anchor="start")
        x += 26 + len(lab) * 7
    s.save(os.path.join(OUT, "28-vary.svg"))


def fig_confuse(res):
    names = list(res.keys())
    tests = [("chow", "구 체제 Chow", "f-bd"), ("casetti", "확장법 1차 F", "f-ok"), ("lmerr", "LM-error", "f-ac")]
    W_, H = 720, 300
    s = Svg(W_, H, "모의 실험(실현값 1,000개씩)에서 세 검정이 5% 수준에서 유의하게 나온 비율. 앞의 둘은 계수가 지역마다 다른지(이질성)를, LM-error는 오차가 닮았는지(의존성)를 묻는 검정임. "
                   "공간오차·공간시차 과정에서는 이질성이 없는데도 체제 Chow가 자주 유의하고, 매끈한 변이 과정에서는 오차가 독립인데도 LM-error가 자주 유의함")
    ax = Axes(s, 140, 30, 540, 200, (-0.5, len(names) - 0.5), (0, 1.05))
    for i, nm in enumerate(names):
        for j, (key, lab, css) in enumerate(tests):
            v = res[nm][key]
            x = i - 0.27 + 0.27 * j
            x0, x1 = float(ax.X(x - 0.11)), float(ax.X(x + 0.11))
            s.rect(x0, float(ax.Y(v)), x1 - x0, float(ax.Y(0)) - float(ax.Y(v)), cls=f"s-bg {css}", width=0.5)
            s.text((x0 + x1) / 2, float(ax.Y(v)) - 4, f"{v * 100:.1f}".replace(".0", ""), size=9)
        s.text(float(ax.X(i)), float(ax.Y(0)) + 16, nm, size=10)
    ax.curve(np.array([-0.5, len(names) - 0.5]), np.array([0.05, 0.05]), cls="s-mu", width=1, dash="3 3")
    ax.yaxis(ticks=[0, 0.25, 0.5, 0.75, 1], fmt=lambda t: f"{t * 100:.0f}%")
    s.text(float(ax.X(len(names) - 0.5)) + 4, float(ax.Y(0.05)) + 4, "5%", size=9, anchor="start", cls="f-mu")
    s.text(80, 24, "유의하게 나온 비율", size=10, anchor="start", cls="f-mu")
    x = 200
    for _, lab, css in tests:
        s.rect(x, H - 22, 12, 12, cls=f"s-mu {css}", width=0.5)
        s.text(x + 16, H - 12, lab, size=10, anchor="start")
        x += 40 + len(lab) * 8
    s.save(os.path.join(OUT, "28-confuse.svg"))


if __name__ == "__main__":
    hand()
    sim, W, out = numbers()
    app_steps(sim, W)
    res = simulate(sim, W)
    fig_regime(sim, out)
    fig_vary(sim, out)
    fig_confuse(res)
