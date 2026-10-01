"""25강 그림과 본문 수치.

- 25-ripple.svg : 한 행정동의 온도편차가 1 오를 때 y가 이웃으로 번지는 모습(참 ρ = 0.5, β = 1.5)
- 25-est.svg : ρ 추정. 왼쪽: Y_시차의 집중 로그우도(야코비 항이 있을 때와 없을 때). 오른쪽: 모의 실험에서 세 추정법의 ρ 분포
- 25-effects.svg : 온도편차의 직접·간접·총 효과. 참값, 공간시차 모형(ML·GM) 추정값, OLS 계수

연습용 모의 자료(practice/hanbit_dong_sim.gpkg)는 24.py가 만듦. 규칙은 regkit.py 머리말에 있음.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/25.py
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
from mapkit import MapFrame, draw, legend_row, outline  # noqa: E402
from plotkit import Axes  # noqa: E402
from regkit import TRUE, app_num, app_p, coefs, dense, diags, fit, load_dong, load_sim, queen, rng, summ, true_effects  # noqa: E402
from svglib import Svg  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
XN = ["고령비율", "온도편차"]


def hand():
    print("[손계산] 한 줄로 이어진 3개 지역(1–2–3), 행 표준화, ρ = 0.5, β = 2")
    W = np.array([[0, 1, 0], [0.5, 0, 0.5], [0, 1, 0]], float)
    A = np.eye(3) - 0.5 * W
    S = np.linalg.inv(A)
    print("  (I − ρW)⁻¹ =\n" + "\n".join("   " + "  ".join(f"{v:.4f}" for v in row) for row in S))
    for r in range(3):
        print(f"   행 {r + 1} 합 {S[r].sum():.4f}")
    b = 2.0
    print(f"  지역 1의 x가 1 오를 때 y의 변화 = β × 첫째 열 = {np.round(b * S[:, 0], 4).tolist()}")
    d = b * np.trace(S) / 3
    t = b * S.sum() / 3
    print(f"  직접 효과 = β × 대각 평균 = {d:.4f}, 총 효과 = β × 행 합 평균 = {t:.4f} (= β/(1−ρ) = {b / 0.5:.1f}), 간접 = {t - d:.4f}")
    P = np.eye(3)
    acc = np.zeros((3, 3))
    for k in range(6):
        acc += P
        print(f"   급수 {k} 차까지 합의 (1,1) 원소 {acc[0, 0]:.4f}, (2,1) {acc[1, 0]:.4f}")
        P = 0.5 * W @ P


def numbers():
    sim = load_sim()
    W = queen(sim)
    Wd = dense(W)
    n = len(sim)
    out = {}
    print("[1] Y_시차")
    for m in ("ols", "lag", "lag_gm"):
        rep, cols = fit(sim, m, "Y_시차", XN, W)
        out[m] = rep
        c, s = coefs(rep), summ(rep)
        print(f"  {m}: " + ", ".join(f"{k} {v['coef']:.4f} (SE {v['se']:.4f}, p {v['p']:.3g})" for k, v in c.items()))
        print("     앱 표시: " + ", ".join(f"{k} {app_num(v['coef'])} / SE {app_num(v['se'])} / {app_num(v['stat'], 3)}" for k, v in c.items()))
        print("     요약: " + ", ".join(f"{k} {app_num(v) if isinstance(v, (int, float)) else v}" for k, v in rep["summary"]))
        print("     진단: " + ", ".join(f"{d['name']} {app_num(d['value'])} p {app_p(d['p'])}" for d in rep["diagnostics"]))
        if rep["fit"]:
            print(f"     모형 비교: R² {app_num(rep['fit']['r2'])}, 로그우도 {app_num(rep['fit']['loglik'], 6)}, AICc {app_num(rep['fit']['aicc'], 6)}, 잔차 I {app_num(rep['fit']['moran_i'], 3)} p {app_p(rep['fit']['moran_p'])}")
        if rep["impacts"]:
            for r in rep["impacts"]["rows"]:
                print(f"     효과 {r['name']}: 직접 {r['direct']:.4f} ({app_num(r['direct'])}), 간접 {r['indirect']:.4f} ({app_num(r['indirect'])}), 총 {r['total']:.4f} ({app_num(r['total'])})")
        print(f"     안내: {rep['notes']}")
    for b, nm in ((TRUE["b1"], "고령비율"), (TRUE["b2"], "온도편차")):
        d_, i_, t_ = true_effects(Wd, TRUE["rho"], b)
        print(f"  참 효과 {nm}: 직접 {d_:.4f}, 간접 {i_:.4f}, 총 {t_:.4f}")
    S = np.linalg.inv(np.eye(n) - 0.5 * Wd)
    print(f"  ρ = 0.5에서 승수: 대각 평균 {np.trace(S) / n:.4f} (최소 {S.diagonal().min():.4f}, 최대 {S.diagonal().max():.4f}), 행 합 {S.sum(1).mean():.4f}")
    # 효과의 불확실성: (β, ρ)의 점근 분포에서 뽑아 효과를 계산함 (LeSage & Pace 2009의 방법)
    import spreg

    y = sim[["Y_시차"]].to_numpy()
    X = sim[XN].to_numpy()
    m = spreg.ML_Lag(y, X, W, method="full")
    b = np.ravel(m.betas)
    V = m.vm
    r = rng("effects_draws_25")
    draws = r.multivariate_normal(b, V, 2000)
    ev = np.linalg.eigvals(Wd).real
    res = {"고령비율": [], "온도편차": []}
    for dr in draws:
        rho = dr[-1]
        Sd = np.linalg.inv(np.eye(n) - rho * Wd)
        dm, tm = np.trace(Sd) / n, Sd.sum() / n
        for j, nm in enumerate(XN):
            bj = dr[1 + j]
            res[nm].append((bj * dm, bj * (tm - dm), bj * tm))
    eff_ci = {}
    for nm in XN:
        a = np.array(res[nm])
        lo, hi = np.quantile(a, 0.025, axis=0), np.quantile(a, 0.975, axis=0)
        eff_ci[nm] = (lo, hi)
        print(f"  {nm} 효과의 95% 구간(2,000번 뽑기): 직접 {lo[0]:.3f}~{hi[0]:.3f}, 간접 {lo[1]:.3f}~{hi[1]:.3f}, 총 {lo[2]:.3f}~{hi[2]:.3f}")
    print(f"  ρ의 95% 구간 {b[-1] - 1.96 * np.sqrt(V[-1, -1]):.3f}~{b[-1] + 1.96 * np.sqrt(V[-1, -1]):.3f}; W 고윳값 범위 {ev.min():.4f}~{ev.max():.4f} → ρ 허용 범위 ({1 / ev.min():.3f}, 1)")
    print("[2] 다른 변수의 공간시차 모형")
    for gdf, y, xs in ((sim, "Y_독립", XN), (sim, "Y_오차", XN)):
        rep, _ = fit(gdf, "lag", y, xs, W)
        c = coefs(rep)
        print(f"  {y}: ρ {c['ρ (W_y)']['coef']:.4f} (p {c['ρ (W_y)']['p']:.3f}), AICc {rep['fit']['aicc']:.3f}")
    dong = load_dong()
    Wn = queen(dong)
    for xs in (["고령비율"], XN):
        rep, _ = fit(dong, "lag", "출동률", xs, Wn)
        c = coefs(rep)
        lr = diags(rep)["우도비 검정 (vs OLS)"]
        print(f"  출동률 {xs}: ρ {c['ρ (W_y)']['coef']:.4f} (p {c['ρ (W_y)']['p']:.3f}), 우도비 {lr['value']:.3f} (p {lr['p']:.3f}), "
              + ", ".join(f"{k} {v['coef']:.4f}" for k, v in c.items() if k in xs))
    return sim, W, Wd, out, eff_ci


def profile(sim, Wd):
    y = sim["Y_시차"].to_numpy()
    X = np.c_[np.ones(len(sim)), sim[XN].to_numpy()]
    n = len(y)
    M = np.eye(n) - X @ np.linalg.solve(X.T @ X, X.T)
    ev = np.linalg.eigvals(Wd).real
    Wy = Wd @ y
    rhos = np.linspace(-0.4, 0.95, 271)
    ll, ll0 = [], []
    for r in rhos:
        e = M @ (y - r * Wy)
        s2 = e @ e / n
        ll.append(-n / 2 * np.log(s2) + np.log(1 - r * ev).sum())
        ll0.append(-n / 2 * np.log(s2))
    ll, ll0 = np.array(ll), np.array(ll0)
    print(f"[3] 집중 로그우도: 최대 ρ {rhos[ll.argmax()]:.3f}, 야코비 항 없이 최대 ρ {rhos[ll0.argmax()]:.3f}")
    from scipy.optimize import minimize_scalar

    f = lambda r: -(-n / 2 * np.log((M @ (y - r * Wy)) @ (M @ (y - r * Wy)) / n) + np.log(1 - r * ev).sum())  # noqa: E731
    g = lambda r: n / 2 * np.log((M @ (y - r * Wy)) @ (M @ (y - r * Wy)) / n)  # noqa: E731
    r1 = minimize_scalar(f, bounds=(-0.9, 0.99), method="bounded").x
    r0 = minimize_scalar(g, bounds=(-0.9, 0.99), method="bounded").x
    print(f"  정밀: 최대 ρ {r1:.4f}, 야코비 없이 {r0:.4f}")
    return rhos, ll, ll0, r1, r0


def mc(sim, W, Wd, R=500):
    import spreg

    X = sim[XN].to_numpy()
    Xc = np.c_[np.ones(len(sim)), X]
    n = len(sim)
    xb = Xc @ np.array([TRUE["b0"], TRUE["b1"], TRUE["b2"]])
    A = np.linalg.inv(np.eye(n) - TRUE["rho"] * Wd)
    r = rng("sim_mc_25")
    naive, ml, gm, b2 = [], [], [], []
    for k in range(R):
        y = A @ (xb + TRUE["sigma"] * r.standard_normal(n))
        Z = np.c_[Xc, Wd @ y]
        naive.append(np.linalg.lstsq(Z, y, rcond=None)[0][-1])
        m = spreg.ML_Lag(y[:, None], X, W, method="full", spat_impacts=None)
        ml.append(float(np.ravel(m.rho)[0]))
        b2.append(float(np.ravel(m.betas)[2]))
        g = spreg.GM_Lag(y[:, None], X, w=W, spat_impacts=None, spat_diag=False)
        gm.append(float(np.ravel(g.rho)[0]))
    naive, ml, gm = map(np.array, (naive, ml, gm))
    print(f"[4] 모의 실험 (실현값 {R}개, 참 ρ 0.5)")
    for nm, v in (("Wy를 넣은 OLS", naive), ("ML", ml), ("GM(2SLS)", gm)):
        print(f"  {nm}: 평균 {v.mean():.3f}, 표준편차 {v.std(ddof=1):.3f}, 2.5~97.5% {np.quantile(v, 0.025):.3f}~{np.quantile(v, 0.975):.3f}")
    print(f"  ML의 온도편차 계수 평균 {np.mean(b2):.3f} (참값 1.5)")
    return naive, ml, gm


# ---------------------------------------------------------------- 그림
def fig_ripple(sim, Wd):
    n = len(sim)
    S = np.linalg.inv(np.eye(n) - TRUE["rho"] * Wd)
    cent = np.array([[g.centroid.x, g.centroid.y] for g in sim.geometry])
    mid = cent.mean(0)
    j = int(np.argmin(((cent - mid) ** 2).sum(1)))
    dy = TRUE["b2"] * S[:, j]
    print(f"[그림] 기준 동 {sim['동이름'][j]}: 자기 자신 {dy[j]:.4f}, 이웃 평균 {dy[Wd[j] > 0].mean():.4f}, 전체 합 {dy.sum():.4f} (총 효과 {TRUE['b2'] / (1 - TRUE['rho']):.1f}), "
          f"0.01 넘는 동 {(dy > 0.01).sum()}개")
    W_, H = 720, 300
    s = Svg(W_, H, f"공간시차 과정(ρ = 0.5)에서 {sim['동이름'][j]}(굵은 테두리)의 온도편차만 1 올렸을 때 각 동의 y가 오르는 양. 계수 1.5보다 큰 {dy[j]:.2f}이 "
                   f"자기 동에 생기고(이웃을 거쳐 돌아오는 몫 포함), 이웃 동으로 갈수록 줄어들며 번짐. 모든 동의 변화를 더하면 {dy.sum():.2f}임. 직접·간접 효과는 "
                   "이런 변화를 모든 동에 대해 평균한 것임")
    bins = [0.002, 0.01, 0.05, 0.2, 1.0]
    cls = [f"q{int(np.digitize(v, bins))}" for v in dy]
    fr = MapFrame(sim.total_bounds, 60, 30, 400)
    draw(s, fr, sim.geometry, cls, width=0.3)
    outline(s, fr, sim.union_all(), cls="s-mu", width=0.8)
    outline(s, fr, sim.geometry[j], stroke="#2563eb", width=2.4)
    items = [("q0", "0.002 미만"), ("q1", "0.002~0.01"), ("q2", "0.01~0.05"), ("q3", "0.05~0.2"), ("q4", "0.2 이상")]
    for k, (c, lab) in enumerate(items):
        s.rect(500, 60 + k * 22, 14, 14, cls=f"s-mu {c}", width=0.5)
        s.text(520, 72 + k * 22, lab, size=11, anchor="start")
    s.text(500, 44, "y의 변화", size=12, weight="600", anchor="start")
    s.text(500, 200, f"자기 동: {dy[j]:.2f}", size=11, anchor="start")
    s.text(500, 220, f"이웃 동 평균: {dy[Wd[j] > 0].mean():.2f}", size=11, anchor="start")
    s.text(500, 240, f"모든 동의 합: {dy.sum():.2f}", size=11, anchor="start")
    s.save(os.path.join(OUT, "25-ripple.svg"))


def fig_est(rhos, ll, ll0, r1, r0, naive, ml, gm):
    W_, H = 720, 300
    H = 315
    s = Svg(W_, H, "왼쪽: Y_시차의 집중 로그우도(최댓값을 0으로 맞춤). 실선은 야코비 항 ln|I − ρW|까지 넣은 ML의 우도로 ρ = 0.50에서 최대이고, "
                   "점선은 그 항을 빼고 잔차 제곱합만 본 것으로 ρ를 크게 잡음. 오른쪽: 모의 실험(실현값 500개, 참 ρ = 0.5)에서 세 방법으로 추정한 ρ의 분포. "
                   "Wy를 설명변수로 넣은 OLS는 ρ를 크게 잡고, ML과 2SLS는 참값 둘레에 모임")
    ax = Axes(s, 60, 40, 260, 200, (-0.4, 0.95), (-40, 2))
    s.text(190, 22, "집중 로그우도", size=12, weight="600")
    ax.curve(rhos, np.maximum(ll - ll.max(), -40), cls="s-ac", width=2)
    ax.curve(rhos, np.maximum(ll0 - ll0.max(), -40), cls="s-mu", width=1.6, dash="4 3")
    ax.vline(r1, cls="s-ac", width=1, dash="2 2")
    ax.vline(0.5, cls="s-fg", width=1)
    ax.xaxis(ticks=[-0.4, 0, 0.4, 0.8], label="ρ")
    ax.yaxis(ticks=[-40, -30, -20, -10, 0])
    s.text(float(ax.X(0.5)) + 3, float(ax.Y(-38)), "참값", size=10, anchor="start", cls="f-mu")
    edges = np.arange(0.1, 0.95, 0.025)
    ax2 = Axes(s, 410, 40, 280, 200, (0.1, 0.95), (0, 1))
    s.text(550, 22, "모의 실험의 ρ 추정값", size=12, weight="600")
    hs = [np.histogram(v, edges)[0] for v in (naive, ml, gm)]
    top = max(h.max() for h in hs) * 1.1
    for v, h, cls, dash in ((naive, hs[0], "s-bd", None), (ml, hs[1], "s-ac", None), (gm, hs[2], "s-ok", "5 3")):
        mids = (edges[:-1] + edges[1:]) / 2
        ax2.curve(mids, h / top, cls=cls, width=2, dash=dash)
    ax2.vline(0.5, cls="s-fg", width=1)
    ax2.xaxis(ticks=[0.2, 0.4, 0.6, 0.8], label="추정한 ρ")
    y = H - 18
    for x, cls, dash, lab in ((70, "s-ac", None, "ML 집중 로그우도"), (220, "s-mu", "4 3", "야코비 항 없음"), (400, "s-bd", None, "Wy를 넣은 OLS"),
                              (530, "s-ac", None, "ML"), (590, "s-ok", "5 3", "GM (2SLS)")):
        s.line(x, y - 4, x + 20, y - 4, cls=cls, width=2, dash=dash)
        s.text(x + 24, y, lab, size=10, anchor="start")
    s.save(os.path.join(OUT, "25-est.svg"))


def fig_effects(Wd, out, eff_ci):
    d_, i_, t_ = true_effects(Wd, TRUE["rho"], TRUE["b2"])
    rows = [("참값", (d_, i_, t_), "f-fg"),
            ("공간시차 ML", None, "f-ac"),
            ("공간시차 GM", None, "f-ok")]
    get = lambda rep: next(r for r in rep["impacts"]["rows"] if r["name"] == "온도편차")  # noqa: E731
    ml, gm = get(out["lag"]), get(out["lag_gm"])
    vals = {"참값": (d_, i_, t_), "공간시차 ML": (ml["direct"], ml["indirect"], ml["total"]), "공간시차 GM": (gm["direct"], gm["indirect"], gm["total"])}
    ols = coefs(out["ols"])["온도편차"]["coef"]
    W_, H = 720, 290
    s = Svg(W_, H, f"온도편차의 직접·간접·총 효과. 짙은 회색 막대(다크 모드에서는 밝은 회색)는 참값, 파랑은 공간시차 모형(ML), 초록은 공간시차 모형(GM)의 추정값이고, 가는 선은 ML 추정의 95% 구간"
                   f"(모수 분포에서 2,000번 뽑아 계산). 점선은 OLS 계수({ols:.2f})로, 어느 효과와도 맞지 않음. 공간시차 모형의 계수 β({coefs(out['lag'])['온도편차']['coef']:.2f})도 "
                   "직접 효과와 같지 않음")
    ax = Axes(s, 90, 30, 560, 200, (-0.5, 2.5), (0, 3.8))
    groups = ["직접 효과", "간접 효과 (파급)", "총 효과"]
    for g, name in enumerate(groups):
        for k, (lab, css) in enumerate((("참값", "f-fg"), ("공간시차 ML", "f-ac"), ("공간시차 GM", "f-ok"))):
            v = vals[lab][g]
            x = g - 0.27 + k * 0.27
            s.rect(float(ax.X(x - 0.12)), float(ax.Y(v)), float(ax.X(x + 0.12)) - float(ax.X(x - 0.12)), float(ax.Y(0)) - float(ax.Y(v)), cls=f"s-bg {css}", width=0.5)
            top = v
            if lab == "공간시차 ML":
                lo, hi = eff_ci["온도편차"][0][g], eff_ci["온도편차"][1][g]
                s.line(float(ax.X(x)), float(ax.Y(lo)), float(ax.X(x)), float(ax.Y(hi)), cls="s-mu", width=1.2)
                top = hi
            s.text(float(ax.X(x)), float(ax.Y(top)) - 5, f"{v:.2f}", size=10)
        s.text(float(ax.X(g)), float(ax.Y(0)) + 18, name, size=11)
    s.line(float(ax.X(-0.5)), float(ax.Y(ols)), float(ax.X(2.5)), float(ax.Y(ols)), cls="s-bd", width=1.4, dash="5 3")
    s.text(float(ax.X(-0.45)), float(ax.Y(ols)) - 5, f"OLS 계수 {ols:.2f}", size=10, anchor="start", cls="f-bd")
    ax.yaxis(ticks=[0, 1, 2, 3])
    x = 200
    for css_, lab in (("f-fg", "참값"), ("f-ac", "공간시차 ML"), ("f-ok", "공간시차 GM")):
        s.rect(x, H - 24, 12, 12, cls=f"s-mu {css_}", width=0.5)
        s.text(x + 16, H - 14, lab, size=10, anchor="start")
        x += 30 + len(lab) * 9
    s.save(os.path.join(OUT, "25-effects.svg"))


if __name__ == "__main__":
    _print = print

    def print(*a, **k):  # noqa: A001  spreg가 모형 이름을 표준출력에 찍으므로, 이 스크립트의 출력만 원래 표준출력으로 보냄
        _print(*a, **k, file=sys.__stdout__)

    sys.stdout = io.StringIO()
    hand()
    sim, W, Wd, out, eff_ci = numbers()
    rhos, ll, ll0, r1, r0 = profile(sim, Wd)
    naive, ml, gm = mc(sim, W, Wd)
    fig_ripple(sim, Wd)
    fig_est(rhos, ll, ll0, r1, r0, naive, ml, gm)
    fig_effects(Wd, out, eff_ci)
