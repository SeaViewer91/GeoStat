"""10강 그림과 본문 수치.

- 10-grid.svg : 3×3 격자에서 룩·퀸 이웃과 행 표준화, 공간 시차 손계산
- 10-types.svg : 행정동 두 곳(도심·외곽)의 이웃이 가중치 종류(퀸, 퀸 2차, KNN 6, 거리 임계값)마다 어떻게 달라지는지
- 10-hist.svg : 가중치 종류별 이웃 수 분포
- 10-lag.svg : 고령비율과 그 공간 시차(이웃 평균)

가중치는 GeoStat 엔진의 weights.build(앱과 같음), Moran's I는 esda_ops.moran(앱 시드)으로 계산함.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/10.py
"""
import os
import sys
import warnings

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import MapFrame, dong_vars, draw, quantile5  # noqa: E402
from plotkit import Axes  # noqa: E402
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import esda_ops as eo  # noqa: E402
from geostat_engine.analysis import weights as gw  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
APP_SEED = 123456789

dong = dong_vars()
B = dong.total_bounds
TH = float(np.ceil(gw.suggest_threshold(dong)["threshold"] * 1000) / 1000)  # 앱이 채워 주는 값과 같게 올림
SPECS = {
    "퀸 1차": {"type": "queen"},
    "룩 1차": {"type": "rook"},
    "퀸 2차 (하위 포함)": {"type": "queen", "order": 2, "include_lower": True},
    "KNN 4": {"type": "knn", "k": 4},
    "KNN 6": {"type": "knn", "k": 6},
    f"거리 {TH:,.0f} m": {"type": "distance", "threshold": TH},
    f"역거리 {TH:,.0f} m": {"type": "distance", "threshold": TH, "inverse": True, "power": 1},
    "커널 (삼각, 적응 k=6)": {"type": "kernel", "k": 6, "function": "triangular", "fixed": False},
}
W = {k: gw.build(dong, v)[0] for k, v in SPECS.items()}


def card(w):
    return np.array([w.cardinalities[i] for i in range(w.n)])


# ---------------------------------------------------------------- 수치
def numbers():
    print(f"[임계값] 앱이 채워 주는 최소 거리 {TH:,.3f} m")
    print("[1] 가중치 요약과 Moran's I (순열 999, 앱 시드)")
    for name, w in W.items():
        sm = gw.summarize(w)
        out = []
        for col in ("고령비율", "출동률"):
            r = eo.moran(dong[col], w, 999, APP_SEED)
            out.append(f"{col} I {r.I:.3f} (p {r.p_sim:.3f})")
        print(f"  {name}: 이웃 평균 {sm['mean_neighbors']:.2f}, 최소 {sm['min_neighbors']}, 최대 {sm['max_neighbors']}, "
              f"비영 비율 {sm['pct_nonzero']:.2f}%, 대칭 {sm['symmetric']}, 섬 {sm['n_islands']} | {'; '.join(out)}")
    q, r = W["퀸 1차"], W["룩 1차"]
    same = all(set(q.neighbors[i]) == set(r.neighbors[i]) for i in range(q.n))
    print(f"  퀸과 룩의 이웃이 모든 동에서 같음: {same}")
    k6 = W["KNN 6"]
    asym = sum(1 for i in range(k6.n) for j in k6.neighbors[i] if i not in k6.neighbors[j])
    print(f"  KNN 6에서 한쪽만 이웃인 (i→j) 쌍 {asym}개 / 전체 {k6.n * 6}개")
    kn = W["커널 (삼각, 적응 k=6)"]
    print(f"  커널 가중치 자기 자신 포함: {all(i in kn.neighbors[i] for i in range(kn.n))}, 자기 가중치 {kn.weights[0][kn.neighbors[0].index(0)]:.3f}")
    d = W[f"거리 {TH:,.0f} m"]
    c = card(d)
    lo, hi = int(np.argmin(c)), int(np.argmax(c))
    print(f"  거리 임계값: 이웃 1개인 동 {(c == 1).sum()}개, 가장 많은 동 {dong['동이름'].iloc[hi]} {c[hi]}개 (면적 {dong['면적_km2'].iloc[hi]:.2f}㎢), "
          f"가장 적은 동 {dong['동이름'].iloc[lo]} {c[lo]}개 (면적 {dong['면적_km2'].iloc[lo]:.2f}㎢)")
    for nm in (dong["동이름"].iloc[hi], dong["동이름"].iloc[lo]):
        i = int(np.flatnonzero(dong["동이름"] == nm)[0])
        print(f"    {nm}: " + ", ".join(f"{k} {W[k].cardinalities[i]}" for k in ("퀸 1차", "퀸 2차 (하위 포함)", "KNN 6", f"거리 {TH:,.0f} m")))
    # 공간 시차
    wq = eo._row_standardized(W["퀸 1차"])
    lag = np.array([sum(wq.weights[i][k] * dong["고령비율"].iloc[j] for k, j in enumerate(wq.neighbors[i])) for i in range(wq.n)])
    i = int(np.flatnonzero(dong["동이름"] == "가람1동")[0])
    nb = W["퀸 1차"].neighbors[i]
    print(f"[2] 공간 시차 예: 가람1동 고령비율 {dong['고령비율'].iloc[i]:.2f}, 이웃 {[dong['동이름'].iloc[j] for j in nb]} "
          f"{[round(dong['고령비율'].iloc[j], 2) for j in nb]}, 시차 {lag[i]:.2f}")
    x = dong["고령비율"].to_numpy()
    print(f"  고령비율 표준편차 {x.std(ddof=1):.2f}, 공간 시차 표준편차 {lag.std(ddof=1):.2f}, 상관 {np.corrcoef(x, lag)[0, 1]:.3f}")
    print("[손계산] 3×3 격자 값 1..9 (행 순서)")
    g = np.arange(1, 10).reshape(3, 3)
    for (r_, c_), nm in (((1, 1), "가운데 5"), ((0, 0), "모서리 1"), ((0, 1), "변 2")):
        rook = [(r_ + a, c_ + b) for a, b in ((-1, 0), (1, 0), (0, -1), (0, 1)) if 0 <= r_ + a < 3 and 0 <= c_ + b < 3]
        queen = [(r_ + a, c_ + b) for a in (-1, 0, 1) for b in (-1, 0, 1) if (a, b) != (0, 0) and 0 <= r_ + a < 3 and 0 <= c_ + b < 3]
        rv = [g[p] for p in rook]
        qv = [g[p] for p in queen]
        print(f"  {nm}: 룩 이웃 {rv} → 합 {sum(rv)}, 평균 {np.mean(rv):.2f}; 퀸 이웃 {qv} → 합 {sum(qv)}, 평균 {np.mean(qv):.2f}")
    return lag


# ---------------------------------------------------------------- 그림 1. 3×3 격자
def fig_grid():
    W_, H = 720, 250
    s = Svg(W_, H, "3×3 격자에서 가운데 칸(5)과 모서리 칸(1)의 이웃. 룩은 변을, 퀸은 변이나 꼭짓점을 공유하는 칸을 이웃으로 침. "
                   "행 표준화하면 이웃의 가중치가 1/이웃 수가 되어, 공간 시차는 이웃의 평균이 됨")
    g = np.arange(1, 10).reshape(3, 3)
    cases = [("룩: 가운데", (1, 1), "rook"), ("퀸: 가운데", (1, 1), "queen"), ("룩: 모서리", (0, 0), "rook"), ("퀸: 모서리", (0, 0), "queen")]
    cell = 40
    for k, (title, (r0, c0), kind) in enumerate(cases):
        x0 = 30 + k * 172
        y0 = 40
        s.text(x0 + cell * 1.5, 26, title, size=12, weight="600")
        nb = []
        for a in (-1, 0, 1):
            for b in (-1, 0, 1):
                if (a, b) == (0, 0):
                    continue
                if kind == "rook" and a != 0 and b != 0:
                    continue
                r, c = r0 + a, c0 + b
                if 0 <= r < 3 and 0 <= c < 3:
                    nb.append((r, c))
        for r in range(3):
            for c in range(3):
                css = "s-fg f-bd" if (r, c) == (r0, c0) else ("s-fg f-acs" if (r, c) in nb else "s-mu f-bg")
                s.rect(x0 + c * cell, y0 + r * cell, cell, cell, cls=css, width=1)
                s.text(x0 + c * cell + cell / 2, y0 + r * cell + cell / 2 + 5, str(g[r, c]), size=13,
                       cls="f-bg" if (r, c) == (r0, c0) else "f-fg", weight="600")
        vals = [g[p] for p in nb]
        s.text(x0 + cell * 1.5, y0 + 3 * cell + 22, f"이웃 {len(nb)}개, 가중치 각 1/{len(nb)}", size=11, cls="f-mu")
        s.text(x0 + cell * 1.5, y0 + 3 * cell + 40, f"공간 시차 = {sum(vals)}/{len(nb)} = {np.mean(vals):.2f}", size=11)
    s.rect(240, H - 22, 12, 12, cls="s-fg f-bd", width=1)
    s.text(256, H - 12, "기준 칸", size=11, anchor="start")
    s.rect(330, H - 22, 12, 12, cls="s-fg f-acs", width=1)
    s.text(346, H - 12, "이웃", size=11, anchor="start")
    s.save(os.path.join(OUT, "10-grid.svg"))


# ---------------------------------------------------------------- 그림 2. 가중치 종류별 이웃
def fig_types():
    W_, H = 720, 300
    d = W[f"거리 {TH:,.0f} m"]
    c = card(d)
    foci = [int(np.argmax(c)), int(np.argmin(c))]
    kinds = ["퀸 1차", "퀸 2차 (하위 포함)", "KNN 6", f"거리 {TH:,.0f} m"]
    s = Svg(W_, H, f"도심의 작은 동(위)과 외곽의 넓은 동(아래)의 이웃이 가중치 종류마다 어떻게 달라지는지. 주황이 기준 동, 파랑이 이웃. "
                   f"거리 임계값({TH:,.0f} m)에서는 도심 동의 이웃이 {c[foci[0]]}개, 외곽 동은 {c[foci[1]]}개로 크게 차이 남")
    mw = 152
    for row, f in enumerate(foci):
        for col, kind in enumerate(kinds):
            fr = MapFrame(B, 76 + col * (mw + 6), 34 + row * 130, mw)
            nb = set(W[kind].neighbors[f])
            css = ["f-bd" if i == f else ("f-ac" if i in nb else "f-sf") for i in range(len(dong))]
            draw(s, fr, dong.geometry, css, width=0.3)
            if row == 0:
                s.text(fr.x + mw / 2, 24, kind, size=12, weight="600")
            s.text(fr.x + mw / 2, fr.y + fr.h + 12, f"이웃 {W[kind].cardinalities[f]}개", size=11, cls="f-mu")
        s.text(70, 34 + row * 130 + 55, dong["동이름"].iloc[f], size=11, anchor="end")
    s.save(os.path.join(OUT, "10-types.svg"))


# ---------------------------------------------------------------- 그림 3. 이웃 수 분포
def fig_hist():
    W_, H = 720, 230
    kinds = ["퀸 1차", "KNN 6", f"거리 {TH:,.0f} m"]
    s = Svg(W_, H, "가중치 종류별 행정동의 이웃 수 분포. 퀸은 2~8개, KNN은 모두 6개, 거리 임계값은 1개에서 22개까지 크게 퍼짐")
    for i, kind in enumerate(kinds):
        c = card(W[kind])
        edges = np.arange(-0.5, 23.5, 1)
        h = np.histogram(c, edges)[0]
        ax = Axes(s, 40 + i * 230, 40, 190, 130, (-0.5, 22.5), (0, 160))
        s.text(ax.x0 + 95, 24, kind, size=12, weight="600")
        ax.hist(h, edges, width=0.4)
        ax.xaxis(ticks=[0, 5, 10, 15, 20], label="이웃 수")
        ax.yaxis(ticks=[0, 50, 100, 150])
    s.save(os.path.join(OUT, "10-hist.svg"))


# ---------------------------------------------------------------- 그림 4. 공간 시차
def fig_lag(lag):
    W_, H = 720, 300
    x = dong["고령비율"].to_numpy()
    s = Svg(W_, H, "행정동 고령비율(왼쪽)과 퀸 인접 행 표준화 가중치로 구한 공간 시차, 즉 이웃 동 고령비율의 평균(오른쪽). "
                   "두 지도는 같은 계급 경계(왼쪽의 5분위)를 씀. 공간 시차는 값을 이웃과 평균하므로 더 매끄러움")
    from geostat_engine.analysis.classify import classify
    import pandas as pd
    c = classify(pd.Series(x, name="x"), "quantile", 5)
    bins = np.array(c.breaks)
    cls_x = np.minimum(np.searchsorted(bins, x, side="left"), 4)
    cls_l = np.minimum(np.searchsorted(bins, lag, side="left"), 4)
    for k, (title, cl) in enumerate((("고령비율", cls_x), ("공간 시차 (이웃 평균)", cls_l))):
        fr = MapFrame(B, 30 + k * 350, 36, 320)
        s.text(fr.x + 160, 24, title, size=13, weight="600")
        draw(s, fr, dong.geometry, [f"q{v}" for v in cl], width=0.3)
    ly = 36 + MapFrame(B, 0, 0, 320).h + 22
    bx = W_ / 2 - 100
    for k in range(5):
        s.rect(bx + k * 40, ly - 6, 40, 12, cls=f"s-bg q{k}", width=0.5)
    s.text(bx - 6, ly + 4, "낮음", size=11, anchor="end", cls="f-mu")
    s.text(bx + 206, ly + 4, "높음 (고령비율 5분위 경계)", size=11, anchor="start", cls="f-mu")
    s.save(os.path.join(OUT, "10-lag.svg"))
    print(f"[그림4] 계급별 동 수 원래 {np.bincount(cls_x, minlength=5).tolist()}, 시차 {np.bincount(cls_l, minlength=5).tolist()}")


if __name__ == "__main__":
    lag = numbers()
    fig_grid()
    fig_types()
    fig_hist()
    fig_lag(lag)
