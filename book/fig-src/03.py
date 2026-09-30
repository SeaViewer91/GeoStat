"""3강 그림과 본문 수치.

- 03-toy.svg : 2×2 블록을 가로·세로로 묶을 때 출동률 차이가 달라지는 손계산 예
- 03-scale.svg : 같은 자료를 500 m·1 km·4 km 격자와 행정동으로 집계한 출동률 지도 (척도 효과)
- 03-zoning.svg : 구역 150개짜리 무작위 구획 500가지에서 구한 상관계수 분포 (구획 효과)
- 03-ecological.svg : 행정동 수준의 상관과 개인 수준의 위험비 (생태학적 오류)

격자 집계는 GeoStat 엔진의 격자 만들기·존 통계·점 집계 함수로 계산해 앱 결과와 같게 함.
무작위 구획은 계산량 때문에 100 m 인구 격자의 셀 중심을 가장 가까운 씨앗점에 붙이는 방식으로 근사함.
같은 방식으로 행정동을 계산하면 r(지표온도, 출동률) 0.354, r(고령비율, 출동률) -0.126으로 정확한 값(0.358, -0.125)과 거의 같음.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/03.py
"""
import os
import sys
import warnings

import geopandas as gpd
import numpy as np
import rasterio
import shapely
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import aggregate as agg  # noqa: E402
from geostat_engine.analysis import grid, zonal  # noqa: E402

warnings.filterwarnings("ignore")
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "..", "fig")
POP = os.path.join(DATA, "hanbit_pop100.tif")
LST = os.path.join(DATA, "hanbit_lst.tif")
MIN_POP = 100  # 출동률을 계산할 최소 인구

dong = gpd.read_file(os.path.join(DATA, "hanbit_dong.gpkg"))
events = gpd.read_file(os.path.join(DATA, "hanbit_events.gpkg"))
UNION = dong.union_all()
BX0, BY0, BX1, BY1 = dong.total_bounds


class _Raster:
    def __init__(self, path, count):
        self.path, self.info = path, {"count": count, "crs": "EPSG:5186"}


def zs(g, path, band, stat):
    pl = zonal.prepare(g, _Raster(path, 2 if path == POP else 1), {"stats": [stat], "band": band})
    return zonal.run(pl, lambda *_: None)["columns"][zonal.STATS[stat][1]]


def summarize(g, pop_col, old_col, lst_col, cnt_col):
    ok = g[pop_col] >= MIN_POP
    h = g[ok]
    rate = h[cnt_col] / h[pop_col] * 1e4
    el = h[old_col] / h[pop_col] * 100
    return {
        "n": len(g), "n_ok": int(ok.sum()), "pop_med": float(h[pop_col].median()),
        "zero": float((h[cnt_col] == 0).mean()),
        "r_lst": float(np.corrcoef(h[lst_col], rate)[0, 1]), "r_el": float(np.corrcoef(el, rate)[0, 1]),
        "rate": rate, "ok": ok.to_numpy(),
    }


def grid_units(size):
    g = grid.make_grid((BX0, BY0, BX1, BY1), dong.crs, size, clip=UNION)
    g["POP_SUM"] = zs(g, POP, 1, "sum")
    g["OLD_SUM"] = zs(g, POP, 2, "sum")
    g["ZS_MEAN"] = zs(g, LST, 1, "mean")
    g["PT_CNT"] = agg.aggregate(g, events, [], count=True).columns["CNT"]
    return g


def dong_units():
    g = dong.copy()
    g["ZS_MEAN"] = zs(g, LST, 1, "mean")
    g["PT_CNT"] = agg.aggregate(g, events, [], count=True).columns["CNT"]
    return g


# ---------------------------------------------------------------- 0. 손계산 예
def fig_toy():
    blocks = {"A": (1000, 2), "B": (1000, 8), "C": (1000, 4), "D": (1000, 6)}
    s = Svg(720, 250, "인구 1,000명씩인 네 블록(출동 2·8·4·6건)을 가로로 묶으면 두 구역의 출동률이 같고, 세로로 묶으면 3건과 7건으로 두 배 넘게 차이 남")
    cell = 70

    def draw(x0, title, groups, labels):
        s.text(x0 + cell, 30, title, size=13, weight="600")
        pos = {"A": (0, 0), "B": (1, 0), "C": (0, 1), "D": (1, 1)}
        for g, cls in zip(groups, ("f-acs", "f-bds")):
            for b in g:
                c, r = pos[b]
                s.rect(x0 + c * cell, 45 + r * cell, cell, cell, cls=f"s-bg {cls}", width=2)
        for b, (c, r) in pos.items():
            s.text(x0 + c * cell + cell / 2, 45 + r * cell + 30, b, size=13, weight="600")
            s.text(x0 + c * cell + cell / 2, 45 + r * cell + 50, f"{blocks[b][1]}건", size=12)
        for i, lab in enumerate(labels):
            s.text(x0 + cell, 45 + 2 * cell + 24 + i * 18, lab, size=12, cls="f-ac" if i == 0 else "f-bd")

    s.rect(30, 45, 2 * cell, 2 * cell, cls="s-bg f-sf", width=2)
    for b, (c, r) in {"A": (0, 0), "B": (1, 0), "C": (0, 1), "D": (1, 1)}.items():
        s.rect(30 + c * cell, 45 + r * cell, cell, cell, cls="s-mu f-sf", width=1)
        s.text(30 + c * cell + cell / 2, 45 + r * cell + 30, b, size=13, weight="600")
        s.text(30 + c * cell + cell / 2, 45 + r * cell + 50, f"{blocks[b][1]}건", size=12)
    s.text(30 + cell, 30, "블록 (각 인구 1,000명)", size=13, weight="600")
    draw(270, "가로로 묶음", [("A", "B"), ("C", "D")], ["위: 10건 ÷ 2,000명 = 5건/1천 명", "아래: 10건 ÷ 2,000명 = 5건/1천 명"])
    draw(510, "세로로 묶음", [("A", "C"), ("B", "D")], ["왼쪽: 6건 ÷ 2,000명 = 3건/1천 명", "오른쪽: 14건 ÷ 2,000명 = 7건/1천 명"])
    s.save(os.path.join(OUT, "03-toy.svg"))


# ---------------------------------------------------------------- 1. 척도 효과
def scale_effect():
    units = {}
    for size in (500, 1000, 2000, 4000):
        units[f"{size} m" if size < 1000 else f"{size // 1000} km"] = grid_units(size)
    d = dong_units()
    units["행정동"] = d
    rows = {}
    print(f"[1] 척도 효과 (인구 {MIN_POP}명 이상인 단위만 출동률 계산)")
    for k, g in units.items():
        if k == "행정동":
            r = summarize(g, "인구", "고령인구", "ZS_MEAN", "PT_CNT")
        else:
            r = summarize(g, "POP_SUM", "OLD_SUM", "ZS_MEAN", "PT_CNT")
        rows[k] = r
        print(f"  {k}: 단위 {r['n']}개 (인구 {MIN_POP}명 이상 {r['n_ok']}개), 인구 중앙값 {r['pop_med']:,.0f}, "
              f"출동 0건 비율 {r['zero']:.0%}, r(지표온도, 출동률) = {r['r_lst']:.3f} (R² {r['r_lst'] ** 2:.3f}), "
              f"r(고령비율, 출동률) = {r['r_el']:.3f}, 출동률 표준편차 {r['rate'].std():.1f}")
    # 앱에서 필터 없이 그린 산점도 (4 km, 행정동)
    for k in ("4 km", "행정동"):
        g = units[k]
        p = g["인구"] if k == "행정동" else g["POP_SUM"]
        rate = g["PT_CNT"] / p * 1e4
        r = np.corrcoef(g["ZS_MEAN"], rate)[0, 1]
        slope = np.polyfit(g["ZS_MEAN"], rate, 1)[0]
        print(f"  [해 보기] {k} 필터 없이: n={len(g)}, 인구 최소 {p.min():,.0f}, R² {r * r:.3f}, 기울기 {slope:.3f}")
    # 4 km 상관계수의 불안정성: 격자 하나씩 뺀 범위와 피셔 z 95% 신뢰구간
    g = units["4 km"]
    x = g["ZS_MEAN"].to_numpy()
    y = (g["PT_CNT"] / g["POP_SUM"] * 1e4).to_numpy()
    loo = [np.corrcoef(np.delete(x, i), np.delete(y, i))[0, 1] for i in range(len(x))]
    r4 = rows["4 km"]["r_lst"]
    z, se = np.arctanh(r4), 1 / np.sqrt(len(x) - 3)
    print(f"  4 km: 하나씩 뺀 r 범위 {min(loo):.2f}~{max(loo):.2f}, 95% 신뢰구간 {np.tanh(z - 1.96 * se):.2f}~{np.tanh(z + 1.96 * se):.2f}")
    g1 = units["1 km"]
    r1 = g1["PT_CNT"] / g1["POP_SUM"] * 1e4
    fin = np.isfinite(r1)
    print(f"  [해 보기] 1 km 필터 없이: 격자 {len(g1)}개, 인구 0인 격자 {(g1['POP_SUM'] == 0).sum()}개, 출동률 최댓값 {r1[fin].max():,.0f} "
          f"(인구 {g1.loc[r1[fin].idxmax(), 'POP_SUM']:.0f}, 출동 {g1.loc[r1[fin].idxmax(), 'PT_CNT']}), R² {np.corrcoef(g1['ZS_MEAN'][fin], r1[fin])[0, 1] ** 2:.3f}")
    fig_scale(units, rows)
    return rows


def fig_scale(units, rows):
    keys = ["500 m", "1 km", "4 km", "행정동"]
    s = Svg(720, 250, "같은 구급 출동 자료를 500 m·1 km·4 km 격자와 행정동으로 집계한 출동률 지도. 작은 단위는 출동 0건과 극단값이 섞인 잡음처럼 보이고, 큰 단위로 갈수록 무늬가 매끄러워지며 지표온도와의 상관도 달라짐")
    w = 165
    for i, k in enumerate(keys):
        x0 = 12 + i * 177
        k_ = w / (BX1 - BX0)
        h = (BY1 - BY0) * k_
        g = units[k]
        r = rows[k]
        rate = np.full(len(g), np.nan)
        rate[r["ok"]] = r["rate"].to_numpy()
        valid = ~np.isnan(rate)
        edges = np.quantile(rate[valid], [0.2, 0.4, 0.6, 0.8])
        s.text(x0 + w / 2, 24, k, size=13, weight="600")
        for geom, v in zip(g.geometry, rate):
            for pg in getattr(geom, "geoms", [geom]):
                pts = [(x0 + (x - BX0) * k_, 36 + (BY1 - y) * k_) for x, y in pg.exterior.coords]
                cls = "s-bg f-sf" if np.isnan(v) else f"s-bg q{int(np.searchsorted(edges, v, side='right'))}"
                s.polygon(pts, cls=cls, width=0.3 if i < 2 else 0.6)
        s.text(x0 + w / 2, 36 + h + 20, f"단위 {r['n_ok']}개, 0건 {r['zero']:.0%}", size=11, cls="f-mu")
        s.text(x0 + w / 2, 36 + h + 38, f"지표온도와 r = {r['r_lst']:.2f}", size=12)
    y = 36 + (BY1 - BY0) * w / (BX1 - BX0) + 58
    for i in range(5):
        s.rect(260 + i * 40, y, 40, 10, cls=f"s-bg q{i}", width=0.5)
    s.text(254, y + 9, "출동률 낮음", size=11, anchor="end", cls="f-mu")
    s.text(466, y + 9, "높음 (5분위)", size=11, anchor="start", cls="f-mu")
    s.h = int(y + 22)
    s.save(os.path.join(OUT, "03-scale.svg"))


# ---------------------------------------------------------------- 2. 구획 효과
def cell_table():
    with rasterio.open(POP) as src:
        pop = src.read(1).astype(float)
        old = src.read(2).astype(float)
        T = src.transform
    with rasterio.open(LST) as src:
        lst = src.read(1, masked=True).filled(np.nan)
    ny, nx = pop.shape
    with np.errstate(all="ignore"):
        lst100 = np.nanmean(lst.reshape(ny, 2, nx, 2), axis=(1, 3))
    yy, xx = np.mgrid[0:ny, 0:nx]
    cx, cy = T.c + T.a * (xx + 0.5), T.f + T.e * (yy + 0.5)
    land = pop >= 0
    return np.c_[cx[land], cy[land]], pop[land], old[land], lst100[land]


def random_seeds(rng, n=150):
    pts = []
    while len(pts) < n:
        q = rng.uniform([BX0, BY0], [BX1, BY1], (400, 2))
        q = q[shapely.contains_xy(UNION, q[:, 0], q[:, 1])]
        pts += list(q)
    return np.array(pts[:n])


def zoning_effect(dong_rows):
    C, P, O, L = cell_table()
    E = np.c_[events.geometry.x, events.geometry.y]
    rng = np.random.default_rng(20260930)
    res, seeds_kept = [], []
    for i in range(500):
        seeds = random_seeds(rng)
        t = cKDTree(seeds)
        zc, ze = t.query(C)[1], t.query(E)[1]
        k = len(seeds)
        pz, oz = np.bincount(zc, P, k), np.bincount(zc, O, k)
        ez = np.bincount(ze, minlength=k)
        has = ~np.isnan(L)
        lz = np.bincount(zc[has], L[has], k) / np.maximum(np.bincount(zc[has], minlength=k), 1)
        ok = pz >= MIN_POP
        rate, el = ez[ok] / pz[ok] * 1e4, oz[ok] / pz[ok] * 100
        res.append((np.corrcoef(lz[ok], rate)[0, 1], np.corrcoef(el, rate)[0, 1]))
        if i < 3:
            seeds_kept.append(seeds)
    res = np.array(res)
    print("[2] 구획 효과: 구역 150개 무작위 구획 500가지")
    for j, name in ((0, "지표온도"), (1, "고령비율")):
        v = res[:, j]
        d = dong_rows["행정동"]["r_lst" if j == 0 else "r_el"]
        print(f"  r({name}, 출동률): 최소 {v.min():.3f}, 5% {np.percentile(v, 5):.3f}, 중앙값 {np.median(v):.3f}, "
              f"95% {np.percentile(v, 95):.3f}, 최대 {v.max():.3f}, 양수 비율 {(v > 0).mean():.0%}; "
              f"행정동 {d:.3f} (무작위 구획 가운데 이보다 큰 비율 {(v > d).mean():.0%})")
    fig_zoning(res, seeds_kept, dong_rows)


def fig_zoning(res, seeds_kept, dong_rows):
    s = Svg(720, 300, "구역 수가 150개로 같은 무작위 구획 500가지에서 구한 고령비율과 출동률의 상관계수 분포. 같은 자료인데 구획만 바꿔도 상관계수가 음수에서 양수까지 흩어짐")
    w = 120
    k_ = w / (BX1 - BX0)
    h = (BY1 - BY0) * k_
    box = shapely.box(BX0 - 1e4, BY0 - 1e4, BX1 + 1e4, BY1 + 1e4)
    for i, seeds in enumerate(seeds_kept):
        x0, y0 = 20, 30 + i * (h + 18)
        vor = shapely.voronoi_polygons(shapely.MultiPoint(seeds), extend_to=box)
        for pg in vor.geoms:
            pg = pg.intersection(UNION)
            for part in getattr(pg, "geoms", [pg]):
                if part.is_empty or part.geom_type != "Polygon":
                    continue
                s.polygon([(x0 + (x - BX0) * k_, y0 + (BY1 - y) * k_) for x, y in part.exterior.coords], cls="s-mu f-sf", width=0.5)
        s.text(x0 + w + 6, y0 + h / 2 + 4, f"구획 {i + 1}", size=11, anchor="start", cls="f-mu")
    # 히스토그램
    v = res[:, 1]
    gx, gy, gw, gh = 250, 40, 430, 190
    bins = np.arange(-0.4, 0.45, 0.05)
    cnt, _ = np.histogram(v, bins)
    X = lambda t: gx + (t - bins[0]) / (bins[-1] - bins[0]) * gw  # noqa: E731
    ymax = cnt.max() * 1.1
    for c, b0 in zip(cnt, bins[:-1]):
        s.rect(X(b0) + 1, gy + gh - c / ymax * gh, X(b0 + 0.05) - X(b0) - 2, c / ymax * gh, cls="f-ac", width=0)
    s.line(gx, gy + gh, gx + gw, gy + gh, cls="s-mu", width=1)
    for t in (-0.4, -0.2, 0.0, 0.2, 0.4):
        s.text(X(t), gy + gh + 16, f"{t:.1f}", size=11, cls="f-mu")
    s.line(X(0), gy, X(0), gy + gh, cls="s-mu", width=1, dash="3 3")
    d = dong_rows["행정동"]["r_el"]
    s.line(X(d), gy - 4, X(d), gy + gh, cls="s-bd", width=2)
    s.text(X(d), gy - 8, f"행정동 {d:.2f}", size=11, cls="f-bd", weight="600")
    s.text(gx + gw / 2, gy + gh + 36, "고령비율과 출동률의 상관계수 r", size=12, cls="f-mu")
    s.text(gx + gw / 2, 18, "무작위 구획 500가지", size=13, weight="600")
    s.save(os.path.join(OUT, "03-zoning.svg"))


# ---------------------------------------------------------------- 3. 생태학적 오류
def ecological(dong_rows):
    old_ev = int((events["연령대"] == "65+").sum())
    young_ev = len(events) - old_ev
    P, O = int(dong["인구"].sum()), int(dong["고령인구"].sum())
    r_old, r_young = old_ev / O * 1e4, young_ev / (P - O) * 1e4
    d = dong_units()
    rate = d["PT_CNT"] / d["인구"] * 1e4
    el = d["고령인구"] / d["인구"] * 100
    r = np.corrcoef(el, rate)[0, 1]
    slope, icpt = np.polyfit(el, rate, 1)
    r_el_lst = np.corrcoef(el, d["ZS_MEAN"])[0, 1]
    print("[3] 생태학적 오류")
    print(f"  개인 수준: 65세 이상 출동 {old_ev}건 / {O:,}명 = {r_old:.2f}/1만 명, 65세 미만 {young_ev}건 / {P - O:,}명 = {r_young:.2f}/1만 명, 위험비 {r_old / r_young:.2f}")
    print(f"  65세 이상 비율: 인구 중 {O / P:.1%}, 출동 중 {old_ev / len(events):.1%}")
    print(f"  행정동 수준: r(고령비율, 출동률) = {r:.3f}, 기울기 {slope:.3f} (고령비율 10%p 증가당 {slope * 10:.2f}건), r(고령비율, 지표온도) = {r_el_lst:.3f}")
    # 행정동 안에서 연령별 출동률: 동마다 65세 이상과 미만의 출동률을 따로 구해 합산 비교
    j = gpd.sjoin(events, d[["동코드", "geometry"]], predicate="within")
    tab = j.assign(old=j["연령대"] == "65+").groupby("동코드")["old"].agg(["sum", "count"])
    dd = d.set_index("동코드").join(tab).fillna(0)
    hi = dd["고령인구"] / dd["인구"] >= np.median(el / 100)
    for name, m in (("고령비율 높은 절반", hi), ("낮은 절반", ~hi)):
        s = dd[m]
        ro = s["sum"].sum() / s["고령인구"].sum() * 1e4
        ry = (s["count"] - s["sum"]).sum() / (s["인구"] - s["고령인구"]).sum() * 1e4
        tot = s["count"].sum() / s["인구"].sum() * 1e4
        print(f"  {name} 동(75개): 전체 {tot:.2f}, 65세 이상 {ro:.2f}, 65세 미만 {ry:.2f}, 평균 지표온도 {s['ZS_MEAN'].mean():.2f}")
    fig_ecological(el, rate, slope, icpt, r, r_old, r_young)


def fig_ecological(el, rate, slope, icpt, r, r_old, r_young):
    s = Svg(720, 300, "왼쪽은 행정동 150개의 고령비율과 출동률 산점도로, 고령비율이 높은 동일수록 출동률이 오히려 조금 낮음. 오른쪽은 같은 자료를 개인 수준으로 본 연령별 출동률로, 65세 이상이 65세 미만의 약 3배임")
    gx, gy, gw, gh = 60, 40, 330, 200
    xmin, xmax = 10, 40
    ymax = float(np.ceil(rate.max() / 10) * 10)
    X = lambda v: gx + (v - xmin) / (xmax - xmin) * gw  # noqa: E731
    Y = lambda v: gy + gh - v / ymax * gh  # noqa: E731
    s.add(f'<rect x="{gx}" y="{gy}" width="{gw}" height="{gh}" class="s-mu" stroke-width="1" fill="none"/>')
    for t in range(10, 41, 10):
        s.text(X(t), gy + gh + 16, f"{t}%", size=11, cls="f-mu")
    for t in np.arange(0, ymax + 1, 10):
        s.text(gx - 6, Y(t) + 4, f"{t:.0f}", size=11, anchor="end", cls="f-mu")
    for a, b in zip(el, rate):
        s.circle(X(a), Y(b), 2.6, cls="f-ac")
    s.line(X(xmin), Y(icpt + slope * xmin), X(xmax), Y(icpt + slope * xmax), cls="s-bd", width=2)
    s.text(gx + gw / 2, 18, f"행정동 수준 (r = {r:.2f})", size=13, weight="600")
    s.text(gx + gw / 2, gy + gh + 34, "고령비율", size=11, cls="f-mu")
    s.text(gx - 6, gy - 8, "출동률 (1만 명당)", size=11, anchor="start", cls="f-mu")
    # 막대
    bx, by, bh = 480, 40, 200
    top = 30.0
    s.text(bx + 90, 24, "개인 수준 (연령별 출동률)", size=13, weight="600")
    for i, (name, v, cls) in enumerate((("65세 미만", r_young, "f-mu"), ("65세 이상", r_old, "f-bd"))):
        x = bx + 20 + i * 90
        h = v / top * bh
        s.rect(x, by + bh - h, 60, h, cls=cls, width=0)
        s.text(x + 30, by + bh - h - 6, f"{v:.1f}", size=12, weight="600")
        s.text(x + 30, by + bh + 16, name, size=11, cls="f-mu")
    s.line(bx, by + bh, bx + 200, by + bh, cls="s-mu", width=1)
    s.text(bx + 90, by + bh + 34, "인구 1만 명당 출동", size=11, cls="f-mu")
    s.save(os.path.join(OUT, "03-ecological.svg"))


if __name__ == "__main__":
    fig_toy()
    rows = scale_effect()
    zoning_effect(rows)
    ecological(rows)
