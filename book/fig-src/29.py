"""29강 그림과 본문 수치.

- 29-kernel.svg : 커널 함수(bisquare, gaussian, exponential)와 적응 대역폭 76개 이웃의 가중치 지도
- 29-bw.svg : 대역폭에 따른 AICc (Y_변이, Y_독립)
- 29-coef.svg : 온도편차 계수 지도. 참 계수, Y_변이의 GWR 추정, Y_독립을 대역폭 30으로 강제한 GWR(거짓 변이)
- 29-tradeoff.svg : 지역 상수와 지역 고령비율 계수의 맞바꿈 (원래 변수, 고령비율 중심화)
- 29-sig.svg : 고령비율 지역 계수의 유의 판정. 보정 전 α 0.05와 da Silva & Fotheringham 보정

연습용 모의 자료의 규칙은 regkit.py 머리말에 있음.
앱 해 보기 수치는 GeoStat 엔진(regression.prepare/run, model "gwr")으로 계산함 (앱과 같은 계산).

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/29.py
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
from mapkit import MapFrame, draw, outline  # noqa: E402
from plotkit import Axes  # noqa: E402
from regkit import app_num, app_p, coefs, diags, fit, fit_gwr, load_dong, load_sim, queen, rng, summ, vary_b2  # noqa: E402
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import fields  # noqa: E402
from geostat_engine.analysis import weights as gw  # noqa: E402

warnings.filterwarnings("ignore")
os.environ["TQDM_DISABLE"] = "1"
OUT = os.path.join(HERE, "..", "fig")
XN = ["고령비율", "온도편차"]


def quiet(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return f(*a, **k)


def gwr_fit(coords, y, X, bw, kernel="bisquare", fixed=False):
    from mgwr.gwr import GWR
    return quiet(GWR(coords, y, X, bw, kernel=kernel, fixed=fixed).fit)


def sel_bw(coords, y, X, criterion="AICc", kernel="bisquare", fixed=False):
    from mgwr.sel_bw import Sel_BW
    return float(quiet(Sel_BW(coords, y, X, kernel=kernel, fixed=fixed).search, criterion=criterion))


# ---------------------------------------------------------------- 손계산
def hand():
    print("[손계산] 1차원 위치 0~5 km의 점 6개, 고정 bisquare 대역폭 3 km")
    pos = np.arange(6.0)
    x = np.arange(1, 7.0)
    y = np.array([1, 2, 3, 5, 7, 9.0])  # 0~2 km는 y = x(기울기 1), 3~5 km는 y = 2x − 3(기울기 2)
    for focal in (0, 1, 2, 3, 5):
        d = np.abs(pos - focal)
        w = np.where(d < 3, (1 - (d / 3) ** 2) ** 2, 0)
        X = np.c_[np.ones(6), x]
        Wm = np.diag(w)
        b = np.linalg.solve(X.T @ Wm @ X, X.T @ Wm @ y)
        xm = (w * x).sum() / w.sum()
        ym = (w * y).sum() / w.sum()
        print(f"  초점 {focal} km: 가중치 {np.round(w, 3).tolist()}, 가중평균 x̄ {xm:.3f}, ȳ {ym:.3f}, "
              f"Σw(x−x̄)(y−ȳ) {(w * (x - xm) * (y - ym)).sum():.3f}, Σw(x−x̄)² {(w * (x - xm) ** 2).sum():.3f} → 절편 {b[0]:.3f}, 기울기 {b[1]:.3f}")
    print("  bisquare 가중치: d=1 → (1 − 1/9)² = 64/81 = 0.790, d=2 → (1 − 4/9)² = 25/81 = 0.309")


# ---------------------------------------------------------------- 본문 수치
def numbers():
    sim = load_sim()
    W = queen(sim)
    coords, _ = gw._metric_points(sim)
    X = sim[XN].to_numpy()
    true = vary_b2(sim["X_km"], sim["Y_km"])
    print(f"[0] 설명변수 상관(전역) {np.corrcoef(X.T)[0, 1]:.3f}, 고령비율 평균 {X[:, 0].mean():.3f}, 참 온도편차 계수 {true.min():.3f}~{true.max():.3f}")
    R = {}
    for yv in ("Y_변이", "Y_독립"):
        o, _ = fit(sim, "ols", yv, XN, W)
        rep, cols = fit_gwr(sim, "gwr", yv, XN, W)
        R[yv] = (rep, cols)
        sm = summ(rep)
        print(f"[1] {yv} GWR(앱 기본: bisquare·적응·AICc): " + ", ".join(f"{k} {app_num(v) if not isinstance(v, str) else v}" for k, v in sm.items()))
        mi = diags(o)["잔차 Moran's I"]
        print(f"    OLS AICc {app_num(o['fit']['aicc'], 6)}, OLS 잔차 I {app_num(mi['value'])} (p {app_p(mi['p'])})")
        for r in rep["local"]:
            print(f"    지역 계수 {r['name']}: 대역폭 {r['bandwidth']}, 평균 {app_num(r['mean'])}, 최소 {app_num(r['min'])}, 중앙값 {app_num(r['median'])}, "
                  f"최대 {app_num(r['max'])}, 유의% {app_num(r['pct_significant'])}")
        for d in rep["diagnostics"]:
            print(f"    진단 {d['name']}: {app_num(d['value'])} (p {app_p(d['p'])})")
        b2 = cols["B_온도편차"]
        if yv == "Y_변이":
            print(f"    온도편차 계수와 참 계수: 상관 {np.corrcoef(b2, true)[0, 1]:.3f}, RMSE {np.sqrt(np.mean((b2 - true) ** 2)):.3f}; "
                  f"고령비율 계수 {cols['B_고령비율'].min():.3f}~{cols['B_고령비율'].max():.3f} (참 0.3), 상수 {cols['B_CONST'].min():.3f}~{cols['B_CONST'].max():.3f} (참 5)")
            print(f"    지역 R² {cols['R2'].min():.3f}~{cols['R2'].max():.3f}")
    # 커널·기준·고정/적응
    y = sim[["Y_변이"]].to_numpy()
    print("[2] Y_변이 대역폭 선택 비교")
    variants = [("bisquare 적응 AICc", dict()), ("bisquare 적응 AIC", dict(criterion="AIC")), ("bisquare 적응 BIC", dict(criterion="BIC")),
                ("bisquare 적응 CV", dict(criterion="CV")), ("gaussian 적응 AICc", dict(kernel="gaussian")),
                ("exponential 적응 AICc", dict(kernel="exponential")), ("bisquare 고정 AICc", dict(fixed=True))]
    VAR = []
    for name, kw in variants:
        bw = sel_bw(coords, y, X, **kw)
        g = gwr_fit(coords, y, X, bw, kernel=kw.get("kernel", "bisquare"), fixed=kw.get("fixed", False))
        b2 = g.params[:, 2]
        VAR.append((name, bw, g.ENP, g.aicc, np.corrcoef(b2, true)[0, 1]))
        print(f"  {name}: 대역폭 {bw:,.1f}, ENP {g.ENP:.2f}, AICc {g.aicc:.2f}, 온도편차 계수 {b2.min():.3f}~{b2.max():.3f}, 참값과 상관 {np.corrcoef(b2, true)[0, 1]:.3f}")
    # 대역폭 프로필
    prof = {}
    for yv in ("Y_변이", "Y_독립"):
        yy = sim[[yv]].to_numpy()
        bws = np.arange(20, 150)
        prof[yv] = (bws, np.array([gwr_fit(coords, yy, X, b).aicc for b in bws]))
        a = prof[yv][1]
        print(f"[3] {yv} AICc 프로필: 최소 {bws[a.argmin()]} ({a.min():.2f}), 대역폭 20 {a[0]:.2f}, 30 {a[10]:.2f}, 149 {a[-1]:.2f}")
    # 거짓 변이: Y_독립을 작은 대역폭으로
    false = {}
    for bw in (20, 30, 50):
        rep, cols = fit_gwr(sim, "gwr", "Y_독립", XN, W, bandwidth=bw)
        false[bw] = cols
        lr = {r["name"]: r for r in rep["local"]}
        print(f"[4] Y_독립 대역폭 {bw} 지정: AICc {app_num(summ(rep)['AICc'], 6)}, ENP {app_num(summ(rep)['유효 모수 수 (ENP)'])}, "
              f"온도편차 {app_num(lr['온도편차']['min'])}~{app_num(lr['온도편차']['max'])} 유의% {app_num(lr['온도편차']['pct_significant'])}, "
              f"고령비율 {app_num(lr['고령비율']['min'])}~{app_num(lr['고령비율']['max'])} 유의% {app_num(lr['고령비율']['pct_significant'])}, 상수 {app_num(lr['상수']['min'])}~{app_num(lr['상수']['max'])}")
    return sim, W, coords, X, true, R, VAR, prof, false


def collinearity(sim, coords, X):
    print("[5] 지역 다중공선성과 계수 맞바꿈 (Y_변이, 대역폭 76)")
    y = sim[["Y_변이"]].to_numpy()
    g = gwr_fit(coords, y, X, 76)
    corr, vif, cn, vdp = g.local_collinearity()
    P = g.params
    print(f"  지역 상관(고령비율, 온도편차) {corr.min():.3f}~{corr.max():.3f}, 지역 VIF 최대 {vif.max():.2f}, 지역 조건수 {cn.min():.1f}~{cn.max():.1f} (중앙값 {np.median(cn):.1f})")
    print(f"  지역 계수끼리의 상관: 상수-고령비율 {np.corrcoef(P[:, 0], P[:, 1])[0, 1]:.3f}, 상수-온도편차 {np.corrcoef(P[:, 0], P[:, 2])[0, 1]:.3f}, "
          f"고령비율-온도편차 {np.corrcoef(P[:, 1], P[:, 2])[0, 1]:.3f}")
    xm = X[:, 0].mean()
    Xc = np.c_[X[:, 0] - xm, X[:, 1]]
    bwc = sel_bw(coords, y, Xc)
    gc = gwr_fit(coords, y, Xc, bwc)
    Pc = gc.params
    print(f"  고령비율 중심화(평균 {xm:.3f} 뺌): 대역폭 {bwc:.0f}, 상수 {Pc[:, 0].min():.3f}~{Pc[:, 0].max():.3f} (참 5 + 0.3×{xm:.2f} = {5 + 0.3 * xm:.3f}), "
          f"상수-고령비율 상관 {np.corrcoef(Pc[:, 0], Pc[:, 1])[0, 1]:.3f}, 고령비율 {Pc[:, 1].min():.3f}~{Pc[:, 1].max():.3f}, "
          f"온도편차 계수 동일? {np.allclose(Pc[:, 2], P[:, 2])}")
    return P, Pc, xm


def significance(sim, coords, X, cols):
    print("[6] 다중검정 보정 (Y_변이, 대역폭 76)")
    y = sim[["Y_변이"]].to_numpy()
    g = gwr_fit(coords, y, X, 76)
    a_adj = g.adj_alpha[1]
    tcrit = stats.t.ppf(1 - a_adj / 2, len(y) - 1)
    t0 = stats.t.ppf(1 - 0.05 / 2, len(y) - 1)
    T = g.tvalues
    unc = (np.abs(T) > t0).mean(0) * 100
    cor = (np.abs(T) > tcrit).mean(0) * 100
    print(f"  k {g.k}, ENP {g.ENP:.3f} → 보정 α = 0.05 × {g.k} / {g.ENP:.3f} = {a_adj:.5f}, 임계 t {tcrit:.3f} (보정 전 {t0:.3f})")
    print(f"  유의 비율(상수, 고령비율, 온도편차): 보정 전 {np.round(unc, 1).tolist()}, 보정 후 {np.round(cor, 1).tolist()}")
    print(f"  앱 SIG 열(고령비율) 비율 {cols['SIG_고령비율'].mean() * 100:.1f}% = 보정 전과 같음? {np.isclose(cols['SIG_고령비율'].mean() * 100, unc[1])}")
    # 앱 계산 필드로 보정 판정
    s = sim.copy()
    s["G1_T_고령비율"] = cols["T_고령비율"]
    s["보정유의"] = fields.evaluate(s, f"(abs(`G1_T_고령비율`) > {tcrit:.3f}) * 1")
    print(f"  계산 필드 (abs(`G1_T_고령비율`) > {tcrit:.3f}) * 1 → 합계 {int(s['보정유의'].sum())}개 동")
    return g, tcrit, t0


def variability(sim, coords, X, R=99):
    """계수 변이의 몬테카를로 검정 (좌표를 뒤섞어 대역폭 선택과 GWR을 다시 함, 검정통계량 = 지역 계수의 표준편차)"""
    print(f"[7] 계수 공간 변이의 몬테카를로 검정 (좌표 순열 {R}회)")
    dong = load_dong()
    cd, _ = gw._metric_points(dong)
    out = {}
    for name, df, cc in (("Y_변이", sim, coords), ("Y_독립", sim, coords), ("출동률", dong, cd)):
        y = df[[name]].to_numpy()
        XX = df[XN].to_numpy()
        bw = sel_bw(cc, y, XX)
        sd0 = gwr_fit(cc, y, XX, bw).params.std(0)
        r = rng(f"gwr_mc_{name}")
        ge = np.zeros(3)
        for _ in range(R):
            p = r.permutation(len(y))
            c2 = cc[p]
            b2 = sel_bw(c2, y, XX)
            ge += gwr_fit(c2, y, XX, b2).params.std(0) >= sd0
        pv = (ge + 1) / (R + 1)
        out[name] = (bw, sd0, pv)
        print(f"  {name}: 대역폭 {bw:.0f}, 지역 계수 표준편차(상수, 고령비율, 온도편차) {np.round(sd0, 4).tolist()}, 유사 p {np.round(pv, 3).tolist()}")
    return out


def dispatch():
    print("[8] 한빛시 출동률")
    dong = load_dong()
    Wd = queen(dong)
    o, _ = fit(dong, "ols", "출동률", XN, Wd)
    rep, cols = fit_gwr(dong, "gwr", "출동률", XN, Wd)
    sm = summ(rep)
    print(f"  OLS: AICc {app_num(o['fit']['aicc'], 6)}, R² {app_num(summ(o)['R²'])}, 온도편차 {app_num(coefs(o)['온도편차']['coef'])}")
    print("  GWR: " + ", ".join(f"{k} {app_num(v) if not isinstance(v, str) else v}" for k, v in sm.items()) + f", AICc(6자리) {app_num(sm['AICc'], 6)}")
    for r in rep["local"]:
        print(f"    {r['name']}: 평균 {app_num(r['mean'])}, 최소 {app_num(r['min'])}, 최대 {app_num(r['max'])}, 유의% {app_num(r['pct_significant'])}")
    for d in rep["diagnostics"]:
        print(f"    진단 {d['name']}: {app_num(d['value'])} (p {app_p(d['p'])})")


# ---------------------------------------------------------------- 그림
def fig_kernel(sim, coords):
    W_, H = 720, 290
    s = Svg(W_, H, "왼쪽: 세 가지 커널 함수. 거리 d를 대역폭 b로 나눈 값에 따라 가중치가 줄어듦. bisquare는 d = b에서 0이 되고 그 밖은 쓰지 않으며, gaussian과 exponential은 멀리까지 작은 가중치가 남음. "
                   "오른쪽: 적응 대역폭 76개 이웃(bisquare)으로 한 행정동(검은 점)의 계수를 추정할 때 각 동이 받는 가중치. 가까울수록 진하고, 76번째로 가까운 동보다 먼 동(흰색)은 가중치 0임")
    ax = Axes(s, 60, 34, 290, 200, (0, 2), (0, 1.05))
    d = np.linspace(0, 2, 200)
    ks = [("bisquare", np.where(d < 1, (1 - d ** 2) ** 2, 0), "s-bd", None),
          ("gaussian", np.exp(-0.5 * d ** 2), "s-ac", "5 3"), ("exponential", np.exp(-d), "s-ok", "2 2")]
    for name, w, cls, dash in ks:
        ax.curve(d, w, cls=cls, width=2, dash=dash)
    ax.xaxis(ticks=[0, 0.5, 1, 1.5, 2], label="거리 / 대역폭 (d / b)")
    ax.yaxis(ticks=[0, 0.25, 0.5, 0.75, 1], label="가중치")
    y0 = 50
    for name, _, cls, dash in ks:
        s.line(250, y0, 272, y0, cls=cls, width=2, dash=dash)
        s.text(277, y0 + 4, name, size=10, anchor="start")
        y0 += 17
    # 가중치 지도
    i0 = int(np.argmin((sim["X_km"] - 34) ** 2 + (sim["Y_km"] - 455) ** 2))
    dd = np.sqrt(((coords - coords[i0]) ** 2).sum(1))
    b = np.sort(dd)[75]  # 76번째로 가까운 동(자기 포함)까지의 거리 = mgwr 적응 대역폭
    w = np.where(dd < b, (1 - (dd / b) ** 2) ** 2, 0)
    cls = ["f-bg" if v == 0 else f"q{min(4, int(v * 5))}" for v in w]
    fr = MapFrame(sim.total_bounds, 400, 52, 300)
    draw(s, fr, sim.geometry, cls, width=0.3, stroke="s-mu")
    outline(s, fr, sim.union_all(), cls="s-fg", width=1)
    px, py = fr.xy(coords[i0, 0], coords[i0, 1])
    s.circle(px, py, 4, cls="f-fg s-bg", width=1)
    s.text(fr.x + 150, 36, f"적응 대역폭 76개 이웃의 가중치 (이웃 {int((w > 0).sum())}개 > 0)", size=11, weight="600")
    x = 420
    for k, lab in enumerate(["0~0.2", "0.2~0.4", "0.4~0.6", "0.6~0.8", "0.8~1"]):
        s.rect(x, H - 22, 12, 12, cls=f"s-mu q{k}", width=0.5)
        s.text(x + 16, H - 12, lab, size=10, anchor="start")
        x += 60 if k else 52
    s.save(os.path.join(OUT, "29-kernel.svg"))
    print(f"[그림] 가중치 지도 초점 동 {sim['동이름'][i0]} ({sim['구'][i0]}), 대역폭 거리 {b / 1000:.2f} km")


def fig_bw(prof, ols_aicc):
    W_, H = 720, 280
    s = Svg(W_, H, "대역폭(적응, 이웃 수)에 따른 GWR의 AICc. 왼쪽 Y_변이는 이웃 76개에서 가장 작아, 계수가 변하는 자료에 맞는 중간 크기의 대역폭을 고름. 오른쪽 Y_독립(계수가 어디서나 같음)은 대역폭이 클수록 계속 작아져 "
                   "가장 큰 149개에서 최소가 되고, 전역 회귀와 거의 같아짐. 점선은 OLS의 AICc. 대역폭이 작으면 유효 모수가 많아져 AICc가 커짐")
    for k, yv in enumerate(("Y_변이", "Y_독립")):
        bws, a = prof[yv]
        lo, hi = np.floor(a.min() / 10) * 10 - 5, min(a.max(), a.min() + 90)
        ax = Axes(s, 70 + k * 355, 36, 270, 190, (20, 150), (lo, hi))
        sel = a <= hi
        ax.curve(bws[sel], a[sel], cls="s-ac", width=2)
        ax.curve(np.array([20, 150]), np.array([ols_aicc[yv]] * 2), cls="s-mu", width=1.2, dash="4 3")
        j = a.argmin()
        s.circle(float(ax.X(bws[j])), float(ax.Y(a[j])), 4, cls="f-bd s-bg", width=1)
        s.text(float(ax.X(bws[j])) + (6 if k == 0 else -6), float(ax.Y(a[j])) + 16, f"최소 {bws[j]}개 ({a[j]:.1f})", size=10, anchor="start" if k == 0 else "end", cls="f-bd")
        s.text(float(ax.X(150)) - 2, float(ax.Y(ols_aicc[yv])) - 5, f"OLS {ols_aicc[yv]:.1f}", size=9, anchor="end", cls="f-mu")
        ax.xaxis(ticks=[20, 50, 76, 100, 149] if k == 0 else [20, 50, 100, 149], label="대역폭 (이웃 수)")
        ax.yaxis(label="AICc")
        s.text(float(ax.X(85)), 26, yv, size=12, weight="600")
    s.save(os.path.join(OUT, "29-bw.svg"))


def fig_coef(sim, true, R, false):
    W_, H = 720, 262
    g = R["Y_변이"][1]["B_온도편차"]
    f30 = false[30]["B_온도편차"]
    s = Svg(W_, H, f"온도편차 계수 지도. 왼쪽: Y_변이의 참 계수(서쪽 가운데 언덕, 0.8~2.2). 가운데: Y_변이를 GWR(이웃 76개)로 추정한 계수({g.min():.2f}~{g.max():.2f}, 참값과 상관 {np.corrcoef(g, true)[0, 1]:.2f}). "
                   f"언덕의 위치는 찾았지만 꼭대기는 낮고 바닥은 높게 평탄해짐. 오른쪽: 계수가 어디서나 1.5인 Y_독립을 대역폭 30개 이웃으로 강제한 GWR({f30.min():.2f}~{f30.max():.2f}). "
                   "변이가 없는 자료에서도 대역폭이 작으면 그럴듯한 무늬가 생김")
    mw = 220
    bins = np.linspace(0.6, 2.4, 6)[1:-1]
    for k, (v, title) in enumerate(((true, "Y_변이 참 계수"), (g, "Y_변이 GWR (이웃 76)"), (f30, "Y_독립 GWR (이웃 30 지정)"))):
        cls = [f"q{int(np.digitize(t, bins))}" for t in v]
        fr = MapFrame(sim.total_bounds, 15 + k * (mw + 14), 36, mw)
        draw(s, fr, sim.geometry, cls, width=0.3)
        outline(s, fr, sim.union_all(), cls="s-mu", width=0.8)
        s.text(fr.x + mw / 2, 24, title, size=12, weight="600")
    x = 170
    for k, lab in enumerate(["< 0.96", "0.96~1.32", "1.32~1.68", "1.68~2.04", "≥ 2.04"]):
        s.rect(x, H - 22, 12, 12, cls=f"s-mu q{k}", width=0.5)
        s.text(x + 16, H - 12, lab, size=10, anchor="start")
        x += 26 + len(lab) * 7
    s.save(os.path.join(OUT, "29-coef.svg"))


def fig_tradeoff(P, Pc, xm):
    W_, H = 720, 300
    r0 = np.corrcoef(P[:, 0], P[:, 1])[0, 1]
    r1 = np.corrcoef(Pc[:, 0], Pc[:, 1])[0, 1]
    m = lambda v: f"{v:.2f}".replace("-", "−")  # noqa: E731
    s = Svg(W_, H, f"Y_변이 GWR(이웃 76)의 지역 계수 150쌍. 왼쪽: 지역 상수와 지역 고령비율 계수가 서로 반대로 움직임(상관 {m(r0)}). 참값(주황 십자: 상수 5, 고령비율 0.3)은 어디서나 같은데, "
                   f"한쪽이 커지면 다른 쪽이 작아지는 방향으로 함께 흔들림. 오른쪽: 고령비율에서 평균({xm:.1f})을 빼고 적합하면 상수는 평균 고령비율에서의 값이 되어 맞바꿈이 줄어듦(상관 {m(r1)}). 참 상수는 5 + 0.3 × {xm:.1f} = {5 + 0.3 * xm:.2f}")
    for k, (Q, c0, title, r) in enumerate(((P, 5.0, "원래 변수", r0), (Pc, 5 + 0.3 * xm, f"고령비율 중심화 (평균 {xm:.1f} 뺌)", r1))):
        lo, hi = (3, 15) if k == 0 else (10.5, 14)
        ax = Axes(s, 70 + k * 355, 50, 270, 200, (lo, hi), (-0.05, 0.5))
        for a, b in Q[:, :2]:
            s.circle(float(ax.X(a)), float(ax.Y(b)), 2.6, cls="f-ac s-bg", width=0.4)
        X0, Y0 = float(ax.X(c0)), float(ax.Y(0.3))
        s.line(X0 - 7, Y0, X0 + 7, Y0, cls="s-bd", width=2.2)
        s.line(X0, Y0 - 7, X0, Y0 + 7, cls="s-bd", width=2.2)
        ax.xaxis(ticks=[3, 6, 9, 12, 15] if k == 0 else [11, 12, 13, 14], label="지역 상수")
        ax.yaxis(ticks=[0, 0.1, 0.2, 0.3, 0.4, 0.5], label="지역 고령비율 계수")
        s.text(float(ax.X((lo + hi) / 2)), 18, f"{title} · 상관 {m(r)}", size=12, weight="600")
    s.save(os.path.join(OUT, "29-tradeoff.svg"))


def fig_sig(sim, g, tcrit, t0):
    W_, H = 720, 280
    T = g.tvalues[:, 1]
    B = g.params[:, 1]
    u = np.abs(T) > t0
    c = np.abs(T) > tcrit
    s = Svg(W_, H, f"Y_변이 GWR(이웃 76)의 고령비율 지역 계수(참값은 어디서나 0.3). 유의한 동만 계수 크기로 칠하고 나머지는 회색으로 가림. 왼쪽: 보정하지 않은 α 0.05(|t| > {t0:.2f})에서는 "
                   f"{u.mean() * 100:.1f}%가 유의함. 앱의 유의%와 _SIG_ 열이 이 기준임. 오른쪽: da Silva & Fotheringham 보정 α {g.adj_alpha[1]:.4f}(|t| > {tcrit:.2f})에서는 {c.mean() * 100:.1f}%로 줄어듦")
    mw = 300
    bins = [0.1, 0.17, 0.24, 0.31]
    for k, (m, title) in enumerate(((u, f"보정 전 α 0.05 · 유의 {u.mean() * 100:.1f}%"), (c, f"보정 α {g.adj_alpha[1]:.4f} · 유의 {c.mean() * 100:.1f}%"))):
        cls = [f"q{int(np.digitize(b, bins))}" if mm else "f-sf" for b, mm in zip(B, m)]
        fr = MapFrame(sim.total_bounds, 40 + k * (mw + 40), 36, mw)
        draw(s, fr, sim.geometry, cls, width=0.3, stroke="s-mu")
        outline(s, fr, sim.union_all(), cls="s-fg", width=0.8)
        s.text(fr.x + mw / 2, 24, title, size=12, weight="600")
    x = 120
    for k, lab in enumerate(["< 0.10", "0.10~0.17", "0.17~0.24", "0.24~0.31", "≥ 0.31"]):
        s.rect(x, H - 22, 12, 12, cls=f"s-mu q{k}", width=0.5)
        s.text(x + 16, H - 12, lab, size=10, anchor="start")
        x += 26 + len(lab) * 7
    s.rect(x, H - 22, 12, 12, cls="s-mu f-sf", width=0.5)
    s.text(x + 16, H - 12, "유의하지 않음", size=10, anchor="start")
    s.save(os.path.join(OUT, "29-sig.svg"))


if __name__ == "__main__":
    hand()
    sim, W, coords, X, true, R, VAR, prof, false = numbers()
    P, Pc, xm = collinearity(sim, coords, X)
    g, tcrit, t0 = significance(sim, coords, X, R["Y_변이"][1])
    dispatch()
    ols = {yv: fit(sim, "ols", yv, XN, W)[0]["fit"]["aicc"] for yv in ("Y_변이", "Y_독립")}
    fig_kernel(sim, coords)
    fig_bw(prof, ols)
    fig_coef(sim, true, R, false)
    fig_tradeoff(P, Pc, xm)
    fig_sig(sim, g, tcrit, t0)
    if "--skip-mc" not in sys.argv:
        variability(sim, coords, X)
