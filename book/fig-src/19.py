"""19강 그림과 본문 수치.

- 19-fit.svg : 공변량 강도 모형(M3)의 추정 강도 지도와, 평활한 잔차(관측 커널 강도 − 모형 강도의 같은 평활) 지도
- 19-env.svg : 보통의 L(r) − r과 모형 모의 99번의 포락선. (가) 인구만의 모형 M1, (나) 공변량 모형 M3, (다) 균질 Thomas 군집 과정 적합 곡선

강도 모형은 100 m 셀마다 출동 수를 포아송 회귀(셀 면적 오프셋)로 적합함. 셀 중심이 시 안이고 지표온도가 있는 셀만 씀.
공변량: log(셀 인구 + 1), 지표온도(셀 평균, 32℃ 기준), 고령비율(인구 격자를 300 m 가우시안으로 평활해 구한 %, 셀 단위)

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/19.py
"""
import os
import sys
import warnings

import geopandas as gpd
import numpy as np
import rasterio
import rasterio.transform as rt
import shapely
from scipy import ndimage
from scipy.optimize import minimize
from scipy.special import gammaln

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import DATA, MapFrame, colorbar, div_rgb, load_dong, outline, png, ramp_rgb  # noqa: E402
from plotkit import Axes  # noqa: E402
from ppkit import events, k_border, l_minus_r, pop_grid, sim_weighted, window  # noqa: E402
from svglib import Svg  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
SEED = 20261019
NSIM = 99
R = np.arange(0, 3001, 50.0)

WIN = window()
EV, P = events()
N = len(P)
POP, ELD, TR = pop_grid()
NY, NX = POP.shape
with rasterio.open(os.path.join(DATA, "hanbit_lst.tif")) as r:
    lst = r.read(1).astype(float)
    lst[lst <= -9000] = np.nan
L100 = np.nanmean(lst.reshape(NY, 2, NX, 2).swapaxes(1, 2).reshape(NY, NX, 4), axis=2)
YY, XX = np.mgrid[0:NY, 0:NX]
CX, CY = (np.array(a) for a in rt.xy(TR, YY.ravel(), XX.ravel()))
USE = shapely.contains_xy(WIN, CX, CY).reshape(NY, NX) & ~np.isnan(L100)
IY = ((TR.f - P[:, 1]) / 100).astype(int)
IX = ((P[:, 0] - TR.c) / 100).astype(int)
SHARE = ndimage.gaussian_filter(ELD, 3) / np.maximum(ndimage.gaussian_filter(POP, 3), 1e-9) * 100


def design(names):
    cols = {"상수": np.ones(USE.sum()), "log(인구+1)": np.log(POP[USE] + 1), "지표온도−32": L100[USE] - 32, "고령비율(%)": SHARE[USE]}
    return np.column_stack([cols[k] for k in names])


def counts(mask=None):
    c = np.zeros((NY, NX))
    m = np.ones(N, bool) if mask is None else mask
    np.add.at(c, (IY[m], IX[m]), 1)
    return c[USE]


def irls(X, y, off):
    b = np.zeros(X.shape[1])
    b[0] = np.log(y.sum() / np.exp(off).sum())
    for _ in range(100):
        eta = X @ b + off
        mu = np.exp(eta)
        z = eta - off + (y - mu) / mu
        XtW = X.T * mu
        nb = np.linalg.solve(XtW @ X, XtW @ z)
        if np.max(np.abs(nb - b)) < 1e-10:
            b = nb
            break
        b = nb
    mu = np.exp(X @ b + off)
    se = np.sqrt(np.diag(np.linalg.inv((X.T * mu) @ X)))
    ll = (y * np.log(np.maximum(mu, 1e-300)) - mu - gammaln(y + 1)).sum()
    return b, se, ll, mu


MODELS = {
    "M0": ["상수"],
    "M1": ["상수", "log(인구+1)"],
    "M2": ["상수", "log(인구+1)", "지표온도−32"],
    "M3": ["상수", "log(인구+1)", "지표온도−32", "고령비율(%)"],
}
OFF = np.log(np.full(USE.sum(), 0.01))   # 셀 면적 0.01 km² → 강도 단위 건/km²


def fit_all():
    print(f"[1] 100 m 셀 {USE.sum()}개({USE.sum() * 0.01:.2f} km²), 셀에 든 출동 {counts().sum():.0f}건 (셀 중심이 바다라 빠진 출동 {N - counts().sum():.0f}건)")
    y = counts()
    fits = {}
    for k, names in MODELS.items():
        b, se, ll, mu = irls(design(names), y, OFF)
        aic = -2 * ll + 2 * len(b)
        fits[k] = (b, se, ll, mu, aic)
        terms = ", ".join(f"{n} {bb:.4f} (SE {s:.4f}, exp {np.exp(bb):.3f})" for n, bb, s in zip(names, b, se))
        print(f"  {k}: 로그우도 {ll:.1f}, AIC {aic:.1f} | {terms}")
    b = fits["M3"][0]
    lam = np.exp(b[0] + b[1] * np.log(101) + b[2] * 2 + b[3] * 20)
    print(f"[손계산] 인구 100명, 지표온도 34℃, 고령비율 20%인 100 m 셀: λ = exp({b[0]:.4f} + {b[1]:.4f}×ln101 + {b[2]:.4f}×2 + {b[3]:.4f}×20) = {lam:.3f}건/km², "
          f"셀의 기대 건수 {lam * 0.01:.4f}")
    lam2 = np.exp(b[0] + b[1] * np.log(201) + b[2] * 2 + b[3] * 20)
    print(f"  인구 200명이면 {lam2:.3f} (비 {lam2 / lam:.3f} = (201/101)^{b[1]:.3f}), 지표온도 1℃ 높으면 ×{np.exp(b[2]):.3f}, 고령비율 10%p 높으면 ×{np.exp(10 * b[3]):.3f}")
    # 과산포: 1 km 블록
    mu = fits["M3"][3]
    lg = np.zeros((NY, NX))
    lg[USE] = mu
    cg = np.zeros((NY, NX))
    cg[USE] = y
    O = cg.reshape(NY // 10, 10, NX // 10, 10).sum((1, 3))
    E = lg.reshape(NY // 10, 10, NX // 10, 10).sum((1, 3))
    ok = E >= 0.5
    pr = (O - E)[ok] / np.sqrt(E[ok])
    print(f"  1 km 블록 {ok.sum()}개의 피어슨 카이제곱 {np.sum(pr ** 2):.1f} (블록 수에 대한 비 {np.sum(pr ** 2) / ok.sum():.2f})")
    return fits


def residual_field(mu, h_cells=5):
    lg = np.zeros((NY, NX))
    lg[USE] = mu
    cg = np.zeros((NY, NX))
    cg[USE] = counts()
    sr = (ndimage.gaussian_filter(cg, h_cells) - ndimage.gaussian_filter(lg, h_cells)) * 100   # 건/km²
    sr = np.where(USE, sr, np.nan)
    dong = load_dong()
    print(f"[2] 평활 잔차(가우시안 {h_cells * 100} m, 건/km²): 범위 {np.nanmin(sr):.2f}~{np.nanmax(sr):.2f}")
    flat = np.argsort(-np.nan_to_num(sr, nan=-99).ravel())
    seen = []
    for f in flat:
        i, j = np.unravel_index(f, sr.shape)
        x, y = CX[f], CY[f]
        nm = dong.loc[dong.contains(shapely.Point(x, y)), "동이름"].values
        nm = nm[0] if len(nm) else "?"
        if all(np.hypot(x - a, y - b) > 2000 for a, b, _ in seen):
            seen.append((x, y, nm))
            print(f"  양의 잔차 봉우리: {nm} ({x:.0f}, {y:.0f}) {sr[i, j]:.2f}")
        if len(seen) >= 4:
            break
    return sr


def envelopes(fits):
    print("[3] 보통 L 함수와 모형 모의 포락선")
    rng = np.random.default_rng(SEED)
    Lo = l_minus_r(k_border(P, WIN, R), R)
    out = {"obs": Lo}
    for k in ("M1", "M3"):
        lam = np.zeros((NY, NX))
        lam[USE] = fits[k][3]
        sims = [sim_weighted(lam, TR, N, rng, WIN) for _ in range(NSIM)]
        Ls = np.array([l_minus_r(k_border(Q, WIN, R), R) for Q in sims])
        above = (Lo > Ls.max(0))[1:]
        below = (Lo < Ls.min(0))[1:]
        print(f"  {k}: " + "; ".join(f"r {r} 관측 {Lo[int(r / 50)]:.0f} (모의 {Ls[:, int(r / 50)].min():.0f}~{Ls[:, int(r / 50)].max():.0f})" for r in (100, 250, 500, 1000, 2000)))
        print(f"    띠 위로 {above.mean():.0%}({R[1:][above].tolist()}), 아래로 {below.mean():.0%} (r 50~3000 m의 {len(above)}개 거리)")
        dev_o = np.nanmax(np.abs(Lo - Ls.mean(0)))
        dev_s = np.nanmax(np.abs(Ls - Ls.mean(0)), axis=1)
        print(f"    전역 검정(최대 절대 편차): 관측 {dev_o:.0f} m, p = {(1 + (dev_s >= dev_o).sum()) / (NSIM + 1):.2f}")
        out[k] = Ls
    return out


def thomas():
    print("[4] 균질 Thomas 군집 과정 최소 대비 적합 (K^0.25, r 0~3 km)")
    K = k_border(P, WIN, R)

    def kth(r, kappa, sig):
        return np.pi * r * r + (1 - np.exp(-r * r / (4 * sig * sig))) / kappa

    m = R > 0

    def contrast(p):
        kappa, sig = np.exp(p)
        return ((K[m] ** 0.25 - kth(R[m], kappa, sig) ** 0.25) ** 2).sum()

    res = minimize(contrast, x0=[np.log(1e-7), np.log(500)], method="Nelder-Mead", options={"maxiter": 5000, "xatol": 1e-8, "fatol": 1e-14})
    kappa, sig = np.exp(res.x)
    print(f"  κ = {kappa * 1e6:.4f}개/km² (시 전체 부모 {kappa * WIN.area:.1f}개), σ = {sig:.0f} m, 부모당 자식 μ = {N / (kappa * WIN.area):.0f}개")
    Lt = l_minus_r(kth(R, kappa, sig), R)
    print(f"  적합 L−r: r 500 {Lt[10]:.0f}, 1000 {Lt[20]:.0f}, 2000 {Lt[40]:.0f} m (관측 {l_minus_r(K, R)[10]:.0f}, {l_minus_r(K, R)[20]:.0f}, {l_minus_r(K, R)[40]:.0f})")
    return Lt, kappa, sig


def holdout():
    print("[5] 6~7월로 적합, 8월 행정동별 건수 예측")
    mon = EV["월"].to_numpy()
    y67, y8 = counts(mon <= 7), counts(mon == 8)
    dong = load_dong()
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(CX, CY), crs=dong.crs)
    j = gpd.sjoin(pts, dong[["geometry"]], predicate="within", how="left")
    did = j["index_right"].fillna(-1).astype(int).to_numpy().reshape(NY, NX)[USE]
    ok = did >= 0
    od = np.bincount(did[ok], weights=y8[ok], minlength=150)
    print(f"  6~7월 {y67.sum():.0f}건, 8월 {y8.sum():.0f}건 (셀에 든 것)")
    res = {}
    for k in ("M0", "M1", "M3"):
        b, _, _, mu = irls(design(MODELS[k]), y67, OFF)
        pred = mu * y8.sum() / y67.sum()
        pdg = np.bincount(did[ok], weights=pred[ok], minlength=150)
        plik = (od * np.log(np.maximum(pdg, 1e-12)) - pdg - gammaln(od + 1)).sum()
        res[k] = (plik, np.corrcoef(pdg, od)[0, 1], np.abs(pdg - od).mean())
        print(f"  {k}: 예측 로그우도 {plik:.1f}, 상관 {res[k][1]:.3f}, 평균 절대 오차 {res[k][2]:.2f}건")
    return res


# ---------------------------------------------------------------- 그림
def place(s, fr, arr, fn, lo, hi):
    x0, y1 = TR.c, TR.f
    x1, y0 = TR.c + NX * 100, TR.f - NY * 100
    X0, Y0 = fr.xy(x0, y1)
    X1, Y1 = fr.xy(x1, y0)
    s.image_png(X0, Y0, X1 - X0, Y1 - Y0, png(fn(arr, lo, hi), int(2 * (X1 - X0))))


def fig_fit(fits, sr):
    W_, H = 720, 320
    s = Svg(W_, H, "왼쪽: 공변량 강도 모형 M3(인구, 지표온도, 고령비율)으로 추정한 출동 강도(건/km², 100 m 셀, 로그 눈금). 오른쪽: 평활한 잔차(관측 출동과 모형 강도를 "
                   "같은 500 m 가우시안으로 평활해 뺀 값, 건/km²). 붉은 곳은 모형이 예측한 것보다 출동이 많은 곳으로, 마루구 원도심(마루16동 부근)에 가장 크게 남고 가람·누리구에 작은 봉우리가 있음. 푸른 곳은 모형이 과대 예측한 곳임")
    mw = 330
    fr = [MapFrame(WIN.bounds, 20 + k * (mw + 20), 40, mw) for k in range(2)]
    s.text(fr[0].x + mw / 2, 26, "모형 M3의 강도 (로그 눈금)", size=12, weight="600")
    s.text(fr[1].x + mw / 2, 26, "평활 잔차", size=12, weight="600")
    lam = np.full((NY, NX), np.nan)
    lam[USE] = fits["M3"][3] / 0.01
    place(s, fr[0], np.log10(np.maximum(lam, 0.01)), ramp_rgb, -1, 2)
    place(s, fr[1], np.clip(sr, -8, 8), div_rgb, -8, 8)
    for f in fr:
        outline(s, f, WIN, cls="s-mu", width=0.8)
    y = 40 + fr[0].h + 22
    colorbar(s, fr[0].x + 40, y, 250, -1, 2, [-1, 0, 1, 2], "강도 (건/km²)", fmt=lambda t: f"{10 ** t:g}")
    colorbar(s, fr[1].x + 40, y, 250, -8, 8, [-8, -4, 0, 4, 8], "관측 − 모형 (건/km²)", diverging=True)
    s.save(os.path.join(OUT, "19-fit.svg"))


def fig_env(env, Lt):
    W_, H = 720, 280
    s = Svg(W_, H, "보통의 L(r) − r(빨간 선)과 모형에서 모의한 99번의 범위(회색 띠). 왼쪽: 인구만 넣은 모형 M1도 거의 모든 거리에서 띠 안에 듦(60개 거리 가운데 2곳에서 살짝 벗어남). "
                   "가운데: 인구·지표온도·고령비율을 넣은 M3는 모든 거리에서 띠 안에 듦. 오른쪽: 강도가 일정하다고 보고 적합한 Thomas 군집 과정의 L(r) − r(점선)도 "
                   "관측과 거의 겹침. 같은 K 함수를 전혀 다른 두 모형이 설명함")
    Lo = env["obs"]
    for k, (key, t) in enumerate((("M1", "M1: 인구"), ("M3", "M3: 인구 + 지표온도 + 고령비율"), (None, "균질 Thomas 군집 과정"))):
        x0 = 60 + k * 225
        ax = Axes(s, x0, 52, 185, 170, (0, 3000), (-100, 2100))
        s.text(x0 + 92, 26, t, size=11, weight="600")
        if key:
            Ls = env[key]
            lo, hi = Ls.min(0), Ls.max(0)
            pts = [(float(ax.X(a)), float(ax.Y(v))) for a, v in zip(R, hi)] + [(float(ax.X(a)), float(ax.Y(v))) for a, v in zip(R[::-1], lo[::-1])]
            s.polygon(pts, cls="s-bg f-sf", width=0)
        else:
            ax.curve(R, Lt, cls="s-ac", width=1.8, dash="5 3")
        ax.curve(R, Lo, cls="s-bd", width=1.8)
        ax.xaxis(ticks=[0, 1000, 2000, 3000], label="거리 r (m)")
        ax.yaxis(ticks=[0, 1000, 2000], label="L(r) − r (m)" if k == 0 else None)
    s.save(os.path.join(OUT, "19-env.svg"))


if __name__ == "__main__":
    fits = fit_all()
    sr = residual_field(fits["M3"][3])
    env = envelopes(fits)
    Lt, kappa, sig = thomas()
    holdout()
    fig_fit(fits, sr)
    fig_env(env, Lt)
