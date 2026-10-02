"""부록 G 수치: 한빛시의 참 모형(book/data/make_hanbit.py, make_hanbit_panel.py)과 책의 추정 비교.

- 지표온도의 성분별 분산(큰 경향, 500 m·120 m 잡음, 픽셀 잡음)
- 출동의 참 기대 건수(동별)와 원비율·EB·BYM2(37강) 추정의 오차
- 국지 군집(전통시장, 산업단지)이 놓인 동, 동 단위의 참 온도 관계
- G-truth.svg: 동별 참 출동률 대 원비율·EB·BYM2 추정

실행 (GeoStat 엔진 환경에서, 1분 안팎):
    cd engine && uv run python ../book/fig-src/G.py
"""
import os
import sys
import warnings

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
sys.path.insert(0, HERE)
sys.path.insert(0, DATA)
import make_hanbit as mh  # noqa: E402
import make_hanbit_panel as mp  # noqa: E402
from plotkit import Axes  # noqa: E402
from regkit import load_dong  # noqa: E402
from svglib import Svg  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(HERE, "..", "fig")


def surfaces():
    land, coast = mh.land_polygon()
    XX, YY = mh.cell_centers()
    tr = from_origin(mh.X0, mh.Y1, mh.CELL, mh.CELL)
    inland = rasterize([(land, 1)], out_shape=(mh.NY, mh.NX), transform=tr, fill=0, dtype="uint8").astype(bool)
    cm = rasterize([(coast.buffer(mh.CELL), 1)], out_shape=(mh.NY, mh.NX), transform=tr, fill=0, dtype="uint8")
    dist_coast = ndimage.distance_transform_edt(1 - cm) * mh.CELL
    dens = np.where(inland, mh.density(XX, YY), 0.0)
    return land, XX, YY, inland, dist_coast, dens


def lst_parts(XX, YY, inland, dist_coast, dens):
    urban = dens / (dens + 4000.0)
    fx, fy, fs = mh.FOREST
    forest = np.exp(-((XX - fx) ** 2 + (YY - fy) ** 2) / (2 * (fs * 0.8) ** 2))
    ix, iy, is_ = mh.INDUSTRY
    industry = np.exp(-((XX - ix) ** 2 + (YY - iy) ** 2) / (2 * is_ ** 2))
    coast_cool = np.exp(-dist_coast / 900.0)
    big = 29.0 + 8.0 * urban - 3.5 * forest + 5.0 * industry - 2.5 * coast_cool
    n500 = 0.9 * mh.smooth_noise("lst_field", 500)
    n120 = 1.1 * urban * mh.smooth_noise("lst_block", 120)
    pix = 0.5 * mh.rng("lst_pixel").standard_normal(dens.shape)
    with rasterio.open(os.path.join(DATA, "hanbit_lst.tif")) as r:
        lst = r.read(1).astype(float)
    m = inland & (lst > -9000)
    recon = (big + n500 + n120 + pix)[m]
    print(f"[지표온도] 재현 최대 오차 {np.abs(recon - lst[m]).max():.2e} (float32 저장)")
    tot = lst[m].var()
    print(f"  육지 셀 분산 {tot:.3f}. 성분별 분산: 큰 경향 {big[m].var():.3f}, 500 m 잡음 {n500[m].var():.3f}, 120 m 잡음 {n120[m].var():.3f}, 픽셀 잡음 {pix[m].var():.3f}")
    print(f"  큰 경향의 항: 도시화 8×{np.round([urban[m].min(), urban[m].max()], 3).tolist()}, 산림 −3.5, 산업단지 +5, 해안 −2.5")
    return lst, m


def risk(dong):
    base, market, industry = mp.risk_components(dong)
    mu = base + market + industry
    return mu, base, market, industry


def compare(d, mu, market, industry):
    y = d["PT_CNT"].to_numpy(float)
    pop = d["인구"].to_numpy(float)
    true = mu / pop * 1e4
    raw = y / pop * 1e4
    from esda.smoothing import Empirical_Bayes
    eb = Empirical_Bayes(y, pop).r.ravel() * 1e4
    z = np.load(os.path.join(HERE, "37-fit.npz"))
    rr = z["BYM2|rr_mean"].astype(float)
    ev = gpd.read_file(os.path.join(DATA, "hanbit_events.gpkg"))
    j = gpd.sjoin(ev, d[["geometry"]], predicate="within")
    old = (j["연령대"] == "65+").groupby(j["index_right"]).sum().reindex(d.index, fill_value=0).to_numpy(float)
    p65 = d["고령인구"].to_numpy(float)
    E = p65 * old.sum() / p65.sum() + (pop - p65) * (y - old).sum() / (pop - p65).sum()
    bym = rr * E / pop * 1e4
    print(f"[출동] 참 기대 건수 합 {mu.sum():.1f}, 관측 {y.sum():.0f}. 참 출동률 범위 {true.min():.2f}~{true.max():.2f} (1만 명당), 동 사이 표준편차 {true.std():.3f}")
    q = np.digitize(pop, np.quantile(pop, [0.25, 0.5, 0.75]))
    res = {}
    for nm, est in (("원비율", raw), ("EB", eb), ("BYM2", bym)):
        e = est - true
        res[nm] = est
        print(f"  {nm}: RMSE {np.sqrt(np.mean(e ** 2)):.3f}, 인구 1분위 RMSE {np.sqrt(np.mean(e[q == 0] ** 2)):.3f}, 4분위 {np.sqrt(np.mean(e[q == 3] ** 2)):.3f}, 참값과 상관 {np.corrcoef(est, true)[0, 1]:.3f}")
    nmv = d["동이름"].to_numpy()
    keep = ~np.isin(nmv, ["다솜23동", "다솜20동", "다솜19동"])
    for nm, est in res.items():
        e = (est - true)[keep]
        print(f"  산업단지 군집 세 동(다솜19·20·23동)을 뺀 {keep.sum()}개 동: {nm} RMSE {np.sqrt(np.mean(e ** 2)):.3f}, 상관 {np.corrcoef(est[keep], true[keep])[0, 1]:.3f}")
    o = np.argsort(-true)[:8]
    print("  참 출동률 상위 8개 동:", [(nmv[i], round(float(true[i]), 2), int(pop[i])) for i in o])
    mk = market / mu
    ik = industry / mu
    print("  전통시장 군집 몫이 큰 동:", [(nmv[i], round(float(mk[i]), 3)) for i in np.argsort(-mk)[:4]])
    print("  산업단지 군집 몫이 큰 동:", [(nmv[i], round(float(ik[i]), 3)) for i in np.argsort(-ik)[:4]])
    print(f"  군집 기대 건수: 전통시장 {market.sum():.1f}, 산업단지 {industry.sum():.1f} (전체 {mu.sum():.0f})")
    for nm in ("다솜23동", "마루16동", "누리12동"):
        i = int(np.where(nmv == nm)[0][0])
        print(f"  {nm}: 참 {true[i]:.2f}, 원비율 {raw[i]:.2f}, EB {eb[i]:.2f}, BYM2 {bym[i]:.2f}")
    # 동 단위의 참 온도 관계: log(참 위험 / 연령 기대) ~ 온도편차
    t = d["온도편차"].to_numpy()
    lr = np.log(mu / E * (y.sum() / mu.sum()))
    X = np.c_[np.ones(len(t)), t]
    b = np.linalg.lstsq(X, lr, rcond=None)[0]
    print(f"  동 단위 참 관계: log(참 기대 / 연령 표준화 기대) = {b[0]:.3f} + {b[1]:.4f} × 온도편차 → 1℃당 {np.exp(b[1]):.3f}배 (37강 BYM2 추정 1.124, 픽셀 수준의 참값 exp(0.15) = {np.exp(0.15):.3f})")
    return true, res, pop, keep


def age():
    ev = gpd.read_file(os.path.join(DATA, "hanbit_events.gpkg"))
    d = load_dong()
    n65 = (ev["연령대"] == "65+").sum()
    r65 = n65 / d["고령인구"].sum()
    ru = (len(ev) - n65) / (d["인구"].sum() - d["고령인구"].sum())
    print(f"[연령] 65세 이상 출동 {n65}건. 1만 명당 65세 이상 {r65 * 1e4:.2f}, 미만 {ru * 1e4:.2f}, 비 {r65 / ru:.3f} (개인 수준 참값 3)")
    for e in (0.15, 0.25, 0.35):
        print(f"  고령비율 {e:.0%}인 곳의 동네 맥락 배수 (0.3 + 6e)/(1 + 2e) = {(0.3 + 6 * e) / (1 + 2 * e):.3f}")


def stations():
    st = gpd.read_file(os.path.join(DATA, "hanbit_stations.gpkg"))
    print(f"[관측소] {len(st)}곳, 기온 {st['기온_8월평균'].min():.2f}~{st['기온_8월평균'].max():.2f}. 참 모형: 25.5 + 0.45 × (1.2 km 평활 지표온도 − 32) + N(0, 0.15²). 22강 회귀(1 km 평활) 기울기 0.4271")


def panel():
    print(f"[패널] 폭염일수 {mp.HEAT_DAYS}")
    print(f"  폭염 효과 하루당 {mp.HEAT_EFFECT:.0%} (35강 포아송 고정효과 추정 0.0270)")
    print(f"  전통시장 군집: {mp.MARKET_FROM - 1}년까지 지금의 {mp.MARKET_BEFORE:.0%}, {mp.MARKET_FROM}년부터 지금 강도")


def fig(true, res, pop, keep):
    W_, H = 720, 280
    rm = {k: np.sqrt(np.mean((v - true) ** 2)) for k, v in res.items()}
    rk = {k: np.sqrt(np.mean((v - true)[keep] ** 2)) for k, v in res.items()}
    svg = Svg(W_, H, f"한빛시의 참 출동률(가로, 1만 명당, 참 모형에서 계산한 동별 기대 건수 ÷ 인구)과 세 가지 추정(세로). 점의 크기는 인구. "
                     f"전체 RMSE는 원비율 {rm['원비율']:.2f}, EB {rm['EB']:.2f}, BYM2 {rm['BYM2']:.2f}로 원비율이 가장 작음. 산업단지 군집에 든 인구 적은 동(오른쪽 끝의 다솜23동, 참 {true.max():.1f})을 "
                     f"수축 추정이 평균 쪽으로 끌어내렸기 때문임. 그 군집의 세 동을 빼면 원비율 {rk['원비율']:.2f}, EB {rk['EB']:.2f}, BYM2 {rk['BYM2']:.2f}로 순서가 뒤집힘. 점선은 추정 = 참값")
    lim = (0, 85)
    for k, nm in enumerate(("원비율", "EB", "BYM2")):
        ax = Axes(svg, 50 + k * 230, 30, 180, 180, lim, lim)
        svg.line(float(ax.X(0)), float(ax.Y(0)), float(ax.X(85)), float(ax.Y(85)), cls="s-mu", width=1, dash="3 3")
        for t, e, p in zip(true, res[nm], pop):
            svg.circle(float(ax.X(t)), float(ax.Y(min(e, 85))), 1.2 + 2.5 * np.sqrt(p / pop.max()), cls="f-ac", width=0)
        ax.xaxis(ticks=[0, 20, 40, 60, 80], label="참 출동률")
        ax.yaxis(ticks=[0, 20, 40, 60, 80])
        svg.text(float(ax.X(25)), 22, f"{nm} (RMSE {rm[nm]:.2f})", size=12, weight="600")
    svg.save(os.path.join(OUT, "G-truth.svg"))


if __name__ == "__main__":
    land, XX, YY, inland, dist_coast, dens = surfaces()
    lst_parts(XX, YY, inland, dist_coast, dens)
    d = load_dong()
    mu, base, market, industry = risk(d)
    true, res, pop, keep = compare(d, mu, market, industry)
    age()
    stations()
    panel()
    fig(true, res, pop, keep)
