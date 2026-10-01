"""16강 그림과 본문 수치.

- 16-patterns.svg : 실제 출동 1,408건, 같은 수의 완전 공간 무작위(CSR) 점, 인구에 비례해 뿌린 점
- 16-quadrat.svg : 2 km 방격 개수 지도와, 안쪽 방격 개수의 분포를 포아송분포와 비교
- 16-nn.svg : 평균 최근린 거리. CSR 모의 99번, 인구 비례 모의 99번과 관측값

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/16.py
"""
import os
import sys
import warnings

import numpy as np
import shapely
from scipy import stats
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import MapFrame, draw, outline  # noqa: E402
from plotkit import Axes  # noqa: E402
from ppkit import events, nn_dist, pop_grid, sim_csr, sim_weighted, window  # noqa: E402
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import aggregate as agg  # noqa: E402
from geostat_engine.analysis.grid import make_grid  # noqa: E402
from pyproj import CRS as _CRS  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
SEED = 20261016

WIN = window()
EV, P = events()
N = len(P)
AREA = WIN.area / 1e6
LAM = N / AREA
CRS = _CRS.from_epsg(5186)


def hand():
    print("[손계산] 10 km × 10 km, 점 10개, 5 km 방격 4개")
    pts = np.array([[1, 1], [2, 1.5], [1.5, 2.5], [2.5, 2], [3, 1], [7, 8], [8, 7.5], [2, 8], [8, 2], [6, 6]], float)
    q = (pts[:, 0] >= 5).astype(int) + 2 * (pts[:, 1] >= 5).astype(int)
    c = np.bincount(q, minlength=4)
    print(f"  방격 개수(왼쪽 아래, 오른쪽 아래, 왼쪽 위, 오른쪽 위): {c.tolist()}, 평균 {c.mean()}, 분산(n−1) {c.var(ddof=1):.4f}, "
          f"VMR {c.var(ddof=1) / c.mean():.3f}, 카이제곱 {((c - c.mean()) ** 2 / c.mean()).sum():.2f}, p {stats.chi2.sf(((c - c.mean()) ** 2 / c.mean()).sum(), 3):.3f}")
    nn = nn_dist(pts)
    print(f"  최근린 거리 {np.round(nn, 3).tolist()}, 평균 {nn.mean():.3f}, CSR 기댓값 0.5/√(10/100) = {0.5 / np.sqrt(0.1):.3f}, R = {nn.mean() / (0.5 / np.sqrt(0.1)):.3f}")


def numbers():
    print(f"[1] 출동 {N}건, 관찰창 면적 {AREA:.2f} km², 강도 {LAM:.3f}건/km²")
    print(f"  연령대: {EV['연령대'].value_counts().to_dict()}")
    nn = nn_dist(P)
    exp_nn = 0.5 / np.sqrt(LAM / 1e6)
    print(f"[2] 평균 최근린 거리 {nn.mean():.1f} m (중앙값 {np.median(nn):.1f}), CSR 기댓값 {exp_nn:.1f} m, Clark–Evans R {nn.mean() / exp_nn:.3f}")
    rng = np.random.default_rng(SEED)
    pop, _, tr = pop_grid()
    csr = [sim_csr(WIN, N, rng) for _ in range(99)]
    popsim = [sim_weighted(pop, tr, N, rng, WIN) for _ in range(99)]
    m_csr = np.array([nn_dist(Q).mean() for Q in csr])
    m_pop = np.array([nn_dist(Q).mean() for Q in popsim])
    print(f"  CSR 모의 99번: 평균 {m_csr.mean():.1f}, 범위 {m_csr.min():.1f}~{m_csr.max():.1f}")
    print(f"  인구 비례 모의 99번: 평균 {m_pop.mean():.1f}, 범위 {m_pop.min():.1f}~{m_pop.max():.1f}")
    print(f"  관측이 CSR 모의보다 작은 비율 {np.mean(m_csr > nn.mean()):.2f}, 인구 비례보다 작은 비율 {np.mean(m_pop > nn.mean()):.2f}")
    # 경계 근처
    bd = shapely.distance(WIN.boundary, shapely.points(P))
    near = bd < 500
    print(f"[3] 시 경계에서 500 m 안의 점 {near.sum()}개 ({near.mean():.1%}), 그 점들의 평균 최근린 {nn[near].mean():.1f} m, 나머지 {nn[~near].mean():.1f} m")
    nnc = nn_dist(csr[0])
    bdc = shapely.distance(WIN.boundary, shapely.points(csr[0]))
    print(f"  CSR 모의 1번: 경계 500 m 안 평균 최근린 {nnc[bdc < 500].mean():.1f} m, 나머지 {nnc[bdc >= 500].mean():.1f} m")
    bb = shapely.box(*WIN.bounds)
    lb = N / (bb.area / 1e6)
    print(f"  창을 시 경계의 외접 사각형({bb.area / 1e6:.1f} km²)으로 잡으면 강도 {lb:.3f}, R {nn.mean() / (0.5 / np.sqrt(lb / 1e6)):.3f}")
    # 방격
    quad = {}
    for s in (1000, 2000, 4000):
        cells_gdf = make_grid(WIN.bounds, CRS, s, "square", clip=WIN)  # 앱의 격자 만들기와 같음(범위: 행정동, 겹치는 셀만)
        inter = [c.intersection(WIN) for c in cells_gdf.geometry]
        ar = np.array([g.area for g in inter])
        keep = ar > 0
        full = ar >= s * s * 0.999
        cnt = np.asarray(agg.aggregate(cells_gdf, EV, stats=[], count=True, density=False).columns["CNT"])
        E = LAM * ar / 1e6
        chi = ((cnt[keep] - E[keep]) ** 2 / E[keep]).sum()
        df = keep.sum() - 1
        cf = cnt[full]
        vmr = cf.var(ddof=1) / cf.mean()
        print(f"[4] 방격 {s / 1000:.0f} km: 창과 겹치는 칸 {keep.sum()} (격자 {len(cells_gdf)}), 완전히 안쪽 {full.sum()}, 카이제곱 {chi:.1f} (자유도 {df}, p {stats.chi2.sf(chi, df):.2g}); "
              f"안쪽 칸 평균 {cf.mean():.2f}, 분산 {cf.var(ddof=1):.2f}, VMR {vmr:.2f}, 0인 칸 {np.mean(cf == 0):.0%} (포아송이면 {np.exp(-cf.mean()):.1%}), 최대 {cf.max()}")
        # CSR 모의 VMR 범위
        vm = []
        for Q in csr[:99]:
            cq = np.array([shapely.contains_xy(g, Q[:, 0], Q[:, 1]).sum() for g, f in zip(inter, full) if f])
            vm.append(cq.var(ddof=1) / cq.mean())
        print(f"    CSR 모의 VMR 범위 {min(vm):.2f}~{max(vm):.2f}")
        quad[s] = (inter, cnt, keep, full, E)
    return nn, m_csr, m_pop, csr[0], popsim[0], quad


# ---------------------------------------------------------------- 그림
def dots(s, fr, Q, r=0.9, cls="f-fg"):
    for x, y in Q:
        X, Y = fr.xy(x, y)
        s.circle(X, Y, r, cls=cls, width=0)


def fig_patterns(csr, pops):
    W_, H = 720, 260
    s = Svg(W_, H, "왼쪽: 실제 폭염 관련 구급 출동 1,408건. 가운데: 같은 수의 점을 시 안에 완전히 무작위로(CSR) 뿌린 것. 오른쪽: 같은 수의 점을 100 m 격자 "
                   "인구에 비례해 뿌린 것. 실제 출동은 CSR보다 훨씬 몰려 있고, 인구 비례 점과 비슷해 보이지만 더 몰린 곳이 있음")
    mw = 220
    fr = [MapFrame(WIN.bounds, 15 + k * (mw + 13), 40, mw) for k in range(3)]
    for k, (Q, t) in enumerate(((P, "실제 출동"), (csr, "완전 공간 무작위 (CSR)"), (pops, "인구에 비례"))):
        s.text(fr[k].x + mw / 2, 26, t, size=12, weight="600")
        draw(s, fr[k], [WIN], ["f-sf"], width=0.6, stroke="s-mu")
        dots(s, fr[k], Q)
    s.save(os.path.join(OUT, "16-patterns.svg"))


def fig_quadrat(quad):
    inter, cnt, keep, full, E = quad[2000]
    W_, H = 720, 300
    cf = cnt[full]
    s = Svg(W_, H, f"왼쪽: 2 km 방격마다의 출동 건수(시 경계로 잘린 칸 포함). 오른쪽: 시 안에 완전히 들어간 {full.sum()}칸의 건수 분포(막대)와, CSR이라면 기대되는 "
                   f"포아송분포(평균 {cf.mean():.2f}, 선). 0건인 칸이 {(cf == 0).sum()}개({(cf == 0).mean():.0%})이고 50건이 넘는 칸도 {(cf > 50).sum()}개 있어 분산이 평균의 {cf.var(ddof=1) / cf.mean():.0f}배임")
    fr = MapFrame(WIN.bounds, 20, 30, 340)
    q = np.zeros(len(cnt), int)
    cuts = [0, 5, 15, 30, 60]
    lab = ["0~4", "5~14", "15~29", "30~59", "60 이상"]
    for i, c in enumerate(cnt):
        q[i] = sum(c >= t for t in cuts[1:])
    for i, g in enumerate(inter):
        if keep[i]:
            draw(s, fr, [g], [f"q{q[i]}"], width=0.4, stroke="s-mu")
    outline(s, fr, WIN, cls="s-fg", width=1.0)
    x = 20
    for k in range(5):
        s.rect(x, 30 + fr.h + 14, 12, 12, cls=f"s-mu q{k}", width=0.5)
        s.text(x + 16, 30 + fr.h + 24, lab[k], size=10, anchor="start")
        x += 66
    cf = cnt[full]
    edges = np.arange(-0.5, 120.5, 5)
    h = np.histogram(cf, edges)[0]
    ax = Axes(s, 430, 40, 260, 200, (-0.5, 120), (0, max(h.max(), 45) * 1.1))
    s.text(560, 22, f"안쪽 {full.sum()}칸의 건수 분포", size=12, weight="600")
    ax.hist(h, edges, width=0.5)
    ax.xaxis(ticks=[0, 20, 40, 60, 80, 100, 120], label="2 km 칸 하나의 출동 건수")
    ax.yaxis(label="칸 수")
    mu = cf.mean()
    xs = np.arange(0, 121)
    ys = stats.poisson.pmf(xs, mu) * len(cf) * 5  # 폭 5 구간에 맞춤
    ax.curve(xs, ys, cls="s-bd", width=1.6)
    s.text(float(ax.X(mu)) + 30, float(ax.Y(ys.max())) + 4, f"포아송(평균 {mu:.2f})", size=10, anchor="start", cls="f-bd")
    s.save(os.path.join(OUT, "16-quadrat.svg"))


def fig_nn(nn, m_csr, m_pop):
    W_, H = 720, 250
    s = Svg(W_, H, "평균 최근린 거리. 회색 막대는 시 안에 1,408개의 점을 완전 무작위로 뿌린 모의 99번, 파란 막대는 인구에 비례해 뿌린 모의 99번의 값. "
                   f"실제 출동({nn.mean():.0f} m)은 두 모의 어느 것보다도 짧음")
    edges = np.arange(200, 306, 2)
    h1 = np.histogram(m_csr, edges)[0]
    h2 = np.histogram(m_pop, edges)[0]
    ax = Axes(s, 60, 30, 620, 160, (200, 305), (0, max(h1.max(), h2.max()) * 1.3))
    ax.hist(h1, edges, cls="s-bg f-mu", width=0.5)
    ax.hist(h2, edges, cls="s-bg f-ac", width=0.5)
    ax.xaxis(ticks=list(range(200, 301, 20)), label="평균 최근린 거리 (m)")
    ax.yaxis(label="모의 횟수")
    ax.vline(nn.mean(), cls="s-bd", width=2)
    s.text(float(ax.X(nn.mean())) + 4, 44, f"실제 {nn.mean():.0f} m", size=11, anchor="start", cls="f-bd")
    s.text(float(ax.X(m_pop.mean())), 44, "인구 비례", size=11, cls="f-ac")
    s.text(float(ax.X(m_csr.mean())), 44, "CSR", size=11, cls="f-mu")
    s.save(os.path.join(OUT, "16-nn.svg"))


if __name__ == "__main__":
    hand()
    nn, m_csr, m_pop, csr0, pop0, quad = numbers()
    fig_patterns(csr0, pop0)
    fig_quadrat(quad)
    fig_nn(nn, m_csr, m_pop)
