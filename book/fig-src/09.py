"""9강 그림과 본문 수치.

- 09-coverage.svg : 지표온도 래스터에서 40개 셀을 반경 R 안에서만 뽑을 때 95% 신뢰구간이 참 평균을 포함하는 비율
- 09-typeI.svg : 서로 관계없는 두 변수가 공간적으로 닮았을수록 상관 t검정이 '유의'를 잘못 내는 비율

두 번째 실험은 한빛시 행정동 150개의 퀸 인접 가중치(행 표준화)로 공간 자기회귀(SAR) 과정 x = (I − ρW)⁻¹ε를 만들어 함.
보정은 Clifford, Richardson & Hémon(1989)의 유효 표본 크기를 참 공분산으로 계산한 것(실제 자료에서는 추정해야 함).

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/09.py
"""
import os
import sys
import warnings

import geopandas as gpd
import numpy as np
import rasterio
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from plotkit import Axes  # noqa: E402
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import aggregate as agg  # noqa: E402
from geostat_engine.analysis import esda_ops as eo  # noqa: E402
from geostat_engine.analysis import weights as gw  # noqa: E402

warnings.filterwarnings("ignore")
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "..", "fig")
SEED = 20261001

dong = gpd.read_file(os.path.join(DATA, "hanbit_dong.gpkg"))
events = gpd.read_file(os.path.join(DATA, "hanbit_events.gpkg"))
dong["PT_CNT"] = agg.aggregate(dong, events, stats=[], count=True, density=False).columns["CNT"]
dong["출동률"] = dong["PT_CNT"] / dong["인구"] * 10000
dong["고령비율"] = dong["고령인구"] / dong["인구"] * 100
WQ, _ = gw.build(dong, {"type": "queen"})
WR = eo._row_standardized(WQ)
WM = WR.full()[0]
N = len(dong)

with rasterio.open(os.path.join(DATA, "hanbit_lst.tif")) as src:
    LSTV = src.read(1, masked=True).filled(np.nan).astype(float)
LAND = np.argwhere(~np.isnan(LSTV))
MU = float(np.nanmean(LSTV))


def moran(x):
    z = x - x.mean()
    return N / WM.sum() * (z @ WM @ z) / (z @ z)


# ---------------------------------------------------------------- 수치와 실험
def hand():
    print("[손계산] 서로 닮은 관측 n개의 평균: 모든 쌍의 상관이 ρ이면 n_eff = n / (1 + (n − 1)ρ)")
    for n, rho in ((48, 0.02), (48, 0.1), (48, 0.3), (150, 0.1)):
        print(f"  n = {n}, ρ = {rho}: n_eff = {n / (1 + (n - 1) * rho):.1f}")


def coverage_experiment():
    print("[1] 40개 셀을 반경 R 안에서만 뽑을 때 95% t 신뢰구간이 참 평균을 포함하는 비율 (각 1,500번)")
    rng = np.random.default_rng(SEED)
    n = 40
    tq = stats.t.ppf(0.975, n - 1)

    def run(sampler, reps=1500):
        hit, width = 0, []
        for _ in range(reps):
            s = sampler()
            h = tq * s.std(ddof=1) / np.sqrt(n)
            hit += abs(s.mean() - MU) <= h
            width.append(2 * h)
        return hit / reps, float(np.mean(width))

    def rand():
        idx = LAND[rng.integers(0, len(LAND), n)]
        return LSTV[idx[:, 0], idx[:, 1]]

    def disc(R):
        rc = R / 50.0

        def f():
            while True:
                cy, cx = LAND[rng.integers(0, len(LAND))]
                cand = LAND[np.hypot(LAND[:, 0] - cy, LAND[:, 1] - cx) <= rc]
                if len(cand) >= n:
                    idx = cand[rng.choice(len(cand), n, replace=False)]
                    return LSTV[idx[:, 0], idx[:, 1]]
        return f

    res = {}
    c, w = run(rand)
    res["random"] = (c, w)
    print(f"  도시 전체에서 무작위: 포함 {c:.1%}, 평균 구간 폭 {w:.2f}℃")
    for R in (250, 500, 1000, 2000, 4000, 8000, 16000):
        c, w = run(disc(R))
        res[R] = (c, w)
        print(f"  반경 {R:,} m: 포함 {c:.1%}, 평균 구간 폭 {w:.2f}℃")
    for lag in (1, 2, 4, 10, 20, 40, 80):
        a, b = LSTV[:, :-lag].ravel(), LSTV[:, lag:].ravel()
        ok = ~np.isnan(a) & ~np.isnan(b)
        print(f"  지표온도 {lag * 50:,} m 떨어진 셀끼리의 상관 {np.corrcoef(a[ok], b[ok])[0, 1]:.2f}")
    return res


def typeI_experiment():
    print("[2] 서로 독립인 두 변수(각각 SAR 과정)로 상관 t검정(α = 0.05)을 4,000번")
    rng = np.random.default_rng(SEED + 1)
    I_ = np.eye(N)
    C = I_ - np.ones((N, N)) / N
    tcrit = stats.t.ppf(0.975, N - 2)
    rows = []
    for rho in (0.0, 0.2, 0.4, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95):
        A = np.linalg.inv(I_ - rho * WM)
        S = A @ A.T
        d = np.sqrt(np.diag(S))
        R = S / np.outer(d, d)
        neff_mean = N ** 2 / R.sum()
        Sc = C @ S @ C
        neff_r = 1 + np.trace(Sc) ** 2 / np.trace(Sc @ Sc)
        tc = stats.t.ppf(0.975, neff_r - 2)
        both = one = corr = 0
        Is = []
        for _ in range(4000):
            x = A @ rng.standard_normal(N)
            y = A @ rng.standard_normal(N)
            y0 = rng.standard_normal(N)
            r = np.corrcoef(x, y)[0, 1]
            r0 = np.corrcoef(x, y0)[0, 1]
            both += abs(r) * np.sqrt((N - 2) / (1 - r * r)) > tcrit
            one += abs(r0) * np.sqrt((N - 2) / (1 - r0 * r0)) > tcrit
            corr += abs(r) * np.sqrt((neff_r - 2) / (1 - r * r)) > tc
            Is.append(moran(x))
        row = dict(rho=rho, I=float(np.mean(Is)), neff_mean=neff_mean, neff_r=neff_r, both=both / 4000, one=one / 4000, corr=corr / 4000)
        rows.append(row)
        print(f"  ρ = {rho:.2f}: 평균 Moran's I {row['I']:.2f}, 평균의 n_eff {neff_mean:.1f}, 상관의 n_eff {neff_r:.1f}, "
              f"잘못 유의: 둘 다 닮음 {row['both']:.1%}, 한쪽만 닮음 {row['one']:.1%}, n_eff 보정 {row['corr']:.1%}")
    return rows


def pseudo():
    print("[3] 의사반복: 행정동 값을 100 m 격자 셀에 그대로 옮겨 상관을 구하면")
    with rasterio.open(os.path.join(DATA, "hanbit_pop100.tif")) as src:
        p = src.read(1)
        T = src.transform
    iy, ix = np.nonzero(p >= 0)
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(T.c + (ix + 0.5) * T.a, T.f + (iy + 0.5) * T.e), crs=dong.crs)
    j = gpd.sjoin(pts, dong[["출동률", "고령비율", "geometry"]], predicate="within")
    r, pv = stats.pearsonr(j["출동률"], j["고령비율"])
    r2, p2 = stats.pearsonr(dong["출동률"], dong["고령비율"])
    print(f"  행정동 150개: r = {r2:.3f}, p = {p2:.3f}")
    print(f"  셀 {len(j):,}개: r = {r:.3f}, p = {pv:.1e}")
    print(f"  동 하나에 셀이 평균 {len(j) / N:.0f}개 (최소 {j.groupby('index_right').size().min()}, 최대 {j.groupby('index_right').size().max()})")


def real_moran():
    print("[4] 한빛시 변수의 Moran's I (퀸, 앱 시드, 순열 999)")
    for col in ("고령비율", "출동률"):
        r = eo.moran(dong[col], WQ, 999, 123456789)
        print(f"  {col}: I = {r.I:.3f}, 유사 p = {r.p_sim:.3f}")


# ---------------------------------------------------------------- 그림
def fig_coverage(res):
    W_, H = 720, 290
    s = Svg(W_, H, "지표온도 래스터에서 셀 40개를 반경 R 안에서만 뽑아 95% 신뢰구간을 만들 때, 구간이 도시 전체의 참 평균을 포함하는 비율(각 1,500번). "
                   "가까이 모인 표본일수록 구간은 좁아지는데(표) 참값은 더 자주 놓침. 파란 가로선은 도시 전체에서 무작위로 뽑았을 때(95.5%)")
    Rs = [250, 500, 1000, 2000, 4000, 8000, 16000]
    ax = Axes(s, 70, 30, 560, 190, (np.log10(200), np.log10(20000)), (0, 1))
    ax.yaxis(ticks=[0, 0.25, 0.5, 0.75, 1.0], fmt=lambda t: f"{t:.0%}", label="참값을 포함한 비율", grid=True)
    ax.xaxis(ticks=[np.log10(r) for r in Rs], fmt=lambda t: f"{10 ** t / 1000:g} km" if 10 ** t >= 1000 else f"{10 ** t:.0f} m",
             label="표본을 뽑은 반경 R (로그 눈금)")
    rv = res["random"][0]
    ax.curve([np.log10(200), np.log10(20000)], [rv, rv], cls="s-ac", width=1.2)
    s.text(float(ax.X(np.log10(200))) + 4, float(ax.Y(rv)) + 14, f"도시 전체에서 무작위로 40개: {rv:.1%}", size=10, anchor="start", cls="f-ac")
    xs = [np.log10(r) for r in Rs]
    ys = [res[r][0] for r in Rs]
    ax.curve(xs, ys, cls="s-bd", width=2)
    for x, y, r in zip(xs, ys, Rs):
        s.circle(float(ax.X(x)), float(ax.Y(y)), 4, cls="s-fg f-bd", width=0.8)
        s.text(float(ax.X(x)), float(ax.Y(y)) - 9, f"{y:.1%}", size=10)
    s.text(W_ / 2, H - 8, "도시의 크기는 가로 약 29 km, 세로 약 20 km", size=10, cls="f-mu")
    s.save(os.path.join(OUT, "09-coverage.svg"))


def fig_typeI(rows):
    W_, H = 720, 300
    s = Svg(W_, H, "서로 아무 관계가 없는 두 변수로 상관 t검정을 할 때 '유의하다'는 잘못된 결론이 나오는 비율(α = 0.05). 가로축은 변수가 "
                   "이웃끼리 닮은 정도(Moran's I). 두 변수가 모두 닮았으면 잘못된 결론이 급격히 늘고, 한쪽만 닮았으면 5% 그대로임. "
                   "유효 표본 크기로 보정하면 5% 이하로 돌아옴")
    ax = Axes(s, 70, 30, 440, 210, (-0.05, 0.85), (0, 0.7))
    ax.yaxis(ticks=[0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7], fmt=lambda t: f"{t:.0%}", label="잘못 '유의'한 비율", grid=True)
    ax.xaxis(ticks=[0, 0.2, 0.4, 0.6, 0.8], fmt=lambda t: f"{t:.1f}", label="두 변수의 Moran's I (평균)")
    ax.curve([-0.05, 0.85], [0.05, 0.05], cls="s-mu", width=1)
    series = [("both", "s-bd", "f-bd", "두 변수 모두 닮음"), ("one", "s-ac", "f-ac", "한 변수만 닮음"), ("corr", "s-ok", "f-ok", "둘 다 닮음, n_eff로 보정")]
    for key, sc, fc, _ in series:
        xs = [r["I"] for r in rows]
        ys = [r[key] for r in rows]
        ax.curve(xs, ys, cls=sc, width=2)
        for x, y in zip(xs, ys):
            s.circle(float(ax.X(x)), float(ax.Y(y)), 3.2, cls=f"s-bg {fc}", width=0.6)
    ax.vline(0.8116, cls="s-fg", width=1, dash="3 3")
    s.text(float(ax.X(0.8116)) - 4, 44, "고령비율 I = 0.81", size=10, anchor="end")
    lx = 540
    for i, (_, sc, fc, label) in enumerate(series):
        y = 70 + i * 28
        s.line(lx, y, lx + 22, y, cls=sc, width=2)
        s.circle(lx + 11, y, 3.2, cls=f"s-bg {fc}", width=0.6)
        s.text(lx + 30, y + 4, label, size=11, anchor="start")
    s.text(lx, 170, "회색 선: 명목 유의수준 5%", size=10, anchor="start", cls="f-mu")
    s.save(os.path.join(OUT, "09-typeI.svg"))


if __name__ == "__main__":
    hand()
    real_moran()
    pseudo()
    res = coverage_experiment()
    rows = typeI_experiment()
    fig_coverage(res)
    fig_typeI(rows)
