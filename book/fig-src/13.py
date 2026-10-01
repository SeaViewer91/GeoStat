"""13강 그림과 본문 수치.

- 13-gi.svg : 출동률의 LISA 군집 지도와 Gi* 핫스팟 지도. 유사 p는 같고 라벨만 다름
- 13-geary.svg : 지표온도(ZS_MEAN)의 LISA 군집 지도와 Local Geary 군집 지도
- 13-bivariate.svg : 지표온도와 출동률의 산점도(피어슨 r)와 이변량 Moran 산점도(기울기 = 이변량 I)
- 13-ljc.svg : 고령상위(고령비율 상위 약 4분의 1) 동과 국지 Join Count로 유의한 동

국지 통계는 GeoStat 엔진의 esda_ops.local(앱과 같은 esda 함수, 조건부 순열 999, 시드 123456789)로 계산함.
Lee's L, 다변량 Local Geary, 국지 Join Count는 앱에 없어 esda로 직접 계산함.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/13.py
"""
import copy
import os
import sys
import warnings

import numpy as np
import pandas as pd
from scipy.stats import norm

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import MapFrame, dong_vars, draw, outline  # noqa: E402
from plotkit import Axes  # noqa: E402
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import esda_ops as eo  # noqa: E402
from geostat_engine.analysis import weights as gw  # noqa: E402

warnings.filterwarnings("ignore")
import esda  # noqa: E402

OUT = os.path.join(HERE, "..", "fig")
APP_SEED = 123456789

dong = dong_vars()
B = dong.total_bounds
NM = dong["동이름"].to_numpy()
WQ = gw.build(dong, {"type": "queen"})[0]
CL_FILL = {0: "#eeeeee", 1: "#ff0000", 2: "#0000ff", 3: "#a7adf9", 4: "#f4ada8", 5: "#464646"}  # 앱의 LISA 색
GI_FILL = {0: "#eeeeee", 1: "#ff0000", 2: "#0000ff", 5: "#464646"}  # 앱의 Gi* 색
GE_FILL = {0: "#eeeeee", 1: "#b2182b", 2: "#ef8a62", 3: "#fddbc7", 4: "#67adc7", 5: "#464646"}  # 앱의 Local Geary 색
CL_NAME = {0: "유의하지 않음", 1: "HH", 2: "LL", 3: "LH", 4: "HL"}


def local(method, col, corr="none", y=None):
    return eo.local(method, dong[col], WQ, 999, APP_SEED, 0.05, corr, y=None if y is None else dong[y])


def names(L, k):
    return NM[L.cluster == k].tolist()


def hand():
    print("[손계산] 3×3 '뭉침'(1,1,0 / 1,1,0 / 0,0,0), 룩 인접 + 자기 자신(이진)")
    x = np.array([1, 1, 0, 1, 1, 0, 0, 0, 0], float)
    W = np.zeros((9, 9))
    for r in range(3):
        for c in range(3):
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if 0 <= r + dr < 3 and 0 <= c + dc < 3:
                    W[r * 3 + c, (r + dr) * 3 + c + dc] = 1
    Ws = W + np.eye(9)
    n = 9
    xb = x.mean()
    S = np.sqrt((x ** 2).mean() - xb ** 2)
    print(f"  x̄ = {xb:.4f}, S = {S:.4f}")
    for i, nm in ((0, "왼쪽 위(1)"), (4, "가운데(1)"), (2, "오른쪽 위(0)"), (8, "오른쪽 아래(0)")):
        Wi = Ws[i].sum()
        S1 = (Ws[i] ** 2).sum()
        num = Ws[i] @ x - xb * Wi
        den = S * np.sqrt((n * S1 - Wi ** 2) / (n - 1))
        print(f"  {nm}: 합 {Ws[i] @ x:.0f} (칸 {Wi:.0f}개), 기댓값 {xb * Wi:.4f}, 분모 {den:.4f}, z = {num / den:.4f}")
    # esda와 대조
    from libpysal.weights import W as PW

    nbs = {i: list(np.flatnonzero(W[i])) for i in range(9)}
    pw = PW(nbs)
    g = esda.G_Local(x, pw, transform="B", star=True, permutations=0)
    print("  esda G_Local(star) Zs:", np.round(g.Zs, 4).tolist())


def gi_vs_lisa():
    print("[1] Gi*와 LISA (퀸 인접, 순열 999, 앱 시드)")
    out = {}
    for col in ("ZS_MEAN", "출동률", "고령비율"):
        for corr in ("none", "fdr"):
            Ll, Lg = local("lisa", col, corr), local("gi_star", col, corr)
            print(f"  {col} {corr}: LISA {Ll.counts}, Gi* {Lg.counts}, 유사 p 같음 {np.allclose(Ll.p, Lg.p, equal_nan=True)}")
            out[(col, corr)] = (Ll, Lg)
    Ll, Lg = out[("출동률", "none")]
    print("  출동률 교차표 (행 Gi*, 열 LISA)")
    print(pd.crosstab(Lg.cluster, Ll.cluster).to_string())
    print("  Gi* 핫스팟:", names(Lg, 1))
    print("  Gi* 콜드스팟:", names(Lg, 2))
    x = dong["출동률"].to_numpy()
    print(f"  출동률 평균 {x.mean():.2f}")
    for nm in ("다솜1동", "누리9동", "라온9동", "라온17동", "라온18동", "다솜18동", "다솜24동", "마루5동"):
        i = np.flatnonzero(NM == nm)[0]
        nb = list(WQ.neighbors[i])
        rest = (x.sum() - x[i]) / (len(x) - 1)
        print(f"   {nm}: 자기 {x[i]:.2f}, 이웃 {len(nb)}개 평균 {x[nb].mean():.2f}, 자기 포함 평균 {x[nb + [i]].mean():.2f}, "
              f"나머지 동 평균 {rest:.2f}, LISA {CL_NAME[Ll.cluster[i]]}, Gi* z {Lg.stat[i]:.3f}, 유사 p {Lg.p[i]:.3f}, 인구 {dong['인구'].iloc[i]}")
    i = np.flatnonzero(NM == "다솜1동")[0]
    nb = list(WQ.neighbors[i])
    print(f"   다솜1동 이웃: {list(zip(NM[nb], np.round(x[nb], 2)))}")
    # 정규 근사 양측 p (ArcGIS Hot Spot Analysis 방식)
    for col in ("출동률", "ZS_MEAN"):
        Lg = out[(col, "none")][1]
        pz = 2 * norm.sf(np.abs(Lg.stat))
        print(f"  {col}: Gi* z의 정규 근사 양측 p ≤ 0.05 {int((pz <= 0.05).sum())}개 (|z| ≥ 1.96), 순열 유사 p ≤ 0.05 {int((Lg.p <= 0.05).sum())}개")
        for lv, zc in ((0.10, 1.645), (0.05, 1.96), (0.01, 2.576)):
            print(f"    신뢰 {1 - lv:.0%} 이상 |z| ≥ {zc}: 핫 {int((Lg.stat >= zc).sum())}, 콜드 {int((Lg.stat <= -zc).sum())}")
    return out


def geary():
    print("[2] Local Geary (퀸 인접 행 표준화, 순열 999)")
    out = {}
    for col in ("ZS_MEAN", "출동률", "고령비율"):
        for corr in ("none", "fdr"):
            L = local("local_geary", col, corr)
            C = L.stat
            x = dong[col].to_numpy()
            # 앱 코드 3은 esda 라벨 3 = C_i가 평균보다 큰(주변과 다른) 동
            c3 = L.cluster == 3
            print(f"  {col} {corr}: {L.counts}, 기준 p ≤ {L.threshold:.4g}, 코드 3의 C_i > 평균 C {int((C[c3] > C.mean()).sum())}/{int(c3.sum())}")
            out[(col, corr)] = L
            if col == "출동률":
                for k in (1, 2, 3):
                    idx = np.flatnonzero(L.cluster == k)
                    print(f"    코드 {k}: " + ", ".join(f"{NM[i]}({x[i]:.1f}; 이웃 {x[list(WQ.neighbors[i])].mean():.1f})" for i in idx))
    Lg, Ll = out[("ZS_MEAN", "none")], local("lisa", "ZS_MEAN")
    print("  ZS_MEAN 교차표 (행 Geary, 열 LISA)")
    print(pd.crosstab(Lg.cluster, Ll.cluster).to_string())
    x = dong["ZS_MEAN"].to_numpy()
    rng_nb = np.array([np.ptp(x[list(WQ.neighbors[i])]) for i in range(WQ.n)])
    neg = Lg.cluster == 3
    print(f"  ZS_MEAN 코드 3(주변과 다름) 동: 이웃 값의 범위 평균 {rng_nb[neg].mean():.2f}℃, 나머지 동 {rng_nb[~neg].mean():.2f}℃")
    sd_nb = np.array([x[list(WQ.neighbors[i])].std() for i in range(WQ.n)])
    print(f"    이웃 값의 표준편차 평균 {sd_nb[neg].mean():.2f} vs {sd_nb[~neg].mean():.2f}")
    print(f"    자기 값과 이웃 평균의 차 |x − lag| 평균 {np.mean([abs(x[i] - x[list(WQ.neighbors[i])].mean()) for i in np.flatnonzero(neg)]):.2f} vs "
          f"{np.mean([abs(x[i] - x[list(WQ.neighbors[i])].mean()) for i in np.flatnonzero(~neg)]):.2f}")
    # 다변량 Local Geary (Anselin 2019)
    wr = copy.deepcopy(WQ)
    wr.transform = "r"
    np.random.seed(APP_SEED)
    mv = esda.Geary_Local_MV(connectivity=wr, permutations=999).fit([dong["ZS_MEAN"].to_numpy(float), dong["고령비율"].to_numpy(float)])
    thr = esda.fdr(mv.p_sim, 0.05)
    print(f"  다변량 Local Geary(지표온도·고령비율): p ≤ 0.05 {int((mv.p_sim <= 0.05).sum())}개, FDR {int((mv.p_sim <= thr).sum())}개")
    return out, Ll


def bivariate():
    print("[3] 이변량 Moran과 Lee's L")
    res = {}
    pairs = (("고령비율", "출동률"), ("ZS_MEAN", "출동률"), ("출동률", "ZS_MEAN"))
    for a, b in pairs:
        m = eo.moran(dong[a], WQ, 999, APP_SEED, y=dong[b])
        r = np.corrcoef(dong[a], dong[b])[0, 1]
        print(f"  자기 {a} × 이웃 {b}: 이변량 I {m.I:.4f} (z_sim {m.z_sim:.2f}, p {m.p_sim:.3f}), 피어슨 r {r:.4f}")
        res[(a, b)] = (m, r)
    # Lee's L
    wr = copy.deepcopy(WQ)
    wr.transform = "r"
    Wsp = wr.sparse
    for a, b in pairs[:2]:
        np.random.seed(APP_SEED)
        sp = esda.Spatial_Pearson(connectivity=Wsp, permutations=999).fit(dong[a].to_numpy(float)[:, None], dong[b].to_numpy(float)[:, None])
        za = (dong[a] - dong[a].mean()) / dong[a].std(ddof=0)
        zb = (dong[b] - dong[b].mean()) / dong[b].std(ddof=0)
        la, lb = Wsp @ za.to_numpy(), Wsp @ zb.to_numpy()
        print(f"  Lee's L({a}, {b}) = {sp.association_[0, 1]:.4f} (p {sp.significance_[0, 1]:.3f}), "
              f"L_XX {sp.association_[0, 0]:.3f}, L_YY {sp.association_[1, 1]:.3f}, 시차끼리의 r {np.corrcoef(la, lb)[0, 1]:.3f}, "
              f"√(L_XX·L_YY)·r = {np.sqrt(sp.association_[0, 0] * sp.association_[1, 1]) * np.corrcoef(la, lb)[0, 1]:.4f}, "
              f"직접 계산 Σ(Wz_a)(Wz_b)/n = {(la * lb).mean():.4f}")
    # 앱의 이변량 LISA
    for a, b in (("ZS_MEAN", "출동률"), ("고령비율", "출동률")):
        for corr in ("none", "fdr"):
            L = local("lisa_bv", a, corr, y=b)
            print(f"  이변량 LISA 자기 {a} × 이웃 {b} {corr}: {L.counts}")
    return res


def ljc():
    print("[4] Join Count (고령상위 = 고령비율 > 26.67)")
    y = (dong["고령비율"] > 26.67).astype(int).to_numpy()
    print(f"  1인 동 {y.sum()}개")
    wb = copy.deepcopy(WQ)
    wb.transform = "b"
    lj = esda.Join_Counts_Local(connectivity=wb, permutations=999, seed=APP_SEED, alternative="greater").fit(y)
    p = np.nan_to_num(lj.p_sim, nan=1.0)
    sig = p <= 0.05
    thr = esda.fdr(p[y == 1], 0.05)
    print(f"  국지 Join Count: 1인 동 가운데 이웃에 1이 있는 동 {int(((lj.LJC > 0) & (y == 1)).sum())}개, p ≤ 0.05 {int(sig.sum())}개, "
          f"FDR(1인 동 {y.sum()}개 기준) {int((p[y == 1] <= thr).sum())}개")
    print(f"  유의한 동의 LJC: {sorted(lj.LJC[sig].astype(int).tolist())}")
    print(f"  유의하지 않은 1인 동의 LJC: {sorted(lj.LJC[(y == 1) & ~sig].astype(int).tolist())}")
    ex = []
    for nm in NM[sig][:3]:
        i = np.flatnonzero(NM == nm)[0]
        ex.append((nm, int(lj.LJC[i]), WQ.cardinalities[i], round(float(p[i]), 3)))
    print(f"  예: {ex}")
    i_ = [i for i in np.flatnonzero((y == 1) & ~sig) if lj.LJC[i] == 3]
    print(f"  LJC 3인데 유의하지 않은 동: {[(NM[i], WQ.cardinalities[i], round(float(p[i]), 3)) for i in i_]}")
    i_ = [i for i in np.flatnonzero(sig) if lj.LJC[i] == 3]
    print(f"  LJC 3이고 유의한 동: {[(NM[i], WQ.cardinalities[i], round(float(p[i]), 3)) for i in i_]}")
    # 이변량 LISA로 본 같은 자료(LISA HH와 겹침)
    L = local("lisa", "고령비율")
    print(f"  유의한 국지 Join Count 동 가운데 고령비율 LISA HH {int((sig & (L.cluster == 1)).sum())}개")
    return y, sig


# ---------------------------------------------------------------- 그림
def legend(s, x, y, items, size=10):
    for fill, label in items:
        s.rect(x, y - 10, 12, 12, cls="s-mu", width=0.5, fill=fill)
        s.text(x + 16, y, label, size=size, anchor="start")
        x += 18 + sum(size * (1.0 if ord(c) > 0x3000 else 0.6) for c in label) + 10


def fig_gi(out):
    Ll, Lg = out[("출동률", "none")]
    W_, H = 720, 330
    s = Svg(W_, H, "출동률의 LISA 군집 지도(왼쪽)와 Gi* 핫스팟 지도(오른쪽). 퀸 인접, 순열 999, α = 0.05, 보정 없음. 두 지도에서 유의한 23개 동은 "
                   "같음. LISA의 Low-High는 Gi*에서 핫스팟이, High-Low는 콜드스팟이 됨. 굵은 테두리의 다솜1동만 High-Low인데 핫스팟으로 찍힘")
    mw = 330
    fr = [MapFrame(B, 20 + k * (mw + 20), 40, mw) for k in range(2)]
    s.text(fr[0].x + mw / 2, 26, "LISA 군집 지도", size=12, weight="600")
    s.text(fr[1].x + mw / 2, 26, "Gi* 핫스팟 지도", size=12, weight="600")
    draw(s, fr[0], dong.geometry, None, width=0.3, fills=[CL_FILL[c] for c in Ll.cluster])
    draw(s, fr[1], dong.geometry, None, width=0.3, fills=[GI_FILL[c] for c in Lg.cluster])
    i = np.flatnonzero(NM == "다솜1동")[0]
    for f in fr:
        outline(s, f, dong.geometry.iloc[i], width=2, stroke="#1c2330")
    y = 40 + fr[0].h + 24
    cl = {k: int((Ll.cluster == k).sum()) for k in range(1, 5)}
    gl = {k: int((Lg.cluster == k).sum()) for k in (1, 2)}
    legend(s, fr[0].x, y, [(CL_FILL[1], f"HH {cl[1]}"), (CL_FILL[2], f"LL {cl[2]}"), (CL_FILL[3], f"LH {cl[3]}"), (CL_FILL[4], f"HL {cl[4]}"), (CL_FILL[0], "유의하지 않음")])
    legend(s, fr[1].x, y, [(GI_FILL[1], f"핫스팟 {gl[1]}"), (GI_FILL[2], f"콜드스팟 {gl[2]}"), (GI_FILL[0], "유의하지 않음")])
    s.text(fr[0].x, y + 22, "굵은 테두리: 다솜1동", size=10, anchor="start", cls="f-mu")
    s.save(os.path.join(OUT, "13-gi.svg"))


def fig_geary(gout, Ll):
    Lg = gout[("ZS_MEAN", "none")]
    W_, H = 720, 330
    s = Svg(W_, H, "지표온도(ZS_MEAN)의 LISA 군집 지도(왼쪽)와 Local Geary 군집 지도(오른쪽). 퀸 인접, 순열 999, α = 0.05, 보정 없음. "
                   "Local Geary는 99개 동을 찍음. 연한 색의 '주변과 다름' 21개 동은 자기 값과 이웃 하나하나의 차이가 큰 곳으로, LISA의 이상치(HL, LH)와 다름")
    mw = 330
    fr = [MapFrame(B, 20 + k * (mw + 20), 40, mw) for k in range(2)]
    s.text(fr[0].x + mw / 2, 26, f"LISA 군집 지도 ({int((Ll.cluster > 0).sum())}개)", size=12, weight="600")
    s.text(fr[1].x + mw / 2, 26, f"Local Geary 군집 지도 ({int((Lg.cluster > 0).sum())}개)", size=12, weight="600")
    draw(s, fr[0], dong.geometry, None, width=0.3, fills=[CL_FILL[c] for c in Ll.cluster])
    draw(s, fr[1], dong.geometry, None, width=0.3, fills=[GE_FILL[c] for c in Lg.cluster])
    y = 40 + fr[0].h + 24
    cl = {k: int((Ll.cluster == k).sum()) for k in range(1, 5)}
    gl = {k: int((Lg.cluster == k).sum()) for k in range(1, 5)}
    legend(s, fr[0].x, y, [(CL_FILL[1], f"HH {cl[1]}"), (CL_FILL[2], f"LL {cl[2]}"), (CL_FILL[0], "유의하지 않음")])
    legend(s, fr[1].x, y, [(GE_FILL[1], f"HH {gl[1]}"), (GE_FILL[2], f"LL {gl[2]}"), (GE_FILL[3], f"주변과 다름 {gl[3]}")])
    s.text(fr[1].x, y + 22, "앱 범례에서는 '기타 양(+)의 연관'으로 표시됨(본문 참고)", size=10, anchor="start", cls="f-mu")
    s.save(os.path.join(OUT, "13-geary.svg"))


def fig_bivariate(res):
    m, r = res[("ZS_MEAN", "출동률")]
    za = m.z
    lag = m.lag
    zb = (dong["출동률"] - dong["출동률"].mean()) / dong["출동률"].std(ddof=0)
    W_, H = 720, 340
    s = Svg(W_, H, f"왼쪽: 지표온도와 출동률(둘 다 표준화)의 산점도. 기울기가 피어슨 r({r:.2f})임. 오른쪽: 이변량 Moran 산점도. 세로축이 이웃 동 "
                   f"출동률의 평균(공간 시차)이고, 기울기가 이변량 Moran's I({m.I:.2f})임. 같은 동 안의 상관과 이웃 간의 연관이 섞여 있음. 왼쪽 그림 위쪽 범위(4.5) 밖의 점 1개는 생략함")
    for k, (yy, ylab, slope_lab) in enumerate(((zb.to_numpy(), "출동률 (표준화)", f"기울기 = r = {r:.2f}"),
                                               (lag, "이웃 동 출동률의 평균 (표준화)", f"기울기 = 이변량 I = {m.I:.2f}"))):
        x0 = 60 + k * 360
        ax = Axes(s, x0, 50, 260, 230, (-2.5, 2.5), (-2.5, 4.5) if k == 0 else (-2.5, 2.5))
        s.text(x0 + 130, 20, "피어슨 상관 (같은 동끼리)" if k == 0 else "이변량 Moran (자기 값 × 이웃 값)", size=12, weight="600")
        ax.xaxis(ticks=[-2, -1, 0, 1, 2], label="지표온도 (표준화)")
        ax.yaxis(ticks=[-2, 0, 2, 4] if k == 0 else [-2, -1, 0, 1, 2], label=ylab)
        lo, hi = (-2.5, 4.5) if k == 0 else (-2.5, 2.5)
        ax.curve([-2.5, 2.5], [0, 0], cls="s-mu", width=0.8)
        ax.curve([0, 0], [lo, hi], cls="s-mu", width=0.8)
        for a, b in zip(za, yy):
            if lo <= b <= hi:
                s.circle(float(ax.X(a)), float(ax.Y(b)), 2.6, cls="s-bg f-ac", width=0.4)
        sl = np.polyfit(za, yy, 1)
        ax.curve([-2.5, 2.5], [sl[1] - 2.5 * sl[0], sl[1] + 2.5 * sl[0]], cls="s-bd", width=1.8)
        s.text(float(ax.X(2.4)), float(ax.Y(lo)) - 8, slope_lab, size=11, anchor="end", cls="f-bd")
        print(f"  그림 기울기 {k}: {sl[0]:.4f}, 범위 밖 점 {int(((yy < lo) | (yy > hi)).sum())}개")
    s.save(os.path.join(OUT, "13-bivariate.svg"))


def fig_ljc(y, sig):
    W_, H = 720, 320
    s = Svg(W_, H, "고령상위 동(고령비율 상위 38개 동)과 국지 Join Count. 진한 색은 이웃에 고령상위 동이 우연보다 많은 동(유사 p ≤ 0.05, 보정 없음), "
                   "연한 색은 고령상위이지만 유의하지 않은 동. 국지 Join Count는 앱에 없어 코드로 계산함")
    fr = MapFrame(B, 170, 20, 380)
    cls = np.where(sig, "#8c2d04", np.where(y == 1, "#fdc98f", "#eeeeee"))
    draw(s, fr, dong.geometry, None, width=0.3, fills=list(cls))
    legend(s, 170, 20 + fr.h + 24, [("#8c2d04", f"고령상위, 유의 {int(sig.sum())}"), ("#fdc98f", f"고령상위, 유의하지 않음 {int(((y == 1) & ~sig).sum())}"),
                                    ("#eeeeee", "나머지")])
    s.save(os.path.join(OUT, "13-ljc.svg"))


if __name__ == "__main__":
    hand()
    out = gi_vs_lisa()
    gout, Ll = geary()
    res = bivariate()
    y, sig = ljc()
    fig_gi(out)
    fig_geary(gout, Ll)
    fig_bivariate(res)
    fig_ljc(y, sig)
