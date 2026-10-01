"""12강 그림과 본문 수치.

- 12-cluster.svg : 고령비율 LISA. 군집 지도(보정 없음), 유의성 지도, 군집 지도(FDR)
- 12-rate.svg : 출동률 LISA 군집 지도(보정 없음). FDR로 보정하면 남는 동이 없음
- 12-random.svg : 고령비율 값을 행정동에 무작위로 섞은 자료 200개에서 LISA가 '유의'로 찍는 동의 수

LISA는 GeoStat 엔진의 esda_ops.local(앱과 같은 Moran_Local, 조건부 순열 999, 시드 123456789)로 계산함.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/12.py
"""
import os
import sys
import warnings

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import MapFrame, dong_vars, draw  # noqa: E402
from plotkit import Axes  # noqa: E402
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import esda_ops as eo  # noqa: E402
from geostat_engine.analysis import weights as gw  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
APP_SEED = 123456789
SEED = 20261001

dong = dong_vars()
B = dong.total_bounds
WQ = gw.build(dong, {"type": "queen"})[0]
CL_FILL = {0: "#eeeeee", 1: "#ff0000", 2: "#0000ff", 3: "#a7adf9", 4: "#f4ada8", 5: "#464646"}  # 앱의 LISA 색
CL_NAME = {0: "유의하지 않음", 1: "High-High", 2: "Low-Low", 3: "Low-High", 4: "High-Low"}
SIG_FILL = ["#1a9641", "#3ca94f", "#76c35b", "#a6d96a", "#eeeeee"]


def lisa(col, corr="none", perms=999):
    return eo.local("lisa", dong[col], WQ, perms, APP_SEED, 0.05, corr)


def counts(L):
    return {CL_NAME[k]: int(L.counts.get(k, 0)) for k in range(1, 5)}


def hand():
    print("[손계산] 3×3 '뭉침'(1,1,0 / 1,1,0 / 0,0,0), 룩 인접 행 표준화, I_i = (n−1) z_i (Wz)_i / Σz²")
    x = np.array([1, 1, 0, 1, 1, 0, 0, 0, 0], float)
    W = np.zeros((9, 9))
    for r in range(3):
        for c in range(3):
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if 0 <= r + dr < 3 and 0 <= c + dc < 3:
                    W[r * 3 + c, (r + dr) * 3 + c + dc] = 1
    Wr = W / W.sum(1, keepdims=True)
    z = x - x.mean()
    lag = Wr @ z
    Ii = 8 * z * lag / (z @ z)
    for i, nm in ((0, "왼쪽 위(1)"), (4, "가운데(1)"), (2, "오른쪽 위(0)"), (8, "오른쪽 아래(0)"), (6, "왼쪽 아래(0)")):
        print(f"  {nm}: z {z[i]:.4f}, 이웃 {np.flatnonzero(W[i]).tolist()}, Wz {lag[i]:.4f}, I_i {Ii[i]:.4f}")
    print(f"  I_i 합 {Ii.sum():.4f}, (n−1) × 전역 I(행 표준화) = {8 * (9 / 9) * (z @ Wr @ z) / (z @ z):.4f}")


def numbers():
    print("[1] 고령비율 LISA (퀸, 순열 999, 앱 시드)")
    res = {}
    for corr in ("none", "fdr", "bonferroni"):
        for P in (999, 9999):
            L = lisa("고령비율", corr, P)
            res[(corr, P)] = L
            n = sum(counts(L).values())
            print(f"  {corr} 순열 {P}: 유의 {n}개 {counts(L)}, 기준 p ≤ {L.threshold:.4g}")
    L = res[("none", 999)]
    print(f"  국지 I의 합 {np.nansum(L.stat):.2f}, 149 × 전역 I = {149 * 0.8116:.2f}")
    p = L.p
    pp = p * (1 - 1e-6)
    print(f"  유의성 구간: p ≤ 0.001 {(pp <= 0.001).sum()}개 (보정 안 한 비교로는 {(p <= 0.001).sum()}개), ≤ 0.01 {(pp <= 0.01).sum()}, ≤ 0.05 {(pp <= 0.05).sum()}")
    # 유의한 HH 동의 이웃 가운데 유의하지 않은 동
    hh = np.flatnonzero(L.cluster == 1)
    nb = set(j for i in hh for j in WQ.neighbors[i]) - set(hh)
    print(f"  유의한 HH {len(hh)}개 동의 이웃이면서 HH로 찍히지 않은 동 {len(nb)}개 (그 가운데 사분면이 HH인 동 {sum(1 for j in nb if L.stat[j] > 0 and dong['고령비율'].iloc[j] > dong['고령비율'].mean())}개)")
    card = np.array([WQ.cardinalities[i] for i in range(WQ.n)])
    sig = L.cluster > 0
    print(f"  이웃 4개 이하 동 {(card <= 4).sum()}개 가운데 유의 {(sig & (card <= 4)).sum()}개 ({(sig & (card <= 4)).sum() / (card <= 4).sum():.0%}), "
          f"5개 이상 {(card >= 5).sum()}개 가운데 {(sig & (card >= 5)).sum()}개 ({(sig & (card >= 5)).sum() / (card >= 5).sum():.0%})")
    print("[2] 출동률 LISA")
    for corr in ("none", "fdr"):
        Lr = lisa("출동률", corr)
        print(f"  {corr}: 유의 {sum(counts(Lr).values())}개 {counts(Lr)}, 기준 p ≤ {Lr.threshold:.4g}, 가장 작은 p {np.nanmin(Lr.p):.4f}")
        if corr == "none":
            for k in (1, 2, 3, 4):
                names = dong.loc[Lr.cluster == k, "동이름"].tolist()
                print(f"    {CL_NAME[k]}: {names}")
            res["rate"] = Lr
    print("[3] 무작위로 섞은 고령비율 200개")
    rng = np.random.default_rng(SEED)
    x = dong["고령비율"].to_numpy(float)
    raw, fdr, ex = [], [], None
    for k in range(200):
        xs = pd.Series(rng.permutation(x), name="섞음")
        L0 = eo.local("lisa", xs, WQ, 999, APP_SEED, 0.05, "none")
        n0 = int((L0.cluster > 0).sum() - (L0.cluster == 5).sum())
        raw.append(n0)
        thr = eo._threshold(L0.p, 0.05, "fdr")
        fdr.append(int((L0.p <= thr).sum()))
        if k == 0:
            ex = L0
            print(f"  첫 번째 섞음: 유의 {n0}개 {counts(L0)}")
    raw, fdr = np.array(raw), np.array(fdr)
    print(f"  보정 없음: 평균 {raw.mean():.2f}개, 범위 {raw.min()}~{raw.max()}, 0개인 경우 {(raw == 0).mean():.1%}")
    print(f"  FDR: 평균 {fdr.mean():.3f}개, 1개 이상인 경우 {(fdr > 0).mean():.1%}")
    return res, raw, fdr, ex


# ---------------------------------------------------------------- 그림
def legend(s, x, y, items):
    for fill, label in items:
        s.rect(x, y - 10, 12, 12, cls="s-mu", width=0.5, fill=fill)
        s.text(x + 16, y, label, size=10, anchor="start")
        x += 18 + len(label) * 6.4 + 10


def fig_cluster(res):
    W_, H = 720, 280
    L, Lf = res[("none", 999)], res[("fdr", 999)]
    s = Svg(W_, H, "한빛시 고령비율의 LISA(퀸 인접, 순열 999). 왼쪽: 군집 지도(α = 0.05, 보정 없음). 가운데: 유의성 지도(유사 p). "
                   "오른쪽: FDR로 보정한 군집 지도. 붉은 HH는 고령비율이 높은 동이 높은 동에 둘러싸인 곳, 파란 LL은 낮은 동이 모인 곳")
    mw = 220
    fr = [MapFrame(B, 15 + k * (mw + 13), 40, mw) for k in range(3)]
    titles = [f"군집 지도 (보정 없음, {int((L.cluster > 0).sum())}개)", "유의성 지도", f"군집 지도 (FDR, {int((Lf.cluster > 0).sum())}개)"]
    for k in range(3):
        s.text(fr[k].x + mw / 2, 26, titles[k], size=12, weight="600")
    draw(s, fr[0], dong.geometry, None, width=0.3, stroke="s-bg", fills=[CL_FILL[c] for c in L.cluster])
    pp = L.p * (1 - 1e-6)  # esda의 p값이 float32에서 와서 0.001이 0.0010000000475로 저장되므로 경계를 바로잡음
    sb = np.select([pp <= 0.0001, pp <= 0.001, pp <= 0.01, pp <= 0.05], [0, 1, 2, 3], 4)
    draw(s, fr[1], dong.geometry, None, width=0.3, stroke="s-bg", fills=[SIG_FILL[c] for c in sb])
    draw(s, fr[2], dong.geometry, None, width=0.3, stroke="s-bg", fills=[CL_FILL[c] for c in Lf.cluster])
    y = 40 + fr[0].h + 26
    legend(s, 20, y, [(CL_FILL[1], "High-High"), (CL_FILL[2], "Low-Low"), (CL_FILL[3], "Low-High"), (CL_FILL[4], "High-Low"), (CL_FILL[0], "유의하지 않음")])
    legend(s, 20, y + 22, [(SIG_FILL[1], "p ≤ 0.001"), (SIG_FILL[2], "p ≤ 0.01"), (SIG_FILL[3], "p ≤ 0.05")])
    s.save(os.path.join(OUT, "12-cluster.svg"))


def fig_rate(res):
    W_, H = 720, 340
    Lr = res["rate"]
    s = Svg(W_, H, "출동률의 LISA 군집 지도(퀸 인접, 순열 999, α = 0.05, 보정 없음). 23개 동이 유의하게 나오지만 FDR로 보정하면 하나도 남지 않음. "
                   "마루구 원도심의 HH와 함께 외곽에 LL과 이상치(HL, LH)가 흩어져 있음")
    fr = MapFrame(B, 160, 30, 400)
    draw(s, fr, dong.geometry, None, width=0.3, stroke="s-bg", fills=[CL_FILL[c] for c in Lr.cluster])
    c = {k: int((Lr.cluster == k).sum()) for k in range(1, 5)}
    legend(s, 150, 30 + fr.h + 26, [(CL_FILL[1], f"High-High {c[1]}"), (CL_FILL[2], f"Low-Low {c[2]}"), (CL_FILL[3], f"Low-High {c[3]}"), (CL_FILL[4], f"High-Low {c[4]}")])
    s.save(os.path.join(OUT, "12-rate.svg"))


def fig_random(raw, fdr, ex):
    W_, H = 720, 300
    s = Svg(W_, H, "고령비율 값을 행정동에 무작위로 섞어(공간 패턴이 없는 자료) LISA를 200번 돌린 결과. 왼쪽: 보정하지 않으면 평균 "
                   f"{raw.mean():.1f}개({raw.min()}~{raw.max()}개) 동이 '유의'하게 찍힘. 오른쪽: 그 가운데 한 번의 군집 지도. 진짜 군집이 없어도 군집처럼 보이는 동이 생김")
    edges = np.arange(-0.5, 41.5, 1)
    h = np.histogram(raw, edges)[0]
    ax = Axes(s, 50, 56, 280, 170, (-0.5, 40.5), (0, max(h) * 1.15))
    s.text(ax.x0 + 140, 24, "무작위 자료에서 '유의한' 동의 수", size=12, weight="600")
    ax.hist(h, edges, width=0.5)
    ax.xaxis(ticks=[0, 10, 20, 30, 40], label="α = 0.05에서 유의한 동 (보정 없음)")
    ax.yaxis(label="횟수 (200번 가운데)")
    ax.vline(raw.mean(), cls="s-bd", width=1.6, dash="4 3")
    s.text(float(ax.X(raw.mean())) + 4, 68, f"평균 {raw.mean():.1f}", size=10, anchor="start", cls="f-bd")
    s.text(ax.x0 + 140, 280, f"FDR로 보정하면 200번 중 {int((fdr > 0).sum())}번만 1개 이상", size=11, cls="f-mu")
    fr = MapFrame(B, 380, 40, 320)
    s.text(fr.x + 160, 24, "섞은 자료 한 번의 군집 지도", size=12, weight="600")
    draw(s, fr, dong.geometry, None, width=0.3, stroke="s-bg", fills=[CL_FILL[c] for c in ex.cluster])
    legend(s, fr.x, 40 + fr.h + 22, [(CL_FILL[1], "HH"), (CL_FILL[2], "LL"), (CL_FILL[3], "LH"), (CL_FILL[4], "HL")])
    s.save(os.path.join(OUT, "12-random.svg"))


if __name__ == "__main__":
    hand()
    res, raw, fdr, ex = numbers()
    fig_cluster(res)
    fig_rate(res)
    fig_random(raw, fdr, ex)
