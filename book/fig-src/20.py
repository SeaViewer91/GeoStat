"""20강 그림과 본문 수치.

- 20-stations.svg : 기상 관측소 48곳의 8월 평균 기온과, 관측소 사이 거리
- 20-interp.svg : 티센 다각형(가장 가까운 관측소), 역거리 가중(IDW, p = 2), 박판 스플라인으로 보간한 기온 지도
- 20-idw.svg : IDW의 거듭제곱 p에 따른 단면(관측소 두 곳 사이)과 교차검증 오차

교차검증은 관측소 하나씩 빼고 나머지 47곳으로 그 자리를 예측하는 방식(LOOCV)임.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/20.py
"""
import os
import sys
import warnings

import numpy as np
from scipy.interpolate import RBFInterpolator
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gskit import dist, grid, stations, window  # noqa: E402
from mapkit import MapFrame, colorbar, outline, png, ramp_rgb, to_array  # noqa: E402
from plotkit import Axes  # noqa: E402
from svglib import Svg  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
WIN = window()
ST, X, Z = stations()
N = len(Z)
G, INSIDE, (GXS, GYS) = grid(WIN, 250.0)
LO, HI = 23.0, 26.8


def idw(p):
    def f(Xt, zt, X0):
        d = np.maximum(dist(X0, Xt), 1e-6)
        w = 1 / d ** p
        return (w * zt).sum(1) / w.sum(1)
    return f


def nearest(Xt, zt, X0):
    return zt[cKDTree(Xt).query(X0)[1]]


def tps(Xt, zt, X0):
    return RBFInterpolator(Xt / 1000, zt, kernel="thin_plate_spline")(X0 / 1000)


def mean_(Xt, zt, X0):
    return np.full(len(X0), zt.mean())


def loo(f):
    e = np.array([f(np.delete(X, i, 0), np.delete(Z, i), X[i:i + 1])[0] - Z[i] for i in range(N)])
    return np.sqrt((e ** 2).mean()), np.abs(e).mean(), e


def hand():
    print("[손계산] 예측 지점에서 1, 2, 3, 4 km 떨어진 관측소의 기온 25.0, 24.0, 26.0, 24.5℃")
    d = np.array([1, 2, 3, 4.0])
    v = np.array([25.0, 24.0, 26.0, 24.5])
    for p in (1, 2, 3):
        w = 1 / d ** p
        print(f"  p = {p}: 가중치 {np.round(w / w.sum(), 4).tolist()}, 예측 {np.sum(w * v) / w.sum():.3f}℃")
    print(f"  가장 가까운 관측소: 25.0℃, 단순 평균 {v.mean():.3f}℃")


def numbers():
    print(f"[1] 관측소 {N}곳: 평균 {Z.mean():.2f}℃, 표준편차 {Z.std(ddof=1):.2f}, 범위 {Z.min():.2f}~{Z.max():.2f}")
    nn = cKDTree(X).query(X, k=2)[0][:, 1]
    D = dist(X, X)
    print(f"  최근린 거리 최소 {nn.min():.0f} m, 평균 {nn.mean():.0f}, 최대 {nn.max():.0f}; 관측소 쌍 {N * (N - 1) // 2}개, 가장 먼 쌍 {D.max():.0f} m")
    print(f"  관측소 하나가 맡는 면적 {WIN.area / 1e6 / N:.2f} km²")
    i = np.argmax(Z)
    j = np.argmin(Z)
    print(f"  가장 높은 {ST['관측소ID'][i]} {Z[i]}℃, 가장 낮은 {ST['관측소ID'][j]} {Z[j]}℃")
    print("[2] LOOCV (RMSE, MAE, 평균 오차)")
    res = {}
    for name, f in (("평균", mean_), ("가장 가까운 관측소", nearest), ("IDW p=1", idw(1)), ("IDW p=2", idw(2)), ("IDW p=3", idw(3)), ("박판 스플라인", tps)):
        r, m, e = loo(f)
        res[name] = (r, m, e)
        print(f"  {name}: RMSE {r:.3f}, MAE {m:.3f}, 평균 오차 {e.mean():+.3f}, 최대 절대 오차 {np.abs(e).max():.3f}")
    preds = {"가장 가까운 관측소": nearest(X, Z, G), "IDW p=2": idw(2)(X, Z, G), "박판 스플라인": tps(X, Z, G)}
    for k, v in preds.items():
        print(f"  지도 {k}: 범위 {v.min():.2f}~{v.max():.2f}")
    return res, preds


# ---------------------------------------------------------------- 그림
def place(s, fr, vals, lo=LO, hi=HI):
    arr = to_array(vals, INSIDE)
    g = GXS[1] - GXS[0]
    X0, Y0 = fr.xy(GXS[0] - g / 2, GYS[-1] + g / 2)
    X1, Y1 = fr.xy(GXS[-1] + g / 2, GYS[0] - g / 2)
    s.image_png(X0, Y0, X1 - X0, Y1 - Y0, png(ramp_rgb(arr, lo, hi), int(2 * (X1 - X0))))


def dots(s, fr, r=3.2):
    for (x, y), v in zip(X, Z):
        X_, Y_ = fr.xy(x, y)
        rgb = ramp_rgb(np.array([v]), LO, HI)[0]
        s.circle(X_, Y_, r, cls="s-fg", width=0.8, fill=f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}")


def fig_stations():
    W_, H = 720, 320
    s = Svg(W_, H, "왼쪽: 기상 관측소 48곳의 8월 평균 기온(점의 색). 관측소는 서로 2.3 km 이상 떨어지게 배치되어 있음. 오른쪽: 관측소 쌍 1,128개의 거리 분포. "
                   "가장 가까운 쌍도 2.3 km 떨어져 있어, 그보다 짧은 거리의 변화는 자료가 직접 말해 주지 않음")
    fr = MapFrame(WIN.bounds, 20, 30, 360)
    outline(s, fr, WIN, cls="s-mu", width=1)
    dots(s, fr, 4)
    colorbar(s, 60, 30 + fr.h + 22, 260, LO, HI, [23, 24, 25, 26], "8월 평균 기온 (℃)")
    D = dist(X, X)[np.triu_indices(N, 1)] / 1000
    edges = np.arange(0, 31, 1)
    h = np.histogram(D, edges)[0]
    ax = Axes(s, 440, 40, 250, 200, (0, 30), (0, h.max() * 1.15))
    s.text(565, 22, "관측소 쌍의 거리", size=12, weight="600")
    ax.hist(h, edges, width=0.5)
    ax.xaxis(ticks=[0, 5, 10, 15, 20, 25, 30], label="거리 (km)")
    ax.yaxis(label="쌍의 수")
    ax.vline(2.3, cls="s-bd", width=1.4, dash="4 3")
    s.text(float(ax.X(2.3)) + 4, 58, "최소 2.3 km", size=10, anchor="start", cls="f-bd")
    s.save(os.path.join(OUT, "20-stations.svg"))


def fig_interp(preds, res):
    W_, H = 720, 290
    s = Svg(W_, H, "관측소 48곳으로 보간한 8월 평균 기온. 왼쪽: 가장 가까운 관측소의 값(티센 다각형)은 경계에서 값이 뚝 끊김. 가운데: 역거리 가중(p = 2)은 관측소마다 "
                   "과녁 같은 무늬가 생김. 오른쪽: 박판 스플라인은 매끈함. 괄호는 교차검증 RMSE")
    mw = 220
    fr = [MapFrame(WIN.bounds, 15 + k * (mw + 13), 40, mw) for k in range(3)]
    for k, name in enumerate(("가장 가까운 관측소", "IDW p=2", "박판 스플라인")):
        s.text(fr[k].x + mw / 2, 26, f"{name} ({res[name][0]:.2f}℃)", size=12, weight="600")
        place(s, fr[k], preds[name])
        outline(s, fr[k], WIN, cls="s-mu", width=0.8)
        for x, y in X:
            X_, Y_ = fr[k].xy(x, y)
            s.circle(X_, Y_, 1.6, cls="s-bg", width=0, fill="#1c2330")
    colorbar(s, 250, 40 + fr[0].h + 22, 220, LO, HI, [23, 24, 25, 26], "8월 평균 기온 (℃)")
    s.save(os.path.join(OUT, "20-interp.svg"))


def fig_idw(res):
    # 가장 먼 두 관측소 쌍이 아닌, 기온 차가 큰 이웃 쌍 사이 단면
    D = dist(X, X)
    best = None
    for i in range(N):
        for j in range(i + 1, N):
            if 4000 < D[i, j] < 9000:
                dz = abs(Z[i] - Z[j])
                if best is None or dz > best[0]:
                    best = (dz, i, j)
    _, i, j = best
    t = np.linspace(-0.3, 1.3, 161)
    line = X[i] + t[:, None] * (X[j] - X[i])
    W_, H = 720, 300
    s = Svg(W_, H, f"왼쪽: 관측소 {ST['관측소ID'][i]}({Z[i]:.2f}℃)와 {ST['관측소ID'][j]}({Z[j]:.2f}℃)을 잇는 선을 따라 본 IDW 예측. p가 클수록 관측소 근처는 "
                   "평평하고 사이에서 가파르게 바뀜. 단면이 다른 관측소 근처를 지나는 곳에서는 그 관측소 쪽으로 휘어짐. 오른쪽: 교차검증 RMSE. 단순 평균보다 모두 낫고, 박판 스플라인이 가장 작음")
    ax = Axes(s, 60, 40, 300, 180, (t[0], t[-1]), (LO, HI))
    for p, cls, dash in ((1, "s-mu", "2 3"), (2, "s-ac", None), (3, "s-bd", "6 3")):
        ax.curve(t, idw(p)(X, Z, line), cls=cls, width=1.8, dash=dash)
    for tt, v in ((0, Z[i]), (1, Z[j])):
        s.circle(float(ax.X(tt)), float(ax.Y(v)), 4, cls="s-bg f-fg", width=0.5)
    ax.xaxis(ticks=[0, 1], label=f"단면 위치 (0 = {ST['관측소ID'][i]}, 1 = {ST['관측소ID'][j]})")
    ax.yaxis(ticks=[23, 24, 25, 26], label="기온 (℃)")
    x = 80
    for lab, cls in (("p = 1", "s-mu"), ("p = 2", "s-ac"), ("p = 3", "s-bd")):
        s.line(x, 282, x + 20, 282, cls=cls, width=2)
        s.text(x + 24, 286, lab, size=10, anchor="start")
        x += 80
    names = ["평균", "가장 가까운 관측소", "IDW p=1", "IDW p=2", "IDW p=3", "박판 스플라인"]
    ax2 = Axes(s, 520, 40, 170, 200, (0, 0.9), (-0.5, len(names) - 0.5))
    s.text(560, 22, "교차검증 RMSE (℃)", size=12, weight="600")
    for k, nm in enumerate(names):
        y = float(ax2.Y(len(names) - 1 - k))
        v = res[nm][0]
        s.rect(float(ax2.X(0)), y - 7, float(ax2.X(v)) - float(ax2.X(0)), 14, cls="s-bg f-ac", width=0.5)
        s.text(float(ax2.X(0)) - 6, y + 4, nm, size=10, anchor="end")
        s.text(float(ax2.X(v)) + 4, y + 4, f"{v:.2f}", size=10, anchor="start")
    ax2.xaxis(ticks=[0, 0.4, 0.8], label="℃")
    s.save(os.path.join(OUT, "20-idw.svg"))
    print(f"[3] 단면: {ST['관측소ID'][i]} {Z[i]} ↔ {ST['관측소ID'][j]} {Z[j]}, 거리 {D[i, j]:.0f} m")


if __name__ == "__main__":
    hand()
    res, preds = numbers()
    fig_stations()
    fig_interp(preds, res)
    fig_idw(res)
