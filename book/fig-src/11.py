"""11강 그림과 본문 수치.

- 11-patterns.svg : 3×3 격자의 세 배치(뭉침, 바둑판, 섞임)와 Moran's I (룩 인접, 이진)
- 11-scatter.svg : 고령비율의 Moran 산점도와 사분면 지도
- 11-correlogram.svg : 퀸 인접 차수별(1~6차, 하위 차수 미포함) Moran's I

Moran's I는 GeoStat 엔진의 esda_ops.moran(앱 시드 123456789), Join Count는 esda_ops.join_counts,
Geary's C와 General G는 앱에 없어 esda로 직접 계산함.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/11.py
"""
import os
import sys
import warnings

import esda
import libpysal as lps
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import MapFrame, dong_vars, draw  # noqa: E402
from plotkit import Axes  # noqa: E402
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import esda_ops as eo  # noqa: E402
from geostat_engine.analysis import fields  # noqa: E402
from geostat_engine.analysis import weights as gw  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
APP_SEED = 123456789

dong = dong_vars()
B = dong.total_bounds
WQ = gw.build(dong, {"type": "queen"})[0]
PATS = {
    "뭉침": [[1, 1, 0], [1, 1, 0], [0, 0, 0]],
    "바둑판": [[1, 0, 1], [0, 1, 0], [1, 0, 1]],
    "섞임": [[1, 0, 0], [0, 0, 1], [0, 1, 1]],
}


def rook3():
    W = np.zeros((9, 9))
    for r in range(3):
        for c in range(3):
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if 0 <= r + dr < 3 and 0 <= c + dc < 3:
                    W[r * 3 + c, (r + dr) * 3 + c + dc] = 1
    return W


def hand():
    W = rook3()
    print(f"[손계산] 3×3 격자, 룩 인접 이진, S0 = {W.sum():.0f}, E[I] = −1/8 = {-1 / 8}")
    res = {}
    for k, p in PATS.items():
        x = np.array(p, float).ravel()
        z = x - x.mean()
        num, den = z @ W @ z, z @ z
        I = 9 / W.sum() * num / den
        bb = int(sum(W[i, j] for i in range(9) for j in range(9) if x[i] == 1 and x[j] == 1) / 2)
        bw = int(sum(W[i, j] for i in range(9) for j in range(9) if x[i] != x[j]) / 2)
        res[k] = I
        print(f"  {k}: 평균 {x.mean():.4f}, Σw z z = {num:.4f} ({num * 81:.0f}/81), Σz² = {den:.4f} ({den * 81:.0f}/81), I = {I:.4f}, BB {bb}, BW {bw}, WW {12 - bb - bw}")
    return res


def numbers():
    print("[1] 전역 Moran's I (퀸, 행 표준화, 순열 999, 앱 시드): 세 가지 추론")
    wr = eo._row_standardized(WQ)
    for col in ("고령비율", "출동률", "ZS_MEAN"):
        x = dong[col].to_numpy(float)
        np.random.seed(APP_SEED)
        m = esda.Moran(x, wr, transformation="r", permutations=999)
        print(f"  {col}: I {m.I:.4f}, E[I] {m.EI:.4f}, 정규 z {m.z_norm:.2f} (p {m.p_norm:.2g}), 무작위화 z {m.z_rand:.2f} (p {m.p_rand:.2g}), "
              f"순열 z {m.z_sim:.2f} (유사 p {m.p_sim:.3f}), 순열 분포 표준편차 {m.seI_sim:.4f}, 정규 분산의 제곱근 {np.sqrt(m.VI_norm):.4f}")
    print("[2] Geary's C와 General G (esda, 순열 999, 시드 고정)")
    wb = lps.weights.W(WQ.neighbors)
    for col in ("고령비율", "출동률", "ZS_MEAN"):
        x = dong[col].to_numpy(float)
        np.random.seed(APP_SEED)
        g = esda.Geary(x, wr, transformation="r", permutations=999)
        np.random.seed(APP_SEED)
        G = esda.G(x, wb, permutations=999)
        print(f"  {col}: Geary C {g.C:.4f} (E 1, z {g.z_norm:.2f}, 유사 p {g.p_sim:.3f}); General G {G.G:.5f} (E {G.EG:.5f}, z {G.z_norm:.2f}, 유사 p {G.p_sim:.3f})")
    print("[3] Join Count: 고령상위 = 고령비율 > 26.67 (Q3)")
    b = fields.evaluate(dong, "`고령비율` > 26.67").rename("고령상위")
    q3 = np.percentile(dong["고령비율"], 75)
    n1 = int(b.sum())
    eb = 0.5 * 812 * n1 * (n1 - 1) / (150 * 149)
    r = eo.join_counts(b, WQ, 999)
    print(f"  Q3 = {q3:.3f}, 1인 동 {n1}개; 관측 BB {r['bb']:.0f}, BW {r['bw']:.0f}, WW {r['ww']:.0f} (합 {r['joins']:.0f}); "
          f"순열 평균 BB {r['mean_bb']:.2f}, BW {r['mean_bw']:.2f}; 유사 p BB {r['p_sim_bb']:.3f}, BW {r['p_sim_bw']:.3f}; 해석적 E[BB] {eb:.2f}")
    print("[4] 차수별 Moran's I (퀸 k차, 하위 차수 미포함)")
    cg = {}
    for col in ("고령비율", "출동률", "ZS_MEAN"):
        row = []
        for k in range(1, 7):
            w = gw.build(dong, {"type": "queen", "order": k, "include_lower": False})[0]
            r = eo.moran(dong[col], w, 999, APP_SEED)
            row.append((k, r.I, r.p_sim, float(np.mean([w.cardinalities[i] for i in range(w.n)]))))
        cg[col] = row
        print(f"  {col}: " + ", ".join(f"{k}차 {I:.3f} (p {p:.3f}, 이웃 {nb:.1f})" for k, I, p, nb in row))
    print("[5] 사분면 (고령비율, 퀸)")
    x = dong["고령비율"].to_numpy(float)
    z = (x - x.mean()) / x.std()
    lag = np.array([np.mean([z[j] for j in WQ.neighbors[i]]) for i in range(WQ.n)])
    q = np.where(z >= 0, np.where(lag >= 0, 1, 4), np.where(lag >= 0, 3, 2))
    print(f"  HH {(q == 1).sum()}, LL {(q == 2).sum()}, LH {(q == 3).sum()}, HL {(q == 4).sum()}; 기울기 {np.polyfit(z, lag, 1)[0]:.4f}")
    return cg, z, lag, q


# ---------------------------------------------------------------- 그림
def fig_patterns(res):
    W_, H = 720, 220
    s = Svg(W_, H, "3×3 격자에 1(주황)과 0(흰색)을 세 가지로 배치하고 룩 인접 이진 가중치로 구한 Moran's I. 같은 값끼리 붙으면 양수, "
                   "바둑판처럼 번갈아 놓이면 음수, 섞여 있으면 무작위일 때의 기댓값 −0.125 근처임")
    cell = 40
    for k, (name, p) in enumerate(PATS.items()):
        x0 = 80 + k * 210
        s.text(x0 + 60, 26, name, size=13, weight="600")
        for r in range(3):
            for c in range(3):
                s.rect(x0 + c * cell, 38 + r * cell, cell, cell, cls="s-fg f-bd" if p[r][c] else "s-fg f-bg", width=1)
                s.text(x0 + c * cell + cell / 2, 38 + r * cell + cell / 2 + 5, str(p[r][c]), size=13,
                       cls="f-bg" if p[r][c] else "f-fg", weight="600")
        s.text(x0 + 60, 38 + 3 * cell + 26, f"I = {res[name]:.3f}".replace("-", "−"), size=13, weight="600")
    s.save(os.path.join(OUT, "11-patterns.svg"))


def fig_scatter(z, lag, q):
    W_, H = 720, 320
    s = Svg(W_, H, "왼쪽: 고령비율의 Moran 산점도. 가로축은 표준화한 고령비율, 세로축은 이웃의 평균(공간 시차). 회귀선의 기울기가 Moran's I(0.81)임. "
                   "오른쪽: 각 동이 어느 사분면에 있는지 칠한 지도. 유의성은 따지지 않은 것으로, 유의성을 따지는 것은 12강의 LISA임")
    ax = Axes(s, 60, 30, 260, 240, (-2.5, 2.5), (-2.5, 2.5))
    ax.xaxis(ticks=[-2, -1, 0, 1, 2], label="고령비율 (표준화)")
    ax.yaxis(ticks=[-2, -1, 0, 1, 2], label="이웃 평균 (공간 시차, 표준화)")
    ax.curve([-2.5, 2.5], [0, 0], cls="s-mu", width=0.8)
    ax.curve([0, 0], [-2.5, 2.5], cls="s-mu", width=0.8)
    css = {1: "d5", 2: "d0", 3: "d2", 4: "d3"}
    for a, b, k in zip(z, lag, q):
        s.circle(float(ax.X(a)), float(ax.Y(b)), 3, cls=f"s-fg {css[k]}", width=0.5)
    sl = np.polyfit(z, lag, 1)
    ax.curve([-2.5, 2.5], [sl[1] + sl[0] * -2.5, sl[1] + sl[0] * 2.5], cls="s-fg", width=1.6)
    for (tx, ty, t) in ((2.1, 2.2, "HH"), (-2.1, -2.2, "LL"), (-2.1, 2.2, "LH"), (2.1, -2.2, "HL")):
        s.text(float(ax.X(tx)), float(ax.Y(ty)) + 4, t, size=12, weight="600")
    s.text(float(ax.X(0.3)), float(ax.Y(-1.5)), f"회귀선 기울기 = I = {sl[0]:.2f}", size=11, anchor="start")
    fr = MapFrame(B, 380, 40, 320)
    draw(s, fr, dong.geometry, [css[k] for k in q], width=0.3)
    items = [("d5", f"HH {int((q == 1).sum())}"), ("d0", f"LL {int((q == 2).sum())}"), ("d2", f"LH {int((q == 3).sum())}"), ("d3", f"HL {int((q == 4).sum())}")]
    x = 400
    for c_, lab in items:
        s.rect(x, H - 34, 12, 12, cls=f"s-mu {c_}", width=0.5)
        s.text(x + 16, H - 24, lab, size=11, anchor="start")
        x += 72
    s.save(os.path.join(OUT, "11-scatter.svg"))


def fig_correlogram(cg):
    W_, H = 720, 290
    s = Svg(W_, H, "퀸 인접 차수별 Moran's I(코렐로그램). k차는 정확히 k단계 떨어진 이웃만 씀. 고령비율과 지표온도는 가까울수록 크게 닮고 "
                   "멀어질수록 닮음이 줄다가 음수가 됨. 출동률은 1차에서만 약하게 닮음. 속이 찬 점은 유사 p ≤ 0.05")
    ax = Axes(s, 70, 30, 440, 210, (0.5, 6.5), (-0.4, 0.9))
    ax.yaxis(ticks=[-0.4, -0.2, 0, 0.2, 0.4, 0.6, 0.8], fmt=lambda t: f"{t:.1f}", label="Moran's I", grid=True)
    ax.xaxis(ticks=[1, 2, 3, 4, 5, 6], fmt=lambda t: f"{int(t)}차", label="퀸 인접 차수 (이웃의 이웃의 …)")
    ax.curve([0.5, 6.5], [-1 / 149, -1 / 149], cls="s-mu", width=1)
    series = [("고령비율", "s-bd", "f-bd"), ("ZS_MEAN", "s-ac", "f-ac"), ("출동률", "s-ok", "f-ok")]
    names = {"고령비율": "고령비율", "ZS_MEAN": "동 평균 지표온도", "출동률": "출동률"}
    for i, (col, sc, fc) in enumerate(series):
        row = cg[col]
        ax.curve([r[0] for r in row], [r[1] for r in row], cls=sc, width=2)
        for k, I, p, _ in row:
            s.circle(float(ax.X(k)), float(ax.Y(I)), 4, cls=f"{sc} {fc}" if p <= 0.05 else f"{sc} f-bg", width=1.4)
        y = 70 + i * 28
        s.line(540, y, 562, y, cls=sc, width=2)
        s.text(570, y + 4, names[col], size=11, anchor="start")
    s.text(540, 170, "회색 선: 무작위일 때의 E[I]", size=10, anchor="start", cls="f-mu")
    s.save(os.path.join(OUT, "11-correlogram.svg"))


if __name__ == "__main__":
    res = hand()
    cg, z, lag, q = numbers()
    fig_patterns(res)
    fig_scatter(z, lag, q)
    fig_correlogram(cg)
