"""42강 그림과 본문 수치.

- 42-map.svg : 같은 결과를 두 가지로 그린 지도. 왼쪽은 흔히 보는 지도(원비율, 등간격, 범례 정보 부족),
               오른쪽은 보고서용 지도(EB 비율 LISA·FDR, 범례에 개수, 축척 막대, 방위, 방법 주석)

EB 비율 LISA는 GeoStat 엔진 함수(앱과 같은 시드 123456789)로 계산함.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/42.py
"""
import os
import sys
import warnings

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import MapFrame, draw, outline  # noqa: E402
from regkit import load_dong, queen  # noqa: E402
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import esda_ops  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")


def main():
    d = load_dong()
    W = queen(d)
    r = esda_ops.local("lisa_eb", d["PT_CNT"].astype(float).rename("PT_CNT"), W, 999, 123456789, 0.05, "fdr", y=d["인구"].astype(float).rename("인구"))
    codes = {1: "High-High", 2: "Low-High", 3: "Low-Low", 4: "High-Low"}
    cnt = {k: int((r.cluster == k).sum()) for k in codes}
    print(f"[EB 비율 LISA, 퀸, 999회, FDR] 유의 기준 p ≤ {r.threshold:.4f}; 군집 {cnt}; 유의하지 않음 {int((r.cluster == 0).sum())}")
    rate = d["출동률"].to_numpy()
    edges = np.linspace(rate.min(), rate.max(), 6)
    k = np.clip(np.searchsorted(edges, rate, side="right") - 1, 0, 4)
    print(f"[등간격 5계급] 경계 {np.round(edges, 2).tolist()}, 계급별 개수 {np.bincount(k, minlength=5).tolist()}")

    W_, H = 720, 380
    svg = Svg(W_, H, f"같은 출동 자료를 두 가지로 그린 지도. 왼쪽: 흔히 보는 지도. 원비율을 등간격 5계급으로 칠해, 인구 적은 동 몇 개의 극단값 때문에 150개 동 가운데 {np.bincount(k, minlength=5)[:2].sum()}개가 옅은 두 계급에 몰리고, "
                     "범례에 단위·계급 방법·기간이 없음. 오른쪽: 보고서용 지도. EB 비율 LISA(퀸, 순열 999회, FDR 5%)의 유의한 군집만 칠하고, 범례에 개수, 축척 막대, 방위 표시, 방법과 자료의 주석을 넣음")
    mw = 320
    seq = ["#fff1e0", "#fdc98f", "#f98f45", "#d9530f", "#8c2d04"]
    fr = MapFrame(d.total_bounds, 20, 40, mw)
    draw(svg, fr, d.geometry, None, width=0.3, stroke="s-bg", fills=[seq[i] for i in k])
    outline(svg, fr, d.union_all(), cls="s-fg", width=0.8)
    svg.text(fr.x + mw / 2, 26, "흔한 지도", size=12, weight="600")
    y = 40 + fr.h + 44
    for i in range(5):
        xx, yy = fr.x + (i % 3) * 100, y + (i // 3) * 16
        svg.rect(xx, yy - 10, 12, 12, cls="s-mu", width=0.5, fill=seq[i])
        svg.text(xx + 16, yy, f"{edges[i]:.1f}–{edges[i + 1]:.1f}", size=10, anchor="start")
    svg.text(fr.x, y + 36, "출동률", size=10, anchor="start", cls="f-mu")

    col = {0: "#eeeeee", 1: "#d7191c", 2: "#abd9e9", 3: "#2c7bb6", 4: "#fdae61"}
    fr2 = MapFrame(d.total_bounds, 380, 40, mw)
    draw(svg, fr2, d.geometry, None, width=0.3, stroke="s-bg", fills=[col[int(c)] for c in r.cluster])
    outline(svg, fr2, d.union_all(), cls="s-fg", width=0.8)
    svg.text(fr2.x + mw / 2, 26, "보고서용 지도", size=12, weight="600")
    # 방위와 축척
    nx, ny = fr2.x + mw - 18, 58
    svg.polygon([(nx, ny - 14), (nx - 6, ny + 2), (nx, ny - 2), (nx + 6, ny + 2)], cls="f-fg s-fg", width=0.5)
    svg.text(nx, ny + 16, "N", size=10)
    x0, y0 = d.total_bounds[0], d.total_bounds[1]
    X0, Y0 = fr2.xy(x0 + 1000, y0)
    X1, _ = fr2.xy(x0 + 6000, y0)
    sy = Y0 + 12
    svg.line(X0, sy, X1, sy, cls="s-fg", width=2)
    svg.line(X0, sy - 4, X0, sy, cls="s-fg", width=1)
    svg.line(X1, sy - 4, X1, sy, cls="s-fg", width=1)
    svg.text((X0 + X1) / 2, sy + 13, "5 km", size=10)
    y = 40 + fr2.h + 44
    items = [(1, "High-High"), (3, "Low-Low"), (2, "Low-High"), (4, "High-Low"), (0, "유의하지 않음")]
    for j, (c, lab) in enumerate(items):
        n = int((r.cluster == c).sum())
        xx = fr2.x + (j % 3) * 110
        yy = y + (j // 3) * 16
        svg.rect(xx, yy - 10, 12, 12, cls="s-mu", width=0.5, fill=col[c])
        svg.text(xx + 16, yy, f"{lab} ({n})", size=10, anchor="start")
    y += 36
    svg.text(fr2.x, y, "2025년 6~8월 폭염 관련 구급 출동, 행정동 150개. EB 비율 LISA(분모: 인구),", size=9, anchor="start", cls="f-mu")
    svg.text(fr2.x, y + 12, "1차 퀸 인접(행 표준화), 순열 999회(시드 123456789), FDR 5%", size=9, anchor="start", cls="f-mu")
    svg.save(os.path.join(OUT, "42-map.svg"))


if __name__ == "__main__":
    main()
