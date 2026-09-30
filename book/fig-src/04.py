"""4강 그림, 본문 수치, 연습용 파일.

- 04-edge.svg : 행정동을 연구 지역 가장자리 종류(행정 경계·해안선·안쪽)로 나눈 지도와 평균 이웃 수
- 04-gap.svg : 경계를 따로 그려 생긴 1 m 미만의 틈 때문에 인접 이웃이 사라지는 원리 (개념도)
- 04-missing.svg : 결측값을 처리하는 방법에 따른 모란 지수
- ../data/practice/hanbit_dong_digitized.gpkg : 해 보기용. 행정동 꼭짓점을 동마다 따로 0.5 m 안에서 흔든 파일

인접 가중치는 GeoStat 엔진의 공간가중치 함수(libpysal 퀸 인접)로 만들어 앱 결과와 같게 함.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/04.py
"""
import os
import sys
import warnings

import geopandas as gpd
import numpy as np
import shapely

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from svglib import Svg  # noqa: E402

warnings.filterwarnings("ignore")
import libpysal.weights as lw  # noqa: E402
from esda import Moran  # noqa: E402

from geostat_engine.analysis import weights as gw  # noqa: E402

DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "..", "fig")
PRACTICE = os.path.join(DATA, "practice")
os.makedirs(PRACTICE, exist_ok=True)

dong = gpd.read_file(os.path.join(DATA, "hanbit_dong.gpkg"))
boundary = gpd.read_file(os.path.join(DATA, "hanbit_boundary.gpkg"))
N = len(dong)


def queen(g):
    w, _ = gw.build(g, {"type": "queen"})
    return w, gw.summarize(w)


def links(w):
    return int(sum(w.cardinalities.values()) // 2)


W, SUM = queen(dong)


# ---------------------------------------------------------------- 1. 지오메트리 품질
def geometry_quality():
    print(f"[1] 원본 퀸 인접: 연결 {links(W)}개, 평균 이웃 {SUM['mean_neighbors']:.2f}, 최소 {SUM['min_neighbors']}, "
          f"최대 {SUM['max_neighbors']}, 섬 {SUM['n_islands']}")
    print(f"  이웃 수 분포: {[(h['neighbors'], h['count']) for h in SUM['histogram']]}")
    nverts = sum(len(g.exterior.coords) - 1 for g in dong.geometry)
    for tol in (25, 50, 100):
        s = dong.copy()
        s["geometry"] = s.geometry.simplify(tol, preserve_topology=True)
        ws, sm = queen(s)
        lost = sum(len(set(W.neighbors[i]) - set(ws.neighbors[i])) for i in range(N)) // 2
        print(f"  동마다 따로 {tol} m 단순화: 연결 {links(ws)}개 (끊어진 연결 {lost}개), 꼭짓점 {nverts} → "
              f"{sum(len(g.exterior.coords) - 1 for g in s.geometry)}")
    # 동마다 따로 흔든 파일 (연습용)
    rng = np.random.default_rng(20260930)

    def jitter(g, a):
        c = np.array(g.exterior.coords)
        c = c + rng.uniform(-a, a, c.shape)
        c[-1] = c[0]
        return shapely.Polygon(c)

    dig = dong.copy()
    dig["geometry"] = [jitter(g, 0.5) for g in dong.geometry]
    path = os.path.join(PRACTICE, "hanbit_dong_digitized.gpkg")
    if os.path.exists(path):
        os.remove(path)
    dig.to_file(path, layer="hanbit_dong_digitized", driver="GPKG")
    wd, sd = queen(dig)
    union = dig.union_all()
    gap = dong.union_all().area - union.area
    overlap = dig.area.sum() - union.area
    print(f"  꼭짓점을 동마다 따로 ±0.5 m 흔듦: 퀸 연결 {links(wd)}개, 섬 {sd['n_islands']}개; "
          f"틈 면적 합 {max(gap, 0):,.0f} ㎡, 겹침 면적 합 {overlap:,.0f} ㎡")
    fz = lw.fuzzy_contiguity(dig, tolerance=0, buffering=True, buffer=0.5)
    lost = sum(len(set(W.neighbors[i]) - set(fz.neighbors[i])) for i in range(N)) // 2
    gained = sum(len(set(fz.neighbors[i]) - set(W.neighbors[i])) for i in range(N)) // 2
    print(f"  동마다 0.5 m씩 넓힌 인접(fuzzy contiguity, 경계 사이 1 m 안): 연결 {links(fz)}개, 원본 대비 잃은 연결 {lost}, 더 생긴 연결 {gained}")
    wk, sk = gw.build(dig, {"type": "knn", "k": 5})[0], None
    same = sum(len(set(W.neighbors[i]) & set(wk.neighbors[i])) for i in range(N))
    print(f"  대안으로 KNN k=5: 이웃 {N * 5}개 가운데 원래 퀸 이웃과 같은 것 {same}개 ({same / (N * 5):.0%})")


# ---------------------------------------------------------------- 2. 경계 효과
def edge_effect():
    coast = boundary.loc[boundary["구분"] == "해안선"].geometry.iloc[0].buffer(1)
    admin = boundary.loc[boundary["구분"] == "행정 경계"].geometry.iloc[0].buffer(1)
    tc, ta = dong.intersects(coast).to_numpy(), dong.intersects(admin).to_numpy()
    card = np.array([W.cardinalities[i] for i in range(N)])
    groups = {
        "행정 경계에 닿음": ta & ~tc,
        "해안선에 닿음": tc & ~ta,
        "둘 다 닿음": ta & tc,
        "안쪽": ~ta & ~tc,
    }
    print("[2] 경계 효과 (퀸 인접 이웃 수)")
    stats = {}
    for k, m in groups.items():
        stats[k] = (int(m.sum()), float(card[m].mean()))
        print(f"  {k}: 동 {m.sum()}개, 평균 이웃 {card[m].mean():.2f}")
    lens = boundary.set_index("구분").length / 1000
    print(f"  경계 길이: 해안선 {lens['해안선']:.1f} km, 행정 경계 {lens['행정 경계']:.1f} km")
    # 해 보기용 예: 행정 경계에 닿은 동 하나와 안쪽 동 하나
    for k in ("행정 경계에 닿음", "안쪽"):
        idx = np.flatnonzero(groups[k])
        i = idx[np.argmin(np.abs(card[idx] - stats[k][1]))] if k == "안쪽" else idx[np.argmin(card[idx])]
        print(f"  예시 ({k}): {dong.loc[i, '동이름']} ({dong.loc[i, '동코드']}), 이웃 {card[i]}개: "
              f"{', '.join(dong.loc[sorted(W.neighbors[i]), '동이름'])}")
    fig_edge(groups, stats)


def fig_edge(groups, stats):
    bx0, by0, bx1, by1 = dong.total_bounds
    s = Svg(720, 330, "한빛시 행정동을 연구 지역 가장자리의 종류로 나눈 지도. 이웃 시와 맞닿은 행정 경계 쪽 동과 해안 쪽 동은 안쪽 동보다 이웃이 적음")
    w = 420
    k = w / (bx1 - bx0)
    x0, y0 = 20, 20
    cls = {"행정 경계에 닿음": "s-bg f-bds", "해안선에 닿음": "s-bg f-acs", "둘 다 닿음": "s-bg q2", "안쪽": "s-bg f-sf"}
    for name, m in groups.items():
        for g in dong.geometry[m]:
            s.polygon([(x0 + (x - bx0) * k, y0 + (by1 - y) * k) for x, y in g.exterior.coords], cls=cls[name], width=0.6)
    for _, row in boundary.iterrows():
        for ln in getattr(row.geometry, "geoms", [row.geometry]):
            d = "M" + " L".join(f"{x0 + (x - bx0) * k:.1f},{y0 + (by1 - y) * k:.1f}" for x, y in ln.coords)
            if row["구분"] == "해안선":
                s.path(d, cls="s-ac", width=3)
            else:
                s.add(f'<path d="{d}" class="s-bd" stroke-width="3" stroke-dasharray="7 4" fill="none"/>')
    lx = 470
    s.text(lx, 40, "가장자리 종류", size=13, anchor="start", weight="600")
    rows = [("행정 경계에 닿음", "f-bds"), ("해안선에 닿음", "f-acs"), ("둘 다 닿음", "q2"), ("안쪽", "f-sf")]
    for i, (name, c) in enumerate(rows):
        yy = 70 + i * 44
        s.rect(lx, yy - 12, 18, 18, cls=f"s-mu {c}", width=0.8)
        n, m = stats[name]
        s.text(lx + 28, yy + 2, f"{name} ({n}개)", size=12, anchor="start")
        s.text(lx + 28, yy + 19, f"평균 이웃 {m:.2f}개", size=11, anchor="start", cls="f-mu")
    yy = 70 + 4 * 44 + 6
    s.line(lx, yy, lx + 26, yy, cls="s-ac", width=3)
    s.text(lx + 34, yy + 4, "해안선: 바깥에 이웃이 없음", size=11, anchor="start", cls="f-mu")
    s.add(f'<path d="M{lx},{yy + 24} L{lx + 26},{yy + 24}" class="s-bd" stroke-width="3" stroke-dasharray="7 4" fill="none"/>')
    s.text(lx + 34, yy + 28, "행정 경계: 이웃이 자료 밖에 있음", size=11, anchor="start", cls="f-mu")
    s.save(os.path.join(OUT, "04-edge.svg"))


# ---------------------------------------------------------------- 3. 틈 개념도
def fig_gap():
    s = Svg(720, 250, "두 행정동이 경계를 공유하는 경우(왼쪽)와 각자 따로 그려 경계가 0.5 m 어긋난 경우(오른쪽). 눈으로는 같아 보여도, 꼭짓점이 정확히 같아야 이웃으로 인정하는 인접 가중치에서는 오른쪽 두 동이 이웃이 아님")
    for i, (title, off) in enumerate((("경계를 공유함", 0), ("따로 그려 어긋남 (크게 확대)", 1))):
        x0 = 40 + i * 350
        s.text(x0 + 140, 26, title, size=13, weight="600")
        A = [(x0, 50), (x0 + 140, 40), (x0 + 150, 120), (x0 + 135, 200), (x0, 210)]
        shared = [(x0 + 140, 40), (x0 + 150, 120), (x0 + 135, 200)]
        B = [(x0 + 140 + 12 * off, 40 - 3 * off), (x0 + 280, 45), (x0 + 285, 205), (x0 + 135 + 12 * off, 200 + 4 * off),
             (x0 + 150 + 10 * off, 120 - 6 * off)]
        s.polygon(A, cls="s-fg f-acs", width=1.5)
        s.polygon(B, cls="s-fg f-bds", width=1.5)
        s.text(x0 + 60, 130, "가 동", size=12)
        s.text(x0 + 220, 130, "나 동", size=12)
        for (px, py) in shared:
            s.circle(px, py, 4, cls="f-fg")
        if off:
            for (px, py) in B[:1] + B[3:5]:
                s.circle(px, py, 4, cls="f-bd")
        s.text(x0 + 140, 232, "퀸 인접: 이웃" if not off else "퀸 인접: 이웃 아님 (섬이 됨)", size=12,
               cls="f-ok" if not off else "f-bd", weight="600")
    s.save(os.path.join(OUT, "04-gap.svg"))


# ---------------------------------------------------------------- 4. 결측
def missing():
    el = (dong["고령인구"] / dong["인구"] * 100).to_numpy()
    w, _ = gw.build(dong, {"type": "queen"})
    w.transform = "r"
    full = Moran(el, w, permutations=0).I
    rng = np.random.default_rng(1)
    res = {"삭제": [], "0으로 채움": [], "전체 평균으로 채움": [], "이웃 평균으로 채움": []}
    isl = []
    for _ in range(300):
        miss = rng.choice(N, 15, replace=False)
        keep = np.setdiff1d(np.arange(N), miss)
        wf, _ = gw.build(dong, {"type": "queen"})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ws = lw.w_subset(wf, keep.tolist(), silence_warnings=True)
        isl.append(len(ws.islands))
        ws.transform = "r"
        res["삭제"].append(Moran(el[keep], ws, permutations=0).I)
        y = el.copy()
        y[miss] = 0
        res["0으로 채움"].append(Moran(y, w, permutations=0).I)
        y = el.copy()
        y[miss] = el[keep].mean()
        res["전체 평균으로 채움"].append(Moran(y, w, permutations=0).I)
        y = el.copy()
        ms = set(miss.tolist())
        for i in miss:
            nb = [j for j in wf.neighbors[i] if j not in ms]
            y[i] = el[nb].mean() if nb else el[keep].mean()
        res["이웃 평균으로 채움"].append(Moran(y, w, permutations=0).I)
    print(f"[3] 결측: 고령비율 모란 지수(퀸, 행 표준화) 전체 {full:.3f}; 무작위 15개 동(10%) 결측 300번")
    summ = {}
    for k, v in res.items():
        v = np.array(v)
        summ[k] = (v.mean(), *np.percentile(v, [5, 95]))
        print(f"  {k}: 평균 {v.mean():.3f}, 90% 범위 {np.percentile(v, 5):.3f}~{np.percentile(v, 95):.3f}")
    print(f"  삭제했을 때 섬이 생긴 경우 {np.mean(np.array(isl) > 0):.1%}")
    fig_missing(full, summ)


def fig_missing(full, summ):
    s = Svg(720, 290, "행정동 고령비율에서 무작위로 10%를 지우고 네 가지 방법으로 처리했을 때의 모란 지수(300번 반복의 평균과 90% 범위). 0으로 채우면 공간 구조가 크게 무너지고, 이웃 평균으로 채우면 조금 부풀려짐")
    gx, gy, gw_, gh = 190, 40, 460, 200
    X = lambda v: gx + v / 1.0 * gw_  # noqa: E731
    names = ["결측 없음"] + list(summ)
    vals = [(full, full, full)] + [summ[k] for k in summ]
    for t in (0, 0.2, 0.4, 0.6, 0.8, 1.0):
        s.line(X(t), gy, X(t), gy + gh, cls="s-mu", width=0.5, dash="2 3" if t else None)
        s.text(X(t), gy + gh + 16, f"{t:.1f}", size=11, cls="f-mu")
    s.line(X(full), gy, X(full), gy + gh, cls="s-ac", width=1.2, dash="5 3")
    bh = gh / len(names)
    for i, (name, (m, lo, hi)) in enumerate(zip(names, vals)):
        y = gy + i * bh + bh / 2
        s.text(gx - 10, y + 4, name, size=12, anchor="end")
        s.rect(gx, y - bh * 0.28, X(m) - gx, bh * 0.56, cls="f-ac" if i == 0 else "f-mu", width=0)
        if i:
            s.line(X(lo), y, X(hi), y, cls="s-fg", width=1.5)
            s.line(X(lo), y - 5, X(lo), y + 5, cls="s-fg", width=1.5)
            s.line(X(hi), y - 5, X(hi), y + 5, cls="s-fg", width=1.5)
        lx = X(max(m, hi)) + 8
        if lx - 4 < X(full) < lx + 34:  # 기준선과 겹치면 기준선 오른쪽으로 옮김
            lx = X(full) + 6
        s.text(lx, y + 4, f"{m:.2f}", size=12, anchor="start", weight="600")
    s.text(gx + gw_ / 2, gy + gh + 36, "고령비율의 모란 지수", size=12, cls="f-mu")
    s.text(gx + gw_ / 2, 22, "결측 10%를 처리하는 방법", size=13, weight="600")
    s.save(os.path.join(OUT, "04-missing.svg"))


if __name__ == "__main__":
    geometry_quality()
    edge_effect()
    fig_gap()
    missing()
