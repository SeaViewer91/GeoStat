"""30강 그림과 본문 수치.

- 30-bw.svg : 변수별 대역폭. GWR 하나 대 MGWR 변수별 (Y_변이, Y_독립)
- 30-coef.svg : 온도편차·고령비율 계수 지도. 참 계수, GWR, MGWR(원래 단위로 환산)
- 30-rep.svg : 반복 실험. 같은 과정에서 ε만 바꿔 만든 자료 50개에 MGWR을 적합한 변수별 대역폭과 계수 오차(GWR과 비교)

앱 해 보기 수치는 GeoStat 엔진(regression.prepare/run, model "mgwr")으로 계산함 (앱과 같은 계산: 표준화한 변수, 역적합 허용오차 1e-5).

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/30.py           # 반복 실험 포함 (20분쯤)
    cd engine && uv run python ../book/fig-src/30.py --quick   # 반복 실험 결과를 30-rep.npz에서 읽음
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
os.environ["TQDM_DISABLE"] = "1"
from mapkit import MapFrame, draw, outline  # noqa: E402
from plotkit import Axes  # noqa: E402
from regkit import TRUE, app_num, app_p, fit, fit_gwr, load_dong, load_sim, queen, rng, summ, vary_b2  # noqa: E402
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import fields  # noqa: E402
from geostat_engine.analysis import weights as gw  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
CACHE = os.path.join(HERE, "30-rep.npz")
XN = ["고령비율", "온도편차"]
NAMES = ["상수", "고령비율", "온도편차"]


def quiet(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return f(*a, **k)


def mgwr_fit(coords, y, X):
    """앱과 같은 MGWR: 표준화한 y와 X, bisquare 적응 대역폭, AICc, 역적합 허용오차 1e-5"""
    from mgwr.gwr import MGWR
    from mgwr.sel_bw import Sel_BW
    ys = (y - y.mean()) / y.std()
    Xs = (X - X.mean(0)) / X.std(0)
    sel = Sel_BW(coords, ys, Xs, multi=True)
    quiet(sel.search, tol_multi=1e-5)
    res = quiet(MGWR(coords, ys, Xs, sel).fit)
    return np.ravel(sel.bw[0]), res


def gwr_fit(coords, y, X):
    from mgwr.gwr import GWR
    from mgwr.sel_bw import Sel_BW
    bw = float(quiet(Sel_BW(coords, y, X).search))
    return bw, quiet(GWR(coords, y, X, bw).fit)


def to_orig(Pstd, y, X):
    """표준화 계수 → 원래 단위 계수 (기울기만)"""
    return Pstd[:, 1:] * y.std() / X.std(0)


# ---------------------------------------------------------------- 손계산: 역적합
def hand():
    print("[손계산] 역적합(backfitting): 평활 대신 전역 기울기를 쓰면 OLS 해로 다가감")
    x1 = np.array([-1.5, -0.5, 0.5, 1.5])
    x2 = np.array([-1.0, -1.0, 1.0, 1.0])
    y = np.array([-3.0, -1.0, 2.0, 2.0])
    print(f"  x1 {x1.tolist()}, x2 {x2.tolist()}, y {y.tolist()} (모두 평균 0), x1·x2 상관 {np.corrcoef(x1, x2)[0, 1]:.3f}")
    ols = np.linalg.lstsq(np.c_[x1, x2], y, rcond=None)[0]
    b1 = b2 = 0.0
    for it in range(1, 21):
        b1 = (x1 * (y - b2 * x2)).sum() / (x1 ** 2).sum()
        b2 = (x2 * (y - b1 * x1)).sum() / (x2 ** 2).sum()
        rss = ((y - b1 * x1 - b2 * x2) ** 2).sum()
        if it in (1, 2, 3, 5, 10, 20):
            print(f"  반복 {it}: b1 {b1:.4f}, b2 {b2:.4f}, RSS {rss:.4f}")
    print(f"  OLS: b1 {ols[0]:.4f}, b2 {ols[1]:.4f}, RSS {((y - np.c_[x1, x2] @ ols) ** 2).sum():.4f}")
    print(f"  Σx1² {(x1 ** 2).sum()}, Σx2² {(x2 ** 2).sum()}, Σx1y {(x1 * y).sum()}, Σx2y {(x2 * y).sum()}, Σx1x2 {(x1 * x2).sum()}")


# ---------------------------------------------------------------- 본문 수치
def numbers():
    sim = load_sim()
    W = queen(sim)
    coords, _ = gw._metric_points(sim)
    X = sim[XN].to_numpy()
    true = vary_b2(sim["X_km"], sim["Y_km"])
    D = np.sqrt(((coords[:, None, :] - coords[None, :, :]) ** 2).sum(-1))
    Ds = np.sort(D, 1)
    out = {}
    for yv in ("Y_변이", "Y_독립"):
        y = sim[[yv]].to_numpy()
        grep, gcols = fit_gwr(sim, "gwr", yv, XN, W)
        rep, cols = fit_gwr(sim, "mgwr", yv, XN, W)
        sm = summ(rep)
        print(f"[1] {yv} MGWR(앱): " + ", ".join(f"{k} {app_num(v) if not isinstance(v, str) else v}" for k, v in sm.items())
              + f" | AICc(6자리) {app_num(sm['AICc'], 6)}, GWR AICc {app_num(summ(grep)['AICc'], 6)}")
        for r in rep["local"]:
            print(f"    {r['name']}: 대역폭 {r['bandwidth']:.0f} (중앙 거리 {np.median(Ds[:, int(r['bandwidth']) - 1]) / 1000:.2f} km), 평균 {app_num(r['mean'])}, "
                  f"최소 {app_num(r['min'])}, 중앙값 {app_num(r['median'])}, 최대 {app_num(r['max'])}, 유의% {app_num(r['pct_significant'])}")
        for d in rep["diagnostics"]:
            print(f"    진단 {d['name']}: {app_num(d['value'])} (p {app_p(d['p'])})")
        print(f"    안내: {rep['notes']}")
        # mgwr로 직접: 원래 단위, ENP_j, 보정
        bws, res = mgwr_fit(coords, y, X)
        orig = to_orig(res.params, y, X)
        same = np.allclose(res.params[:, 2], cols["B_온도편차"])
        print(f"    직접 계산 대역폭 {bws.tolist()} (앱과 계수 같음 {same}); sd(y) {y.std():.4f}, sd(x) {np.round(X.std(0), 4).tolist()}, "
              f"환산 배수 고령비율 {y.std() / X.std(0)[0]:.4f}, 온도편차 {y.std() / X.std(0)[1]:.4f}")
        print(f"    원래 단위 고령비율 {orig[:, 0].min():.3f}~{orig[:, 0].max():.3f} (평균 {orig[:, 0].mean():.3f}), 온도편차 {orig[:, 1].min():.3f}~{orig[:, 1].max():.3f} (평균 {orig[:, 1].mean():.3f})")
        enp = np.ravel(res.ENP_j)
        aj = np.ravel(res.adj_alpha_j[:, 1])
        tc = np.ravel(res.critical_tval())
        T = res.tvalues
        print(f"    ENP_j {np.round(enp, 3).tolist()} (합 {enp.sum():.3f}), 보정 α_j {np.round(aj, 5).tolist()}, 임계 t {np.round(tc, 3).tolist()}")
        print(f"    유의 비율 보정 전 {np.round((np.abs(T) > stats.t.ppf(0.975, len(y) - 1)).mean(0) * 100, 1).tolist()}, 보정 후 {np.round((np.abs(T) > tc).mean(0) * 100, 1).tolist()}")
        if yv == "Y_변이":
            g2 = gcols["B_온도편차"]
            print(f"    온도편차 계수와 참값: GWR 상관 {np.corrcoef(g2, true)[0, 1]:.3f}, RMSE {np.sqrt(np.mean((g2 - true) ** 2)):.3f} | "
                  f"MGWR 상관 {np.corrcoef(orig[:, 1], true)[0, 1]:.3f}, RMSE {np.sqrt(np.mean((orig[:, 1] - true) ** 2)):.3f}")
            xm = X.mean(0)
            c_true = (TRUE["b0"] + TRUE["b1"] * xm[0] + true * xm[1] - y.mean()) / y.std()
            c_est = cols["B_CONST"]
            print(f"    표준화 모형의 참 상수 = (5 + 0.3×{xm[0]:.3f} + b2(u,v)×{xm[1]:.3f} − ȳ) / sd(y): {c_true.min():.3f}~{c_true.max():.3f}; "
                  f"MGWR 상수 {c_est.min():.3f}~{c_est.max():.3f}, 상관 {np.corrcoef(c_true, c_est)[0, 1]:.3f}")
            g1 = gcols["B_고령비율"]
            print(f"    고령비율 계수와 참값 0.3: GWR {g1.min():.3f}~{g1.max():.3f}, RMSE {np.sqrt(np.mean((g1 - 0.3) ** 2)):.3f} | "
                  f"MGWR RMSE {np.sqrt(np.mean((orig[:, 0] - 0.3) ** 2)):.3f}")
            # 앱 계산 필드로 환산
            s = sim.copy()
            s["M1_B_온도편차"] = cols["B_온도편차"]
            k = y.std() / X.std(0)[1]
            s["M1_온도"] = fields.evaluate(s, f"`M1_B_온도편차` * {k:.4f}")
            print(f"    계산 필드 `M1_B_온도편차` * {k:.4f} → {s['M1_온도'].min():.3f}~{s['M1_온도'].max():.3f}")
        out[yv] = dict(gwr=gcols, mgwr=cols, bws=bws, orig=orig, gbw=float(grep["local"][0]["bandwidth"]), res=res)
    return sim, coords, X, true, out


def dispatch():
    print("[2] 한빛시 출동률")
    dong = load_dong()
    Wd = queen(dong)
    o, _ = fit(dong, "ols", "출동률", XN, Wd)
    rep, cols = fit_gwr(dong, "mgwr", "출동률", XN, Wd)
    sm = summ(rep)
    print(f"  MGWR: AICc {app_num(sm['AICc'], 6)}, ENP {app_num(sm['유효 모수 수 (ENP)'])}, R² {app_num(sm['R²'])} | OLS AICc {app_num(o['fit']['aicc'], 6)}")
    for r in rep["local"]:
        print(f"    {r['name']}: 대역폭 {r['bandwidth']:.0f}, 평균 {app_num(r['mean'])}, 최소 {app_num(r['min'])}, 최대 {app_num(r['max'])}, 유의% {app_num(r['pct_significant'])}")
    y = dong[["출동률"]].to_numpy()
    X = dong[XN].to_numpy()
    print(f"    표준화 계수 → 원래 단위 배수: 고령비율 {y.std() / X[:, 0].std():.4f}, 온도편차 {y.std() / X[:, 1].std():.4f}; "
          f"온도편차 평균 {np.mean(cols['B_온도편차']) * y.std() / X[:, 1].std():.3f}")


# ---------------------------------------------------------------- 반복 실험
def replicate(sim, coords, X, R=50):
    n = len(sim)
    x1, x2 = X[:, 0], X[:, 1]
    true = vary_b2(sim["X_km"], sim["Y_km"])
    dgps = {"Y_변이": TRUE["b0"] + TRUE["b1"] * x1 + true * x2, "Y_독립": TRUE["b0"] + TRUE["b1"] * x1 + TRUE["b2"] * x2}
    res = {}
    for name, mu in dgps.items():
        r = rng(f"mgwr_rep_{name}")
        B = np.zeros((R, 3))
        G = np.zeros(R)
        E = np.zeros((R, 4))  # GWR 고령비율, GWR 온도편차, MGWR 고령비율, MGWR 온도편차 RMSE
        tb2 = true if name == "Y_변이" else np.full(n, TRUE["b2"])
        for k in range(R):
            y = (mu + TRUE["sigma"] * r.standard_normal(n))[:, None]
            gb, g = gwr_fit(coords, y, X)
            mb, m = mgwr_fit(coords, y, X)
            o = to_orig(m.params, y, X)
            G[k] = gb
            B[k] = mb
            E[k] = [np.sqrt(np.mean((g.params[:, 1] - 0.3) ** 2)), np.sqrt(np.mean((g.params[:, 2] - tb2) ** 2)),
                    np.sqrt(np.mean((o[:, 0] - 0.3) ** 2)), np.sqrt(np.mean((o[:, 1] - tb2) ** 2))]
            print(f"    {name} {k + 1}/{R}: GWR {gb:.0f}, MGWR {B[k].tolist()}", flush=True)
        res[name] = (G, B, E)
    np.savez(CACHE, **{f"{k}_{i}": v[i] for k, v in res.items() for i in range(3)})
    return res


def load_rep():
    z = np.load(CACHE)
    return {k: (z[f"{k}_0"], z[f"{k}_1"], z[f"{k}_2"]) for k in ("Y_변이", "Y_독립")}


def rep_summary(res):
    print("[3] 반복 실험 요약 (자료 50개씩)")
    for name, (G, B, E) in res.items():
        print(f"  {name}: GWR 대역폭 중앙값 {np.median(G):.0f} ({G.min():.0f}~{G.max():.0f}), 140 이상 {np.mean(G >= 140) * 100:.0f}%")
        for j, nm in enumerate(NAMES):
            b = B[:, j]
            print(f"    MGWR {nm}: 중앙값 {np.median(b):.0f}, 사분위 {np.percentile(b, 25):.0f}~{np.percentile(b, 75):.0f}, 범위 {b.min():.0f}~{b.max():.0f}, 140 이상 {np.mean(b >= 140) * 100:.0f}%")
        m = E.mean(0)
        print(f"    평균 RMSE: 고령비율 GWR {m[0]:.3f} / MGWR {m[2]:.3f}, 온도편차 GWR {m[1]:.3f} / MGWR {m[3]:.3f}; "
              f"MGWR이 더 작은 비율 고령비율 {np.mean(E[:, 2] < E[:, 0]) * 100:.0f}%, 온도편차 {np.mean(E[:, 3] < E[:, 1]) * 100:.0f}%")


# ---------------------------------------------------------------- 그림
def fig_bw(out):
    W_, H = 720, 250
    s = Svg(W_, H, "변수별 대역폭(적응, 이웃 수). 회색 막대는 GWR이 모든 계수에 쓴 하나의 대역폭, 주황 점은 MGWR이 변수마다 고른 대역폭. 왼쪽 Y_변이(원래 식에서 상수와 고령비율의 계수는 어디서나 같고 온도편차만 변함)에서 "
                   f"MGWR은 온도편차에 가장 좁은 대역폭({out['Y_변이']['bws'][2]:.0f})을 주었지만, 변하지 않는 고령비율({out['Y_변이']['bws'][1]:.0f})을 전역(149)까지 넓히지는 못했음. "
                   f"상수({out['Y_변이']['bws'][0]:.0f})는 변수를 표준화한 모형에서는 실제로 변하는 계수임. 오른쪽 Y_독립(모든 계수가 같음)에서는 세 대역폭이 모두 전역에 가까움")
    for k, yv in enumerate(("Y_변이", "Y_독립")):
        ax = Axes(s, 100 + k * 340, 40, 250, 150, (0, 150), (-0.5, 2.5))
        o = out[yv]
        for j, nm in enumerate(NAMES):
            yy = float(ax.Y(2 - j))
            x0 = float(ax.X(0))
            s.rect(x0, yy - 9, float(ax.X(o["gbw"])) - x0, 18, cls="s-bg f-sf", width=0.5)
            s.circle(float(ax.X(o["bws"][j])), yy, 6, cls="f-bd s-bg", width=1)
            s.text(float(ax.X(o["bws"][j])) + (10 if o["bws"][j] < 130 else -10), yy + 4, f"{o['bws'][j]:.0f}", size=10, anchor="start" if o["bws"][j] < 130 else "end", cls="f-bd")
            s.text(x0 - 8, yy + 4, nm, size=11, anchor="end")
        ax.xaxis(ticks=[0, 50, 100, 150], label="대역폭 (이웃 수)")
        s.text(float(ax.X(75)), 28, f"{yv} · GWR {o['gbw']:.0f}", size=12, weight="600")
    s.save(os.path.join(OUT, "30-bw.svg"))


def fig_coef(sim, true, out):
    W_, H = 720, 470
    g = out["Y_변이"]["gwr"]
    o = out["Y_변이"]["orig"]
    s = Svg(W_, H, f"Y_변이의 지역 계수(원래 단위). 위: 온도편차. 참 계수, GWR(상관 {np.corrcoef(g['B_온도편차'], true)[0, 1]:.2f}), MGWR(상관 {np.corrcoef(o[:, 1], true)[0, 1]:.2f}). "
                   f"MGWR이 언덕의 모양을 더 잘 그림. 아래: 고령비율. 참 계수는 어디서나 0.3이고, GWR은 {g['B_고령비율'].min():.2f}~{g['B_고령비율'].max():.2f}로 크게 흔들리며, "
                   f"MGWR은 {o[:, 0].min():.2f}~{o[:, 0].max():.2f}로 흔들림이 줄었지만 평평하지는 않음")
    mw = 220
    rows = [("온도편차", (true, g["B_온도편차"], o[:, 1]), np.linspace(0.6, 2.4, 6)[1:-1], ["< 0.96", "0.96~1.32", "1.32~1.68", "1.68~2.04", "≥ 2.04"]),
            ("고령비율", (np.full(len(sim), 0.3), g["B_고령비율"], o[:, 0]), np.array([0.1, 0.17, 0.24, 0.31]), ["< 0.10", "0.10~0.17", "0.17~0.24", "0.24~0.31", "≥ 0.31"])]
    for r, (var, vals, bins, labs) in enumerate(rows):
        y0 = 36 + r * 222
        for k, (v, title) in enumerate(zip(vals, ("참 계수", "GWR", "MGWR"))):
            cls = [f"q{int(np.digitize(t, bins))}" for t in v]
            fr = MapFrame(sim.total_bounds, 15 + k * (mw + 14), y0, mw)
            draw(s, fr, sim.geometry, cls, width=0.3)
            outline(s, fr, sim.union_all(), cls="s-mu", width=0.8)
            s.text(fr.x + mw / 2, y0 - 12, f"{var} · {title}", size=12, weight="600")
        x = 170
        for k, lab in enumerate(labs):
            s.rect(x, y0 + 160, 12, 12, cls=f"s-mu q{k}", width=0.5)
            s.text(x + 16, y0 + 170, lab, size=10, anchor="start")
            x += 26 + len(lab) * 7
    s.save(os.path.join(OUT, "30-coef.svg"))


def fig_rep(res):
    W_, H = 720, 300
    s = Svg(W_, H, "반복 실험: 같은 규칙에서 오차 ε만 바꿔 만든 자료 50개에 GWR과 MGWR을 적합해 고른 대역폭(점 하나가 자료 하나). 왼쪽 Y_변이 과정에서 MGWR은 고령비율에 대부분 전역 근처(148)를 주지만 "
                   "가끔 아주 좁게도 고르고, 온도편차에는 중앙값 74의 좁은 대역폭을 줌. 상수는 표준화 모형에서 실제로 변하므로 좁게 나옴. 오른쪽 Y_독립 과정에서는 대부분 전역 근처지만 가끔 좁게 나옴. "
                   "자료 하나에서 고른 대역폭 하나를 과정의 척도로 단정하지 말아야 함")
    for k, name in enumerate(("Y_변이", "Y_독립")):
        G, B, E = res[name]
        ax = Axes(s, 100 + k * 340, 40, 250, 190, (40, 152), (-0.6, 3.6))
        rows = [("GWR (공통)", G)] + [(nm, B[:, j]) for j, nm in enumerate(NAMES)]
        r = rng(f"jitter_{name}")
        for i, (lab, v) in enumerate(rows):
            yy = 3 - i
            jit = r.uniform(-0.25, 0.25, len(v))
            cls = "f-mu" if i == 0 else "f-bd"
            for vv, jj in zip(v, jit):
                s.circle(float(ax.X(vv)), float(ax.Y(yy + jj)), 2.6, cls=f"{cls} s-bg", width=0.4)
            med = np.median(v)
            s.line(float(ax.X(med)), float(ax.Y(yy + 0.38)), float(ax.X(med)), float(ax.Y(yy - 0.38)), cls="s-fg", width=2)
            s.text(float(ax.X(40)) - 8, float(ax.Y(yy)) + 4, lab, size=11, anchor="end")
        ax.xaxis(ticks=[46, 75, 100, 125, 149], label="고른 대역폭 (이웃 수)")
        s.text(float(ax.X(96)), 28, f"{name} 과정 · 자료 {len(G)}개", size=12, weight="600")
    s.text(360, H - 12, "검은 세로선은 중앙값", size=10, cls="f-mu")
    s.save(os.path.join(OUT, "30-rep.svg"))


if __name__ == "__main__":
    hand()
    sim, coords, X, true, out = numbers()
    dispatch()
    fig_bw(out)
    fig_coef(sim, true, out)
    res = load_rep() if "--quick" in sys.argv and os.path.exists(CACHE) else replicate(sim, coords, X)
    rep_summary(res)
    fig_rep(res)
