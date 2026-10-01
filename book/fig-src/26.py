"""26강 그림과 본문 수치.

- 26-family.svg : 공간 회귀 모형의 계보(Elhorst 2010). GNS에서 제약을 걸어 내려가는 관계
- 26-filter.svg : Y_오차의 공간오차 모형(ML) 잔차. 걸러내기 전 u(앱의 ERR_RESID)와 걸러낸 ε
- 26-compare.svg : 연습용 모의 자료 세 변수에 여섯 모형(OLS·SLX·SAR·SEM·SDM·SDEM)을 적합한 AICc

앱에 있는 모형(OLS·공간시차·공간오차, ML·GM)은 GeoStat 엔진의 regression.prepare/run으로, 나머지(SLX·SDM·SDEM)는 spreg로 계산함.
AICc는 앱과 같은 방식(계수 수 + σ²를 모수 수로 셈)으로 계산함.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/26.py
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
from regkit import app_num, app_p, coefs, dense, diags, fit, load_dong, load_sim, queen, summ  # noqa: E402
from svglib import Svg  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
XN = ["고령비율", "온도편차"]
YS = ["Y_독립", "Y_시차", "Y_오차"]
MODELS = ["OLS", "SLX", "SAR", "SEM", "SDM", "SDEM"]


def aicc(ll, k, n):
    return -2 * ll + 2 * k * n / (n - k - 1)


def fit_all(sim, W, yv):
    import spreg

    y = sim[[yv]].to_numpy()
    X = sim[XN].to_numpy()
    with contextlib.redirect_stdout(io.StringIO()):
        m = {
            "OLS": spreg.OLS(y, X, name_x=XN),
            "SLX": spreg.OLS(y, X, w=W, slx_lags=1, name_x=XN),
            "SAR": spreg.ML_Lag(y, X, W, name_x=XN, spat_impacts=None),
            "SEM": spreg.ML_Error(y, X, W, name_x=XN),
            "SDM": spreg.ML_Lag(y, X, W, slx_lags=1, name_x=XN, spat_impacts=None),
            "SDEM": spreg.ML_Error(y, X, W, slx_lags=1, name_x=XN),
            "SAC_GM": spreg.GM_Combo_Het(y, X, w=W, name_x=XN),
        }
    return m


def numbers():
    from esda import Moran

    sim = load_sim()
    W = queen(sim)
    Wd = dense(W)
    n = len(sim)
    print("[1] 공간오차 모형 (앱): Y_오차")
    app = {}
    for mdl in ("ols", "lag", "error", "error_gm"):
        rep, cols = fit(sim, mdl, "Y_오차", XN, W)
        app[mdl] = (rep, cols)
        c = coefs(rep)
        print(f"  {mdl}: " + ", ".join(f"{k} {v['coef']:.4f} (SE {v['se']:.4f}, p {v['p']:.3g}) [앱 {app_num(v['coef'])} / {app_num(v['se'])} / {app_num(v['stat'], 3)}]" for k, v in c.items()))
        print("     요약: " + ", ".join(f"{k} {app_num(v) if isinstance(v, (int, float)) else v}" for k, v in rep["summary"]))
        print("     진단: " + ", ".join(f"{d['name']} {app_num(d['value'])} p {app_p(d['p'])}" for d in rep["diagnostics"]))
        if rep["fit"]:
            f = rep["fit"]
            print(f"     모형 비교: R² {app_num(f['r2'])}, 로그우도 {app_num(f['loglik'], 6)}, AICc {app_num(f['aicc'], 6)}, 잔차 I {app_num(f['moran_i'], 3)} p {app_p(f['moran_p'])}")
        print(f"     안내: {rep['notes']}")
    print("[2] 걸러낸 잔차")
    res = {}
    for yv in YS:
        res[yv] = fit_all(sim, W, yv)
    sem = res["Y_오차"]["SEM"]
    lam = float(np.ravel(sem.betas)[-1])
    u = np.ravel(sem.u)
    ef = np.ravel(sem.e_filtered)
    eh = u - lam * (Wd @ u)
    np.random.seed(123456789)
    mu = Moran(u, W, permutations=999)
    me = Moran(ef, W, permutations=999)
    print(f"  Y_오차 SEM: λ {lam:.4f}, u의 Moran's I {mu.I:.4f} (순열 p {mu.p_sim:.3f}), ε = (I − λW)u의 Moran's I {me.I:.4f} (p {me.p_sim:.3f}); "
          f"e_filtered와 직접 계산의 차이 {np.abs(ef - eh).max():.2e}")
    print(f"  앱의 ERR_RESID와 spreg u의 차이 {np.abs(np.asarray(app['error'][1]['RESID']) - u).max():.2e}")
    print("[3] 여섯 모형 (spreg ML, AICc는 앱 방식)")
    table = {}
    for yv in YS:
        print(f"  == {yv}")
        for name in MODELS:
            m = res[yv][name]
            b = np.ravel(m.betas)
            k = len(b) + 1
            a = aicc(m.logll, k, n)
            table[(yv, name)] = (m.logll, a)
            names = list(m.name_x)
            se = np.ravel(m.std_err)
            print(f"   {name}: 로그우도 {m.logll:.3f}, AICc {a:.3f} | " + ", ".join(f"{nm_} {bb:.4f} ({s_:.4f})" for nm_, bb, s_ in zip(names, b, se)))
        g = res[yv]["SAC_GM"]
        print(f"   SAC(GM, 우도 없음): " + ", ".join(f"{nm_} {bb:.4f}" for nm_, bb in zip(g.name_z, np.ravel(g.betas))))
        best = min(MODELS, key=lambda nm_: table[(yv, nm_)][1])
        print(f"   AICc 최소: {best}")
        ll = {nm_: res[yv][nm_].logll for nm_ in MODELS}
        for a_, b_, df in (("SDM", "SAR", 2), ("SDM", "SEM", 2), ("SDM", "SLX", 1), ("SDEM", "SEM", 2), ("SDEM", "SLX", 1), ("SAR", "OLS", 1), ("SEM", "OLS", 1)):
            lr = 2 * (ll[a_] - ll[b_])
            print(f"   우도비 {a_} vs {b_}: {lr:.3f} (자유도 {df}, p {stats.chi2.sf(lr, df):.4f})")
        sdm = res[yv]["SDM"]
        b = np.ravel(sdm.betas)
        rho = b[-1]
        print(f"   SDM 공통인수 점검: θ = ({b[3]:.4f}, {b[4]:.4f}), −ρβ = ({-rho * b[1]:.4f}, {-rho * b[2]:.4f})")
        S = np.linalg.inv(np.eye(n) - rho * Wd)
        for j, nm_ in enumerate(XN):
            Sr = S @ (np.eye(n) * b[1 + j] + Wd * b[3 + j])
            d_, t_ = np.trace(Sr) / n, Sr.sum() / n
            print(f"   SDM 효과 {nm_}: 직접 {d_:.4f}, 간접 {t_ - d_:.4f}, 총 {t_:.4f}")
        slx = res[yv]["SLX"]
        bs = np.ravel(slx.betas)
        print(f"   SLX 효과: 고령비율 직접 {bs[1]:.4f} 간접 {bs[3]:.4f}; 온도편차 직접 {bs[2]:.4f} 간접 {bs[4]:.4f}")
    # 자동 탐색 (spreg.gets_sdm, GM 기반)
    import spreg

    print("[4] spreg.gets_sdm (GM 기반 일반→특수 탐색, p 0.01)")
    for yv in YS:
        with contextlib.redirect_stdout(io.StringIO()):
            r, _ = spreg.gets_sdm(sim[[yv]].to_numpy(), sim[XN].to_numpy(), W, name_x=XN, name_y=yv, mprint=False)
        print(f"  {yv}: {r}")
    ev = np.linalg.eigvals(Wd).real
    print(f"[5] W 고윳값 {ev.min():.4f}~{ev.max():.4f} → λ·ρ 범위 ({1 / ev.min():.3f}, 1)")
    # 출동률에 공간 더빈 모형
    dong = load_dong()
    Wn = queen(dong)
    import spreg

    with contextlib.redirect_stdout(io.StringIO()):
        o = spreg.OLS(dong[["출동률"]].to_numpy(), dong[XN].to_numpy(), name_x=XN)
        sl = spreg.OLS(dong[["출동률"]].to_numpy(), dong[XN].to_numpy(), w=Wn, slx_lags=1, name_x=XN)
    bs, se = np.ravel(sl.betas), np.ravel(sl.std_err)
    lr = 2 * (sl.logll - o.logll)
    print(f"[6] 출동률 SLX: " + ", ".join(f"{a} {b:.3f} (SE {s:.3f}, p {p:.3f})" for a, b, s, p in zip(sl.name_x, bs, se, [t[1] for t in sl.t_stat]))
          + f"; OLS 대비 우도비 {lr:.3f} (p {stats.chi2.sf(lr, 2):.3f}), AICc OLS {aicc(o.logll, 4, len(dong)):.3f}, SLX {aicc(sl.logll, 6, len(dong)):.3f}")
    return sim, W, res, table, app, (u, ef, mu, me, lam)


# ---------------------------------------------------------------- 그림
def fig_family():
    W_, H = 720, 378
    s = Svg(W_, H, "공간 회귀 모형의 계보(Elhorst 2010). 맨 위의 일반 둥지 모형(GNS)은 세 가지 공간 항(ρWy, WXθ, λWu)을 모두 가지고, 화살표를 따라 "
                   "항을 하나씩 0으로 두면 아래 모형이 됨. 공간오차 모형(SEM)은 공간 더빈 모형(SDM)에서 θ = −ρβ인 특수한 경우이기도 함(공통인수 제약). "
                   "GeoStat에는 OLS, SAR, SEM이 있고 나머지는 코드로 추정함")

    def box(x, y, w, title, eq, cls="s-fg f-sf"):
        s.rect(x - w / 2, y - 22, w, 44, cls=cls, width=1.2, rx=6)
        s.text(x, y - 4, title, size=11, weight="600")
        s.text(x, y + 13, eq, size=10, cls="f-mu")

    def arrow(x1, y1, x2, y2, label, t=0.5, lx=0, ly=0, dash=None):
        s.line(x1, y1, x2, y2, cls="s-mu", width=1.2, dash=dash)
        ang = np.arctan2(y2 - y1, x2 - x1)
        a1, a2 = ang + 2.7, ang - 2.7
        s.polygon([(x2, y2), (x2 + 7 * np.cos(a1), y2 + 7 * np.sin(a1)), (x2 + 7 * np.cos(a2), y2 + 7 * np.sin(a2))], cls="s-mu f-mu", width=0.5)
        tx, ty = x1 + (x2 - x1) * t + lx, y1 + (y2 - y1) * t + ly
        s.rect(tx - len(label) * 3.4 - 3, ty - 10, len(label) * 6.8 + 6, 14, cls="s-bg f-bg", width=0)
        s.text(tx, ty + 1, label, size=10, cls="f-ac")

    box(360, 36, 300, "일반 둥지 모형 GNS", "y = ρWy + Xβ + WXθ + u,  u = λWu + ε")
    box(130, 130, 200, "SAC (SARAR)", "y = ρWy + Xβ + u, u = λWu + ε")
    box(360, 130, 200, "공간 더빈 모형 SDM", "y = ρWy + Xβ + WXθ + ε")
    box(590, 130, 200, "공간 더빈 오차 모형 SDEM", "y = Xβ + WXθ + u, u = λWu + ε")
    box(130, 240, 180, "공간시차 SAR ●", "y = ρWy + Xβ + ε", cls="s-bd f-bds")
    box(360, 240, 180, "공간오차 SEM ●", "y = Xβ + u, u = λWu + ε", cls="s-ac f-acs")
    box(590, 240, 180, "공간시차 X SLX", "y = Xβ + WXθ + ε")
    box(360, 330, 160, "OLS ●", "y = Xβ + ε", cls="s-mu f-bg")
    arrow(300, 58, 160, 107, "θ = 0")
    arrow(360, 58, 360, 107, "λ = 0")
    arrow(420, 58, 560, 107, "ρ = 0")
    arrow(115, 152, 115, 217, "λ = 0", t=0.45)
    arrow(170, 152, 330, 217, "ρ = 0", t=0.25)
    arrow(320, 152, 175, 217, "θ = 0", t=0.25)
    arrow(360, 152, 360, 217, "θ = −ρβ", t=0.45, dash="4 3")
    arrow(400, 152, 545, 217, "ρ = 0", t=0.25)
    arrow(550, 152, 395, 217, "θ = 0", t=0.25)
    arrow(605, 152, 605, 217, "λ = 0", t=0.45)
    arrow(150, 262, 300, 314, "ρ = 0")
    arrow(360, 262, 360, 307, "λ = 0")
    arrow(570, 262, 420, 314, "θ = 0")
    s.text(705, 368, "● GeoStat에서 추정할 수 있음", size=10, anchor="end", cls="f-mu")
    s.save(os.path.join(OUT, "26-family.svg"))


def fig_filter(sim, flt):
    u, ef, mu, me, lam = flt
    W_, H = 720, 280
    s = Svg(W_, H, f"Y_오차에 공간오차 모형(ML, λ = {lam:.2f})을 적합한 잔차(표준편차 단위). 왼쪽: y − Xβ로 구한 u. GeoStat이 잔차 열(<접두어>_RESID)로 저장하고 잔차 Moran's I를 "
                   f"계산하는 값으로, 오차의 공간 구조를 그대로 담고 있어 I = {mu.I:.2f}임. 오른쪽: 공간 필터 (I − λW)를 거친 ε. 모형이 독립이라고 가정한 부분으로, "
                   f"I = {me.I:.3f}로 공간 구조가 남지 않음. 동쪽의 큰 동 몇 개가 눈에 띄지만, 면적이 커서 눈길을 끌 뿐임(5강의 면적 편향)")
    bins = [-1.5, -0.5, 0, 0.5, 1.5]
    mw = 300
    for k, (v, title) in enumerate(((u, f"걸러내기 전 u (I = {mu.I:.2f})"), (ef, f"걸러낸 ε (I = {me.I:.3f})"))):
        z = (v - v.mean()) / v.std()
        cls = [f"d{int(np.digitize(t, bins))}" for t in z]
        fr = MapFrame(sim.total_bounds, 40 + k * (mw + 40), 36, mw)
        draw(s, fr, sim.geometry, cls, width=0.3)
        outline(s, fr, sim.union_all(), cls="s-mu", width=0.8)
        s.text(fr.x + mw / 2, 24, title.replace("-", "−"), size=12, weight="600")
    legend_row(s, 120, H - 14, [("d0", "< −1.5"), ("d1", "−1.5~−0.5"), ("d2", "−0.5~0"), ("d3", "0~0.5"), ("d4", "0.5~1.5"), ("d5", "> 1.5")], size=10)
    s.save(os.path.join(OUT, "26-filter.svg"))


def fig_compare(table):
    W_, H = 720, 300
    s = Svg(W_, H, "연습용 모의 자료의 세 변수에 여섯 모형을 적합한 AICc(각 변수에서 가장 작은 값과의 차이, 작을수록 좋음). Y_독립은 OLS, Y_시차는 공간시차(SAR), "
                   "Y_오차는 공간오차(SEM)가 가장 작음. 참 모형을 포함하는 더 큰 모형(예: Y_오차의 SDM·SDEM, Y_시차의 SDM)은 모수가 많아 AICc가 4~6 정도 뒤짐. 차이가 2보다 작은 모형들은 자료로 잘 구별되지 않음")
    ax = Axes(s, 110, 40, 560, 200, (-0.5, len(MODELS) - 0.5), (-1, 33))
    css = {"Y_독립": ("s-mu", "f-mu"), "Y_시차": ("s-bd", "f-bd"), "Y_오차": ("s-ac", "f-ac")}
    for k, yv in enumerate(YS):
        best = min(table[(yv, m)][1] for m in MODELS)
        for j, m in enumerate(MODELS):
            d = table[(yv, m)][1] - best
            x = float(ax.X(j - 0.2 + 0.2 * k))
            yv_ = float(ax.Y(min(d, 32)))
            s.circle(x, yv_, 5, cls=f"s-bg {css[yv][1]}", width=1)
            if d < 0.05:
                s.text(x + 8, yv_ + 4, "최소", size=9, anchor="start", cls=css[yv][1])
    for j, m in enumerate(MODELS):
        s.text(float(ax.X(j)), float(ax.Y(-1)) + 18, m, size=11)
    ax.curve(np.array([-0.5, len(MODELS) - 0.5]), np.array([2, 2]), cls="s-mu", width=1, dash="3 3")
    ax.yaxis(ticks=[0, 2, 10, 20, 30], label="AICc − 최솟값")
    x = 200
    for yv in YS:
        s.circle(x, H - 18, 5, cls=f"s-bg {css[yv][1]}", width=1)
        s.text(x + 10, H - 14, yv, size=10, anchor="start")
        x += 120
    s.save(os.path.join(OUT, "26-compare.svg"))


if __name__ == "__main__":
    sim, W, res, table, app, flt = numbers()
    fig_family()
    fig_filter(sim, flt)
    fig_compare(table)
