"""6강 그림과 본문 수치.

- 06-shapes.svg : 행정동 고령비율·출동률·인구밀도·log(인구밀도)의 히스토그램 (분포의 모양)
- 06-funnel.svg : 행정동 출동률과 인구. 도시 전체 출동률을 참값으로 둘 때 우연만으로 생기는 범위(깔때기)
- 06-sampling.svg : 지표온도 래스터(육지 셀 전체)에서 무작위로 10·40·160개를 뽑을 때 표본평균의 분포
- 06-bootstrap.svg : 기상 관측소 48곳 기온 평균의 부트스트랩 분포와 신뢰구간

출동 건수는 엔진의 점 집계, 동별 평균 지표온도는 엔진의 존 통계로 계산해 앱 결과와 같게 함.

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/06.py
"""
import os
import sys
import warnings

import geopandas as gpd
import numpy as np
import rasterio
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from plotkit import Axes  # noqa: E402
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import aggregate as agg  # noqa: E402
from geostat_engine.analysis import zonal  # noqa: E402

warnings.filterwarnings("ignore")
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "..", "fig")
LST = os.path.join(DATA, "hanbit_lst.tif")
SEED = 20261001

dong = gpd.read_file(os.path.join(DATA, "hanbit_dong.gpkg"))
events = gpd.read_file(os.path.join(DATA, "hanbit_events.gpkg"))
stations = gpd.read_file(os.path.join(DATA, "hanbit_stations.gpkg"))
dong["PT_CNT"] = agg.aggregate(dong, events, stats=[], count=True, density=False).columns["CNT"]
pl = zonal.prepare(dong, type("R", (), {"path": LST, "info": {"count": 1, "crs": "EPSG:5186"}})(), {"stats": ["mean"], "band": 1})
dong["ZS_MEAN"] = zonal.run(pl, lambda *_: None)["columns"]["MEAN"]
dong["출동률"] = dong["PT_CNT"] / dong["인구"] * 10000
dong["고령비율"] = dong["고령인구"] / dong["인구"] * 100
dong["인구밀도"] = dong["인구"] / dong["면적_km2"]
with rasterio.open(LST) as src:
    LST_ALL = src.read(1, masked=True).compressed().astype(float)
TEMP = stations["기온_8월평균"].to_numpy(float)
CITY_RATE = dong["PT_CNT"].sum() / dong["인구"].sum() * 10000


def describe(x):
    x = np.asarray(x, float)
    q1, q3 = np.percentile(x, [25, 75])
    return dict(n=x.size, mean=x.mean(), median=np.median(x), sd=x.std(ddof=1), iqr=q3 - q1, q1=q1, q3=q3,
                cv=x.std(ddof=1) / x.mean(), skew=stats.skew(x), min=x.min(), max=x.max())


# ---------------------------------------------------------------- 수치
def numbers():
    print("[1] 요약통계 (행정동 150개)")
    for v in ("고령비율", "출동률", "인구밀도", "ZS_MEAN"):
        d = describe(dong[v])
        print(f"  {v}: 평균 {d['mean']:.2f}, 중앙값 {d['median']:.2f}, 표준편차 {d['sd']:.2f}, Q1 {d['q1']:.2f}, Q3 {d['q3']:.2f}, "
              f"IQR {d['iqr']:.2f}, 변동계수 {d['cv']:.2f}, 왜도 {d['skew']:.2f}, 최소 {d['min']:.2f}, 최대 {d['max']:.2f}")
    ld = np.log(dong["인구밀도"])
    print(f"  log(인구밀도): 평균 {ld.mean():.3f}, 중앙값 {ld.median():.3f}, 왜도 {stats.skew(ld):.2f}; "
          f"exp(평균 log) = 기하평균 {np.exp(ld.mean()):,.0f}명/㎢")
    print(f"  출동률: 동별 비율의 단순 평균 {dong['출동률'].mean():.2f}, 도시 전체 {dong['PT_CNT'].sum()}건 ÷ {dong['인구'].sum():,}명 = {CITY_RATE:.2f}, "
          f"인구 가중 평균 {np.average(dong['출동률'], weights=dong['인구']):.2f}")
    top = dong.nlargest(1, "출동률")
    d2 = dong.drop(top.index)
    print(f"  가장 큰 출동률 1개({top['동이름'].iloc[0]} {top['출동률'].iloc[0]:.2f}) 제외: 평균 {d2['출동률'].mean():.2f}, 중앙값 {d2['출동률'].median():.2f}")

    print("[2] 포아송과 깔때기")
    lam = dong["인구"] * CITY_RATE / 1e4
    for q, name in ((0.025, "95% 아래"), (0.975, "95% 위"), (0.001, "99.8% 아래"), (0.999, "99.8% 위")):
        lim = stats.poisson.ppf(q, lam)
        out = (dong["PT_CNT"] < lim) if q < 0.5 else (dong["PT_CNT"] > lim)
        print(f"  {name} 밖: {int(out.sum())}개 동 {dong.loc[out, '동이름'].tolist() if out.sum() <= 5 else ''}")
    for nm in ("다솜23동", "마루16동"):
        r = dong[dong["동이름"] == nm].iloc[0]
        l = r["인구"] * CITY_RATE / 1e4
        print(f"  {nm}: 인구 {r['인구']:,}, 기대 건수 {l:.2f}, 건수 표준편차 √λ {np.sqrt(l):.2f}, 출동률 표준오차 {np.sqrt(l) / r['인구'] * 1e4:.2f}, "
              f"95% 범위(건) {stats.poisson.ppf(0.025, l):.0f}~{stats.poisson.ppf(0.975, l):.0f}, 관측 {r['PT_CNT']}건")
    print(f"  95% 범위 밖 기대 수(참값이 도시 전체 출동률일 때): 약 150 × 0.05 = 7.5 (이산분포라 실제로는 더 적음)")
    # 이산 포아송에서 실제 바깥 확률의 합
    p_out = stats.poisson.cdf(stats.poisson.ppf(0.025, lam) - 1, lam) + stats.poisson.sf(stats.poisson.ppf(0.975, lam), lam)
    print(f"  이산 포아송의 실제 바깥 확률 합 = 기대 {p_out.sum():.2f}개 동")

    print("[3] 표본분포 (지표온도 육지 셀 전체를 모집단으로)")
    mu, sig = LST_ALL.mean(), LST_ALL.std()
    print(f"  모집단: 셀 {LST_ALL.size:,}개, 평균 {mu:.3f}, 표준편차 {sig:.3f}, 왜도 {stats.skew(LST_ALL):.2f}")
    rng = np.random.default_rng(SEED)
    for n in (10, 40, 160):
        means = np.array([LST_ALL[rng.integers(0, LST_ALL.size, n)].mean() for _ in range(5000)])
        print(f"  n={n}: 이론 표준오차 σ/√n {sig / np.sqrt(n):.3f}, 5000번 표본평균의 표준편차 {means.std():.3f}, 평균 {means.mean():.3f}")
    rng = np.random.default_rng(SEED + 1)
    for n in (10, 40):
        cover = 0
        for _ in range(2000):
            s = LST_ALL[rng.integers(0, LST_ALL.size, n)]
            h = stats.t.ppf(0.975, n - 1) * s.std(ddof=1) / np.sqrt(n)
            cover += abs(s.mean() - mu) <= h
        print(f"  n={n} t 신뢰구간 2000번 중 참 평균을 포함한 비율 {cover / 2000:.1%}")

    print("[4] 관측소 48곳 기온")
    d = describe(TEMP)
    se = d["sd"] / np.sqrt(d["n"])
    tq = stats.t.ppf(0.975, d["n"] - 1)
    print(f"  평균 {d['mean']:.3f}, 중앙값 {d['median']:.3f}, 표준편차 {d['sd']:.3f}, 표준오차 {se:.4f}, t(0.975, 47) {tq:.3f}, "
          f"95% CI {d['mean'] - tq * se:.3f} ~ {d['mean'] + tq * se:.3f}, 최소 {d['min']:.2f}, 최대 {d['max']:.2f}")
    print(f"  처음 5곳: {stations[['관측소ID', '기온_8월평균']].head(5).values.tolist()}")

    print("[5] 부트스트랩 (B = 9999)")
    rng = np.random.default_rng(SEED + 2)
    idx = rng.integers(0, TEMP.size, (9999, TEMP.size))
    bm = TEMP[idx].mean(1)
    bmed = np.median(TEMP[idx], 1)
    print(f"  평균: 부트스트랩 표준오차 {bm.std(ddof=1):.4f}, 백분위 95% CI {np.percentile(bm, 2.5):.3f} ~ {np.percentile(bm, 97.5):.3f}")
    print(f"  중앙값: 관측 {np.median(TEMP):.3f}, 부트스트랩 표준오차 {bmed.std(ddof=1):.4f}, 백분위 95% CI {np.percentile(bmed, 2.5):.3f} ~ {np.percentile(bmed, 97.5):.3f}")
    small = TEMP[:5]
    rng = np.random.default_rng(SEED + 3)
    ex = [np.sort(rng.choice(small, 5)).round(2).tolist() for _ in range(3)]
    print(f"  손 예시 5개 {small.round(2).tolist()}, 평균 {small.mean():.3f}; 재표본 3개 {ex}, 평균 {[round(float(np.mean(e)), 3) for e in ex]}")
    return bm, bmed


# ---------------------------------------------------------------- 그림 1. 분포의 모양
def fig_shapes():
    W, H = 720, 250
    s = Svg(W, H, "행정동 150개의 고령비율, 출동률, 인구밀도, 로그 인구밀도의 히스토그램. 파란 실선은 평균, 주황 점선은 중앙값. "
                  "고령비율은 좌우가 비슷하고, 출동률과 인구밀도는 오른쪽 꼬리가 길며, 인구밀도에 로그를 취하면 꼬리가 줄어듦")
    panels = [
        ("고령비율 (%)", dong["고령비율"], (10, 40), 10),
        ("출동률 (1만 명당)", dong["출동률"], (0, 50), 10),
        ("인구밀도 (명/km²)", dong["인구밀도"], (0, 24000), 12),
        ("log(인구밀도)", np.log(dong["인구밀도"]), (4, 10.5), 13),
    ]
    pw, gap = 145, 34
    for i, (title, x, lim, nb) in enumerate(panels):
        x = np.asarray(x, float)
        edges = np.linspace(lim[0], lim[1], nb + 1)
        c = np.histogram(x, edges)[0]
        ax = Axes(s, 30 + i * (pw + gap), 44, pw, 150, lim, (0, max(c) * 1.1))
        s.text(ax.x0 + pw / 2, 24, title, size=12, weight="600")
        ax.hist(c, edges)
        ax.vline(x.mean(), cls="s-ac", width=1.8)
        ax.vline(np.median(x), cls="s-bd", width=1.6, dash="4 3")
        ticks = {0: [10, 20, 30, 40], 1: [0, 25, 50], 2: [0, 10000, 20000], 3: [4, 6, 8, 10]}[i]
        ax.xaxis(ticks=ticks, fmt=lambda t: f"{t / 10000:.0f}만" if t >= 10000 else f"{t:g}")
        s.text(ax.x0 + pw / 2, 228, f"왜도 {stats.skew(x):.2f}".replace("-", "−"), size=11, cls="f-mu")
    s.line(250, H - 8, 270, H - 8, cls="s-ac", width=1.8)
    s.text(274, H - 4, "평균", size=10, anchor="start", cls="f-mu")
    s.line(320, H - 8, 340, H - 8, cls="s-bd", width=1.6, dash="4 3")
    s.text(344, H - 4, "중앙값", size=10, anchor="start", cls="f-mu")
    s.save(os.path.join(OUT, "06-shapes.svg"))


# ---------------------------------------------------------------- 그림 2. 깔때기
def fig_funnel():
    W, H = 720, 340
    s = Svg(W, H, "행정동의 출동률(점)과 인구. 가로선은 도시 전체 출동률 11.73이고, 점선과 실선은 모든 동의 참 출동률이 11.73일 때 "
                  "우연만으로 나올 수 있는 95%와 99.8% 범위(포아송분포로 정확히 계산해 계단 모양임). 인구가 적을수록 범위가 넓어 깔때기 모양이 됨. "
                  "95% 범위 밖은 12개이고, 그 가운데 속까지 주황인 3개는 99.8% 범위도 벗어남")
    ax = Axes(s, 70, 30, 600, 240, (0, 19000), (0, 52))
    ax.yaxis(ticks=[0, 10, 20, 30, 40, 50], label="출동률 (1만 명당)", grid=True)
    ax.xaxis(ticks=[0, 5000, 10000, 15000], label="행정동 인구 (명)")
    pops = np.linspace(600, 19000, 2400)
    lam = pops * CITY_RATE / 1e4
    for q, cls, dash in ((0.025, "s-mu", "5 3"), (0.975, "s-mu", "5 3"), (0.001, "s-fg", None), (0.999, "s-fg", None)):
        # 판정 규칙(건수 > 위쪽 분위수, 건수 < 아래쪽 분위수)과 맞도록 분위수에서 0.5건 떨어진 곳에 경계를 그림
        k = stats.poisson.ppf(q, lam)
        y = (k + 0.5) / pops * 1e4 if q > 0.5 else np.clip((k - 0.5) / pops * 1e4, 0, None)
        keep = y <= 52
        ax.curve(pops[keep], y[keep], cls=cls, width=1.1 if dash else 1.3, dash=dash)
    ax.s.line(float(ax.X(0)), float(ax.Y(CITY_RATE)), float(ax.X(19000)), float(ax.Y(CITY_RATE)), cls="s-ac", width=1.4)
    lam_d = dong["인구"] * CITY_RATE / 1e4
    x_ = dong["PT_CNT"]
    out998 = (x_ > stats.poisson.ppf(0.999, lam_d)) | (x_ < stats.poisson.ppf(0.001, lam_d))
    out95 = (x_ > stats.poisson.ppf(0.975, lam_d)) | (x_ < stats.poisson.ppf(0.025, lam_d))
    for x, y, h, o in zip(dong["인구"], dong["출동률"], out998, out95):
        cls = "s-fg f-bd" if h else ("s-bd f-bg" if o else "s-mu f-sf")
        s.circle(float(ax.X(x)), float(ax.Y(y)), 3.2 if (h or o) else 2.6, cls=cls, width=1.2 if (o and not h) else 0.6)
    s.text(float(ax.X(18900)), float(ax.Y(CITY_RATE)) - 6, "도시 전체 11.73", size=10, anchor="end", cls="f-ac")
    y0 = H - 14
    s.line(250, y0, 270, y0, cls="s-mu", width=1.1, dash="5 3")
    s.text(274, y0 + 4, "95% 범위", size=10, anchor="start", cls="f-mu")
    s.line(335, y0, 355, y0, cls="s-fg", width=1.3)
    s.text(359, y0 + 4, "99.8% 범위", size=10, anchor="start", cls="f-mu")
    s.circle(430, y0, 3.2, cls="s-bd f-bg", width=1.2)
    s.text(438, y0 + 4, f"95% 밖 ({int(out95.sum() - out998.sum())}개)", size=10, anchor="start", cls="f-mu")
    s.circle(520, y0, 3.2, cls="s-fg f-bd", width=0.6)
    s.text(528, y0 + 4, f"99.8% 밖 ({int(out998.sum())}개)", size=10, anchor="start", cls="f-mu")
    s.save(os.path.join(OUT, "06-funnel.svg"))


# ---------------------------------------------------------------- 그림 3. 표본분포
def fig_sampling():
    W, H = 720, 260
    mu, sig = LST_ALL.mean(), LST_ALL.std()
    s = Svg(W, H, "지표온도 래스터의 육지 셀 전체(모집단)에서 무작위로 10개, 40개, 160개를 뽑아 평균을 내는 일을 5,000번 반복한 "
                  "표본평균의 분포. 표본이 4배가 될 때마다 퍼짐(표준오차)이 절반으로 줄어듦. 곡선은 σ/√n을 표준편차로 한 정규분포")
    rng = np.random.default_rng(SEED)
    lim = (28, 33)
    edges = np.linspace(*lim, 51)
    for i, n in enumerate((10, 40, 160)):
        means = np.array([LST_ALL[rng.integers(0, LST_ALL.size, n)].mean() for _ in range(5000)])
        c = np.histogram(means, edges)[0]
        ax = Axes(s, 30 + i * 235, 46, 200, 150, lim, (0, 1500))
        s.text(ax.x0 + 100, 26, f"n = {n}", size=13, weight="600")
        ax.hist(c, edges, width=0.3)
        xs = np.linspace(*lim, 200)
        ax.curve(xs, stats.norm.pdf(xs, mu, sig / np.sqrt(n)) * 5000 * (edges[1] - edges[0]), cls="s-bd", width=1.4)
        ax.vline(mu, cls="s-ac", width=1.2, dash="3 2")
        ax.xaxis(ticks=[28, 29, 30, 31, 32, 33])
        s.text(ax.x0 + 100, 236, f"표준오차 {sig / np.sqrt(n):.2f}℃", size=11, cls="f-mu")
    s.text(W / 2, H - 4, f"파란 점선: 모집단 평균 {mu:.2f}℃", size=10, cls="f-mu")
    s.save(os.path.join(OUT, "06-sampling.svg"))


# ---------------------------------------------------------------- 그림 4. 부트스트랩
def fig_bootstrap(bm):
    W, H = 720, 280
    s = Svg(W, H, "관측소 48곳 기온에서 복원 추출로 48개씩 다시 뽑아 평균을 낸 부트스트랩 분포(9,999번). 주황 구간은 부트스트랩 "
                  "백분위 95% 신뢰구간, 파란 구간은 t분포로 구한 95% 신뢰구간. 두 구간이 거의 같음")
    lim = (24.35, 25.2)
    edges = np.linspace(*lim, 43)
    c = np.histogram(bm, edges)[0]
    ax = Axes(s, 60, 30, 600, 170, lim, (0, max(c) * 1.1))
    ax.hist(c, edges, width=0.4)
    ax.xaxis(ticks=[24.4, 24.6, 24.8, 25.0, 25.2], label="부트스트랩 표본의 평균 기온 (℃)", fmt=lambda t: f"{t:.1f}")
    m = TEMP.mean()
    ax.vline(m, cls="s-fg", width=1.6)
    lo, hi = np.percentile(bm, [2.5, 97.5])
    se = TEMP.std(ddof=1) / np.sqrt(TEMP.size)
    tq = stats.t.ppf(0.975, TEMP.size - 1)
    y1, y2 = 244, 262
    s.line(float(ax.X(lo)), y1, float(ax.X(hi)), y1, cls="s-bd", width=3)
    s.text(float(ax.X(hi)) + 8, y1 + 4, f"부트스트랩 {lo:.2f} ~ {hi:.2f}", size=11, anchor="start", cls="f-bd")
    s.line(float(ax.X(m - tq * se)), y2, float(ax.X(m + tq * se)), y2, cls="s-ac", width=3)
    s.text(float(ax.X(m + tq * se)) + 8, y2 + 4, f"t분포 {m - tq * se:.2f} ~ {m + tq * se:.2f}", size=11, anchor="start", cls="f-ac")
    s.text(float(ax.X(m)), 24, f"관측 평균 {m:.2f}℃", size=11)
    s.save(os.path.join(OUT, "06-bootstrap.svg"))


if __name__ == "__main__":
    bm, _ = numbers()
    fig_shapes()
    fig_funnel()
    fig_sampling()
    fig_bootstrap(bm)
