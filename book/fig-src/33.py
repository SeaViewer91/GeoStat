"""33강 그림과 본문 수치.

- 33-trend.svg : 연도별 출동 건수와 폭염일수 (도시 전체)
- 33-maps.svg : 2016, 2018, 2020, 2025년 동별 출동률 지도 (모든 연도 같은 계급 경계)
- 33-interp.svg : 경계 변화. 2016년에 한 동이던 곳을 지금 경계로 나눌 때 면적 비례와 인구 비례(격자 인구)
- 33-stw.svg : 시공간 가중치의 구조 (동 3개 × 연도 3개)

자료는 book/data/hanbit_dong_panel.gpkg (make_hanbit_panel.py로 만듦, 규칙은 책을 끝까지 읽기 전에는 보지 않기를 권함).

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/33.py
"""
import os
import sys
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import MapFrame, draw, outline  # noqa: E402
from plotkit import Axes  # noqa: E402
from regkit import queen, rng  # noqa: E402
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import fields  # noqa: E402
from geostat_engine.analysis import timeseries as ts  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
DATA = os.path.join(HERE, "..", "data")
PANEL = os.path.join(DATA, "hanbit_dong_panel.gpkg")
YEARS = list(range(2016, 2026))


def load():
    p = gpd.read_file(PANEL)
    p["출동률"] = fields.evaluate(p, "`출동건수` / `인구` * 10000")
    return p


# ---------------------------------------------------------------- 손계산
def hand():
    print("[손계산 1] 긴 형태 ↔ 넓은 형태: 동 2개 × 연도 3개")
    long = pd.DataFrame({"동": ["A", "A", "A", "B", "B", "B"], "연도": [2023, 2024, 2025] * 2, "건수": [3, 5, 4, 7, 6, 9]})
    print(long.to_string(index=False))
    print(long.pivot(index="동", columns="연도", values="건수").add_prefix("건수_").to_string())
    print("[손계산 2] 한 동(인구 10,000)을 A(면적 3 ㎢, 지금 인구 2,000), B(1 ㎢, 6,000)로 나눔")
    for nm, wa, wb in (("면적 비례", 3, 1), ("인구 비례", 2000, 6000)):
        print(f"  {nm}: A {10000 * wa / (wa + wb):,.0f}, B {10000 * wb / (wa + wb):,.0f}")
    print("[손계산 3] 시공간 가중치: 동 1–2–3이 한 줄로 이웃, 연도 2개")
    Ws = np.array([[0, 1, 0], [1, 0, 1], [0, 1, 0.0]])
    T = 2
    same = np.kron(np.eye(T), Ws)
    lag = np.kron(np.eye(T, k=-1), np.eye(3))
    lag_nb = np.kron(np.eye(T, k=-1), Ws)
    print("  같은 연도 이웃 (I ⊗ W):\n" + str(same.astype(int)))
    print("  앞 연도 같은 동 (L ⊗ I):\n" + str(lag.astype(int)))
    print("  앞 연도 이웃 (L ⊗ W):\n" + str(lag_nb.astype(int)))


# ---------------------------------------------------------------- 본문 수치
def numbers(p):
    print("[1] 자료 요약")
    print(f"  {len(p)}행, 동 {p['동코드'].nunique()}개, 연도 {p['연도'].min()}~{p['연도'].max()}, 열 {list(p.columns)}")
    s = p.groupby("연도").agg(인구=("인구", "sum"), 고령인구=("고령인구", "sum"), 출동건수=("출동건수", "sum"), 폭염일수=("폭염일수", "first"))
    s["출동률"] = s["출동건수"] / s["인구"] * 10000
    s["고령비율"] = s["고령인구"] / s["인구"] * 100
    print(s.round(3).to_string())
    r = np.corrcoef(s["폭염일수"], s["출동건수"])[0, 1]
    b = np.polyfit(s["폭염일수"], np.log(s["출동건수"]), 1)
    print(f"  폭염일수와 연 출동 건수의 상관 {r:.3f}; log(건수) 기울기 {b[0]:.4f} (하루당 {np.expm1(b[0]) * 100:.1f}%)")
    # 넓은 형태로 (앱의 기간별 자료 만들기와 같은 함수)
    wide, groups, notes = ts.pivot_long(p, "동코드", "연도", ["인구", "고령인구", "출동건수", "출동률"])
    print(f"[2] 넓은 형태: {wide.shape[0]}행, 열 {wide.shape[1]}개 (처음 열 {list(wide.columns[:4])}, 마지막 {list(wide.columns[-2:])}), 묶음 {[g['name'] for g in groups]}, 안내 {notes}")
    first = wide.iloc[0]
    print(f"  {first['동코드']}: 출동건수_2016 {first['출동건수_2016']:.0f}, 출동건수_2025 {first['출동건수_2025']:.0f}, 출동률_2025 {first['출동률_2025']:.2f}")
    # 분산 분해 (균형 패널, 출동률)
    R = p.pivot(index="동코드", columns="연도", values="출동률").to_numpy()
    g = R.mean()
    dong_eff = R.mean(1, keepdims=True) - g
    year_eff = R.mean(0, keepdims=True) - g
    resid = R - g - dong_eff - year_eff
    tot = ((R - g) ** 2).sum()
    ss = [(dong_eff ** 2).sum() * R.shape[1], (year_eff ** 2).sum() * R.shape[0], (resid ** 2).sum()]
    print(f"[3] 출동률 분산 분해(동 × 연도 이원 배치): 전체 제곱합 {tot:.1f} = 동 {ss[0]:.1f} ({ss[0] / tot * 100:.1f}%) + 연도 {ss[1]:.1f} ({ss[1] / tot * 100:.1f}%) + 나머지 {ss[2]:.1f} ({ss[2] / tot * 100:.1f}%)")
    big = p.groupby("동코드")["인구"].mean().to_numpy() >= 10000
    Rb = R[big]
    gb = Rb.mean()
    de = Rb.mean(1, keepdims=True) - gb
    ye = Rb.mean(0, keepdims=True) - gb
    rb = Rb - gb - de - ye
    tb = ((Rb - gb) ** 2).sum()
    print(f"    인구 1만 명 이상 {big.sum()}개 동만: 동 {(de ** 2).sum() * Rb.shape[1] / tb * 100:.1f}%, 연도 {(ye ** 2).sum() * Rb.shape[0] / tb * 100:.1f}%, 나머지 {(rb ** 2).sum() / tb * 100:.1f}%")
    # 시간 자기상관
    lag1 = lambda M: np.corrcoef(M[:, 1:].ravel(), M[:, :-1].ravel())[0, 1]  # noqa: E731
    print(f"[4] 앞뒤 연도 상관(동마다 이웃한 두 해를 짝지음): 출동률 그대로 {lag1(R):.3f}, 연도 평균을 뺀 값 {lag1(R - R.mean(0, keepdims=True)):.3f}, "
          f"동 평균과 연도 평균을 모두 뺀 값 {lag1(resid):.3f}")
    r0 = rng("lag1_null")
    sims = []
    for _ in range(1000):
        N = r0.standard_normal(R.shape)
        N = N - N.mean(1, keepdims=True) - N.mean(0, keepdims=True) + N.mean()
        sims.append(lag1(N))
    sims = np.array(sims)
    print(f"    서로 독립인 잡음(150 × 10)에서 두 평균을 뺀 뒤의 상관: 평균 {sims.mean():.3f}, 95% 범위 {np.quantile(sims, 0.025):.3f}~{np.quantile(sims, 0.975):.3f} (−1/(T−1) = {-1 / 9:.3f})")
    C = p.pivot(index="동코드", columns="연도", values="출동건수").to_numpy()
    P = p.pivot(index="동코드", columns="연도", values="인구").to_numpy()
    print(f"    출동건수 그대로 {lag1(C):.3f}; 인구 그대로 {lag1(P):.4f}")
    # 연도별 Moran's I (출동률)
    from esda import Moran
    d25 = p[p["연도"] == 2025].reset_index(drop=True)
    W = queen(d25)
    mi = [Moran(R[:, k], W, permutations=0).I for k in range(len(YEARS))]
    print(f"[5] 연도별 출동률 Moran's I {np.round(mi, 3).tolist()}; 10년 평균 출동률의 Moran's I {Moran(R.mean(1), W, permutations=0).I:.3f}")
    # 동별 시계열 기울기
    tt = np.array(YEARS) - 2020.5
    slope = (R - R.mean(1, keepdims=True)) @ tt / (tt @ tt)
    print(f"    동별 출동률 연 변화(최소제곱 기울기) {slope.min():.2f}~{slope.max():.2f}, 중앙값 {np.median(slope):.3f}")
    return s, R, W, d25


def interp(p):
    """경계 변화: 빨리 자란 동 8곳을 2016년에는 이웃 동과 한 동이었다고 보고, 지금 경계로 다시 나눔"""
    from exactextract import exact_extract

    d = p[p["연도"] == 2025].reset_index(drop=True)
    v16 = p[p["연도"] == 2016].set_index("동코드").loc[d["동코드"]]
    grow = (d["인구"].to_numpy() / v16["인구"].to_numpy())
    W = queen(d)
    order = np.argsort(-grow)
    used, pairs = set(), []
    for i in order:
        if i in used:
            continue
        nb = [j for j in W.neighbors[i] if j not in used and d["구"][j] == d["구"][i]]  # 같은 구 안의 이웃
        if not nb:
            continue
        j = max(nb, key=lambda j: d.geometry[i].intersection(d.geometry[j]).length)
        pairs.append((i, j))
        used |= {i, j}
        if len(pairs) == 8:
            break
    grid_pop = exact_extract(os.path.join(DATA, "hanbit_pop100.tif"), d, "sum", output="pandas")
    gp = grid_pop.iloc[:, 0].to_numpy()  # 1밴드(인구) 합
    res = []
    for i, j in pairs:
        for var in ("인구", "출동건수"):
            tot16 = v16[var].iloc[i] + v16[var].iloc[j]
            a = d.geometry[i].area / (d.geometry[i].area + d.geometry[j].area)
            w = gp[i] / (gp[i] + gp[j])
            res.append((var, d["동이름"][i], d["동이름"][j], tot16, v16[var].iloc[i], tot16 * a, tot16 * w, a, w))
    df = pd.DataFrame(res, columns=["변수", "동", "짝", "합친값", "참값", "면적비례", "인구비례", "면적몫", "인구몫"])
    print("[6] 경계 변화 재현: 2016년에 한 동이던 8쌍을 지금 경계로 나눔 (쌍의 첫 동 기준)")
    print(df.round(3).to_string(index=False))
    for var in ("인구", "출동건수"):
        x = df[df["변수"] == var]
        print(f"  {var}: 평균 절대 오차 면적 비례 {np.abs(x['면적비례'] - x['참값']).mean():.1f}, 인구 비례(2025년 격자 인구) {np.abs(x['인구비례'] - x['참값']).mean():.1f}; "
              f"상대 오차 중앙값 면적 {np.median(np.abs(x['면적비례'] / x['참값'] - 1)) * 100:.1f}%, 인구 {np.median(np.abs(x['인구비례'] / x['참값'] - 1)) * 100:.1f}%")
    return d, pairs, df


def stweights(W, T=10):
    from scipy import sparse
    n = W.n
    Ws = W.sparse
    I_T = sparse.identity(T)
    L = sparse.eye(T, k=-1)
    blocks = {"같은 연도 이웃": sparse.kron(I_T, Ws), "앞 연도 같은 동": sparse.kron(L, sparse.identity(n)), "앞 연도 이웃": sparse.kron(L, Ws)}
    print(f"[7] 시공간 가중치 (동 {n}개 × 연도 {T}개 = {n * T}): " + ", ".join(f"{k} 0이 아닌 칸 {v.nnz:,}" for k, v in blocks.items()))


# ---------------------------------------------------------------- 그림
def fig_trend(s):
    W_, H = 720, 280
    r = np.corrcoef(s["폭염일수"], s["출동건수"])[0, 1]
    s_ = s.reset_index()
    svg = Svg(W_, H, f"왼쪽: 한빛시 전체의 연도별 폭염 구급 출동 건수(막대)와 그해 폭염일수(막대 위 숫자). 2018년과 2024년처럼 폭염일수가 많은 해에 출동이 많음. "
                     f"오른쪽: 폭염일수와 출동 건수(점 하나가 한 해, 상관 {r:.2f}). 연도에 따라 도시 전체가 함께 오르내리는 시간 변동이 큼")
    ax = Axes(svg, 60, 36, 330, 190, (2015.4, 2025.6), (0, 1800))
    for _, row in s_.iterrows():
        x0, x1 = float(ax.X(row["연도"] - 0.36)), float(ax.X(row["연도"] + 0.36))
        svg.rect(x0, float(ax.Y(row["출동건수"])), x1 - x0, float(ax.Y(0)) - float(ax.Y(row["출동건수"])), cls="s-bg f-ac", width=0.5)
        svg.text((x0 + x1) / 2, float(ax.Y(row["출동건수"])) - 4, f"{int(row['폭염일수'])}일", size=9, cls="f-mu")
    ax.xaxis(ticks=[2016, 2019, 2022, 2025], label="연도", fmt=lambda t: f"{int(t)}")
    ax.yaxis(ticks=[0, 500, 1000, 1500], label="출동 건수")
    ax2 = Axes(svg, 470, 36, 220, 190, (5, 38), (700, 1800))
    for _, row in s_.iterrows():
        X, Y = float(ax2.X(row["폭염일수"])), float(ax2.Y(row["출동건수"]))
        svg.circle(X, Y, 4, cls="f-bd s-bg", width=0.8)
        svg.text(X + 6, Y + 4, f"{int(row['연도']) % 100:02d}", size=9, anchor="start", cls="f-mu")
    ax2.xaxis(ticks=[10, 20, 30], label="폭염일수")
    ax2.yaxis(ticks=[800, 1200, 1600])
    svg.save(os.path.join(OUT, "33-trend.svg"))


def fig_maps(p, R, d25):
    W_, H = 720, 190
    br = np.quantile(R, [0.2, 0.4, 0.6, 0.8])
    svg = Svg(W_, H, "동별 출동률(1만 명당) 지도. 2016, 2018, 2020, 2025년을 열 해 전체의 5분위 경계(모든 기간 같은 계급 경계)로 칠함. 폭염일수가 많았던 2018년은 전체가 진하고 "
                     "적었던 2020년은 옅음. 해마다 계급 경계를 따로 정하면 이 차이가 사라지고 순위의 변화만 보임")
    mw = 168
    for k, yr in enumerate((2016, 2018, 2020, 2025)):
        v = R[:, YEARS.index(yr)]
        cls = [f"q{int(np.digitize(t, br))}" for t in v]
        fr = MapFrame(d25.total_bounds, 10 + k * (mw + 9), 36, mw)
        draw(svg, fr, d25.geometry, cls, width=0.25)
        outline(svg, fr, d25.union_all(), cls="s-mu", width=0.7)
        svg.text(fr.x + mw / 2, 24, f"{yr}년", size=12, weight="600")
    x = 140
    labs = [f"< {br[0]:.1f}", f"{br[0]:.1f}~{br[1]:.1f}", f"{br[1]:.1f}~{br[2]:.1f}", f"{br[2]:.1f}~{br[3]:.1f}", f"≥ {br[3]:.1f}"]
    for k, lab in enumerate(labs):
        svg.rect(x, H - 22, 12, 12, cls=f"s-mu q{k}", width=0.5)
        svg.text(x + 16, H - 12, lab, size=10, anchor="start")
        x += 30 + len(lab) * 6.5
    svg.save(os.path.join(OUT, "33-maps.svg"))
    print(f"[그림] 출동률 5분위 경계(열 해 전체) {np.round(br, 2).tolist()}, 최댓값 {R.max():.2f}")
    for yr in (2016, 2018, 2020, 2025):
        v = R[:, YEARS.index(yr)]
        print(f"  {yr}: 가장 높은 계급 {(v > br[3]).sum()}개 동, 가장 낮은 계급 {(v <= br[0]).sum()}개 동")


def fig_interp(d, pairs, df):
    W_, H = 720, 300
    x = df[df["변수"] == "인구"]
    svg = Svg(W_, H, "경계 변화 다루기. 왼쪽: 2016년에는 한 동이었다고 보고 합친 8쌍(진한 테두리). 진한 주황은 추정 대상인 빨리 자란 동, 옅은 주황은 그 짝 동. 오른쪽: 2016년 인구의 참값과, 합친 값을 지금 경계로 나눈 추정값. "
                     "면적 비례(속 빈 점)는 인구가 몰린 쪽을 크게 틀리고, 지금의 격자 인구로 나눈 인구 비례(속 찬 점)는 참값에 가까움")
    fr = MapFrame(d.total_bounds, 20, 36, 330)
    first = {i for i, _ in pairs}
    pair_any = {k for ij in pairs for k in ij}
    cls = ["q3" if k in first else ("q1" if k in pair_any else "f-sf") for k in range(len(d))]
    draw(svg, fr, d.geometry, cls, width=0.3, stroke="s-mu")
    for i, j in pairs:
        outline(svg, fr, d.geometry[i].union(d.geometry[j]), cls="s-fg", width=1.6)
    outline(svg, fr, d.union_all(), cls="s-mu", width=0.8)
    svg.text(185, 24, "2016년에 한 동이던 8쌍", size=12, weight="600")
    lo, hi = 0, max(x["참값"].max(), x["면적비례"].max(), x["인구비례"].max()) * 1.08
    ax = Axes(svg, 440, 36, 240, 200, (lo, hi), (lo, hi))
    ax.curve(np.array([lo, hi]), np.array([lo, hi]), cls="s-mu", width=1, dash="4 3")
    for _, row in x.iterrows():
        svg.circle(float(ax.X(row["참값"])), float(ax.Y(row["면적비례"])), 4.5, cls="s-bd f-bg", width=1.6)
        svg.circle(float(ax.X(row["참값"])), float(ax.Y(row["인구비례"])), 4, cls="f-ac s-bg", width=0.6)
    ax.xaxis(label="2016년 인구 참값")
    ax.yaxis(label="나눠 얻은 추정값")
    svg.save(os.path.join(OUT, "33-interp.svg"))


def fig_stw():
    W_, H = 720, 250
    svg = Svg(W_, H, "시공간 가중치의 구조. 동 3개(1–2–3이 한 줄로 이웃)를 연도 3개만큼 쌓은 것. 가로 선은 같은 연도의 이웃(공간), 세로 선은 같은 동의 앞 연도(시간), "
                     "비스듬한 점선은 앞 연도의 이웃(시공간 파급). 어떤 선을 이웃으로 셀지에 따라 시공간 분석과 모형이 달라짐")
    xs = [250, 380, 510]
    ys = [190, 125, 60]
    for t, y in enumerate(ys):
        svg.text(150, y + 5, f"{2023 + t}년", size=12, anchor="end", weight="600")
        for a, b in ((0, 1), (1, 2)):
            svg.line(xs[a] + 20, y, xs[b] - 20, y, cls="s-ac", width=2.2)
        for k, x in enumerate(xs):
            svg.circle(x, y, 18, cls="f-acs s-fg", width=1.2)
            svg.text(x, y + 5, f"동{k + 1}", size=12)
        if t > 0:
            yp = ys[t - 1]
            for k, x in enumerate(xs):
                svg.line(x, yp - 18, x, y + 18, cls="s-bd", width=2)
            for a, b in ((0, 1), (1, 0), (1, 2), (2, 1)):
                svg.line(xs[a] + (12 if b > a else -12), yp - 14, xs[b] + (-14 if b > a else 14), y + 14, cls="s-ok", width=1.2, dash="4 3")
    lx = 575
    for k, (cls, dash, lab) in enumerate((("s-ac", None, "같은 연도 이웃"), ("s-bd", None, "앞 연도 같은 동"), ("s-ok", "4 3", "앞 연도 이웃"))):
        y = 80 + k * 30
        svg.line(lx, y, lx + 26, y, cls=cls, width=2, dash=dash)
        svg.text(lx + 32, y + 4, lab, size=11, anchor="start")
    svg.save(os.path.join(OUT, "33-stw.svg"))


if __name__ == "__main__":
    hand()
    p = load()
    s, R, W, d25 = numbers(p)
    stweights(W)
    d, pairs, df = interp(p)
    fig_trend(s)
    fig_maps(p, R, d25)
    fig_interp(d, pairs, df)
    fig_stw()
