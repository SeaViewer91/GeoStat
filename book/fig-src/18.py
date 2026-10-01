"""18강 그림과 본문 수치.

- 18-gfl.svg : G(최근린 거리), F(빈 공간 거리), L(r) − r 함수와 CSR 모의 99번의 포락선
- 18-inhom.svg : 불균질 L 함수. 강도를 (가) 인구 비례, (나) 출동 커널 밀도(865 m)로 둘 때. 각각 같은 강도의 불균질 포아송 모의 99번 포락선
- 18-cross.svg : 65세 이상과 미만의 K 함수 차이 K₆₅(r) − K₆₅미만(r)와 무작위 표지 99번 포락선

경계 보정은 모두 경계(border) 보정: 거리 r을 볼 때 시 경계에서 r보다 가까운 점은 중심점으로 쓰지 않음(이웃으로는 씀).

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/18.py
"""
import os
import sys
import warnings

import numpy as np
import shapely
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from plotkit import Axes  # noqa: E402
from ppkit import edge_mass, events, grid, kmat, pop_grid, sim_csr, sim_weighted, window  # noqa: E402
from svglib import Svg  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
SEED = 20261018
NSIM = 99
R = np.arange(0, 3001, 50.0)

WIN = window()
AREA = WIN.area
BOUND = WIN.boundary
EV, P = events()
N = len(P)
OLD = (EV["연령대"] == "65+").to_numpy()


def bdist(Q):
    return shapely.distance(BOUND, shapely.points(Q))


def pair_d(Q, rmax=R[-1]):
    pairs = cKDTree(Q).query_pairs(rmax, output_type="ndarray")
    d = np.hypot(*(Q[pairs[:, 0]] - Q[pairs[:, 1]]).T)
    return pairs, d


def k_border(Q, b=None, lam_w=None):
    """경계 보정 K. lam_w가 있으면 불균질 K(점마다 1/λ 가중)"""
    n = len(Q)
    b = bdist(Q) if b is None else b
    pairs, d = pair_d(Q)
    i, j = pairs[:, 0], pairs[:, 1]
    out = np.zeros(len(R))
    if lam_w is None:
        lam = n / AREA
        for k, r in enumerate(R):
            if r == 0:
                continue
            m = d <= r
            cnt = (m & (b[i] >= r)).sum() + (m & (b[j] >= r)).sum()  # 순서쌍(i 중심, j 중심)
            nb = (b >= r).sum()
            out[k] = cnt / (lam * nb) if nb else np.nan
    else:
        w = 1 / lam_w
        for k, r in enumerate(R):
            if r == 0:
                continue
            m = d <= r
            s = (w[i] * w[j] * (m & (b[i] >= r))).sum() + (w[i] * w[j] * (m & (b[j] >= r))).sum()
            den = w[b >= r].sum()
            out[k] = s / den if den else np.nan
    return out


def L_minus_r(K):
    return np.sqrt(np.maximum(K, 0) / np.pi) - R


def g_func(Q, b=None):
    """최근린 거리 분포 G(r), 경계 보정(최근린 거리 ≤ 경계 거리인 점만)"""
    b = bdist(Q) if b is None else b
    d, _ = cKDTree(Q).query(Q, k=2)
    nn = d[:, 1]
    ok = nn <= b
    return np.array([(nn[ok] <= r).mean() if r > 0 else 0 for r in R])


def f_func(Q, test, tb):
    """빈 공간 거리 분포 F(r): 격자 시험점에서 가장 가까운 점까지의 거리. 경계 보정"""
    d, _ = cKDTree(Q).query(test, k=1)
    ok = d <= tb
    return np.array([(d[ok] <= r).mean() if r > 0 else 0 for r in R])


def hand():
    print("[손계산] 16강의 점 10개 (10 km × 10 km), r = 1.2 km, 경계 보정 없음")
    pts = np.array([[1, 1], [2, 1.5], [1.5, 2.5], [2.5, 2], [3, 1], [7, 8], [8, 7.5], [2, 8], [8, 2], [6, 6]], float)
    D = np.hypot(*(pts[:, None] - pts[None]).T)
    np.fill_diagonal(D, np.inf)
    c = (D <= 1.2).sum()
    labels = "ABCDEFGHIJ"
    close = [(labels[a], labels[b], round(D[a, b], 3)) for a in range(10) for b in range(a + 1, 10) if D[a, b] <= 1.2]
    K = 100 / (10 * 9) * c
    print(f"  1.2 km 안의 쌍(순서 없이) {c // 2}개: {close}")
    print(f"  K = |W| / (n(n−1)) × 순서쌍 수 = 100/90 × {c} = {K:.2f} km², CSR이면 πr² = {np.pi * 1.44:.2f}, L = √(K/π) = {np.sqrt(K / np.pi):.3f} km")


def numbers():
    rng = np.random.default_rng(SEED)
    b = bdist(P)
    test, _, _ = grid(WIN, 250.0)
    tb = bdist(test)
    print(f"[1] 출동 {N}건, 시 경계에서 1 km 안의 점 {(b < 1000).sum()}개, 3 km 안 {(b < 3000).sum()}개")
    Kobs = k_border(P, b)
    Gobs = g_func(P, b)
    Fobs = f_func(P, test, tb)
    sims = [sim_csr(WIN, N, rng) for _ in range(NSIM)]
    Ks = np.array([k_border(Q) for Q in sims])
    Gs = np.array([g_func(Q) for Q in sims])
    Fs = np.array([f_func(Q, test, tb) for Q in sims])
    for r in (100, 200, 500, 1000, 2000, 3000):
        k = int(r / 50)
        print(f"  r {r} m: K {Kobs[k] / 1e6:.3f} km² (CSR πr² {np.pi * r * r / 1e6:.3f}, 모의 {Ks[:, k].min() / 1e6:.3f}~{Ks[:, k].max() / 1e6:.3f}), "
              f"L−r {L_minus_r(Kobs)[k]:.0f} m, G {Gobs[k]:.3f} (모의 {Gs[:, k].min():.3f}~{Gs[:, k].max():.3f}), F {Fobs[k]:.3f} (모의 {Fs[:, k].min():.3f}~{Fs[:, k].max():.3f})")
    k = int(1000 / 50)
    print(f"  r 1 km에서 점 하나 주변의 평균 점 수: 관측 λK = {N / AREA * Kobs[k]:.1f}, CSR {N / AREA * np.pi * 1e6:.1f}")
    Jobs = (1 - Gobs) / np.maximum(1 - Fobs, 1e-9)
    print(f"  J(200 m) = (1 − G)/(1 − F) = {Jobs[4]:.3f}, J(500) {Jobs[10]:.3f}")
    # 전역 포락선 검정(최대 편차): r 0~3 km
    Lo = L_minus_r(Kobs)
    Lsim = np.array([L_minus_r(k) for k in Ks])
    Lmean = Lsim.mean(0)
    dev_obs = np.nanmax(np.abs(Lo - Lmean))
    dev_sim = np.nanmax(np.abs(Lsim - Lmean), axis=1)
    print(f"  최대 편차 검정: 관측 {dev_obs:.0f} m, 모의 최대 {dev_sim.max():.0f} m, p = {(1 + (dev_sim >= dev_obs).sum()) / (NSIM + 1):.2f}")
    return Kobs, Ks, Gobs, Gs, Fobs, Fs


def inhom():
    print("[2] 불균질 K")
    rng = np.random.default_rng(SEED + 1)
    b = bdist(P)
    pop, _, tr = pop_grid()
    # (가) 인구 비례 불균질 포아송을 귀무가설로 한 모의 검정. 통계량은 보통의 K(1/λ 가중 없음)
    zero = (pop[((tr.f - P[:, 1]) / 100).astype(int), ((P[:, 0] - tr.c) / 100).astype(int)] == 0).sum()
    print(f"  (가) 인구 비례: 인구가 0인 100 m 셀에 떨어진 출동 {zero}건 (1/λ 가중을 쓰는 불균질 K는 이런 점의 가중이 폭주함)")
    Ka = k_border(P, b)
    sims = [sim_weighted(pop, tr, N, rng, WIN) for _ in range(NSIM)]
    Kas = np.array([k_border(Q) for Q in sims])
    # 참고: 인구를 평활한 강도로 1/λ 가중 불균질 K를 구하면 평활 폭에 따라 결과가 크게 달라짐
    from scipy import ndimage

    for sig in (3, 5, 10):
        sf = ndimage.gaussian_filter(pop, sig)
        lam_cell = sf / sf[pop > 0].sum() * N / 1e4
        lam_at = lam_cell[((tr.f - P[:, 1]) / 100).astype(int), ((P[:, 0] - tr.c) / 100).astype(int)]
        Kw = k_border(P, b, np.maximum(lam_at, 1e-12))
        Lw = L_minus_r(Kw)
        print(f"    참고: 인구를 {sig * 100} m로 평활한 강도의 1/λ 가중 불균질 L−r: r 250 {Lw[5]:.0f}, 500 {Lw[10]:.0f}, 1000 {Lw[20]:.0f} m, "
              f"출동 지점 강도 최소 {lam_at.min() * 1e6:.4f}건/km²")
    # (나) 출동 커널 밀도 865 m (한 점 빼기)
    h = 865.0
    G, _, _ = grid(WIN, 200.0)

    def lam_kde_at(Q, own=True):
        Kq = kmat(Q, Q, h)
        s = np.asarray(Kq.sum(0)).ravel()
        if own:
            s = s - 1 / (2 * np.pi * h * h)   # 자기 자신 빼기
        e = edge_mass(G, 200.0 * 200.0, h, at=Q)
        return np.maximum(s / e, 1e-12)

    Kb = k_border(P, b, lam_kde_at(P))
    # 모의: 관측 커널 강도에서 불균질 포아송, 그 모의 자료에서 다시 강도를 추정
    lam_grid = np.asarray(kmat(P, G, h).sum(0)).ravel() / edge_mass(G, 200.0 * 200.0, h)
    x0, y0, x1, y1 = WIN.bounds
    nx, ny = int(np.ceil((x1 - x0) / 200)), int(np.ceil((y1 - y0) / 200))
    arr = np.zeros((ny, nx))
    gi = ((y1 - G[:, 1]) // 200).astype(int)
    gj = ((G[:, 0] - x0) // 200).astype(int)
    arr[gi, gj] = lam_grid
    from rasterio.transform import from_origin
    trk = from_origin(x0, y1, 200, 200)
    simsb = [sim_weighted(arr, trk, N, rng, WIN) for _ in range(NSIM)]
    Kbs = np.array([k_border(Q, None, lam_kde_at(Q)) for Q in simsb])
    for name, Ko, Ksim in (("(가) 보통 K, 인구 비례 모의", Ka, Kas), ("(나) 불균질 K, 커널 865 m", Kb, Kbs)):
        Lo, Ls = L_minus_r(Ko), np.array([L_minus_r(k) for k in Ksim])
        out = [(r, Lo[int(r / 50)], Ls[:, int(r / 50)].min(), Ls[:, int(r / 50)].max()) for r in (100, 250, 500, 1000, 2000)]
        print(f"  {name}: " + "; ".join(f"r {r} L−r {a:.0f} (모의 {lo:.0f}~{hi:.0f})" for r, a, lo, hi in out))
        above = (Lo > Ls.max(0))[1:]
        below = (Lo < Ls.min(0))[1:]
        print(f"    포락선 위로 벗어난 r 구간: {R[1:][above].min() if above.any() else '-'} ~ {R[1:][above].max() if above.any() else '-'} m, 비율 {above.mean():.0%}; "
              f"아래로 {below.mean():.0%}")
    return Ka, Kas, Kb, Kbs


def cross():
    print("[3] 65세 이상 vs 미만: 무작위 표지")
    rng = np.random.default_rng(SEED + 2)
    b = bdist(P)
    pairs, d = pair_d(P)

    def k_sub(mask):
        i, j = pairs[:, 0], pairs[:, 1]
        both = mask[i] & mask[j]
        n = mask.sum()
        lam = n / AREA
        out = np.zeros(len(R))
        for k, r in enumerate(R):
            if r == 0:
                continue
            m = (d <= r) & both
            cnt = (m & (b[i] >= r)).sum() + (m & (b[j] >= r)).sum()
            nb = (b[mask] >= r).sum()
            out[k] = cnt / (lam * nb)
        return out

    D = k_sub(OLD) - k_sub(~OLD)
    sims = np.array([(lambda lab: k_sub(lab) - k_sub(~lab))(rng.permutation(OLD)) for _ in range(NSIM)])
    for r in (250, 500, 1000, 2000, 3000):
        k = int(r / 50)
        print(f"  r {r} m: K65 − K65미만 = {D[k] / 1e6:.3f} km², 무작위 표지 {sims[:, k].min() / 1e6:.3f}~{sims[:, k].max() / 1e6:.3f}")
    above = (D > sims.max(0))[1:]
    below = (D < sims.min(0))[1:]
    print(f"  포락선 위로 벗어난 r: {R[1:][above].min() if above.any() else '-'} ~ {R[1:][above].max() if above.any() else '-'} m, "
          f"아래로 벗어난 r: {R[1:][below].min() if below.any() else '-'} ~ {R[1:][below].max() if below.any() else '-'} m")
    # 각 집단의 평균 최근린·도심 거리
    from ppkit import nn_dist
    c = P.mean(0)
    print(f"  65세 이상 출동의 중심(평균 좌표)까지 거리 중앙값 {np.median(np.hypot(*(P[OLD] - c).T)):.0f} m, 65세 미만 {np.median(np.hypot(*(P[~OLD] - c).T)):.0f} m")
    dev = np.nanmax(np.abs(D - sims.mean(0)) / np.maximum(sims.std(0), 1))
    devs = np.nanmax(np.abs(sims - sims.mean(0)) / np.maximum(sims.std(0), 1), axis=1)
    print(f"  최대 표준화 편차 검정 p = {(1 + (devs >= dev).sum()) / (NSIM + 1):.2f}")
    return D, sims


# ---------------------------------------------------------------- 그림
def env_panel(s, x0, y0, w, h, xs, obs, sims, ylim, title, ylab, ref=None, yticks=None, xlab="거리 r (m)", xticks=(0, 1000, 2000, 3000)):
    ax = Axes(s, x0, y0, w, h, (0, xs[-1]), ylim)
    s.text(x0 + w / 2, y0 - 26, title, size=12, weight="600")
    lo, hi = np.nanmin(sims, 0), np.nanmax(sims, 0)
    pts = [(float(ax.X(a)), float(ax.Y(np.clip(v, *ylim)))) for a, v in zip(xs, hi)] + \
          [(float(ax.X(a)), float(ax.Y(np.clip(v, *ylim)))) for a, v in zip(xs[::-1], lo[::-1])]
    s.polygon(pts, cls="s-bg f-sf", width=0)
    if ref is not None:
        ax.curve(xs, np.clip(ref, *ylim), cls="s-mu", width=1.2, dash="4 3")
    ax.curve(xs, np.clip(obs, *ylim), cls="s-bd", width=2)
    ax.xaxis(ticks=list(xticks), label=xlab)
    ax.yaxis(ticks=yticks, label=ylab)
    return ax


def fig_gfl(Kobs, Ks, Gobs, Gs, Fobs, Fs):
    W_, H = 720, 282
    s = Svg(W_, H, "출동의 거리 함수(빨간 선)와 CSR 모의 99번의 범위(회색 띠), 점선은 CSR의 이론값. 왼쪽: G 함수(최근린 거리가 r 이하인 점의 비율)는 CSR보다 "
                   "빨리 올라감. 가운데: F 함수(임의의 위치에서 가장 가까운 출동까지 거리가 r 이하인 비율)는 CSR보다 느리게 올라감. "
                   "오른쪽: L(r) − r은 모든 거리에서 0보다 훨씬 위에 있음. 세 함수 모두 군집을 가리킴")
    lam = N / AREA
    theo = 1 - np.exp(-lam * np.pi * R ** 2)
    env_panel(s, 50, 52, 190, 170, R[:21], Gobs[:21], Gs[:, :21], (0, 1), "G 함수", "G(r)", ref=theo[:21], yticks=[0, 0.5, 1], xlab="r (m)", xticks=(0, 500, 1000))
    env_panel(s, 290, 52, 190, 170, R[:21], Fobs[:21], Fs[:, :21], (0, 1), "F 함수", "F(r)", ref=theo[:21], yticks=[0, 0.5, 1], xlab="r (m)", xticks=(0, 500, 1000))
    Lo = L_minus_r(Kobs)
    Ls = np.array([L_minus_r(k) for k in Ks])
    env_panel(s, 530, 52, 170, 170, R, Lo, Ls, (-100, 2100), "L(r) − r", "m", ref=np.zeros(len(R)), yticks=[0, 1000, 2000])
    s.save(os.path.join(OUT, "18-gfl.svg"))


def fig_inhom(Ka, Kas, Kb, Kbs):
    W_, H = 720, 292
    s = Svg(W_, H, "왼쪽: 보통의 L(r) − r(빨간 선)과, 출동을 100 m 격자 인구에 비례해 뿌린 불균질 포아송 모의 99번의 범위(회색 띠). 관측이 1.5 km까지 띠보다 "
                   "위에 있어 인구 분포만으로 설명되지 않는 몰림이 남음. 오른쪽: 강도를 출동 자체의 커널 밀도(865 m)로 추정해 1/λ로 가중한 불균질 L 함수와, "
                   "그 강도의 불균질 포아송 모의(모의마다 강도를 다시 추정) 99번의 범위. 0~2 km의 모든 거리에서 띠 안에 듦")
    m = R <= 2000
    for k, (Ko, Ksim, t, yl) in enumerate(((Ka, Kas, "(가) 보통 L, 인구 비례 모의", (-100, 1600)), (Kb, Kbs, "(나) 불균질 L, 커널 밀도 865 m", (-1100, 300)))):
        Lo = L_minus_r(Ko)
        Ls = np.array([L_minus_r(x) for x in Ksim])
        env_panel(s, 70 + k * 340, 52, 280, 180, R[m], Lo[m], Ls[:, m], yl, t, "L(r) − r (m)", ref=np.zeros(m.sum()), xticks=(0, 500, 1000, 1500, 2000))
    s.save(os.path.join(OUT, "18-inhom.svg"))


def fig_cross(D, sims):
    W_, H = 720, 260
    s = Svg(W_, H, "65세 이상 출동끼리의 K 함수에서 65세 미만 출동끼리의 K 함수를 뺀 값(빨간 선)과, 연령 표지를 무작위로 섞은 모의 99번의 범위(회색 띠). "
                   "0보다 크면 65세 이상 출동이 65세 미만보다 더 몰려 있다는 뜻. 1.1 km 이상에서 띠 아래로 내려가, 큰 거리에서는 65세 미만 출동이 더 몰려 있음")
    env_panel(s, 80, 40, 600, 170, R, D / 1e6, sims / 1e6, (min(np.nanmin(D), np.nanmin(sims)) / 1e6 * 1.15, max(np.nanmax(D), np.nanmax(sims)) / 1e6 * 1.15),
              "", "K₆₅ − K₆₅미만 (km²)", ref=np.zeros(len(R)))
    s.save(os.path.join(OUT, "18-cross.svg"))


if __name__ == "__main__":
    hand()
    Kobs, Ks, Gobs, Gs, Fobs, Fs = numbers()
    Ka, Kas, Kb, Kbs = inhom()
    D, sims = cross()
    fig_gfl(Kobs, Ks, Gobs, Gs, Fobs, Fs)
    fig_inhom(Ka, Kas, Kb, Kbs)
    fig_cross(D, sims)
