"""5강 그림과 본문 수치.

- 05-breaks.svg : 행정동 출동률 150개를 분류 방법 다섯 가지로 나눈 결과 (점 하나가 동 하나)
- 05-classify.svg : 같은 출동률을 분위수·등간격·자연 분류·박스 지도로 칠한 지도 네 장
- 05-color.svg : 순차·발산·질적 색 체계와 무지개 색의 밝기 변화
- 05-cartogram.svg : 고령비율 단계구분도와 인구에 비례한 원 카토그램(Dorling)
- 05-brush.svg : 박스 지도의 상위 이상치를 골랐을 때 히스토그램·지도·산점도에 함께 표시되는 모습

분류는 GeoStat 엔진의 classify(앱의 주제도와 같은 함수)로, 출동 건수는 엔진의 점 집계로 계산해 앱 결과와 같게 함.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/05.py
"""
import os
import sys
import warnings

import geopandas as gpd
import mapclassify as mc
import numpy as np
import pandas as pd
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import aggregate as agg  # noqa: E402
from geostat_engine.analysis.classify import classify  # noqa: E402

warnings.filterwarnings("ignore")
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "..", "fig")

dong = gpd.read_file(os.path.join(DATA, "hanbit_dong.gpkg"))
events = gpd.read_file(os.path.join(DATA, "hanbit_events.gpkg"))
dong["PT_CNT"] = agg.aggregate(dong, events, stats=[], count=True, density=False).columns["CNT"]
dong["출동률"] = dong["PT_CNT"] / dong["인구"] * 10000
dong["고령비율"] = dong["고령인구"] / dong["인구"] * 100
dong["인구밀도"] = dong["인구"] / dong["면적_km2"]
RATE = dong["출동률"].rename("출동률")
X0, Y0, X1, Y1 = dong.total_bounds

METHODS = [
    ("quantile", "분위수"),
    ("equal_interval", "등간격"),
    ("natural_breaks", "자연 분류 (Jenks)"),
    ("std_mean", "표준편차"),
    ("box_plot", "박스 지도 (1.5 IQR)"),
]


def cls_names(method, c):
    """계급 번호 → 그림 색 클래스. 5계급은 순차 q0~q4, 6계급 고정 지도는 발산 d0~d5"""
    if method in ("std_mean", "box_plot", "percentile"):
        return [f"d{i}" for i in range(6)]
    n = len(c.labels)
    return [f"q{i + (5 - n)}" for i in range(n)]


def gvf(x, classes):
    """분산 적합도 GVF = 1 - (계급 안 제곱합 / 전체 제곱합)"""
    x = np.asarray(x, float)
    sdam = ((x - x.mean()) ** 2).sum()
    sdcm = sum(((x[classes == k] - x[classes == k].mean()) ** 2).sum() for k in np.unique(classes))
    return 1 - sdcm / sdam


class MapFrame:
    def __init__(self, x, y, w):
        self.x, self.y, self.w = x, y, w
        self.k = w / (X1 - X0)
        self.h = (Y1 - Y0) * self.k

    def xy(self, X, Y):
        return self.x + (X - X0) * self.k, self.y + (Y1 - Y) * self.k


def draw_map(s, fr, classes_css, width=0.4, stroke="s-bg"):
    for g, c in zip(dong.geometry, classes_css):
        s.polygon([fr.xy(x, y) for x, y in g.exterior.coords], cls=f"{stroke} {c}", width=width)


def beeswarm(xs, r):
    """점이 겹치지 않도록 위아래로 쌓은 y 오프셋 (결정적)"""
    order = np.argsort(xs)
    placed = []
    off = np.zeros(len(xs))
    cands = [0] + [s * k * r * 1.9 for k in range(1, 12) for s in (1, -1)]
    for i in order:
        for dy in cands:
            if all((xs[i] - px) ** 2 + (dy - py) ** 2 >= (2 * r * 0.95) ** 2 for px, py in placed if abs(xs[i] - px) < 2 * r):
                off[i] = dy
                placed.append((xs[i], dy))
                break
    return off


# ---------------------------------------------------------------- 수치
def numbers():
    print("[자료] 행정동 150개")
    for v in ("출동률", "고령비율", "인구밀도"):
        x = dong[v]
        print(f"  {v}: 평균 {x.mean():.2f}, 중앙값 {x.median():.2f}, 표준편차 {x.std():.2f}, "
              f"최소 {x.min():.2f}, 최대 {x.max():.2f}, 왜도 {stats.skew(x):.2f}")
    print(f"  출동 0건인 동 {int((dong.PT_CNT == 0).sum())}개, 평균 인구 {dong.loc[dong.PT_CNT == 0, '인구'].mean():,.0f}")

    print("[1] 출동률 분류 (k=5)")
    for m, name in METHODS:
        c = classify(RATE, m, 5)
        g = gvf(RATE, c.classes) if m in ("quantile", "equal_interval", "natural_breaks") else None
        gtxt = f", GVF {g:.3f}" if g is not None else ""
        print(f"  {name}: 동 수 {c.counts}, 경계 {[round(b, 2) for b in c.breaks]}{gtxt}")
        print(f"     라벨 {c.labels}")
        top = c.classes == c.classes.max()
        tt = dong[top]
        print(f"     가장 높은 계급 {top.sum()}개: 인구 합 {tt['인구'].sum():,}, 출동 {tt['PT_CNT'].sum()}건, "
              f"{', '.join(f'{a}({b:,}명·{n}건)' for a, b, n in tt.sort_values('출동률')[['동이름', '인구', 'PT_CNT']].values[:8])}")
    c = classify(RATE, "box_plot")
    q1, q2, q3 = np.percentile(RATE, [25, 50, 75])
    print(f"  박스 지도: Q1 {q1:.2f}, 중앙값 {q2:.2f}, Q3 {q3:.2f}, IQR {q3 - q1:.2f}, 위 울타리 {q3 + 1.5 * (q3 - q1):.2f}, 아래 울타리 {q1 - 1.5 * (q3 - q1):.2f}")
    out = dong[c.classes == 5].sort_values("출동률")
    for _, r in out.iterrows():
        print(f"     {r['동이름']} ({r['동코드']}, {r['구']}): 인구 {r['인구']:,}, 출동 {r['PT_CNT']}건, 출동률 {r['출동률']:.2f}, 면적 {r['면적_km2']:.2f}")
    s = classify(RATE, "std_mean")
    print(f"  표준편차 지도 경계 {[round(b, 2) for b in s.breaks]} → 평균-2σ가 음수, 동 수 {s.counts}")

    print("[손계산] 값 9개, 3계급")
    v = np.array([2, 4, 5, 6, 7, 9, 11, 14, 34.0])
    print(f"  평균 {v.mean():.2f}, 전체 제곱합(SDAM) {((v - v.mean()) ** 2).sum():.2f}")
    for C in (mc.Quantiles(v, k=3), mc.EqualInterval(v, k=3), mc.FisherJenks(v, k=3)):
        groups = [v[C.yb == k].tolist() for k in range(3)]
        sc = sum(((v[C.yb == k] - v[C.yb == k].mean()) ** 2).sum() for k in range(3))
        print(f"  {type(C).__name__}: 경계 {np.round(C.bins, 2).tolist()}, 계급 {groups}, 계급 안 제곱합 {sc:.2f}, GVF {gvf(v, C.yb):.3f}")

    print("[3] 고령비율과 면적 편향")
    g = dong["고령비율"].rename("고령비율")
    c = classify(g, "quantile", 5)
    for k in range(5):
        m = c.classes == k
        print(f"  {k + 1}분위 ({c.labels[k]}): 동 {m.sum()}개, 면적 {dong.loc[m, '면적_km2'].sum() / dong['면적_km2'].sum():.1%}, "
              f"인구 {dong.loc[m, '인구'].sum() / dong['인구'].sum():.1%}, 고령인구 {dong.loc[m, '고령인구'].sum() / dong['고령인구'].sum():.1%}")
    print(f"  r(고령비율, 면적) {np.corrcoef(g, dong['면적_km2'])[0, 1]:.2f}, r(고령비율, log 인구밀도) {np.corrcoef(g, np.log(dong['인구밀도']))[0, 1]:.2f}")
    half = dong["면적_km2"] <= dong["면적_km2"].median()
    print(f"  면적이 작은 절반(75개 동): 면적 {dong.loc[half, '면적_km2'].sum() / dong['면적_km2'].sum():.1%}, 인구 {dong.loc[half, '인구'].sum() / dong['인구'].sum():.1%}")
    print(f"  동 면적 {dong['면적_km2'].min():.2f}~{dong['면적_km2'].max():.2f} ㎢ ({dong['면적_km2'].max() / dong['면적_km2'].min():.0f}배)")

    print("[5] 연동 선택: 박스 지도 상위 이상치 7개")
    sel = (classify(RATE, "box_plot").classes == 5)
    b, a = np.polyfit(dong["인구"], dong["출동률"], 1)
    r2 = np.corrcoef(dong["인구"], dong["출동률"])[0, 1] ** 2
    bs, _ = np.polyfit(dong.loc[sel, "인구"], dong.loc[sel, "출동률"], 1)
    print(f"  산점도 인구×출동률: 기울기 {b:.6f} (1,000명당 {b * 1000:.3f}), R² {r2:.3f}, 선택 7개 기울기 {bs:.6f}")
    edges = np.linspace(RATE.min(), RATE.max(), 11)
    h_all = np.histogram(RATE, edges)[0]
    h_sel = np.histogram(RATE[sel], edges)[0]
    print(f"  히스토그램 10구간 폭 {edges[1] - edges[0]:.2f}: 전체 {h_all.tolist()}, 선택 {h_sel.tolist()}")


# ---------------------------------------------------------------- 그림 1. 분류 방법별 점 그림
def fig_breaks():
    W, H = 720, 404
    s = Svg(W, H, "행정동 150개의 인구 1만 명당 출동률을 다섯 가지 방법으로 나눈 결과. 점 하나가 동 하나이고 색이 계급임. "
                  "세로 점선은 계급 경계. 오른쪽 숫자는 계급별 동 수")
    gx, gw = 150, 440
    lo, hi = 0, 50
    X = lambda v: gx + (v - lo) / (hi - lo) * gw  # noqa: E731
    top, rh = 44, 62
    s.text(gx + gw / 2, 22, "인구 1만 명당 출동률 (행정동 150개)", size=13, weight="600")
    s.text(W - 62, 22, "계급별 동 수", size=11, cls="f-mu")
    xs = X(RATE.to_numpy())
    off = beeswarm(xs, 2.4)
    for i, (m, name) in enumerate(METHODS):
        c = classify(RATE, m, 5)
        css = cls_names(m, c)
        yc = top + i * rh + rh / 2
        s.text(gx - 12, yc + 4, name, size=12, anchor="end")
        s.line(gx, yc + rh / 2 - 2, gx + gw, yc + rh / 2 - 2, cls="s-mu", width=0.4)
        for b in c.breaks[:-1] if m not in ("std_mean", "box_plot") else c.breaks:
            if lo <= b <= hi:
                s.line(X(b), yc - rh / 2 + 6, X(b), yc + rh / 2 - 6, cls="s-fg", width=1, dash="3 2")
        for j in range(len(xs)):
            k = c.classes[j]
            s.circle(xs[j], yc + off[j] * 0.8, 2.4, cls=f"s-fg {css[k]}", width=0.4)
        counts = c.counts
        s.text(W - 62, yc + 4, "·".join(str(n) for n in counts), size=11, cls="f-mu")
    ay = top + len(METHODS) * rh + 4
    for t in range(0, 51, 10):
        s.line(X(t), ay - 4, X(t), ay, cls="s-mu", width=1)
        s.text(X(t), ay + 14, str(t), size=11, cls="f-mu")
    s.text(gx + gw / 2, ay + 32, "출동률 (건/1만 명)", size=12, cls="f-mu")
    s.save(os.path.join(OUT, "05-breaks.svg"))


# ---------------------------------------------------------------- 그림 2. 같은 자료, 지도 네 장
def fig_classify():
    W = 720
    mw = 300
    fr_h = mw * (Y1 - Y0) / (X1 - X0)
    cell_h = 28 + fr_h + 70
    H = int(2 * cell_h + 10)
    s = Svg(W, H, "같은 출동률을 분위수, 등간격, 자연 분류(Jenks), 박스 지도로 칠한 지도. 분위수는 계급마다 30개 동을, "
                  "등간격과 자연 분류는 극단값 몇 개만 진하게 칠하며, 박스 지도는 이상치 7개를 따로 표시함")
    items = [METHODS[0], METHODS[1], METHODS[2], METHODS[4]]
    for i, (m, name) in enumerate(items):
        col, row = i % 2, i // 2
        x0 = 30 + col * (mw + 60)
        y0 = 10 + row * cell_h
        c = classify(RATE, m, 5)
        css = cls_names(m, c)
        s.text(x0 + mw / 2, y0 + 18, name, size=13, weight="600")
        fr = MapFrame(x0, y0 + 28, mw)
        draw_map(s, fr, [css[k] for k in c.classes])
        # 범례: 색 칸 + 동 수
        n = len(c.labels)
        bw = mw / n
        ly = y0 + 28 + fr_h + 12
        for k in range(n):
            s.rect(x0 + k * bw, ly, bw, 12, cls=f"s-bg {css[k]}", width=0.5)
            s.text(x0 + k * bw + bw / 2, ly + 27, f"{c.counts[k]}개", size=11, cls="f-mu")
        if m == "box_plot":
            s.text(x0, ly + 44, f"왼쪽부터 하위 이상치, 1~4사분위, 상위 이상치 (울타리 {c.breaks[-1]:.1f})", size=10, anchor="start", cls="f-mu")
        else:
            s.text(x0, ly + 44, f"경계: {', '.join(f'{b:.1f}' for b in c.breaks[:-1])}", size=10, anchor="start", cls="f-mu")
    s.save(os.path.join(OUT, "05-classify.svg"))


# ---------------------------------------------------------------- 그림 3. 색 체계
def srgb_to_lstar(hexs):
    out = []
    for h in hexs:
        rgb = np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)]) / 255
        lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
        yy = lin @ np.array([0.2126, 0.7152, 0.0722])
        f = yy ** (1 / 3) if yy > 216 / 24389 else (24389 / 27 * yy + 16) / 116
        out.append(116 * f - 16)
    return out


YLORRD9 = ["#ffffcc", "#ffeda0", "#fed976", "#feb24c", "#fd8d3c", "#fc4e2a", "#e31a1c", "#bd0026", "#800026"]
SEQ = [YLORRD9[i] for i in (0, 2, 4, 6, 8)]
DIV = ["#2166ac", "#67a9cf", "#d1e5f0", "#fddbc7", "#ef8a62", "#b2182b"]
QUAL = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f", "#edc948"]
RAINBOW = ["#8000ff", "#0000ff", "#00ffff", "#00ff00", "#ffff00", "#ff8000", "#ff0000"]


def fig_color():
    W, H = 720, 330
    s = Svg(W, H, "색 체계 세 가지와 무지개 색. 오른쪽 선은 각 색의 밝기(L*). 순차 색은 밝기가 한 방향으로, 발산 색은 가운데에서 "
                  "양쪽으로 어두워지며, 질적 색은 밝기가 비슷함. 무지개 색은 밝기가 오르내려 순서를 읽을 수 없음")
    rows = [
        ("순차", "적음 → 많음 (출동률, 고령비율)", SEQ),
        ("발산", "기준값의 양쪽 (평균과의 차, 잔차)", DIV),
        ("질적", "순서 없는 종류 (구, 토지 이용)", QUAL),
        ("무지개", "순서가 있는 값에는 피함", RAINBOW),
    ]
    sx, sw = 130, 300
    lx, lw = 500, 180
    s.text(sx + sw / 2, 22, "색 견본", size=12, cls="f-mu")
    s.text(lx + lw / 2, 22, "밝기 L* (0~100)", size=12, cls="f-mu")
    for i, (name, desc, cols) in enumerate(rows):
        y = 40 + i * 70
        s.text(sx - 14, y + 18, name, size=13, anchor="end", weight="600")
        n = len(cols)
        w = sw / n
        for j, h in enumerate(cols):
            s.rect(sx + j * w, y, w, 28, cls="s-bg", width=1, fill=h)
        s.text(sx, y + 46, desc, size=11, anchor="start", cls="f-mu")
        L = srgb_to_lstar(cols)
        s.rect(lx, y - 4, lw, 36, cls="s-mu f-sf", width=0.5)
        pts = [(lx + 10 + j * (lw - 20) / (n - 1), y + 30 - L[j] / 100 * 32) for j in range(n)]
        s.path("M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in pts), cls="s-fg" if i < 3 else "s-bd", width=1.6)
        for (a, b), h in zip(pts, cols):
            s.circle(a, b, 3.2, cls="s-fg", width=0.6, fill=h)
    s.text(W / 2, H - 12, "순차·발산 색은 GeoStat 주제도의 색(노랑–빨강, 파랑–빨강), 질적 색은 고유값 지도의 색", size=11, cls="f-mu")
    s.save(os.path.join(OUT, "05-color.svg"))
    return {name: [round(v) for v in srgb_to_lstar(cols)] for name, _, cols in rows}


# ---------------------------------------------------------------- 그림 4. 카토그램
def dorling(frac=0.5, iters=3000):
    """인구에 비례한 원(Dorling 카토그램). 원 면적 합이 도시 면적의 frac가 되게 하고 겹치지 않을 때까지 밀어냄"""
    c = dong.geometry.representative_point()
    p0 = np.c_[c.x, c.y]
    pop = dong["인구"].to_numpy(float)
    area = dong.geometry.area.sum()
    r = np.sqrt(pop / pop.sum() * area * frac / np.pi)
    p = p0.copy()
    for it in range(iters):
        d = p[:, None, :] - p[None, :, :]
        dist = np.sqrt((d ** 2).sum(-1)) + 1e-9
        ov = (r[:, None] + r[None, :]) - dist
        np.fill_diagonal(ov, 0)
        ov = np.clip(ov, 0, None)
        if ov.max() < 1 and it > 0.6 * iters:
            break
        push = (d / dist[..., None]) * (ov / 2)[..., None]
        p = p + push.sum(1) * 0.5
        p = p + (p0 - p) * 0.01 * max(0.0, 1 - it / (0.6 * iters))  # 끝으로 갈수록 제자리로 끌어당기는 힘을 없앰
    return p, r, ov.max()


def fig_cartogram():
    W = 720
    mw = 330
    fr_h = mw * (Y1 - Y0) / (X1 - X0)
    H = int(40 + fr_h + 70)
    g = dong["고령비율"].rename("고령비율")
    c = classify(g, "quantile", 5)
    css = [f"q{k}" for k in c.classes]
    s = Svg(W, H, "행정동 고령비율(분위수 5계급)을 보통의 단계구분도(왼쪽)와 인구에 비례한 원 카토그램(오른쪽)으로 그린 것. "
                  "가장 진한 계급은 지도 면적의 37%를 차지하지만 사는 사람은 9%뿐임")
    left, right = MapFrame(20, 40, mw), MapFrame(370, 40, mw)
    s.text(left.x + mw / 2, 24, "단계구분도 (면적 = 행정동 넓이)", size=13, weight="600")
    s.text(right.x + mw / 2, 24, "원 카토그램 (원 넓이 = 인구)", size=13, weight="600")
    draw_map(s, left, css)
    for gg in dong.union_all().geoms if hasattr(dong.union_all(), "geoms") else [dong.union_all()]:
        s.polygon([right.xy(x, y) for x, y in gg.exterior.coords], cls="s-mu f-sf", width=0.6)
    p, r, ovmax = dorling()
    for i in np.argsort(-r):
        x, y = right.xy(*p[i])
        s.circle(x, y, max(r[i] * right.k, 0.8), cls=f"s-fg q{c.classes[i]}", width=0.4)
    ly = 40 + fr_h + 22
    bx = W / 2 - 100
    for k in range(5):
        s.rect(bx + k * 40, ly - 6, 40, 12, cls=f"s-bg q{k}", width=0.5)
    s.text(bx - 6, ly + 4, "낮음", size=11, anchor="end", cls="f-mu")
    s.text(bx + 206, ly + 4, "높음 (고령비율 5분위)", size=11, anchor="start", cls="f-mu")
    top = c.classes == 4
    a = dong.loc[top, "면적_km2"].sum() / dong["면적_km2"].sum()
    pp = dong.loc[top, "인구"].sum() / dong["인구"].sum()
    s.text(W / 2, ly + 30, f"가장 진한 계급 30개 동: 도시 면적의 {a:.0%}, 인구의 {pp:.0%}", size=12, cls="f-mu")
    s.save(os.path.join(OUT, "05-cartogram.svg"))
    print(f"[그림4] 카토그램 원 겹침 최대 {ovmax:.1f} m, 원 반지름 {r.min():.0f}~{r.max():.0f} m")


# ---------------------------------------------------------------- 그림 5. 연동 선택
def fig_brush():
    W, H = 720, 300
    sel = classify(RATE, "box_plot").classes == 5
    s = Svg(W, H, "박스 지도에서 출동률 상위 이상치 7개 동을 고르면 히스토그램, 지도, 산점도에 같은 동이 함께 표시됨. "
                  "지도에서는 마루구 원도심 4개와 다솜구 3개로 나뉘고, 산점도에서는 그 가운데 2개가 인구 1천 명 남짓한 동임을 알 수 있음")
    # 히스토그램
    hx, hy, hw, hh = 30, 50, 170, 170
    edges = np.linspace(RATE.min(), RATE.max(), 11)
    ha = np.histogram(RATE, edges)[0]
    hs = np.histogram(RATE[sel], edges)[0]
    s.text(hx + hw / 2, 26, "히스토그램 (10구간)", size=13, weight="600")
    bw = hw / 10
    for i in range(10):
        h1 = ha[i] / ha.max() * hh
        s.rect(hx + i * bw, hy + hh - h1, bw, h1, cls="s-bg f-mu", width=0.6)
        if hs[i]:
            h2 = hs[i] / ha.max() * hh
            s.rect(hx + i * bw, hy + hh - max(h2, 3), bw, max(h2, 3), cls="s-fg f-bd", width=0.6)
    s.line(hx, hy + hh, hx + hw, hy + hh, cls="s-mu", width=1)
    for t in (0, 10, 20, 30, 40):
        xx = hx + (t - edges[0]) / (edges[-1] - edges[0]) * hw
        s.text(xx, hy + hh + 14, str(t), size=10, cls="f-mu")
    s.text(hx + hw / 2, hy + hh + 32, "출동률", size=11, cls="f-mu")
    # 지도
    fr = MapFrame(225, 50, 270)
    s.text(fr.x + fr.w / 2, 26, "지도", size=13, weight="600")
    for g, on in zip(dong.geometry, sel):
        s.polygon([fr.xy(x, y) for x, y in g.exterior.coords], cls="s-bg f-bd" if on else "s-bg f-sf", width=0.4)
    g = dong.loc[dong["동이름"] == "다솜1동"].geometry.iloc[0].centroid
    x, y = fr.xy(g.x, g.y)
    s.text(x - 22, y + 4, "다솜1동", size=10, anchor="end")
    g = dong[dong["동이름"].isin(["다솜19동", "다솜23동"])].geometry.union_all().centroid
    x, y = fr.xy(g.x, g.y)
    s.text(x - 22, y + 4, "다솜19·23동", size=10, anchor="end")
    mar = dong[sel & (dong["구"] == "마루구")].geometry.union_all().centroid
    x, y = fr.xy(mar.x, mar.y)
    s.text(x, y + 26, "마루구 4개", size=10)
    # 산점도
    px, py, pw, ph = 535, 50, 155, 170
    s.text(px + pw / 2, 26, "산점도 (인구 × 출동률)", size=13, weight="600")
    xmax, ymax = 20000, 50
    Px = lambda v: px + v / xmax * pw  # noqa: E731
    Py = lambda v: py + ph - v / ymax * ph  # noqa: E731
    s.rect(px, py, pw, ph, cls="s-mu", width=0.6, fill="none")
    b, a = np.polyfit(dong["인구"], dong["출동률"], 1)
    s.line(Px(0), Py(a), Px(xmax), Py(a + b * xmax), cls="s-ac", width=1.2)
    for on in (False, True):
        for v, w in zip(dong["인구"][sel == on], RATE[sel == on]):
            s.circle(Px(v), Py(w), 3 if on else 2.2, cls="s-fg f-bd" if on else "s-mu f-sf", width=0.6 if on else 0.5)
    for t in (0, 10000, 20000):
        s.text(Px(t), py + ph + 14, f"{t:,}", size=10, cls="f-mu")
    for t in (0, 25, 50):
        s.text(px - 6, Py(t) + 4, str(t), size=10, anchor="end", cls="f-mu")
    s.text(px + pw / 2, py + ph + 32, "인구", size=11, cls="f-mu")
    # 범례
    s.rect(225, H - 34, 14, 12, cls="s-fg f-bd", width=0.6)
    s.text(245, H - 24, "선택한 동 (박스 지도의 상위 이상치 7개)", size=11, anchor="start")
    s.save(os.path.join(OUT, "05-brush.svg"))


if __name__ == "__main__":
    numbers()
    fig_breaks()
    fig_classify()
    L = fig_color()
    print("[그림3] 밝기 L*:", L)
    fig_cartogram()
    fig_brush()
