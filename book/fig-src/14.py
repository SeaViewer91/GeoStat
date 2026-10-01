"""14강 그림과 본문 수치.

- 14-null.svg : 모든 동의 참 출동률이 같을 때(포아송) 원비율이 어떻게 흩어지는지. 한 번의 모의 자료와, 1,000번 모의에서 상위 10개 동이 어느 인구 4분위에서 나오는지
- 14-shrink.svg : 원비율과 EB 평활 비율. 인구가 적을수록 전체 비율 쪽으로 크게 당겨짐
- 14-maps.svg : 원비율, EB 평활, 공간 EB 평활을 같은 분위수 5계급으로 칠한 지도
- 14-eblisa.svg : 출동률의 LISA(원비율)와 EB 비율 LISA, EB 비율 LISA의 FDR 보정

비율은 GeoStat 엔진의 rates.compute(앱의 비율 지도 · EB 보정과 같은 esda 함수), EB Moran·EB LISA는 esda_ops로 계산함.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/14.py
"""
import os
import sys
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapkit import DATA, MapFrame, dong_vars, draw, quantile5  # noqa: E402
from plotkit import Axes  # noqa: E402
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import esda_ops as eo  # noqa: E402
from geostat_engine.analysis import rates  # noqa: E402
from geostat_engine.analysis import weights as gw  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")
APP_SEED = 123456789
SEED = 20261014
NSIM = 1000

dong = dong_vars()
B = dong.total_bounds
NM = dong["동이름"].to_numpy()
WQ = gw.build(dong, {"type": "queen"})[0]
POP = dong["인구"].to_numpy(float)
E = dong["PT_CNT"].to_numpy(float)
RAW = E / POP * 1e4
BETA = E.sum() / POP.sum() * 1e4
CL_FILL = {0: "#eeeeee", 1: "#ff0000", 2: "#0000ff", 3: "#a7adf9", 4: "#f4ada8", 5: "#464646"}
CL_NAME = {1: "HH", 2: "LL", 3: "LH", 4: "HL"}
QUART = np.searchsorted(np.quantile(POP, [0.25, 0.5, 0.75]), POP, side="left")  # 0~3, 인구 4분위


def row(nm):
    return np.flatnonzero(NM == nm)[0]


def raw_numbers():
    print("[1] 원비율")
    print(f"  출동 {E.sum():.0f}건, 인구 {POP.sum():.0f}명, 전체 비율 β = {BETA:.4f} (1만 명당)")
    print(f"  인구 4분위 경계: {np.quantile(POP, [0.25, 0.5, 0.75]).round(0).tolist()}, 4분위별 동 수 {np.bincount(QUART).tolist()}")
    z = E == 0
    print(f"  출동 0건인 동 {z.sum()}개: {list(zip(NM[z], POP[z].astype(int)))}, 평균 인구 {POP[z].mean():.0f}")
    lam = POP * BETA / 1e4
    print(f"  모든 동의 참 비율이 β라면 0건인 동의 기댓값 {np.exp(-lam).sum():.2f}개")
    o = np.argsort(-RAW, kind="stable")
    print("  원비율 상위 6:", [(NM[i], round(RAW[i], 2), int(E[i]), int(POP[i])) for i in o[:6]])
    print(f"  원비율 상위 10개 가운데 인구 최하위 4분위 {int((QUART[o[:10]] == 0).sum())}개, 하위 10개(0건 7개 포함) 가운데 {int((QUART[o[-10:]] == 0).sum())}개")
    for nm in ("다솜23동", "마루16동"):
        i = row(nm)
        print(f"  {nm}: 출동 {E[i]:.0f}, 인구 {POP[i]:.0f}, 원비율 {RAW[i]:.2f}, 1건 적으면 {(E[i] - 1) / POP[i] * 1e4:.2f}, 1건 많으면 {(E[i] + 1) / POP[i] * 1e4:.2f}")
    # 귀무 모의: 모든 동의 참 비율이 β
    rng = np.random.default_rng(SEED)
    top_q = np.zeros(4)
    ext_q = np.zeros(4)
    sd_q = np.zeros((NSIM, 4))
    ex = None
    for k in range(NSIM):
        es = rng.poisson(lam)
        rs = es / POP * 1e4
        o = np.lexsort((rng.random(150), -rs))  # 같은 값은 무작위로
        top_q += np.bincount(QUART[o[:10]], minlength=4)
        ext_q += np.bincount(QUART[o[-10:]], minlength=4)
        sd_q[k] = [rs[QUART == q].std() for q in range(4)]
        if k == 0:
            ex = rs
    print(f"  귀무 모의 {NSIM}번: 상위 10개 동의 인구 4분위 비율(최하위→최상위) {np.round(top_q / top_q.sum(), 3).tolist()}, "
          f"하위 10개 {np.round(ext_q / ext_q.sum(), 3).tolist()}")
    print(f"  귀무 모의의 4분위별 원비율 표준편차 평균 {sd_q.mean(0).round(2).tolist()}")
    print(f"  첫 모의: 범위 {ex.min():.2f}~{ex.max():.2f}, 0인 동 {(ex == 0).sum()}개, 최댓값 동 {NM[np.argmax(ex)]}(인구 {POP[np.argmax(ex)]:.0f})")
    print(f"  실제 자료 4분위별 원비율 표준편차 {[round(RAW[QUART == q].std(), 2) for q in range(4)]}")
    return top_q / top_q.sum(), ex


def smoothing():
    print("[2] 초과위험, EB, 공간 EB")
    out = {}
    for m in ("excess_risk", "eb", "spatial_rate", "spatial_eb"):
        out[m] = rates.compute(m, dong["PT_CNT"], dong["인구"], WQ, 1.0 if m == "excess_risk" else 10000)
        v = out[m]
        print(f"  {m}: 범위 {v.min():.3f}~{v.max():.3f}, 표준편차 {v.std():.3f}")
    print(f"  원비율 표준편차 {RAW.std():.3f}, 범위 {RAW.min():.2f}~{RAW.max():.2f}")
    print(f"  초과위험 = 원비율/β 확인: {np.allclose(out['excess_risk'], RAW / BETA)}")
    # EB 손계산 (1만 명당 단위)
    n = POP / 1e4
    s2 = (POP * (RAW - BETA) ** 2).sum() / POP.sum()
    nbar = n.mean()
    alpha = s2 - BETA / nbar
    w = alpha / (alpha + BETA / n)
    eb = w * RAW + (1 - w) * BETA
    print(f"  s² = {s2:.3f}, β/n̄ = {BETA / nbar:.3f} (n̄ = {nbar:.2f}만 명), α = {alpha:.3f}, 엔진과 같음 {np.allclose(eb, out['eb'])}")
    print(f"  가중치 범위 {w.min():.3f}~{w.max():.3f}")
    for nm in ("다솜23동", "다솜1동", "누리12동", "마루16동", "마루15동", "마루20동"):
        i = row(nm)
        print(f"   {nm}: 인구 {POP[i]:.0f}, 출동 {E[i]:.0f}, 원비율 {RAW[i]:.2f}, β/n {BETA / n[i]:.2f}, 가중치 {w[i]:.3f}, EB {eb[i]:.2f}, 공간 EB {out['spatial_eb'][i]:.2f}, 초과위험 {out['excess_risk'][i]:.3f}")
    o = np.argsort(-out["eb"])
    print("  EB 상위 6:", [(NM[i], round(out['eb'][i], 2), int(POP[i])) for i in o[:6]])
    print(f"  EB 상위 10개 가운데 인구 최하위 4분위 {int((QUART[o[:10]] == 0).sum())}개")
    o = np.argsort(-out["spatial_eb"])
    print("  공간 EB 상위 6:", [(NM[i], round(out['spatial_eb'][i], 2), int(POP[i])) for i in o[:6]])
    # 초과위험 박스 지도 상위 이상치
    q1, q3 = np.percentile(out["excess_risk"], [25, 75])
    fence = q3 + 1.5 * (q3 - q1)
    up = out["excess_risk"] > fence
    print(f"  초과위험 박스 지도 위 울타리 {fence:.3f}, 상위 이상치 {up.sum()}개: {[(NM[i], round(out['excess_risk'][i], 2), int(POP[i])) for i in np.flatnonzero(up)]}")
    return out, w


def smr():
    print("[3] 연령 표준화 SMR")
    ev = gpd.read_file(os.path.join(DATA, "hanbit_events.gpkg"))
    j = gpd.sjoin(ev, dong[["geometry"]], predicate="within")
    print(f"  출동의 연령대: {ev['연령대'].value_counts().to_dict()}")
    old = (j["연령대"] == "65+").groupby(j["index_right"]).sum().reindex(dong.index, fill_value=0).to_numpy()
    tot = j.groupby("index_right").size().reindex(dong.index, fill_value=0).to_numpy()
    assert np.array_equal(tot, E)
    P65 = dong["고령인구"].to_numpy(float)
    Pu = POP - P65
    r65 = old.sum() / P65.sum() * 1e4
    ru = (tot - old).sum() / Pu.sum() * 1e4
    print(f"  65세 이상 출동 {old.sum()}건 / 고령인구 {P65.sum():.0f} → {r65:.4f}, 65세 미만 출동 {(tot - old).sum()}건 / {Pu.sum():.0f} → {ru:.4f} (1만 명당), 비 {r65 / ru:.2f}")
    Ex = (P65 * r65 + Pu * ru) / 1e4
    S = E / Ex
    ER = E / (POP * BETA / 1e4)
    print(f"  기대 건수 합 {Ex.sum():.1f}, SMR 범위 {S.min():.3f}~{S.max():.3f}, 초과위험과의 상관 {np.corrcoef(S, ER)[0, 1]:.3f}")
    for nm in ("다솜23동", "가람33동", "다솜8동", "가람19동"):
        i = row(nm)
        print(f"   {nm}: 고령 {P65[i]:.0f}/{POP[i]:.0f} ({P65[i] / POP[i] * 100:.1f}%), 관측 {E[i]:.0f}, 기대(나이 무시) {POP[i] * BETA / 1e4:.2f}, 기대(연령 표준화) {Ex[i]:.2f}, 초과위험 {ER[i]:.3f}, SMR {S[i]:.3f}")
    o1, o2 = np.argsort(-ER)[:10], np.argsort(-S)[:10]
    print(f"  초과위험 상위 10: {NM[o1].tolist()}")
    print(f"  SMR 상위 10: {NM[o2].tolist()}")
    for c, v in (("초과위험", ER), ("SMR", S)):
        m = eo.moran(pd.Series(v, name=c), WQ, 999, APP_SEED)
        print(f"  Moran's I ({c}) {m.I:.4f}, 유사 p {m.p_sim:.3f}")
    return S, Ex


def autocorr(out):
    print("[4] EB Moran과 EB LISA")
    m = eo.moran(dong["출동률"], WQ, 999, APP_SEED)
    print(f"  원비율 Moran's I {m.I:.4f} (z_sim {m.z_sim:.2f}, p {m.p_sim:.3f})")
    m = eo.moran(dong["PT_CNT"], WQ, 999, APP_SEED, rate_base=dong["인구"])
    print(f"  EB Moran's I {m.I:.4f} (z_sim {m.z_sim:.2f}, p {m.p_sim:.3f})")
    # Assunção-Reis 표준화 값
    n = POP / 1e4
    s2 = (POP * (RAW - BETA) ** 2).sum() / POP.sum()
    alpha = s2 - BETA / n.mean()
    zar = (RAW - BETA) / np.sqrt(alpha + BETA / n)
    o = np.argsort(-zar)
    print("  EB 표준화 값 상위 5:", [(NM[i], round(zar[i], 2)) for i in o[:5]], f"범위 {zar.min():.2f}~{zar.max():.2f}")
    for c in ("eb", "spatial_rate", "spatial_eb"):
        mm = eo.moran(pd.Series(out[c], name=c), WQ, 999, APP_SEED)
        print(f"  평활한 비율로 Moran's I ({c}) {mm.I:.4f}, 유사 p {mm.p_sim:.3f}")
    res = {}
    for corr in ("none", "fdr"):
        for P in (999, 9999):
            L = eo.local("lisa_eb", dong["PT_CNT"], WQ, P, APP_SEED, 0.05, corr, y=dong["인구"])
            Lr = eo.local("lisa", dong["출동률"], WQ, P, APP_SEED, 0.05, corr)
            print(f"  {corr} 순열 {P}: EB LISA {L.counts}, 원비율 LISA {Lr.counts}, EB 기준 p ≤ {L.threshold:.4g}")
            res[(corr, P)] = (L, Lr)
    L, Lr = res[("none", 999)]
    for k in (1, 2, 3, 4):
        print(f"   EB LISA {CL_NAME[k]}: {NM[L.cluster == k].tolist()}")
    print(f"   원비율에서만 유의: {NM[(Lr.cluster > 0) & (L.cluster == 0)].tolist()}")
    print(f"   EB에서만 유의: {NM[(L.cluster > 0) & (Lr.cluster == 0)].tolist()}")
    Lf = res[("fdr", 999)][0]
    print(f"   EB LISA FDR: {NM[Lf.cluster > 0].tolist()}, 유사 p {np.round(Lf.p[Lf.cluster > 0], 4).tolist()}")
    for nm in ("다솜1동", "다솜24동"):
        i = row(nm)
        print(f"   {nm}: 원비율 LISA {Lr.cluster[i]} (p {Lr.p[i]:.3f}), EB LISA {L.cluster[i]} (p {L.p[i]:.3f})")
    return res


# ---------------------------------------------------------------- 그림
def legend(s, x, y, items, size=10):
    for fill, label in items:
        s.rect(x, y - 10, 12, 12, cls="s-mu", width=0.5, fill=fill)
        s.text(x + 16, y, label, size=size, anchor="start")
        x += 18 + sum(size * (1.0 if ord(c) > 0x3000 else 0.6) for c in label) + 10


def logx_axes(s, x0, y0, w, h, ylim):
    ax = Axes(s, x0, y0, w, h, (np.log10(600), np.log10(25000)), ylim)
    ax.xaxis(ticks=[np.log10(v) for v in (1000, 2000, 5000, 10000, 20000)], label="인구 (로그 눈금)",
             fmt=lambda t: f"{10 ** t:,.0f}")
    return ax


def fig_null(share, ex):
    W_, H = 720, 350
    s = Svg(W_, H, "모든 동의 참 출동률이 도시 전체와 같은 11.73이라고 두고 출동 건수를 포아송분포로 만든 모의 자료. 왼쪽: 한 번의 모의에서 동별 원비율과 인구. "
                   "인구가 적은 동일수록 위아래로 크게 흩어짐. 오른쪽: 1,000번 모의에서 원비율 상위 10개 동이 인구 4분위 가운데 어디에서 나왔는지의 비율")
    ax = logx_axes(s, 60, 60, 330, 230, (0, 50))
    ax.yaxis(ticks=[0, 10, 20, 30, 40, 50], label="모의 출동률 (1만 명당)")
    s.text(60 + 165, 20, "참 비율이 모두 같을 때 (모의 1회)", size=12, weight="600")
    ax.curve([ax.xlim[0], ax.xlim[1]], [BETA, BETA], cls="s-bd", width=1.4, dash="4 3")
    for p, r in zip(POP, ex):
        s.circle(float(ax.X(np.log10(p))), float(ax.Y(min(r, 50))), 2.8, cls="s-bg f-ac", width=0.4)
    s.text(float(ax.X(np.log10(24000))), float(ax.Y(47)), f"점선: 참 비율 {BETA:.2f}", size=10, anchor="end", cls="f-bd")
    # 막대
    bx = 470
    ax2 = Axes(s, bx, 60, 220, 230, (-0.5, 3.5), (0, 0.7))
    s.text(bx + 110, 20, "상위 10개 동이 나온 인구 4분위", size=12, weight="600")
    ax2.yaxis(ticks=[0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7], label="비율", fmt=lambda t: f"{t:.0%}")
    labs = ["최하위", "2분위", "3분위", "최상위"]
    for q in range(4):
        x0 = float(ax2.X(q - 0.32))
        x1 = float(ax2.X(q + 0.32))
        y = float(ax2.Y(share[q]))
        s.rect(x0, y, x1 - x0, float(ax2.Y(0)) - y, cls="s-bg f-ac", width=0.5)
        s.text((x0 + x1) / 2, y - 5, f"{share[q]:.0%}", size=11)
        s.text((x0 + x1) / 2, float(ax2.Y(0)) + 16, labs[q], size=10, cls="f-mu")
    s.line(float(ax2.X(-0.5)), float(ax2.Y(0.25)), float(ax2.X(3.5)), float(ax2.Y(0.25)), cls="s-mu", width=1, dash="3 3")
    s.text(float(ax2.X(3.5)), float(ax2.Y(0.25)) - 5, "25%", size=10, anchor="end", cls="f-mu")
    s.text(bx + 110, 326, "인구 4분위 (동 37~38개씩)", size=11, cls="f-mu")
    s.save(os.path.join(OUT, "14-null.svg"))


def fig_shrink(out):
    W_, H = 720, 330
    eb = out["eb"]
    s = Svg(W_, H, "동별 원비율(속이 빈 점)과 EB 평활 비율(속이 찬 점). 선은 같은 동을 잇고, 가로 점선은 전체 비율 11.73임. "
                   "인구 1천 명 남짓한 동은 거의 전체 비율까지 당겨지고, 인구 1만 명이 넘는 동은 절반쯤만 당겨짐")
    ax = logx_axes(s, 70, 30, 600, 240, (0, 50))
    ax.yaxis(ticks=[0, 10, 20, 30, 40, 50], label="출동률 (1만 명당)")
    ax.curve([ax.xlim[0], ax.xlim[1]], [BETA, BETA], cls="s-bd", width=1.2, dash="4 3")
    for p, r, e in zip(POP, RAW, eb):
        X = float(ax.X(np.log10(p)))
        s.line(X, float(ax.Y(r)), X, float(ax.Y(e)), cls="s-mu", width=0.8)
    for p, r, e in zip(POP, RAW, eb):
        X = float(ax.X(np.log10(p)))
        s.circle(X, float(ax.Y(r)), 3, cls="s-mu f-bg", width=1)
        s.circle(X, float(ax.Y(e)), 2.6, cls="s-bg f-ac", width=0.4)
    for nm, dx, anchor in (("다솜23동", 8, "start"), ("마루16동", 8, "start"), ("다솜1동", 8, "start")):
        i = row(nm)
        s.text(float(ax.X(np.log10(POP[i]))) + dx, float(ax.Y(RAW[i])) + 4, f"{nm} {RAW[i]:.1f} → {eb[i]:.1f}", size=10, anchor=anchor)
    s.save(os.path.join(OUT, "14-shrink.svg"))


def fig_maps(out):
    W_, H = 720, 290
    s = Svg(W_, H, "같은 출동률을 세 가지로 계산해 각각 분위수 5계급으로 칠한 지도. 왼쪽: 원비율. 가운데: EB 평활(전체 비율 쪽으로). "
                   "오른쪽: 공간 EB 평활(이웃 비율 쪽으로). 원비율에서 가장 옅던 인구 적은 동(0건 등)이 EB에서 가운데 계급으로 올라오고, 공간 EB는 이웃과 섞여 매끈해짐")
    mw = 220
    fr = [MapFrame(B, 15 + k * (mw + 13), 40, mw) for k in range(3)]
    for k, (v, t) in enumerate(((RAW, "원비율"), (out["eb"], "EB 평활"), (out["spatial_eb"], "공간 EB 평활"))):
        q = quantile5(v)
        s.text(fr[k].x + mw / 2, 26, t, size=12, weight="600")
        draw(s, fr[k], dong.geometry, [f"q{c}" for c in q], width=0.3)
        print(f"  지도 {t}: 분위수 경계 {np.round(np.quantile(v, [0.2, 0.4, 0.6, 0.8]), 2).tolist()}")
    y = 40 + fr[0].h + 26
    x = 20
    for c, lab in zip(range(5), ["1분위(낮음)", "2", "3", "4", "5분위(높음)"]):
        s.rect(x, y - 10, 12, 12, cls=f"s-mu q{c}", width=0.5)
        s.text(x + 16, y, lab, size=10, anchor="start")
        x += 18 + sum(10 * (1.0 if ord(ch) > 0x3000 else 0.6) for ch in lab) + 12
    s.save(os.path.join(OUT, "14-maps.svg"))


def fig_eblisa(res):
    W_, H = 720, 290
    L, Lr = res[("none", 999)]
    Lf = res[("fdr", 999)][0]
    s = Svg(W_, H, "출동률의 LISA 군집 지도. 왼쪽: 원비율(12강, 보정 없음). 가운데: EB 비율 LISA(보정 없음). 오른쪽: EB 비율 LISA를 FDR로 보정. "
                   "인구가 적은 동의 이상치가 사라지고, 마루구 원도심의 다섯 동은 보정 후에도 남음")
    mw = 220
    fr = [MapFrame(B, 15 + k * (mw + 13), 40, mw) for k in range(3)]
    for k, (LL, t) in enumerate(((Lr, f"원비율 LISA ({int((Lr.cluster > 0).sum())}개)"), (L, f"EB 비율 LISA ({int((L.cluster > 0).sum())}개)"),
                                 (Lf, f"EB 비율 LISA, FDR ({int((Lf.cluster > 0).sum())}개)"))):
        s.text(fr[k].x + mw / 2, 26, t, size=12, weight="600")
        draw(s, fr[k], dong.geometry, None, width=0.3, fills=[CL_FILL[c] for c in LL.cluster])
    legend(s, 20, 40 + fr[0].h + 26, [(CL_FILL[1], "High-High"), (CL_FILL[2], "Low-Low"), (CL_FILL[3], "Low-High"), (CL_FILL[4], "High-Low"), (CL_FILL[0], "유의하지 않음")])
    s.save(os.path.join(OUT, "14-eblisa.svg"))


if __name__ == "__main__":
    share, ex = raw_numbers()
    out, w = smoothing()
    smr()
    res = autocorr(out)
    fig_null(share, ex)
    fig_shrink(out)
    fig_maps(out)
    fig_eblisa(res)
