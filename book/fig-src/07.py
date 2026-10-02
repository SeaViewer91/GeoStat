"""7강 그림과 본문 수치.

- 07-perm.svg : 마루구와 나머지 구의 출동률 평균 차이에 대한 순열 분포 (라벨을 섞음)
- 07-moran.svg : 출동률과 고령비율의 Moran's I 순열 분포 (값을 위치에 섞음)
- 07-multiple.svg : 행정동 150개를 하나씩 검정할 때 우연히 나오는 '유의한 동'의 수와, 정렬한 p값과 보정 기준

Moran's I와 LISA는 GeoStat 엔진의 함수(esda_ops.moran, esda_ops.local)와 앱의 기본 난수 시드(123456789)로 계산해 앱 결과와 같게 함.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/07.py
"""
import itertools
import os
import sys
import warnings

import geopandas as gpd
import numpy as np
from scipy import stats
from scipy.stats import false_discovery_control

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from plotkit import Axes  # noqa: E402
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import aggregate as agg  # noqa: E402
from geostat_engine.analysis import esda_ops as eo  # noqa: E402
from geostat_engine.analysis import weights as gw  # noqa: E402

warnings.filterwarnings("ignore")
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "..", "fig")
APP_SEED = 123456789  # GeoStat 기본 시드 (GeoDa와 같음)
SEED = 20261001

dong = gpd.read_file(os.path.join(DATA, "hanbit_dong.gpkg"))
events = gpd.read_file(os.path.join(DATA, "hanbit_events.gpkg"))
dong["PT_CNT"] = agg.aggregate(dong, events, stats=[], count=True, density=False).columns["CNT"]
dong["출동률"] = dong["PT_CNT"] / dong["인구"] * 10000
dong["고령비율"] = dong["고령인구"] / dong["인구"] * 100
W, _ = gw.build(dong, {"type": "queen"})
CITY = dong["PT_CNT"].sum() / dong["인구"].sum() * 10000
LAM = dong["인구"].to_numpy() * CITY / 1e4
RATE = dong["출동률"].to_numpy()
MARU = (dong["구"] == "마루구").to_numpy()


def poisson_p(x, lam):
    """양쪽 포아송 검정 p값: 2 × 작은 쪽 꼬리 확률 (1을 넘으면 1)"""
    return np.minimum(1, 2 * np.minimum(stats.poisson.cdf(x, lam), stats.poisson.sf(x - 1, lam)))


# ---------------------------------------------------------------- 수치
def numbers():
    print("[손계산] 3 대 3 순열")
    v = np.array([14, 18, 22, 9, 11, 13.0])
    obs = v[:3].mean() - v[3:].mean()
    ds = []
    for c in itertools.combinations(range(6), 3):
        m = np.zeros(6, bool)
        m[list(c)] = True
        ds.append(v[m].mean() - v[~m].mean())
    ds = np.array(ds)
    print(f"  관측 차이 {obs:.2f}, 배치 {len(ds)}가지, 차이 목록 {sorted(np.round(ds, 2).tolist())}")
    print(f"  한쪽 p = {(ds >= obs - 1e-9).sum()}/{len(ds)}, 양쪽 p = {(np.abs(ds) >= abs(obs) - 1e-9).sum()}/{len(ds)}")

    print("[1] 마루구 대 나머지 구 출동률")
    a, b = RATE[MARU], RATE[~MARU]
    obs = a.mean() - b.mean()
    t = stats.ttest_ind(a, b, equal_var=False)
    print(f"  마루구 {MARU.sum()}개 평균 {a.mean():.2f}, 나머지 {(~MARU).sum()}개 평균 {b.mean():.2f}, 차이 {obs:.2f}")
    print(f"  웰치 t검정: t = {t.statistic:.2f}, 자유도 {t.df:.1f}, p = {t.pvalue:.4f}")
    rng = np.random.default_rng(SEED)
    perm = np.empty(9999)
    for i in range(9999):
        m = rng.permutation(MARU)
        perm[i] = RATE[m].mean() - RATE[~m].mean()
    ge = (np.abs(perm) >= abs(obs)).sum()
    print(f"  순열 9,999번: |차이| ≥ 관측인 경우 {ge}번, 양쪽 p = ({ge} + 1)/(9999 + 1) = {(ge + 1) / 10000:.4f}; 순열 차이의 표준편차 {perm.std():.2f}")
    for nm, g in dong.groupby("구"):
        print(f"    {nm}: 동 {len(g)}개, 출동률 평균 {g['출동률'].mean():.2f}, 합산 출동률 {g['PT_CNT'].sum() / g['인구'].sum() * 1e4:.2f}")

    print("[2] 검정력: 참 출동률이 도시 전체의 2배인 동을 동 하나의 포아송 검정으로 찾을 확률 (α = 0.05)")
    ks = np.arange(0, 400)
    for pop in (1000, 3000, 10000, 18000):
        l0 = pop * CITY / 1e4
        rej = poisson_p(ks, l0) < 0.05
        print(f"  인구 {pop:,}: 기대 {l0:.2f}건, 검정력 {stats.poisson.pmf(ks, 2 * l0)[rej].sum():.1%}, 실제 1종 오류율 {stats.poisson.pmf(ks, l0)[rej].sum():.2%}")

    print("[3] Moran's I 순열 (퀸 인접, 행 표준화, 앱 시드)")
    for col in ("출동률", "고령비율"):
        for P in (99, 999, 9999):
            r = eo.moran(dong[col], W, P, APP_SEED)
            print(f"  {col} 순열 {P}: I = {r.I:.4f}, E[I] = {r.expected:.4f}, 유사 p = {r.p_sim:.4f}, z = {r.z_sim:.2f}")

    print("[4] 동별 포아송 검정 150개")
    p = poisson_p(dong["PT_CNT"].to_numpy(), LAM)
    q = false_discovery_control(p)
    order = np.argsort(p)
    print(f"  p < 0.05: {(p < 0.05).sum()}개 (위로 {((p < 0.05) & (RATE > CITY)).sum()}, 아래로 {((p < 0.05) & (RATE < CITY)).sum()})")
    print(f"  본페로니(0.05/150 = {0.05 / 150:.5f}): {(p < 0.05 / 150).sum()}개, BH(FDR 5%): {(q < 0.05).sum()}개")
    for i in order[:13]:
        print(f"    {dong['동이름'].iloc[i]}: 인구 {dong['인구'].iloc[i]:,}, {dong['PT_CNT'].iloc[i]}건 (기대 {LAM[i]:.1f}), p = {p[i]:.5f}, BH q = {q[i]:.4f}")
    k = np.arange(1, 151)
    passed = np.flatnonzero(np.sort(p) <= k * 0.05 / 150)
    print(f"  BH: p(k) ≤ k × 0.05/150을 만족하는 가장 큰 k = {passed.max() + 1 if passed.size else 0}")
    print(f"  홀름: {sum(1 for j, pv in enumerate(np.sort(p)) if all(np.sort(p)[:j + 1] <= 0.05 / (150 - np.arange(j + 1))))}개")
    rng = np.random.default_rng(SEED + 1)
    cnt, any_raw, any_bf, any_bh = [], 0, 0, 0
    for _ in range(2000):
        ps = poisson_p(rng.poisson(LAM), LAM)
        c = (ps < 0.05).sum()
        cnt.append(c)
        any_raw += c > 0
        any_bf += (ps < 0.05 / 150).any()
        any_bh += (false_discovery_control(ps) < 0.05).any()
    cnt = np.array(cnt)
    print(f"  귀무가설(모든 동 11.73)에서 2,000번: '유의한 동' 평균 {cnt.mean():.2f}개, 95% 분위 {np.percentile(cnt, 95):.0f}개, 최대 {cnt.max()}, "
          f"12개 이상인 경우 {(cnt >= 12).mean():.2%}")
    print(f"    하나라도 유의(가족별 오류율): 보정 없음 {any_raw / 2000:.1%}, 본페로니 {any_bf / 2000:.1%}, BH {any_bh / 2000:.1%}")

    print("[5] LISA (고령비율, 출동률) 유의한 피처 수 (앱 시드, α = 0.05)")
    for col in ("고령비율", "출동률"):
        for corr in ("none", "fdr", "bonferroni"):
            for P in (999, 9999):
                L = eo.local("lisa", dong[col], W, P, APP_SEED, 0.05, corr)
                n = sum(v for c, v in L.counts.items() if c in (1, 2, 3, 4))
                print(f"  {col} {corr} 순열 {P}: 유의 {n}개, 기준 p ≤ {L.threshold:.3g}, 가장 작은 p {np.nanmin(L.p):.4f}")
    return p, cnt, perm, obs


# ---------------------------------------------------------------- 그림 1. 두 집단 순열
def fig_perm(perm, obs):
    W_, H = 720, 260
    s = Svg(W_, H, "마루구 35개 동과 나머지 115개 동의 출동률 평균 차이. 막대는 구 라벨을 무작위로 섞어 9,999번 계산한 차이의 분포(순열 분포)이고, "
                   "주황 실선은 실제 차이 2.97, 주황 점선은 반대 방향의 같은 크기 −2.97로, 양쪽 p값은 두 선의 바깥을 모두 셈. 섞은 결과가 실제만큼 극단적인 경우는 드묾")
    lim = (-4, 4)
    edges = np.linspace(*lim, 57)
    c = np.histogram(perm, edges)[0]
    ax = Axes(s, 60, 30, 600, 170, lim, (0, max(c) * 1.12))
    ax.hist(c, edges, width=0.4)
    ax.xaxis(ticks=[-4, -3, -2, -1, 0, 1, 2, 3, 4], label="마루구 평균 − 나머지 평균 (출동률, 1만 명당)")
    ax.vline(obs, cls="s-bd", width=2)
    ax.vline(-obs, cls="s-bd", width=1.2, dash="4 3")
    s.text(float(ax.X(obs)) + 6, 44, f"실제 {obs:.2f}", size=11, anchor="start", cls="f-bd")
    s.text(float(ax.X(-obs)) - 6, 44, f"−{obs:.2f}", size=11, anchor="end", cls="f-bd")
    s.save(os.path.join(OUT, "07-perm.svg"))


# ---------------------------------------------------------------- 그림 2. Moran 순열
def moran_sims(col, P=999):
    """앱과 같은 방식(esda Moran, 시드 고정)으로 순열 분포를 얻음"""
    import esda
    np.random.seed(APP_SEED)
    wr = eo._row_standardized(W)
    m = esda.Moran(dong[col].to_numpy(float), wr, transformation="r", permutations=P)
    return m.I, m.sim, m.p_sim


def fig_moran():
    W_, H = 720, 270
    s = Svg(W_, H, "값을 행정동에 무작위로 다시 배치해 999번 계산한 Moran's I의 분포(막대)와 실제 값(주황 선). 출동률은 실제 값이 분포의 "
                   "오른쪽 끝에 걸쳐 있고(유사 p 0.031), 고령비율은 분포에서 멀리 떨어져 있음(유사 p 0.001)")
    for i, (col, title) in enumerate((("출동률", "출동률"), ("고령비율", "고령비율"))):
        I, sim, p = moran_sims(col)
        lim = (-0.25, 0.9)
        edges = np.linspace(*lim, 70)
        c = np.histogram(sim, edges)[0]
        ax = Axes(s, 40 + i * 350, 46, 310, 160, lim, (0, max(c) * 1.1))
        s.text(ax.x0 + 155, 26, f"{title}: I = {I:.3f}, 유사 p = {p:.3f}", size=12, weight="600")
        ax.hist(c, edges, width=0.3)
        ax.vline(I, cls="s-bd", width=2)
        ax.vline(-1 / 149, cls="s-mu", width=1, dash="3 2")
        ax.xaxis(ticks=[-0.2, 0, 0.2, 0.4, 0.6, 0.8], label="Moran's I", fmt=lambda t: f"{t:.1f}")
    s.text(W_ / 2, H - 6, "회색 점선: 무작위일 때의 기댓값 E[I] = −1/149", size=10, cls="f-mu")
    s.save(os.path.join(OUT, "07-moran.svg"))


# ---------------------------------------------------------------- 그림 3. 다중검정
def fig_multiple(p, cnt):
    W_, H = 720, 300
    s = Svg(W_, H, "왼쪽: 모든 동의 참 출동률이 같을 때 동 150개를 하나씩 검정하면 우연만으로 '유의한 동'이 평균 4.5개 나옴(2,000번 모의 실험). "
                   "실제 자료에서는 12개였음. 오른쪽: 실제 p값을 작은 것부터 늘어놓고 0.05, BH, 본페로니 기준과 비교한 것. 속이 찬 주황 점은 본페로니 기준을, 테두리가 진한 점은 0.05를 통과한 p값")
    # 왼쪽: 귀무 분포
    edges = np.arange(-0.5, 16.5, 1)
    c = np.histogram(cnt, edges)[0]
    ax = Axes(s, 50, 40, 270, 180, (-0.5, 15.5), (0, max(c) * 1.12))
    s.text(ax.x0 + 135, 22, "귀무가설에서 '유의한 동'의 수", size=12, weight="600")
    ax.hist(c, edges, width=0.5)
    obs = int((p < 0.05).sum())
    ax.vline(obs, cls="s-bd", width=2)
    s.text(float(ax.X(obs)) - 4, 56, f"실제 {obs}개", size=11, anchor="end", cls="f-bd")
    ax.xaxis(ticks=[0, 5, 10, 15], label="p < 0.05인 동의 수")
    # 오른쪽: 정렬 p값 (로그 눈금), 앞쪽 30개
    k = np.arange(1, 31)
    ps = np.sort(p)[:30]
    ax2 = Axes(s, 420, 40, 270, 180, (0.5, 30.5), (-5.2, 0))
    s.text(ax2.x0 + 140, 22, "작은 p값 30개 (로그 눈금)", size=12, weight="600")
    ax2.yaxis(ticks=[-5, -4, -3, -2, -1, 0], fmt=lambda t: f"{10 ** t:.{max(0, -int(t))}f}")
    ax2.xaxis(ticks=[1, 10, 20, 30], label="p값의 순위 k")
    ax2.curve([0.5, 30.5], [np.log10(0.05)] * 2, cls="s-mu", width=1.2)
    ax2.curve(k, np.log10(k * 0.05 / 150), cls="s-ok", width=1.4)
    ax2.curve([0.5, 30.5], [np.log10(0.05 / 150)] * 2, cls="s-ac", width=1.4)
    for kk, pv in zip(k, ps):
        cls = "s-fg f-bd" if pv < 0.05 / 150 else ("s-fg f-sf" if pv < 0.05 else "s-mu f-sf")
        s.circle(float(ax2.X(kk)), float(ax2.Y(np.log10(pv))), 3, cls=cls, width=0.7)
    s.text(ax2.x0 + ax2.w - 2, float(ax2.Y(np.log10(0.05))) - 5, "0.05", size=10, anchor="end", cls="f-mu")
    s.text(ax2.x0 + ax2.w - 2, float(ax2.Y(np.log10(30 * 0.05 / 150))) + 14, "BH: k × 0.05/150", size=10, anchor="end", cls="f-ok")
    s.text(ax2.x0 + ax2.w - 2, float(ax2.Y(np.log10(0.05 / 150))) + 14, "본페로니: 0.05/150", size=10, anchor="end", cls="f-ac")
    s.save(os.path.join(OUT, "07-multiple.svg"))


if __name__ == "__main__":
    p, cnt, perm, obs = numbers()
    fig_perm(perm, obs)
    fig_moran()
    fig_multiple(p, cnt)
