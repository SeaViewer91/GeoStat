"""24강 그림과 본문 수치.

- 24-resid.svg : 연습용 모의 자료 세 변수(Y_독립·Y_시차·Y_오차)를 OLS로 적합한 잔차 지도
- 24-mc.svg : 모의 실험. 공간시차·공간오차 과정에서 OLS 계수(온도편차)의 평균과 95% 신뢰구간 포함률
- 24-lm.svg : 모의 실험. LM 검정 판단 절차(Anselin 2005)가 고르는 모형의 비율
- 24-flow.svg : LM 검정으로 모형을 고르는 흐름(Anselin 2005)

연습용 모의 자료(practice/hanbit_dong_sim.gpkg)도 이 스크립트가 만듦. 규칙은 regkit.py 머리말에 있음.
회귀는 GeoStat 엔진의 regression.prepare/run(앱과 같은 spreg)으로 계산함.
모의 실험은 같은 식을 numpy로 한꺼번에 계산함(spreg와 한 실현값에서 대조함).

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/24.py
"""
import os
import sys

import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import MapFrame, draw, legend_row, outline  # noqa: E402
from plotkit import Axes  # noqa: E402
from regkit import TRUE, app_num, app_p, coefs, dense, diags, fit, load_dong, load_sim, make_sim, queen, rng, summ, true_effects  # noqa: E402
from svglib import Svg  # noqa: E402

OUT = os.path.join(HERE, "..", "fig")
X_NAMES = ["고령비율", "온도편차"]
YS = ["Y_독립", "Y_시차", "Y_오차"]


# ---------------------------------------------------------------- 손계산
def hand():
    print("[손계산] 한 줄로 이어진 4개 지역(1–2–3–4), 행 표준화 인접, 잔차 e = (2, 1, −1, −2)")
    Wd = np.array([[0, 1, 0, 0], [0.5, 0, 0.5, 0], [0, 0.5, 0, 0.5], [0, 0, 1, 0]], float)
    e = np.array([2, 1, -1, -2.0])
    n = 4
    We = Wd @ e
    ewe, ee = e @ We, e @ e
    T = np.trace(Wd.T @ Wd + Wd @ Wd)
    lm = (ewe / (ee / n)) ** 2 / T
    print(f"  We = {We.tolist()}, e'We = {ewe}, e'e = {ee}, I = (n/S0)(e'We/e'e) = {n / n * ewe / ee:.3f}")
    print(f"  tr(W'W) = {np.trace(Wd.T @ Wd):.2f}, tr(WW) = {np.trace(Wd @ Wd):.2f}, T = {T:.2f}")
    print(f"  LM-error = (n e'We/e'e)² / T = {lm:.4f}, p = {stats.chi2.sf(lm, 1):.3f}")
    e2 = np.array([2, -1, 1, -2.0])
    print(f"  번갈아 놓인 잔차 (2, −1, 1, −2): e'We = {e2 @ Wd @ e2}, I = {e2 @ Wd @ e2 / (e2 @ e2):.3f}")


# ---------------------------------------------------------------- 본문 수치
def numbers():
    from esda import Moran

    dong = load_dong()
    W = queen(dong)
    sim = make_sim(dong, W)
    sim = load_sim()
    Ws = queen(sim)
    np.random.seed(123456789)
    print(f"[0] 퀸 인접: 평균 이웃 수 {np.mean(list(W.cardinalities.values())):.2f}, 섬 {sum(1 for v in W.cardinalities.values() if v == 0)}개")
    for v in ("출동률", "고령비율", "온도편차"):
        m = Moran(dong[v].to_numpy(), W, permutations=999)
        print(f"  {v}의 Moran's I {m.I:.3f} (순열 p {m.p_sim:.3f})")
    print("[1] 출동률 회귀(8강 M1, M3)의 공간 진단")
    out = {}
    for name, xs in (("M1", ["고령비율"]), ("M3", X_NAMES)):
        rep, _ = fit(dong, "ols", "출동률", xs, W)
        d = diags(rep)
        print(f"  {name} {xs}: 잔차 I {d["잔차 Moran's I"]['value']:.4f} (p {d["잔차 Moran's I"]['p']:.4f}), "
              + ", ".join(f"{k} {d[k]['value']:.3f} (p {d[k]['p']:.3f})" for k in ("LM (lag)", "Robust LM (lag)", "LM (error)", "Robust LM (error)", "LM (SARMA)"))
              + f" | 순열 I {rep['fit']['moran_i']:.4f} p {rep['fit']['moran_p']:.3f} | {rep['notes'][-1]}")
    print("[2] 연습용 모의 자료 (퀸, 행 표준화)")
    print(f"  규칙: xb = {TRUE['b0']} + {TRUE['b1']}·고령비율 + {TRUE['b2']}·온도편차, σ = {TRUE['sigma']}, ρ = {TRUE['rho']}, λ = {TRUE['lam']}")
    for y in YS:
        v = sim[y]
        print(f"  {y}: 평균 {v.mean():.3f}, 표준편차 {v.std(ddof=1):.3f}, 범위 {v.min():.3f}~{v.max():.3f}, Moran's I {Moran(v.to_numpy(), Ws).I:.3f}")
    for y in YS:
        rep, cols = fit(sim, "ols", y, X_NAMES, Ws)
        c, d, s = coefs(rep), diags(rep), summ(rep)
        out[y] = (rep, cols)
        print(f"  OLS {y}: " + ", ".join(f"{k} {v['coef']:.4f} (SE {v['se']:.4f}, p {v['p']:.3g})" for k, v in c.items()) + f", R² {s['R²']:.4f}, AICc {rep['fit']['aicc']:.3f}")
        print("     " + ", ".join(f"{k} {d[k]['value']:.4f} (p {d[k]['p']:.4f})" for k in ("잔차 Moran's I", "LM (lag)", "Robust LM (lag)", "LM (error)", "Robust LM (error)", "LM (SARMA)"))
              + f", Moran z {d["Moran's I (z)"]['value']:.3f}")
        print(f"     순열 999회: I {rep['fit']['moran_i']:.4f}, p {rep['fit']['moran_p']:.3f} | 안내: {rep['notes'][-1]}")
    print("  앱 결과 카드 표시값")
    for y in YS:
        rep = out[y][0]
        c, d = coefs(rep), diags(rep)
        print(f"   {y}: " + ", ".join(f"{k} {app_num(v['coef'])}" for k, v in c.items()) + " | "
              + ", ".join(f"{k} {app_num(d[k]['value'])} p {app_p(d[k]['p'])}" for k in ("잔차 Moran's I", "LM (lag)", "Robust LM (lag)", "LM (error)", "Robust LM (error)", "LM (SARMA)"))
              + f" | 모형 비교: AICc {app_num(rep['fit']['aicc'], 6)}, 잔차 I {app_num(rep['fit']['moran_i'], 3)} p {app_p(rep['fit']['moran_p'])}")
    print("[2b] 온도편차를 빼고 고령비율만 넣으면 (빠진 변수)")
    for y in ("Y_독립", "Y_시차"):
        rep, _ = fit(sim, "ols", y, ["고령비율"], Ws)
        c, d = coefs(rep), diags(rep)
        print(f"  {y}: 고령비율 {c['고령비율']['coef']:.4f} (앱 {app_num(c['고령비율']['coef'])}), "
              + ", ".join(f"{k} {d[k]['value']:.4f} (앱 {app_num(d[k]['value'])}, p {app_p(d[k]['p'])})" for k in ("잔차 Moran's I", "LM (lag)", "Robust LM (lag)", "LM (error)", "Robust LM (error)"))
              + f" | {rep['notes'][-1]}")
    Wd = dense(Ws)
    for b, nm in ((TRUE["b1"], "고령비율"), (TRUE["b2"], "온도편차")):
        d_, i_, t_ = true_effects(Wd, TRUE["rho"], b)
        print(f"  참 효과(공간시차 과정) {nm}: 직접 {d_:.4f}, 간접 {i_:.4f}, 총 {t_:.4f}")
    return dong, sim, Ws, out


# ---------------------------------------------------------------- 모의 실험
def lm_batch(X, Wd, Y):
    """OLS와 LM 검정을 여러 실현값(Y의 열)에 한꺼번에 계산 (Anselin 1988; Anselin 외 1996)"""
    n, k = X.shape
    XtXi = np.linalg.inv(X.T @ X)
    B = XtXi @ X.T @ Y
    E = Y - X @ B
    M = np.eye(n) - X @ XtXi @ X.T
    s2n = (E * E).sum(0) / n
    s2 = (E * E).sum(0) / (n - k)
    se = np.sqrt(np.outer(np.diag(XtXi), s2))
    T = np.trace(Wd.T @ Wd + Wd @ Wd)
    WE = Wd @ E
    WY = Wd @ Y
    dE = (E * WE).sum(0) / s2n
    dL = (E * WY).sum(0) / s2n
    WXB = Wd @ (X @ B)
    nJ = ((WXB * (M @ WXB)).sum(0) + T * s2n) / s2n
    lm_err = dE ** 2 / T
    lm_lag = dL ** 2 / nJ
    rlm_lag = (dL - dE) ** 2 / (nJ - T)
    rlm_err = (dE - T / nJ * dL) ** 2 / (T * (1 - T / nJ))
    p = {k_: stats.chi2.sf(v, 1) for k_, v in (("lag", lm_lag), ("err", lm_err), ("rlag", rlm_lag), ("rerr", rlm_err))}
    I = (E * WE).sum(0) / (E * E).sum(0)
    return B, se, p, I


def decide(p, a=0.05):
    """GeoStat의 안내(_lm_advice)와 같은 규칙: 0 = OLS, 1 = 시차, 2 = 오차"""
    lag, err, rl, re = p["lag"], p["err"], p["rlag"], p["rerr"]
    out = np.zeros(len(lag), int)
    only_lag = (lag <= a) & (err > a)
    only_err = (err <= a) & (lag > a)
    both = (lag <= a) & (err <= a)
    out[only_lag] = 1
    out[only_err] = 2
    b_lag = both & (rl <= a) & (re > a)
    b_err = both & (re <= a) & (rl > a)
    b_tie = both & ~b_lag & ~b_err
    out[b_lag] = 1
    out[b_err] = 2
    out[b_tie] = np.where(rl[b_tie] <= re[b_tie], 1, 2)
    return out


def check_batch(sim, Ws):
    import spreg

    X = np.c_[np.ones(len(sim)), sim[X_NAMES].to_numpy()]
    Wd = dense(Ws)
    for y in YS:
        Y = sim[[y]].to_numpy()
        B, se, p, I = lm_batch(X, Wd, Y)
        m = spreg.OLS(Y, X[:, 1:], w=Ws, spat_diag=True, moran=True)
        print(f"  대조 {y}: numpy LM-lag p {p['lag'][0]:.4g} / spreg {m.lm_lag[1]:.4g}, RLM-err p {p['rerr'][0]:.4g} / {m.rlm_error[1]:.4g}, I {I[0]:.4f} / {m.moran_res[0]:.4f}")


def simulate(sim, Ws, R=2000):
    X = np.c_[np.ones(len(sim)), sim[X_NAMES].to_numpy()]
    Wd = dense(Ws)
    n = len(sim)
    xb = X @ np.array([TRUE["b0"], TRUE["b1"], TRUE["b2"]])
    grid = np.round(np.arange(0, 0.81, 0.1), 2)
    r = rng("sim_mc_24")
    res = {}
    for kind in ("lag", "err"):
        for a in grid:
            A = np.linalg.inv(np.eye(n) - a * Wd)
            Eps = TRUE["sigma"] * r.standard_normal((n, R))
            Y = A @ (xb[:, None] + Eps) if kind == "lag" else xb[:, None] + A @ Eps
            B, se, p, I = lm_batch(X, Wd, Y)
            b2, s2 = B[2], se[2]
            cover = np.mean(np.abs(b2 - TRUE["b2"]) <= 1.96 * s2)
            dec = decide(p)
            res[(kind, a)] = dict(mean=b2.mean(), lo=np.quantile(b2, 0.025), hi=np.quantile(b2, 0.975), sd=b2.std(ddof=1), se=s2.mean(),
                                  cover=cover, dec=np.bincount(dec, minlength=3) / R, I=I.mean(),
                                  rej_I=np.mean(p["err"] <= 0.05))
    print(f"[3] 모의 실험 (실현값 {R}개씩, 온도편차 계수의 참값 {TRUE['b2']})")
    for kind in ("lag", "err"):
        for a in grid:
            q = res[(kind, a)]
            print(f"  {kind} {a:.1f}: OLS 평균 {q['mean']:.3f} (95% {q['lo']:.3f}~{q['hi']:.3f}), 실제 표준편차 {q['sd']:.4f}, 보고 SE 평균 {q['se']:.4f}, "
                  f"포함률 {q['cover']:.3f}, 잔차 I 평균 {q['I']:.3f}, 선택 OLS/시차/오차 {np.round(q['dec'], 3).tolist()}")
    for a in (0.2, 0.5, 0.8):
        _, _, t_ = true_effects(Wd, a, TRUE["b2"])
        d_, _, _ = true_effects(Wd, a, TRUE["b2"])
        print(f"  ρ {a}: 참 직접 {d_:.3f}, 총 {t_:.3f}")
    return res, grid


# ---------------------------------------------------------------- 그림
def fig_resid(sim, out):
    W_, H = 720, 240
    s = Svg(W_, H, "연습용 모의 자료의 세 변수를 같은 두 변수(고령비율, 온도편차)로 OLS 적합한 잔차(표준편차 단위). 왼쪽 Y_독립은 잔차가 흩어져 있고, "
                   "가운데 Y_시차와 오른쪽 Y_오차는 같은 색끼리 뭉침. 괄호는 잔차의 Moran's I(퀸 인접). 두 지도의 무늬만 보고는 어느 과정에서 나왔는지 알 수 없음")
    mw = 222
    bounds = sim.total_bounds
    bins = [-np.inf, -1.5, -0.5, 0, 0.5, 1.5, np.inf]
    for k, y in enumerate(YS):
        rep, cols = out[y]
        e = np.asarray(cols["RESID"])
        z = (e - e.mean()) / e.std()
        cls = [f"d{int(np.digitize(v, bins[1:-1]))}" for v in z]
        fr = MapFrame(bounds, 15 + k * (mw + 14), 40, mw)
        draw(s, fr, sim.geometry, cls, width=0.3)
        outline(s, fr, sim.union_all(), cls="s-mu", width=0.8)
        I = diags(rep)["잔차 Moran's I"]["value"]
        s.text(fr.x + mw / 2, 26, f"{y} (I = {I:.2f})".replace("-", "−"), size=12, weight="600")
    legend_row(s, 120, H - 18, [("d0", "< −1.5"), ("d1", "−1.5~−0.5"), ("d2", "−0.5~0"), ("d3", "0~0.5"), ("d4", "0.5~1.5"), ("d5", "> 1.5")], size=10)
    s.save(os.path.join(OUT, "24-resid.svg"))


def fig_mc(res, grid, Wd):
    W_, H = 720, 320
    s = Svg(W_, H, "모의 실험(실현값 2,000개씩). 왼쪽: 공간 의존의 세기(ρ 또는 λ)에 따른 OLS 온도편차 계수의 평균과 95% 범위. 공간오차 과정(파랑)에서는 "
                   "참값 1.5 둘레에 머물지만, 공간시차 과정(주황)에서는 참 직접 효과(점선)보다도 커지고 총 효과(쇄선)를 향해 끌려감. 오른쪽: OLS가 보고한 95% 신뢰구간이 "
                   "참값 1.5를 포함한 비율. 공간오차 과정에서도 포함률이 95%보다 낮아짐(표준오차를 과소 추정)")
    ax = Axes(s, 70, 40, 270, 210, (0, 0.8), (1.0, 4.0))
    s.text(205, 22, "OLS 온도편차 계수", size=12, weight="600")
    for kind, cls in (("lag", "s-bd"), ("err", "s-ac")):
        mean = [res[(kind, a)]["mean"] for a in grid]
        lo = [res[(kind, a)]["lo"] for a in grid]
        hi = [res[(kind, a)]["hi"] for a in grid]
        pts = [(float(ax.X(a)), float(ax.Y(v))) for a, v in zip(grid, hi)] + [(float(ax.X(a)), float(ax.Y(v))) for a, v in zip(grid[::-1], lo[::-1])]
        s.polygon(pts, cls=f"s-bg {'f-bds' if kind == 'lag' else 'f-acs'}", width=0)
        ax.curve(grid, mean, cls=cls, width=2)
    gg = np.linspace(0, 0.8, 41)
    direct = [true_effects(Wd, a, TRUE["b2"])[0] for a in gg]
    total = [min(true_effects(Wd, a, TRUE["b2"])[2], 4.0) for a in gg]
    ax.curve(gg, direct, cls="s-fg", width=1.2, dash="3 3")
    ax.curve(gg[gg <= 0.6255], np.array(total)[gg <= 0.6255], cls="s-fg", width=1.2, dash="8 3 2 3")
    ax.curve(np.array([0, 0.8]), np.array([1.5, 1.5]), cls="s-mu", width=1)
    ax.xaxis(ticks=[0, 0.2, 0.4, 0.6, 0.8], label="공간 의존의 세기 (ρ 또는 λ)")
    ax.yaxis(ticks=[1, 2, 3, 4])
    s.text(float(ax.X(0.62)) + 4, float(ax.Y(3.95)) + 12, "총 효과", size=10, anchor="start", cls="f-mu")
    s.text(float(ax.X(0.77)), float(ax.Y(1.97)), "직접 효과", size=10, anchor="end", cls="f-mu")
    ax2 = Axes(s, 440, 40, 250, 210, (0, 0.8), (0, 1.0))
    s.text(565, 22, "95% 신뢰구간이 참값을 포함한 비율", size=12, weight="600")
    for kind, cls in (("lag", "s-bd"), ("err", "s-ac")):
        ax2.curve(grid, [res[(kind, a)]["cover"] for a in grid], cls=cls, width=2)
    ax2.curve(np.array([0, 0.8]), np.array([0.95, 0.95]), cls="s-mu", width=1, dash="3 3")
    ax2.xaxis(ticks=[0, 0.2, 0.4, 0.6, 0.8], label="공간 의존의 세기 (ρ 또는 λ)")
    ax2.yaxis(ticks=[0, 0.25, 0.5, 0.75, 0.95])
    y = H - 18
    s.line(200, y - 4, 222, y - 4, cls="s-bd", width=2)
    s.text(226, y, "공간시차 과정 (ρ)", size=10, anchor="start")
    s.line(380, y - 4, 402, y - 4, cls="s-ac", width=2)
    s.text(406, y, "공간오차 과정 (λ)", size=10, anchor="start")
    s.save(os.path.join(OUT, "24-mc.svg"))


def fig_lm(res):
    W_, H = 720, 280
    cases = [("독립", ("lag", 0.0)), ("시차 ρ 0.2", ("lag", 0.2)), ("시차 ρ 0.5", ("lag", 0.5)), ("오차 λ 0.2", ("err", 0.2)), ("오차 λ 0.5", ("err", 0.5))]
    s = Svg(W_, H, "모의 실험(실현값 2,000개씩)에서 LM 검정 판단 절차가 고른 모형의 비율. 독립 자료에서는 92%를 OLS로 둠(검정을 여럿 하므로 5%보다 조금 더 자주 잘못 경보함). "
                   "의존이 약하면(0.2) 공간시차 과정의 47%, 공간오차 과정의 70%를 놓침. 0.5이면 거의 모두 공간 모형을 고르고, 공간오차 과정의 11%는 공간시차 모형으로 잘못 고름")
    ax = Axes(s, 150, 30, 520, 190, (0, 1), (-0.5, len(cases) - 0.5))
    css = ["f-mu", "f-bd", "f-ac"]
    for k, (lab, key) in enumerate(cases):
        dec = res[key]["dec"]
        y = float(ax.Y(len(cases) - 1 - k))
        x0 = 0.0
        for j in range(3):
            w = dec[j]
            if w > 0:
                s.rect(float(ax.X(x0)), y - 13, float(ax.X(x0 + w)) - float(ax.X(x0)), 26, cls=f"s-bg {css[j]}", width=0.8)
                if w >= 0.06:
                    s.add(f'<text x="{(float(ax.X(x0)) + float(ax.X(x0 + w))) / 2:.1f}" y="{y + 4:.1f}" font-size="10" text-anchor="middle" fill="#ffffff">{w * 100:.0f}%</text>')
            x0 += w
        s.text(float(ax.X(0)) - 8, y + 4, lab, size=11, anchor="end")
    ax.xaxis(ticks=[0, 0.25, 0.5, 0.75, 1], label="고른 비율", fmt=lambda t: f"{t * 100:.0f}%")
    x = 200
    for css_, lab in (("f-mu", "OLS로 충분"), ("f-bd", "공간시차 모형"), ("f-ac", "공간오차 모형")):
        s.rect(x, H - 22, 12, 12, cls=f"s-mu {css_}", width=0.5)
        s.text(x + 16, H - 12, lab, size=10, anchor="start")
        x += 26 + len(lab) * 10.5
    s.save(os.path.join(OUT, "24-lm.svg"))


def fig_flow():
    W_, H = 720, 330
    s = Svg(W_, H, "LM 검정으로 모형을 고르는 흐름(Anselin 2005). OLS를 적합해 LM-lag와 LM-error를 보고, 둘 다 유의하면 Robust LM으로 가름. Robust LM이 둘 다 유의하거나 둘 다 유의하지 않으면 한쪽으로 정하기 어려움. "
                   "둘 다 유의하지 않으면 OLS에 머묾. 이 흐름은 공간시차와 공간오차 둘 중 하나를 고르는 출발점일 뿐, 다른 모형(26강)을 배제하지 않음")

    def box(x, y, w, h, text, cls="s-fg f-sf"):
        s.rect(x - w / 2, y - h / 2, w, h, cls=cls, width=1.2, rx=6)
        lines = text.split("\n")
        for i, t in enumerate(lines):
            s.text(x, y + 4 + (i - (len(lines) - 1) / 2) * 15, t, size=11)

    def arrow(x1, y1, x2, y2, label=None, lx=0, ly=0):
        s.line(x1, y1, x2, y2, cls="s-mu", width=1.3)
        ang = np.arctan2(y2 - y1, x2 - x1)
        a1, a2 = ang + 2.7, ang - 2.7
        s.polygon([(x2, y2), (x2 + 8 * np.cos(a1), y2 + 8 * np.sin(a1)), (x2 + 8 * np.cos(a2), y2 + 8 * np.sin(a2))], cls="s-mu f-mu", width=0.5)
        if label:
            s.text((x1 + x2) / 2 + lx, (y1 + y2) / 2 + ly, label, size=10, cls="f-mu")

    box(360, 30, 260, 34, "OLS 적합, 잔차 진단 (가중치 W)")
    box(360, 100, 260, 34, "LM-lag와 LM-error")
    arrow(360, 47, 360, 83)
    box(110, 185, 170, 40, "둘 다 유의하지 않음\n→ OLS에 머묾", cls="s-mu f-bg")
    box(300, 185, 150, 40, "LM-lag만 유의\n→ 공간시차 모형", cls="s-bd f-bds")
    box(470, 185, 150, 40, "LM-error만 유의\n→ 공간오차 모형", cls="s-ac f-acs")
    box(630, 185, 150, 40, "둘 다 유의\n→ Robust LM으로", cls="s-fg f-sf")
    for x in (110, 300, 470, 630):
        arrow(360, 117, x, 163)
    box(440, 290, 170, 40, "Robust LM-lag만 유의\n→ 공간시차 모형", cls="s-bd f-bds")
    box(625, 290, 170, 40, "Robust LM-error만 유의\n→ 공간오차 모형", cls="s-ac f-acs")
    box(255, 290, 170, 40, "그 밖의 경우 → 값이 큰\n쪽 먼저, 또는 26강", cls="s-fg f-sf")
    for x in (255, 440, 625):
        arrow(630, 207, x, 268)
    s.save(os.path.join(OUT, "24-flow.svg"))


if __name__ == "__main__":
    hand()
    dong, sim, Ws, out = numbers()
    check_batch(sim, Ws)
    res, grid = simulate(sim, Ws)
    fig_resid(sim, out)
    fig_mc(res, grid, dense(Ws))
    fig_lm(res)
    fig_flow()
