"""한빛시 행정동 시계열(패널) 자료 만들기. 33강에서 추가.

hanbit_dong_panel.gpkg: 행정동 150개 × 2016~2025년 10개 연도 = 1,500행의 긴 형태 자료.
열: 동코드, 구, 동이름, 연도, 인구, 고령인구, 출동건수, 폭염일수, 면적_km2, geometry(행정동 경계, 연도마다 반복)

원칙 (make_hanbit.py와 같음)
- 모든 값은 알려진 규칙(참 모형)으로 만들었고, 규칙은 이 스크립트에 그대로 있음.
  책을 끝까지 읽기 전에는 '참 모형' 부분을 보지 않기를 권함 (부록 G에서 정리함)
- 2025년 값은 hanbit_dong.gpkg(인구, 고령인구)와 hanbit_events.gpkg(동별 출동 건수)와 정확히 같음
- 경계는 모든 연도에 2025년 행정동 경계를 씀 (과거 값을 현재 경계로 다시 집계해 둔 자료라고 봄)
- 구성 요소마다 난수 흐름을 따로 씀 (시드 = 기본 시드 + 이름). 기존 파일은 바꾸지 않음

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/data/make_hanbit_panel.py
"""
from __future__ import annotations

import os
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy import ndimage

OUT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, OUT)
import make_hanbit as mh  # noqa: E402

YEARS = list(range(2016, 2026))

# ---------------------------------------------------------------- 참 모형
# 해마다 도시 전체의 여름 더위(폭염일수, 일 최고기온 33℃ 이상인 날). 2025년이 기준
HEAT_DAYS = {2016: 22, 2017: 18, 2018: 35, 2019: 15, 2020: 9, 2021: 20, 2022: 16, 2023: 21, 2024: 31, 2025: 24}
HEAT_EFFECT = 0.03  # 폭염일수 하루당 출동 위험 3% 증가 (도시 전체)
# 인구 변화: 연 증가율(로그) = 기본 + 신도심 성장 + 원도심 감소 + 동부 개발(2020년부터)
GROWTH_BASE, GROWTH_SD = -0.001, 0.004
NEW_TOWN = (33500, 456500, 3000, 0.012)
OLD_TOWN = (40500, 447600, 2500, -0.015)
EAST_DEV = (51500, 456500, 2000, 0.06, 2020)
# 고령비율의 연 증가(비율 포인트): 기본 + 원도심 가속 + 동부 개발지 둔화
AGING_BASE, AGING_OLD, AGING_DEV, AGING_SD = 0.004, 0.003, -0.003, 0.001
# 전통시장 주변 군집: 2020년까지는 지금 강도의 30%, 2021년 시장 확장 뒤 지금 강도
MARKET = (39800, 448700, 350, 12000.0)
MARKET_BEFORE, MARKET_FROM = 0.3, 2021
INDUSTRY_CLUSTER = (52300, 450200, 500, 9000.0)


def weight(x, y, c):
    return np.exp(-((x - c[0]) ** 2 + (y - c[1]) ** 2) / (2 * c[2] ** 2))


def risk_components(dong):
    """make_hanbit.make_events와 같은 위험 표면을 동별로 합침: (기본, 시장 군집, 산업단지 군집)"""
    land, _ = mh.land_polygon()
    XX, YY = mh.cell_centers()
    transform = from_origin(mh.X0, mh.Y1, mh.CELL, mh.CELL)
    inland = rasterize([(land, 1)], out_shape=(mh.NY, mh.NX), transform=transform, fill=0, dtype="uint8").astype(bool)
    dens = np.where(inland, mh.density(XX, YY), 0.0)
    eld = mh.elderly_share(dens, XX, YY)
    with rasterio.open(os.path.join(OUT, "hanbit_lst.tif")) as src:
        lst = src.read(1).astype("float64")
        lst[lst == src.nodata] = np.nan
    base = dens * (0.3 + 6.0 * eld) * np.exp(0.15 * (np.nan_to_num(lst, nan=30.0) - 32.0))
    market = MARKET[3] * weight(XX, YY, MARKET)
    industry = INDUSTRY_CLUSTER[3] * weight(XX, YY, INDUSTRY_CLUSTER)
    ids = rasterize(((g, k + 1) for k, g in enumerate(dong.geometry)), out_shape=(mh.NY, mh.NX),
                    transform=transform, fill=0, dtype="int32")
    idx = np.arange(1, len(dong) + 1)
    comp = [np.asarray(ndimage.sum(np.where(inland, a, 0.0), ids, index=idx)) for a in (base, market, industry)]
    total = sum(c.sum() for c in comp)
    return [c / total * 1400.0 for c in comp]  # 2025년 기대 건수 (make_events의 평균 1,400건)


def main():
    dong = gpd.read_file(os.path.join(OUT, "hanbit_dong.gpkg"))
    events = gpd.read_file(os.path.join(OUT, "hanbit_events.gpkg"))
    n = len(dong)
    cnt25 = gpd.sjoin(events, dong, predicate="within").groupby("index_right").size().reindex(dong.index, fill_value=0).to_numpy()
    cx, cy = dong.geometry.centroid.x.to_numpy(), dong.geometry.centroid.y.to_numpy()
    w_new, w_old, w_dev = weight(cx, cy, NEW_TOWN), weight(cx, cy, OLD_TOWN), weight(cx, cy, EAST_DEV)

    # 인구: 2025년에서 거꾸로 거슬러 올라감
    rg = mh.rng("panel_growth")
    pop = {2025: dong["인구"].to_numpy().astype(float)}
    for t in range(2025, 2016, -1):
        r = (GROWTH_BASE + rg.normal(0, GROWTH_SD, n) + NEW_TOWN[3] * w_new + OLD_TOWN[3] * w_old
             + (EAST_DEV[3] * w_dev if t >= EAST_DEV[4] else 0.0))
        pop[t - 1] = pop[t] * np.exp(-r)
    # 고령비율
    ra = mh.rng("panel_aging")
    e25 = dong["고령인구"].to_numpy() / dong["인구"].to_numpy()
    a = np.clip(AGING_BASE + AGING_OLD * w_old + AGING_DEV * w_dev + ra.normal(0, AGING_SD, n), 0.0005, None)
    share = {t: np.clip(e25 - a * (2025 - t), 0.03, None) for t in YEARS}

    base, market, industry = risk_components(dong)
    rc = mh.rng("panel_events")
    rows = []
    for t in YEARS:
        p = np.round(pop[t]).astype(int) if t < 2025 else dong["인구"].to_numpy()
        old = np.round(p * share[t]).astype(int) if t < 2025 else dong["고령인구"].to_numpy()
        e_t = old / p
        mu = (base * (p / dong["인구"].to_numpy()) * (0.3 + 6 * e_t) / (0.3 + 6 * e25)
              + market * (1.0 if t >= MARKET_FROM else MARKET_BEFORE) + industry)
        mu = mu * np.exp(HEAT_EFFECT * (HEAT_DAYS[t] - HEAT_DAYS[2025]))
        c = rc.poisson(mu) if t < 2025 else cnt25
        for i in range(n):
            rows.append((dong.at[i, "동코드"], dong.at[i, "구"], dong.at[i, "동이름"], t, int(p[i]), int(old[i]), int(c[i]),
                         HEAT_DAYS[t], float(dong.at[i, "면적_km2"]), dong.geometry[i]))
    panel = gpd.GeoDataFrame(rows, columns=["동코드", "구", "동이름", "연도", "인구", "고령인구", "출동건수", "폭염일수", "면적_km2", "geometry"],
                             geometry="geometry", crs=dong.crs)
    path = os.path.join(OUT, "hanbit_dong_panel.gpkg")
    if os.path.exists(path):
        os.remove(path)
    panel.to_file(path, layer="hanbit_dong_panel", driver="GPKG")
    s = panel.groupby("연도").agg(인구=("인구", "sum"), 고령인구=("고령인구", "sum"), 출동건수=("출동건수", "sum"), 폭염일수=("폭염일수", "first"))
    s["고령비율"] = (s["고령인구"] / s["인구"] * 100).round(2)
    print(f"{len(panel)}행 ({n}개 동 × {len(YEARS)}개 연도) → {path}")
    print(s.to_string())


if __name__ == "__main__":
    main()
