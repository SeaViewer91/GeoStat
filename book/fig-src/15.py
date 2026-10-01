"""15강 그림과 본문 수치.

- 15-windows.svg : 원형 창이 커지며 이웃 동을 차례로 묶는 모습(마루16동 중심)
- 15-result.svg : 출동의 가장 가능성 높은 군집과 2차 군집. 왼쪽은 인구 기준, 오른쪽은 연령 표준화 기대 건수 기준
- 15-llr.svg : 귀무가설 아래 최대 로그우도비의 분포(몬테카를로 999회)와 관측값

GeoStat에는 스캔 통계가 없어 Kulldorff(1997)의 포아송 공간 스캔 통계를 numpy로 구현함.
창은 동 중심점에서 가까운 동부터 차례로 묶는 원이고, 창의 인구는 전체의 50% 이하로 제한함(SaTScan 기본값).
높은 비율의 군집만 찾고, 2차 군집은 SaTScan처럼 중심마다 가장 큰 창 하나씩을 후보로 두고 앞서 찾은 군집과 겹치지 않는 것을 고름.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/15.py
"""
import os
import sys
import warnings

import geopandas as gpd
import numpy as np
from scipy.stats import poisson

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import DATA, MapFrame, dong_vars, draw, outline  # noqa: E402
from plotkit import Axes  # noqa: E402
from svglib import Svg  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
SEED = 20261015
R = 999

dong = dong_vars()
B = dong.total_bounds
NM = dong["동이름"].to_numpy()
POP = dong["인구"].to_numpy(float)
CASES = dong["PT_CNT"].to_numpy(float)
CEN = dong.geometry.centroid
XY = np.c_[CEN.x, CEN.y]
D = np.sqrt(((XY[:, None] - XY[None]) ** 2).sum(-1))
ORDER = np.argsort(D, axis=1, kind="stable")  # 중심 동에서 가까운 순서

ev = gpd.read_file(os.path.join(DATA, "hanbit_events.gpkg"))
J = gpd.sjoin(ev, dong[["geometry"]], predicate="within")


def counts(mask):
    return J[mask].groupby("index_right").size().reindex(dong.index, fill_value=0).to_numpy(float)


def llr(O, E, C):
    """포아송 로그우도비. 창 안이 기대보다 많을 때만(높은 비율의 군집)"""
    with np.errstate(divide="ignore", invalid="ignore"):
        v = O * np.log(O / E) + (C - O) * np.log((C - O) / (C - E))
    return np.nan_to_num(np.where(O > E, v, 0.0))


def scan_llr(cases, base, maxfrac):
    C = cases.sum()
    cb = np.cumsum(base[ORDER], axis=1)
    E = cb / base.sum() * C
    O = np.cumsum(cases[ORDER], axis=1)
    L = np.where(cb <= maxfrac * base.sum(), llr(O, E, C), 0.0)
    return L, O, E


def scan(cases, base, maxfrac=0.5, seed=SEED, nclust=4):
    """Kulldorff 포아송 스캔. base는 인구(또는 기대 건수). 귀무가설: 사건이 base에 비례해 다항분포로 흩어짐"""
    L, O, E = scan_llr(cases, base, maxfrac)
    rng = np.random.default_rng(seed)
    C = int(cases.sum())
    p = base / base.sum()
    mx = np.array([scan_llr(rng.multinomial(C, p).astype(float), base, maxfrac)[0].max() for _ in range(R)])
    # SaTScan처럼 중심마다 LLR이 가장 큰 창 하나만 후보로 남기고, 큰 순서로 앞 군집과 겹치지 않는 것을 고름
    best_k = L.argmax(axis=1)
    cand = sorted(((L[i, best_k[i]], i, best_k[i]) for i in range(len(cases))), reverse=True)
    out, used = [], np.zeros(len(cases), bool)
    for v, i, k in cand:
        if v <= 0 or len(out) >= nclust:
            break
        mem = ORDER[i, : k + 1]
        if used[mem].any():
            continue
        o, e = O[i, k], E[i, k]
        out.append(dict(center=i, members=mem, O=o, E=e, RR=(o / e) / ((C - o) / (C - e)), LLR=L[i, k],
                        p=(1 + (mx >= L[i, k]).sum()) / (R + 1), radius=D[i, mem].max(), pop=POP[mem].sum()))
        used[mem] = True
    return out, mx, L


def show(res):
    for r in res:
        print(f"   중심 {NM[r['center']]}, 동 {len(r['members'])}개 {NM[r['members']].tolist()}, 반지름 {r['radius']:.0f} m, 인구 {r['pop']:.0f} ({r['pop'] / POP.sum():.1%}), "
              f"관측 {r['O']:.0f}, 기대 {r['E']:.2f}, O/E {r['O'] / r['E']:.2f}, RR {r['RR']:.2f}, LLR {r['LLR']:.2f}, p {r['p']:.3f}")


def numbers():
    out = {}
    C = CASES.sum()
    print(f"[0] 출동 {C:.0f}건, 인구 {POP.sum():.0f}, 전체 비율 {C / POP.sum() * 1e4:.4f}")
    nwin = int((np.cumsum(POP[ORDER], axis=1) <= 0.5 * POP.sum()).sum())
    print(f"  인구 50% 이하 창의 수 {nwin} (중심 150개 × 크기), 중심마다 창 수 평균 {nwin / 150:.1f}")
    print("[1] 인구 기준, 최대 50%")
    res, mx, L = scan(CASES, POP, 0.5)
    show(res)
    print(f"  귀무 최대 LLR: 평균 {mx.mean():.2f}, 95% {np.quantile(mx, 0.95):.2f}, 99% {np.quantile(mx, 0.99):.2f}, 최댓값 {mx.max():.2f}")
    out["pop"] = (res, mx)
    i = np.flatnonzero(NM == "다솜23동")[0]
    e1 = POP[i] / POP.sum() * C
    l1 = float(llr(np.array(CASES[i]), np.array(e1), C))
    print(f"  다솜23동 하나: 관측 {CASES[i]:.0f}, 기대 {e1:.2f}, 포아송 P(X ≥ {CASES[i]:.0f}) = {poisson.sf(CASES[i] - 1, e1):.4f}, "
          f"LLR {l1:.2f}, 스캔의 귀무 분포로 본 p {(1 + (mx >= l1).sum()) / (R + 1):.3f}, Bonferroni 기준 {0.05 / 150:.5f}")
    # 마루 군집에서 창 크기별 LLR
    c = res[0]["center"]
    print(f"  {NM[c]} 중심 창 크기별: " + ", ".join(f"{k + 1}개 LLR {L[c, k]:.2f}" for k in range(12)))
    print("[2] 인구 기준, 최대 10%")
    res10, mx10, _ = scan(CASES, POP, 0.1)
    show(res10)
    print(f"  귀무 최대 LLR 95% {np.quantile(mx10, 0.95):.2f}")
    print("[3] 연령 표준화 기대 건수 기준, 최대 50%")
    old = counts(J["연령대"] == "65+")
    P65 = dong["고령인구"].to_numpy(float)
    Pu = POP - P65
    Ex = P65 * old.sum() / P65.sum() + Pu * (C - old.sum()) / Pu.sum()
    resA, mxA, _ = scan(CASES, Ex, 0.5)
    show(resA)
    print(f"  귀무 최대 LLR 95% {np.quantile(mxA, 0.95):.2f}")
    out["age"] = (resA, mxA)
    hi = resA[1]["members"]
    print(f"  2차 군집 동들의 고령비율 평균 {(P65[hi] / POP[hi]).mean() * 100:.1f}% (도시 {P65.sum() / POP.sum() * 100:.1f}%), "
          f"인구 기준 O/E {CASES[hi].sum() / (POP[hi].sum() / POP.sum() * C):.2f}, 연령 표준화 O/E {CASES[hi].sum() / Ex[hi].sum():.2f}")
    print("[4] 찾고 확인하기: 6~7월로 찾고 8월로 확인")
    m67 = J["월"].isin([6, 7])
    c67, c8 = counts(m67), counts(J["월"] == 8)
    print(f"  6~7월 {c67.sum():.0f}건, 8월 {c8.sum():.0f}건")
    res67, mx67, _ = scan(c67, POP, 0.5)
    show(res67)
    for r in res67[:2]:
        mem = r["members"]
        e8 = POP[mem].sum() / POP.sum() * c8.sum()
        o8 = c8[mem].sum()
        print(f"   → 8월에 같은 창: 관측 {o8:.0f}, 기대 {e8:.2f}, O/E {o8 / e8:.2f}, 단측 포아송 p {poisson.sf(o8 - 1, e8):.2g}")
    print("[5] 귀무 자료에 스캔을 돌리면")
    rng = np.random.default_rng(SEED + 1)
    ps, sizes = [], []
    for k in range(2000):
        sim = rng.multinomial(int(C), POP / POP.sum()).astype(float)
        L0 = scan_llr(sim, POP, 0.5)[0]
        f = np.unravel_index(np.argmax(L0), L0.shape)
        ps.append((1 + (mx >= L0.max()).sum()) / (R + 1))
        sizes.append(f[1] + 1)
    ps, sizes = np.array(ps), np.array(sizes)
    print(f"  2000번 가운데 p ≤ 0.05 {int((ps <= 0.05).sum())}번 ({(ps <= 0.05).mean():.1%}), 가장 가능성 높은 창의 동 수 중앙값 {np.median(sizes):.0f}, 1개 동인 경우 {int((sizes == 1).sum())}번")
    return out, L


# ---------------------------------------------------------------- 그림
def circle_path(s, fr, cx, cy, r, cls="s-fg", width=1.6, dash=None, stroke=None):
    """원. stroke를 주면 모드와 관계없이 그 색으로 그림(밝은 지도 위에 그릴 때)"""
    X, Y = fr.xy(cx, cy)
    rr = r * fr.k
    d = f"M{X - rr:.1f},{Y:.1f} a{rr:.1f},{rr:.1f} 0 1,0 {2 * rr:.1f},0 a{rr:.1f},{rr:.1f} 0 1,0 {-2 * rr:.1f},0"
    da = f' stroke-dasharray="{dash}"' if dash else ""
    if stroke:
        s.add(f'<path d="{d}" stroke="{stroke}" stroke-width="{width}" fill="none"{da}/>')
    else:
        s.add(f'<path d="{d}" class="{cls}" stroke-width="{width}" fill="none"{da}/>')


def map_text(s, x, y, t, size=9, anchor="middle"):
    """지도(모드와 관계없이 밝은 색) 위의 글자는 항상 어두운 색으로 씀"""
    s.add(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" fill="#1c2330">{t}</text>')


def fig_windows(L):
    W_, H = 720, 320
    c = np.flatnonzero(NM == "마루16동")[0]
    s = Svg(W_, H, "스캔 통계의 원형 창. 마루16동의 중심점에서 원을 키우며 가까운 동을 하나씩 묶음(중심점이 원 안에 들어오면 그 동 전체를 넣음). 실선·파선·점선은 동 1개·4개·8개를 묶은 창이고, 점은 동의 중심점임. "
                   "창마다 관측 건수와 기대 건수로 로그우도비를 계산하고, 모든 중심과 크기의 창 가운데 가장 큰 것을 고름")
    x0, y0, x1, y1 = XY[c, 0] - 5000, XY[c, 1] - 3800, XY[c, 0] + 5000, XY[c, 1] + 3800
    fr = MapFrame((x0, y0, x1, y1), 20, 20, 400)
    from shapely.geometry import box

    clip = dong.geometry.intersection(box(x0, y0, x1, y1))
    keep = ~clip.is_empty
    draw(s, fr, clip[keep], None, width=0.6, stroke="s-mu", fills=["#f0f2f5"] * int(keep.sum()))
    for kk, cls, dash in ((1, "s-bd", None), (4, "s-bd", "5 3"), (8, "s-bd", "2 3")):
        mem = ORDER[c, :kk]
        rad = max(D[c, mem].max(), 250)  # 1개 동 창은 반지름이 0이라 보이도록 작은 원으로 그림
        circle_path(s, fr, XY[c, 0], XY[c, 1], rad, cls=cls, width=1.8, dash=dash)
        X, Y = fr.xy(XY[c, 0] + rad * 0.71, XY[c, 1] + rad * 0.71)
        s.add(f'<text x="{X + 3:.1f}" y="{Y - 2:.1f}" font-size="10" text-anchor="start" fill="#9a3412">{kk}개</text>')
    for j in ORDER[c, :12]:
        X, Y = fr.xy(*XY[j])
        if 20 <= X <= 420 and 20 <= Y <= 20 + fr.h:
            s.circle(X, Y, 2.5, cls="s-bg", width=0, fill="#1c2330")
    # 오른쪽: 창 크기별 LLR
    ax = Axes(s, 500, 40, 190, 220, (0.5, 12.5), (0, 28))
    s.text(595, 22, "마루16동 중심 창의 로그우도비", size=12, weight="600")
    ax.xaxis(ticks=[1, 4, 8, 12], label="창에 든 동의 수")
    ax.yaxis(ticks=[0, 5, 10, 15, 20, 25], label="LLR")
    ks = np.arange(1, 13)
    ax.curve(ks, L[c, :12], cls="s-ac", width=1.6)
    for k in ks:
        s.circle(float(ax.X(k)), float(ax.Y(L[c, k - 1])), 3 if k != 8 else 4.5, cls="s-bg f-ac" if k != 8 else "s-bg f-bd", width=0.5)
    s.text(float(ax.X(8)), float(ax.Y(L[c, 7])) - 9, f"최대 {L[c, 7]:.1f}", size=10, cls="f-bd")
    s.save(os.path.join(OUT, "15-windows.svg"))


def fig_result(out):
    W_, H = 720, 330
    s = Svg(W_, H, "출동의 공간 스캔 통계 결과(포아송, 창의 인구 50% 이하, 몬테카를로 999회). 왼쪽: 인구 기준. 오른쪽: 연령 표준화 기대 건수 기준. "
                   "진한 색은 유의한 군집(p ≤ 0.05), 연한 색은 유의하지 않은 2차 군집이고, 원은 창의 범위임(동 1개인 창은 작은 원으로 표시). 글자가 겹치는 2차 군집의 p는 본문 표에 있음")
    mw = 330
    fr = [MapFrame(B, 20 + k * (mw + 20), 40, mw) for k in range(2)]
    for k, (key, t) in enumerate((("pop", "인구 기준"), ("age", "연령 표준화 기준"))):
        res = out[key][0]
        fill = np.array(["#eeeeee"] * len(dong), dtype=object)
        for r in res:
            fill[r["members"]] = "#c2410c" if r["p"] <= 0.05 else "#fdc98f"
        s.text(fr[k].x + mw / 2, 26, t, size=12, weight="600")
        draw(s, fr[k], dong.geometry, None, width=0.3, fills=list(fill))
        placed = []
        for r in res:
            c = r["center"]
            circle_path(s, fr[k], XY[c, 0], XY[c, 1], max(r["radius"], 300), width=1.2, dash=None if r["p"] <= 0.05 else "3 3", stroke="#1c2330")
            X, Y = fr[k].xy(*XY[c])
            lab = f"p {r['p']:.3f}"
            ty = Y - r["radius"] * fr[k].k - 5 if r["radius"] > 0 else Y + 300 * fr[k].k + 11
            if all(abs(X - px) > 40 or abs(ty - py) > 12 for px, py in placed):  # 겹치는 글자는 생략(본문 표 참고)
                map_text(s, X, ty, lab)
                placed.append((X, ty))
    legend_y = 40 + fr[0].h + 24
    x = 20
    for fill, lab in (("#c2410c", "유의한 군집"), ("#fdc98f", "유의하지 않은 2차 군집")):
        s.rect(x, legend_y - 10, 12, 12, cls="s-mu", width=0.5, fill=fill)
        s.text(x + 16, legend_y, lab, size=10, anchor="start")
        x += 18 + len(lab) * 10 + 14
    s.save(os.path.join(OUT, "15-result.svg"))


def fig_llr(out):
    res, mx = out["pop"]
    W_, H = 720, 280
    s = Svg(W_, H, "귀무가설(출동이 인구에 비례해 무작위로 흩어짐) 아래에서 999번 모의한 자료마다 모든 창 가운데 가장 큰 로그우도비. "
                   "점선은 그 95% 지점임. 관측된 가장 가능성 높은 군집(마루구 8개 동)은 이 분포의 어떤 값보다 크고, 다솜23동 하나만의 LLR은 분포의 아래쪽에 있음")
    edges = np.arange(0, 27, 0.5)
    h = np.histogram(np.clip(mx, 0, 26.9), edges)[0]
    ax = Axes(s, 60, 30, 620, 190, (0, 27), (0, h.max() * 1.7))
    ax.hist(h, edges, width=0.5)
    ax.xaxis(ticks=[0, 5, 10, 15, 20, 25], label="최대 로그우도비 (LLR)")
    ax.yaxis(label="모의 횟수")
    q95 = np.quantile(mx, 0.95)
    i = np.flatnonzero(NM == "다솜23동")[0]
    C = CASES.sum()
    l1 = float(llr(np.array(CASES[i]), np.array(POP[i] / POP.sum() * C), C))
    items = ((l1, f"다솜23동 하나 {l1:.1f}", 46, "s-bd", "f-bd", None, "start"),
             (res[1]["LLR"], f"2차 군집({NM[res[1]['center']]} 중심) {res[1]['LLR']:.1f}", 66, "s-bd", "f-bd", None, "start"),
             (q95, f"귀무 분포의 95% {q95:.1f}", 86, "s-mu", "f-mu", "4 3", "start"),
             (res[0]["LLR"], f"마루구 8개 동 {res[0]['LLR']:.1f}", 46, "s-bd", "f-bd", None, "end"))
    for v, lab, y, sc, fc, dash, anc in items:
        ax.vline(v, cls=sc, width=1.6 if dash is None else 1.2, dash=dash, top=y - 4)
        s.text(float(ax.X(v)) + (4 if anc == "start" else -4), y, lab, size=10, anchor=anc, cls=fc)
    s.save(os.path.join(OUT, "15-llr.svg"))


if __name__ == "__main__":
    out, L = numbers()
    fig_windows(L)
    fig_result(out)
    fig_llr(out)
