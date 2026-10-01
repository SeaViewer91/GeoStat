"""21강 그림과 본문 수치.

- 21-anatomy.svg : 베리오그램 모형 세 가지(구형·지수·가우시안)의 모양과 너깃·문턱값·상관거리
- 21-cloud.svg : 관측소 기온의 베리오그램 구름, 1.5 km 구간 실험 베리오그램, 적합한 모형
- 21-dir.svg : 방향별 실험 베리오그램(0°, 45°, 90°, 135°)과, 지표온도로 설명하고 남은 잔차의 베리오그램

모형 적합은 Cressie(1985)의 가중 최소제곱(가중치 N(h)/γ(h)²), 거리 15 km까지.
상관거리 a는 '실효 상관거리'(문턱값의 95%에 이르는 거리)로 맞춤.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/21.py
"""
import os
import sys
import warnings

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gskit import dist, empirical, expo, fit_wls, gauss, lst_smooth, matern, sample, sph, stations  # noqa: E402
from plotkit import Axes  # noqa: E402
from svglib import Svg  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
ST, X, Z = stations()
N = len(Z)
WIDTH, MAXD = 1500.0, 15000.0
MODELS = {"구형": sph, "지수": expo, "가우시안": gauss, "마테른(ν=1.5)": matern(1.5)}


def hand():
    print("[손계산] 1 km 간격 다섯 지점 24.0, 24.4, 25.1, 24.9, 25.6℃")
    v = np.array([24.0, 24.4, 25.1, 24.9, 25.6])
    for lag in (1, 2, 3):
        d = v[lag:] - v[:-lag]
        print(f"  h = {lag} km: 차이 {np.round(d, 2).tolist()}, 제곱 {np.round(d ** 2, 2).tolist()}, γ = 반 × 평균 = {0.5 * np.mean(d ** 2):.4f} (쌍 {len(d)}개)")
    print(f"  분산(n−1) {v.var(ddof=1):.4f}, 분산(n) {v.var():.4f}")


def numbers():
    print(f"[1] 관측소 {N}곳, 표본분산 {Z.var(ddof=1):.4f} (표준편차 {Z.std(ddof=1):.3f})")
    E, d, g = empirical(X, Z, WIDTH, MAXD)
    print(f"  쌍 {len(d)}개, 15 km 안 {(d <= MAXD).sum()}개, 최소 거리 {d.min():.0f} m")
    for h, gg, nn in E:
        print(f"   평균 거리 {h:6.0f} m: γ {gg:.4f} (쌍 {int(nn)})")
    fits = {}
    for name, f in MODELS.items():
        p, obj = fit_wls(E, f, [0.05, 0.7, 9000])
        fits[name] = p
        print(f"  {name}: 너깃 {p[0]:.4f}, 부분 문턱값 {p[1]:.4f}, 문턱값 {p[0] + p[1]:.4f}, 실효 상관거리 {p[2]:.0f} m, 가중 제곱합 {obj:.2f}")
    for w in (1000.0, 2500.0):
        E2, _, _ = empirical(X, Z, w, MAXD)
        p, _ = fit_wls(E2, sph, [0.05, 0.7, 9000])
        print(f"  구간 폭 {w:.0f} m로 바꾸면 구형 모형: 너깃 {p[0]:.4f}, 문턱값 {p[0] + p[1]:.4f}, 상관거리 {p[2]:.0f} m (구간 {len(E2)}개)")
    # 선형 좌표 추세
    A = np.c_[np.ones(N), (X - X.mean(0)) / 1000]
    b = np.linalg.lstsq(A, Z, rcond=None)[0]
    r = Z - A @ b
    print(f"  좌표의 선형 추세: 동쪽 1 km당 {b[1]:+.4f}℃, 북쪽 1 km당 {b[2]:+.4f}℃, R² {1 - r.var() / Z.var():.3f}")
    return E, d, g, fits


def residual():
    print("[2] 지표온도로 설명한 뒤의 잔차")
    out = {}
    for s_ in (0, 500, 1000, 1500, 2000):
        sm, tr = lst_smooth(s_)
        x = sample(sm, tr, X)
        out[s_] = np.corrcoef(x, Z)[0, 1]
        print(f"  지표온도를 {s_} m로 평활: 관측소 기온과의 상관 {out[s_]:.3f}")
    sm, tr = lst_smooth(1000)
    x = sample(sm, tr, X)
    A = np.c_[np.ones(N), x]
    b = np.linalg.lstsq(A, Z, rcond=None)[0]
    res = Z - A @ b
    print(f"  회귀(1 km 평활): 기온 = {b[0]:.3f} + {b[1]:.4f} × 지표온도, R² {1 - res.var() / Z.var():.3f}, 잔차 표준편차 {res.std(ddof=2):.3f}, 잔차 분산 {res.var(ddof=2):.4f}")
    E, _, _ = empirical(X, res, WIDTH, MAXD)
    for h, gg, nn in E:
        print(f"   잔차 γ: {h:6.0f} m {gg:.4f}")
    p, _ = fit_wls(E, sph, [0.01, 0.01, 5000])
    print(f"  잔차 구형 모형: 너깃 {p[0]:.4f}, 부분 문턱값 {p[1]:.5f}, 상관거리 {p[2]:.0f} m")
    return E, res


def directional():
    print("[3] 방향별 (허용 각 ±22.5°, 3 km 구간)")
    D = dist(X, X)
    iu = np.triu_indices(N, 1)
    d = D[iu]
    dx = (X[None, :, 0] - X[:, None, 0])[iu]
    dy = (X[None, :, 1] - X[:, None, 1])[iu]
    ang = np.degrees(np.arctan2(dx, dy)) % 180   # 0° = 남북, 90° = 동서 (방위각)
    g = (0.5 * (Z[:, None] - Z[None]) ** 2)[iu]
    out = {}
    for a0 in (0, 45, 90, 135):
        dm = np.minimum(np.abs(ang - a0), 180 - np.abs(ang - a0)) <= 22.5
        rows = []
        for lo in np.arange(0, 15000, 3000):
            m = dm & (d > lo) & (d <= lo + 3000)
            if m.sum():
                rows.append((d[m].mean(), g[m].mean(), int(m.sum())))
        out[a0] = np.array(rows)
        print(f"  {a0}°: " + "; ".join(f"{h / 1000:.1f} km γ {gg:.3f} (N {nn})" for h, gg, nn in rows))
    return out


# ---------------------------------------------------------------- 그림
def fig_anatomy():
    W_, H = 720, 260
    s = Svg(W_, H, "베리오그램 모형의 모양. 너깃 0.1, 문턱값 1.0, 실효 상관거리 10 km로 같게 맞춘 구형(실선), 지수(파선), 가우시안(점선). "
                   "원점 근처의 모양이 다름: 가우시안은 매우 매끄러운 표면, 지수는 거친 표면을 뜻함")
    ax = Axes(s, 70, 30, 560, 180, (0, 20), (0, 1.15))
    h = np.linspace(0, 20, 401)
    for f, cls, dash in ((sph, "s-fg", None), (expo, "s-ac", "6 3"), (gauss, "s-bd", "2 3")):
        ax.curve(h, f(h * 1000, 0.1, 0.9, 10000), cls=cls, width=2, dash=dash)
    ax.xaxis(ticks=[0, 5, 10, 15, 20], label="거리 h (km)")
    ax.yaxis(ticks=[0, 0.5, 1.0], label="γ(h)")
    ax.curve([0, 20], [1, 1], cls="s-mu", width=0.8, dash="3 3")
    s.text(float(ax.X(19.8)), float(ax.Y(1.0)) - 6, "문턱값 (sill)", size=10, anchor="end", cls="f-mu")
    s.line(float(ax.X(0)), float(ax.Y(0)), float(ax.X(0)), float(ax.Y(0.1)), cls="s-bd", width=3)
    s.text(float(ax.X(0.35)), float(ax.Y(0.025)), "너깃 (nugget)", size=10, anchor="start", cls="f-bd")
    ax.vline(10, cls="s-mu", width=0.8, dash="3 3")
    s.text(float(ax.X(10)) + 4, float(ax.Y(0.25)), "실효 상관거리 (range)", size=10, anchor="start", cls="f-mu")
    x = 660
    for lab, cls, dash in (("구형", "s-fg", None), ("지수", "s-ac", "6 3"), ("가우시안", "s-bd", "2 3")):
        pass
    y = 60
    for lab, cls, dash in (("구형", "s-fg", None), ("지수", "s-ac", "6 3"), ("가우시안", "s-bd", "2 3")):
        if dash:
            s.add(f'<line x1="{x - 10}" y1="{y}" x2="{x + 10}" y2="{y}" class="{cls}" stroke-width="2" stroke-dasharray="{dash}"/>')
        else:
            s.line(x - 10, y, x + 10, y, cls=cls, width=2)
        s.text(x + 14, y + 4, lab, size=10, anchor="start")
        y += 18
    s.save(os.path.join(OUT, "21-anatomy.svg"))


def fig_cloud(E, d, g, fits):
    W_, H = 720, 300
    s = Svg(W_, H, "관측소 기온의 베리오그램. 회색 점은 15 km 안의 관측소 쌍 하나하나(구름), 검은 점은 1.5 km 구간 평균(실험 베리오그램, 크기는 쌍의 수), "
                   "선은 가중 최소제곱으로 적합한 구형·가우시안 모형. 점선은 표본분산. γ가 2.6을 넘는 44쌍은 그리지 않음. 2.3 km보다 가까운 쌍이 없어 원점 근처(너깃)는 자료가 정하지 못함")
    ax = Axes(s, 70, 30, 560, 210, (0, 15), (0, 2.6))
    m = d <= MAXD
    for dd, gg in zip(d[m], g[m]):
        if gg <= 2.6:
            s.circle(float(ax.X(dd / 1000)), float(ax.Y(gg)), 1.6, cls="s-bg f-mu", width=0)
    h = np.linspace(0, 15000, 301)
    ax.curve(h / 1000, sph(h, *fits["구형"]), cls="s-ac", width=2)
    ax.curve(h / 1000, gauss(h, *fits["가우시안"]), cls="s-bd", width=2, dash="6 3")
    for hh, gg, nn in E:
        s.circle(float(ax.X(hh / 1000)), float(ax.Y(gg)), 2 + np.sqrt(nn) / 3, cls="s-bg f-fg", width=0.8)
    ax.curve([0, 15], [Z.var(ddof=1)] * 2, cls="s-mu", width=1, dash="3 3")
    ax.xaxis(ticks=[0, 3, 6, 9, 12, 15], label="거리 h (km)")
    ax.yaxis(ticks=[0, 0.5, 1.0, 1.5, 2.0, 2.5], label="γ(h) (℃²)")
    s.rect(400, 38, 230, 54, cls="f-bg", width=0)
    y = 50
    for lab, cls, dash in ((f"구형: 너깃 {fits['구형'][0]:.2f}, 문턱값 {fits['구형'][0] + fits['구형'][1]:.2f}, 상관거리 {fits['구형'][2] / 1000:.1f} km", "s-ac", None),
                           (f"가우시안: 너깃 {fits['가우시안'][0]:.2f}, 문턱값 {fits['가우시안'][0] + fits['가우시안'][1]:.2f}, 상관거리 {fits['가우시안'][2] / 1000:.1f} km", "s-bd", "6 3"),
                           (f"표본분산 {Z.var(ddof=1):.2f}", "s-mu", "3 3")):
        if dash:
            s.add(f'<line x1="410" y1="{y}" x2="430" y2="{y}" class="{cls}" stroke-width="2" stroke-dasharray="{dash}"/>')
        else:
            s.line(410, y, 430, y, cls=cls, width=2)
        s.text(436, y + 4, lab, size=10, anchor="start")
        y += 16
    s.save(os.path.join(OUT, "21-cloud.svg"))


def fig_dir(D_, Er):
    W_, H = 720, 280
    s = Svg(W_, H, "왼쪽: 방향별 실험 베리오그램(방위각 ±22.5°, 3 km 구간). 0°는 남북, 90°는 동서 방향의 쌍. 쌍의 수가 적어(구간마다 8~67쌍) 방향 차이를 단정하기 어려움. "
                   "오른쪽: 1 km로 평활한 지표온도로 기온을 회귀하고 남은 잔차의 베리오그램. 거리와 관계없이 평평한 순수 너깃으로, 공간 구조가 지표온도로 모두 설명됨")
    ax = Axes(s, 60, 40, 300, 180, (0, 15), (0, 1.2))
    s.text(210, 22, "방향별", size=12, weight="600")
    styles = {0: ("s-fg", None), 45: ("s-ac", "6 3"), 90: ("s-bd", None), 135: ("s-mu", "2 3")}
    for a0, rows in D_.items():
        cls, dash = styles[a0]
        ax.curve(rows[:, 0] / 1000, rows[:, 1], cls=cls, width=1.8, dash=dash)
        for hh, gg, nn in rows:
            s.circle(float(ax.X(hh / 1000)), float(ax.Y(gg)), 2.5, cls=f"s-bg {cls.replace('s-', 'f-')}", width=0.4)
    ax.xaxis(ticks=[0, 5, 10, 15], label="거리 h (km)")
    ax.yaxis(ticks=[0, 0.5, 1.0], label="γ(h)")
    y = 52
    for a0, (cls, dash) in styles.items():
        if dash:
            s.add(f'<line x1="80" y1="{y}" x2="98" y2="{y}" class="{cls}" stroke-width="2" stroke-dasharray="{dash}"/>')
        else:
            s.line(80, y, 98, y, cls=cls, width=2)
        s.text(102, y + 4, f"{a0}°", size=10, anchor="start")
        y += 15
    ax2 = Axes(s, 440, 40, 250, 180, (0, 15), (0, 0.05))
    s.text(565, 22, "지표온도 회귀 잔차", size=12, weight="600")
    for hh, gg, nn in Er:
        s.circle(float(ax2.X(hh / 1000)), float(ax2.Y(gg)), 2 + np.sqrt(nn) / 3, cls="s-bg f-fg", width=0.6)
    ax2.xaxis(ticks=[0, 5, 10, 15], label="거리 h (km)")
    ax2.yaxis(ticks=[0, 0.02, 0.04], label="γ(h)", fmt=lambda t: f"{t:.2f}")
    s.save(os.path.join(OUT, "21-dir.svg"))


if __name__ == "__main__":
    hand()
    E, d, g, fits = numbers()
    Er, res = residual()
    D_ = directional()
    fig_anatomy()
    fig_cloud(E, d, g, fits)
    fig_dir(D_, Er)
