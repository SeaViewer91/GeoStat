"""17강 그림과 본문 수치.

- 17-kde.svg : 가우시안 커널 밀도(강도) 지도. 대역폭 300 m, 우도 교차검증으로 고른 값, Scott 규칙
- 17-bw.svg : 대역폭에 따른 우도 교차검증 점수
- 17-rate.svg : 인구 1만 명당 출동 강도(출동 커널 밀도 ÷ 인구 커널 밀도)와 65세 이상 출동의 상대 강도(무작위 표지 모의로 유의 영역 표시)
- 17-lst.svg : 지표온도 구간별 출동 강도(km²당)와 인구 1만 명당 출동

커널은 가우시안이고 경계 보정은 균일 보정(Diggle 1985: 위치마다 커널 질량 가운데 시 안에 드는 비율로 나눔)임.
평가 격자는 200 m임.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/17.py
"""
import os
import sys
import warnings

import numpy as np
import rasterio
from scipy.optimize import minimize_scalar

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import DATA, MapFrame, colorbar, div_rgb, draw, outline, png, ramp_rgb, to_array  # noqa: E402
from plotkit import Axes  # noqa: E402
from ppkit import edge_mass, events, grid, kmat, pop_grid, window  # noqa: E402
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import aggregate as agg  # noqa: E402
from geostat_engine.analysis.grid import make_grid  # noqa: E402
from pyproj import CRS  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
SEED = 20261017
G_M = 200.0
CELL_A = G_M * G_M

WIN = window()
EV, P = events()
N = len(P)
OLD = (EV["연령대"] == "65+").to_numpy()
G, INSIDE, (GXS, GYS) = grid(WIN, G_M)


def hand():
    print("[손계산] 위치 x에서 0.5, 1, 2 km 떨어진 점 세 개, 가우시안 h = 1 km")
    d = np.array([0.5, 1.0, 2.0])
    k = np.exp(-d ** 2 / 2) / (2 * np.pi)
    print(f"  커널 값(km⁻²) {np.round(k, 4).tolist()}, 합 {k.sum():.4f}, 경계 보정(질량 0.5)하면 {k.sum() / 0.5:.4f}")


def kde(pts, h, edge=None):
    e = edge_mass(G, CELL_A, h) if edge is None else edge
    return np.asarray(kmat(pts, G, h).sum(0)).ravel() / e, e


def cv_score(h, D2):
    K = np.exp(-D2 / (2 * h * h)) / (2 * np.pi * h * h)
    e = edge_mass(G, CELL_A, h, at=P)
    return np.log(K.sum(1) / e).sum() - N


def bandwidth():
    print("[1] 대역폭")
    sx, sy = P.std(0)
    h_scott = np.sqrt((sx ** 2 + sy ** 2) / 2) * N ** (-1 / 6)
    print(f"  좌표 표준편차 x {sx:.0f} m, y {sy:.0f} m → Scott 규칙 h = {h_scott:.0f} m")
    D2 = ((P[:, None, :] - P[None, :, :]) ** 2).sum(-1)
    np.fill_diagonal(D2, np.inf)
    hs = np.array([100, 150, 200, 250, 300, 400, 500, 600, 700, 800, 900, 1000, 1200, 1500, 2000])
    sc = np.array([cv_score(h, D2) for h in hs])
    for h, v in zip(hs, sc):
        print(f"   h {h:5d}: CV {v:.1f}")
    r = minimize_scalar(lambda h: -cv_score(h, D2), bounds=(300, 2000), method="bounded")
    print(f"  우도 교차검증 최적 h = {r.x:.0f} m (점수 {-r.fun:.1f})")
    return h_scott, r.x, hs, sc


def maps(h_list):
    print("[2] 커널 밀도")
    out = {}
    for h in h_list:
        lam, e = kde(P, h)
        lam_km = lam * 1e6
        print(f"  h {h:.0f} m: 최대 {lam_km.max():.1f}건/km², 중앙값 {np.median(lam_km):.2f}, 상위 1% {np.percentile(lam_km, 99):.1f}, "
              f"적분 {(lam * CELL_A).sum():.1f}, 경계 질량 최소 {e.min():.2f}")
        i = np.argmax(lam_km)
        print(f"    최대 위치 ({G[i, 0]:.0f}, {G[i, 1]:.0f})")
        lam0, _ = kde(P, h, edge=np.ones(len(G)))
        print(f"    경계 보정 없이 하면 적분 {(lam0 * CELL_A).sum():.1f}건 (창 밖으로 샌 질량 {N - (lam0 * CELL_A).sum():.1f}건)")
        out[h] = lam_km
    # 앱의 1 km 방격 밀도
    cells = make_grid(WIN.bounds, CRS.from_epsg(5186), 1000, "square", clip=WIN)
    r = agg.aggregate(cells, EV, stats=[], count=True, density=True)
    dens = np.asarray(r.columns["DENS"])
    print(f"  1 km 격자 점 집계 밀도(앱 DENS): 최대 {dens.max():.1f}건/km², 0인 칸 {(dens == 0).sum()}/{len(dens)}")
    return out


def rate_and_rr(h):
    print(f"[3] 인구 대비 강도와 65세 이상 상대 강도 (h = {h:.0f} m)")
    pop, eld, tr = pop_grid()
    PY, PX = np.nonzero(pop > 0)
    pc = np.c_[tr.c + 100 * (PX + 0.5), tr.f - 100 * (PY + 0.5)]
    KP = kmat(pc, G, h)
    sp = KP.T @ pop[PY, PX]
    se = KP.T @ eld[PY, PX]
    K = kmat(P, G, h)
    lam = np.asarray(K.sum(0)).ravel()
    rate = lam / sp * 1e4   # 경계 보정은 분자·분모에 같이 들어가 상쇄됨
    pool = lam / edge_mass(G, CELL_A, h) * 1e6
    valid = pool >= 0.5
    print(f"  인구 1만 명당 출동 강도: 5% {np.percentile(rate[valid], 5):.1f}, 중앙값 {np.median(rate[valid]):.1f}, 95% {np.percentile(rate[valid], 95):.1f} "
          f"(출동 강도 0.5건/km² 이상인 {valid.sum() * CELL_A / 1e6:.1f} km²에서)")
    i = np.argmax(np.where(valid, rate, -1))
    print(f"    가장 높은 곳 ({G[i, 0]:.0f}, {G[i, 1]:.0f}) {rate[i]:.1f}")

    def rr_of(lab):
        a = np.asarray(K[lab].sum(0)).ravel()
        b = np.asarray(K[~lab].sum(0)).ravel()
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.log((a / lab.sum()) / (b / (~lab).sum()))

    rr = rr_of(OLD)
    rng = np.random.default_rng(SEED)
    sims = np.array([rr_of(rng.permutation(OLD)) for _ in range(199)])
    ph = (1 + (sims >= rr).sum(0)) / 200
    pl = (1 + (sims <= rr).sum(0)) / 200
    hi = (ph <= 0.025) & valid
    lo = (pl <= 0.025) & valid
    share = se / sp
    print(f"  65세 이상 {OLD.sum()}건, 65세 미만 {(~OLD).sum()}건. 상대 강도 범위(유효 영역) {np.exp(rr[valid]).min():.2f}~{np.exp(rr[valid]).max():.2f}")
    print(f"  무작위 표지 199번: 65세 이상이 유의하게 높은 영역 {hi.sum() * CELL_A / 1e6:.1f} km², 낮은 영역 {lo.sum() * CELL_A / 1e6:.1f} km² (양쪽 각 2.5%)")
    print(f"  유의하게 높은 영역의 평활 고령비율 평균 {share[hi].mean() * 100:.1f}%, 낮은 영역 {share[lo].mean() * 100:.1f}%, 시 전체 {eld.sum() / pop.sum() * 100:.1f}%")
    print(f"  log 상대 강도와 평활 고령비율의 상관 {np.corrcoef(rr[valid], share[valid])[0, 1]:.2f}")
    return rate, rr, hi, lo, valid


def lst_bins():
    print("[4] 지표온도 구간별")
    with rasterio.open(os.path.join(DATA, "hanbit_lst.tif")) as r:
        lst = r.read(1).astype(float)
        lst[lst <= -9000] = np.nan
    pop, _, tr = pop_grid()
    l100 = np.nanmean(lst.reshape(240, 2, 320, 2).swapaxes(1, 2).reshape(240, 320, 4), axis=2)
    land = ~np.isnan(l100)
    iy = ((tr.f - P[:, 1]) / 100).astype(int)
    ix = ((P[:, 0] - tr.c) / 100).astype(int)
    lv = l100[iy, ix]
    bins = [-np.inf, 30, 32, 34, 36, np.inf]
    labs = ["30 미만", "30~32", "32~34", "34~36", "36 이상"]
    rows = []
    for k in range(5):
        m = land & (l100 >= bins[k]) & (l100 < bins[k + 1])
        a = m.sum() * 0.01
        pp = pop[m].sum()
        e = int(((lv >= bins[k]) & (lv < bins[k + 1])).sum())
        rows.append((labs[k], a, pp, e))
        print(f"  {labs[k]}℃: 면적 {a:.1f} km², 인구 {pp:,.0f}, 출동 {e}, km²당 {e / a:.2f}, 인구 1만 명당 {e / pp * 1e4:.2f}, 인구 밀도 {pp / a:,.0f}명/km²")
    print(f"  빈 값(바다 셀)에 걸린 출동 {int(np.isnan(lv).sum())}")
    return rows


# ---------------------------------------------------------------- 그림
def place(s, fr, arr, rgb_fn, lo, hi):
    x0, y0 = GXS[0] - G_M / 2, GYS[0] - G_M / 2
    x1, y1 = GXS[-1] + G_M / 2, GYS[-1] + G_M / 2
    X0, Y0 = fr.xy(x0, y1)
    X1, Y1 = fr.xy(x1, y0)
    s.image_png(X0, Y0, X1 - X0, Y1 - Y0, png(rgb_fn(arr, lo, hi), int(2 * (X1 - X0))))


def fig_kde(maps_, hs):
    W_, H = 720, 300
    s = Svg(W_, H, "출동의 가우시안 커널 강도 지도(건/km², 경계 보정). 왼쪽: 대역폭 300 m는 점 하나하나가 얼룩으로 남음. 가운데: 우도 교차검증으로 고른 "
                   f"{hs[1]:.0f} m. 오른쪽: Scott 규칙 {hs[2]:.0f} m는 마루구와 가람구의 큰 덩어리 두 개와 동쪽 해안의 옅은 언덕만 남을 만큼 매끈함. 세 지도는 같은 색 범위(0~30)를 씀")
    mw = 220
    fr = [MapFrame(WIN.bounds, 15 + k * (mw + 13), 40, mw) for k in range(3)]
    for k, h in enumerate(hs):
        s.text(fr[k].x + mw / 2, 26, f"h = {h:.0f} m", size=12, weight="600")
        place(s, fr[k], to_array(maps_[h], INSIDE), ramp_rgb, 0, 30)
        outline(s, fr[k], WIN, cls="s-mu", width=0.8)
    colorbar(s, 250, 40 + fr[0].h + 22, 220, 0, 30, [0, 10, 20, 30], "강도 (건/km²)")
    s.save(os.path.join(OUT, "17-kde.svg"))


def fig_bw(hs_grid, sc, h_cv, h_scott):
    W_, H = 720, 250
    s = Svg(W_, H, f"대역폭에 따른 우도 교차검증 점수. 점 하나를 빼고 나머지로 그 자리의 강도를 추정해 로그를 더한 값으로, 클수록 좋음. 최댓값은 {h_cv:.0f} m이고, "
                   f"Scott 규칙({h_scott:.0f} m)은 그보다 크며, 300 m 아래로 내려가면 점수가 급격히 나빠짐")
    ax = Axes(s, 80, 30, 600, 170, (0, 2100), (sc.min() - 200, sc.max() + 300))
    ax.curve(hs_grid, sc, cls="s-ac", width=1.8)
    for h, v in zip(hs_grid, sc):
        s.circle(float(ax.X(h)), float(ax.Y(v)), 3, cls="s-bg f-ac", width=0.5)
    ax.xaxis(ticks=[0, 300, 500, 1000, 1500, 2000], label="대역폭 h (m)")
    ax.yaxis(label="교차검증 로그우도")
    ax.vline(h_cv, cls="s-bd", width=1.4, dash="4 3")
    s.text(float(ax.X(h_cv)) + 4, 120, f"최적 {h_cv:.0f} m", size=11, anchor="start", cls="f-bd")
    ax.vline(h_scott, cls="s-mu", width=1.2, dash="2 3")
    s.text(float(ax.X(h_scott)) + 4, 136, f"Scott {h_scott:.0f} m", size=11, anchor="start", cls="f-mu")
    s.save(os.path.join(OUT, "17-bw.svg"))


def fig_rate(rate, rr, hi, lo, valid, h):
    W_, H = 720, 320
    s = Svg(W_, H, f"대역폭 {h:.0f} m. 왼쪽: 인구 1만 명당 출동 강도(출동 커널 밀도 ÷ 인구 커널 밀도). 출동이 거의 없는 곳(0.5건/km² 미만)은 회색. "
                   "오른쪽: 65세 이상 출동의 상대 강도(65세 이상 밀도 ÷ 65세 미만 밀도, 각각 건수로 나눔). 붉을수록 65세 이상 출동의 비중이 큼. "
                   "검은 테두리 안은 무작위 표지 모의 199번에서 유의하게 높은 곳, 파란 테두리 안은 낮은 곳")
    mw = 330
    fr = [MapFrame(WIN.bounds, 20 + k * (mw + 20), 40, mw) for k in range(2)]
    s.text(fr[0].x + mw / 2, 26, "인구 1만 명당 출동", size=12, weight="600")
    s.text(fr[1].x + mw / 2, 26, "65세 이상 출동의 상대 강도", size=12, weight="600")
    r2 = np.where(valid, rate, np.nan)
    gray = np.where(valid, np.nan, 0.0)
    place(s, fr[0], to_array(gray, INSIDE), lambda v, a, b: np.where(np.isnan(v)[..., None], 0, np.array([200, 200, 200, 255])).astype(np.uint8), 0, 1)
    place(s, fr[0], to_array(r2, INSIDE), ramp_rgb, 5, 30)
    lr = np.where(valid, np.clip(rr, -1.2, 1.2), np.nan)
    place(s, fr[1], to_array(gray, INSIDE), lambda v, a, b: np.where(np.isnan(v)[..., None], 0, np.array([200, 200, 200, 255])).astype(np.uint8), 0, 1)
    place(s, fr[1], to_array(lr, INSIDE), div_rgb, -1.2, 1.2)
    # 유의 영역 테두리: 격자 셀을 합쳐 외곽선
    import shapely

    for mask, col in ((hi, "#111111"), (lo, "#1d4ed8")):
        cells = [shapely.box(x - G_M / 2, y - G_M / 2, x + G_M / 2, y + G_M / 2) for x, y in G[mask]]
        if cells:
            u = shapely.union_all(cells)
            for p in getattr(u, "geoms", [u]):
                d = "M" + " L".join(f"{fr[1].xy(x, y)[0]:.1f},{fr[1].xy(x, y)[1]:.1f}" for x, y in p.exterior.coords) + " Z"
                s.add(f'<path d="{d}" stroke="{col}" stroke-width="1.4" fill="none"/>')
    for f in fr:
        outline(s, f, WIN, cls="s-mu", width=0.8)
    y = 40 + fr[0].h + 22
    colorbar(s, fr[0].x + 40, y, 250, 5, 30, [5, 10, 20, 30], "인구 1만 명당 출동")
    colorbar(s, fr[1].x + 40, y, 250, -1.2, 1.2, [np.log(0.33), np.log(0.5), 0, np.log(2), np.log(3)], "상대 강도", diverging=True,
             fmt=lambda t: f"{np.exp(t):.2g}")
    s.save(os.path.join(OUT, "17-rate.svg"))


def fig_lst(rows):
    W_, H = 720, 280
    s = Svg(W_, H, "지표온도 구간별 출동. 왼쪽: 면적 1 km²당 출동 건수는 더운 곳일수록 가파르게 늘어남. 오른쪽: 인구 1만 명당으로 바꾸면 증가 폭이 훨씬 작아짐. "
                   "더운 곳은 사람이 많이 사는 도심이라, 면적 기준 강도에는 인구의 효과가 섞여 있음")
    labs = [r[0] for r in rows]
    a1 = [r[3] / r[1] for r in rows]
    a2 = [r[3] / r[2] * 1e4 for r in rows]
    for k, (vals, title, ylab, top) in enumerate(((a1, "km²당 출동 (강도)", "건/km²", max(a1) * 1.2), (a2, "인구 1만 명당 출동", "건/1만 명", max(a2) * 1.25))):
        x0 = 70 + k * 360
        ax = Axes(s, x0, 40, 270, 180, (-0.5, 4.5), (0, top))
        s.text(x0 + 135, 22, title, size=12, weight="600")
        ax.yaxis(label=ylab)
        for i, v in enumerate(vals):
            X0, X1 = float(ax.X(i - 0.32)), float(ax.X(i + 0.32))
            Y = float(ax.Y(v))
            s.rect(X0, Y, X1 - X0, float(ax.Y(0)) - Y, cls="s-bg f-ac", width=0.5)
            s.text((X0 + X1) / 2, Y - 5, f"{v:.1f}", size=10)
            s.text((X0 + X1) / 2, float(ax.Y(0)) + 15, labs[i], size=10, cls="f-mu")
        s.text(x0 + 135, 252, "지표온도 (℃, 100 m 셀 평균)", size=11, cls="f-mu")
    s.save(os.path.join(OUT, "17-lst.svg"))


if __name__ == "__main__":
    hand()
    h_scott, h_cv, hs_grid, sc = bandwidth()
    m = maps([300.0, h_cv, h_scott])
    rate, rr, hi, lo, valid = rate_and_rr(1000.0)
    rows = lst_bins()
    fig_kde(m, [300.0, h_cv, h_scott])
    fig_bw(hs_grid, sc, h_cv, h_scott)
    fig_rate(rate, rr, hi, lo, valid, 1000.0)
    fig_lst(rows)
