"""가상 도시 '한빛시' 예제 자료 만들기.

책 전체에서 이어 쓰는 예제 자료임. 모든 값을 알려진 규칙(참 모형)으로 만들었으므로,
분석 방법이 참 구조를 찾아내는지 확인할 수 있음. 규칙은 이 스크립트에 그대로 있음.
책을 끝까지 읽기 전에는 '참 모형' 부분을 보지 않기를 권함 (부록 G에서 정리함).

원칙
- 좌표계 EPSG:5186 (중부원점). 실제 지형과 겹치지 않도록 서해 바다 위(동경 125.0~125.4°, 북위 36.5~36.8°)에 둠.
  GeoStat에서 배경지도를 켜면 도시가 바다 위에 뜨는데, 가상 자료이기 때문임
- 구성 요소마다 난수 흐름을 따로 씀 (시드 = 기본 시드 + 이름). 나중에 변수를 더해도 기존 값이 바뀌지 않음
- 이미 책에 쓴 값이 바뀌지 않도록, 기존 구성 요소의 규칙은 고치지 않고 새 구성 요소만 더함

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/data/make_hanbit.py

결과 (book/data/)
    hanbit_dong.gpkg      행정동 폴리곤 (면 자료)
    hanbit_events.gpkg    폭염 관련 119 구급 출동 위치 (점 패턴)
    hanbit_stations.gpkg  기상 관측소 (연속 표면의 표본)
    hanbit_roads.gpkg     주요 도로 (선)
    hanbit_lst.tif        여름 한낮 지표온도 50 m 래스터
    hanbit_pop100.tif     100 m 격자 인구 (1밴드 인구, 2밴드 고령인구). 3강에서 추가
"""
from __future__ import annotations

import os
import zlib

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy import ndimage
from scipy.spatial import Voronoi, cKDTree
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

OUT = os.path.dirname(os.path.abspath(__file__))
CRS = "EPSG:5186"
BASE_SEED = 20260930

# 도시 범위 (m). 32 km × 24 km
X0, X1, Y0, Y1 = 25000.0, 57000.0, 440000.0, 464000.0
CELL = 50.0  # 래스터 해상도
TOTAL_POP = 1_200_000
NX, NY = int((X1 - X0) / CELL), int((Y1 - Y0) / CELL)


def rng(name: str) -> np.random.Generator:
    """구성 요소별 독립 난수 흐름"""
    return np.random.default_rng([BASE_SEED, zlib.crc32(name.encode("utf-8"))])


def cell_centers():
    xs = X0 + CELL * (np.arange(NX) + 0.5)
    ys = Y1 - CELL * (np.arange(NY) + 0.5)  # 위쪽 행부터
    return np.meshgrid(xs, ys)


def smooth_noise(name: str, sigma_m: float) -> np.ndarray:
    """표준편차 1로 맞춘 매끄러운 잡음장 (래스터 격자)"""
    pad = int(3 * sigma_m / CELL) + 2
    z = rng(name).standard_normal((NY + 2 * pad, NX + 2 * pad))
    z = ndimage.gaussian_filter(z, sigma_m / CELL)[pad:pad + NY, pad:pad + NX]
    return (z - z.mean()) / z.std()


# ---------------------------------------------------------------- 1. 땅 (시 경계)
# 북·서쪽은 이웃 시와 맞닿은 행정 경계, 남·동쪽은 해안선
def land_polygon() -> tuple[Polygon, LineString]:
    r = rng("land")

    def wiggle(n, amp, smooth):
        w = ndimage.gaussian_filter1d(r.standard_normal(n), smooth, mode="nearest")
        return amp * w / (np.abs(w).max() + 1e-9)

    # 북쪽 행정 경계: 서 → 동
    xn = np.linspace(27000, 50500, 60)
    north = np.c_[xn, 462500 + wiggle(60, 700, 3)]
    # 동쪽 해안: 북 → 남 (만 하나)
    t = np.linspace(0, 1, 90)
    xe = 50500 + 4500 * t + wiggle(90, 900, 2)
    ye = 462500 - 15500 * t
    east = np.c_[xe, ye]
    # 남쪽 해안: 동 → 서. 원도심 앞의 항만(만)을 파 넣음
    t = np.linspace(0, 1, 140)
    xs = 55000 - 28500 * t
    ys = 447000 - 3500 * t + wiggle(140, 600, 2)
    bay = 2600 * np.exp(-((xs - 40500) / 1600) ** 2)
    south = np.c_[xs, ys + bay]
    # 서쪽 행정 경계: 남 → 북
    yw = np.linspace(443500, 462500, 50)
    west = np.c_[26500 + wiggle(50, 600, 3), yw]
    ring = np.vstack([north, east[1:], south[1:], west[1:]])
    poly = Polygon(ring).buffer(0)
    coast = LineString(np.vstack([east, south[1:]]))
    return poly, coast


# ---------------------------------------------------------------- 2. 인구 밀도 표면 (명/㎢)
CENTERS = {
    "원도심": (40500, 447600, 1900, 17000),  # 항만 앞
    "신도심": (33500, 456500, 2600, 12000),
    "동부": (50500, 455000, 2000, 4500),
}
FOREST = (43500, 458500, 3200)  # 도시 가운데 북쪽의 산림 (사람이 적고 시원함)
INDUSTRY = (53000, 449500, 1500)  # 동쪽 해안 산업단지 (거주 인구 적고 뜨거움)


def density(x, y, land_mask=None):
    d = 250.0 + np.zeros_like(x)
    for cx, cy, s, peak in CENTERS.values():
        d += peak * np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * s**2))
    fx, fy, fs = FOREST
    d *= 1 - 0.85 * np.exp(-((x - fx) ** 2 + (y - fy) ** 2) / (2 * fs**2))
    ix, iy, is_ = INDUSTRY
    d *= 1 - 0.8 * np.exp(-((x - ix) ** 2 + (y - iy) ** 2) / (2 * is_**2))
    return d


def elderly_share(dens, XX, YY):
    """65세 이상 인구 비율 표면. 외곽(인구가 적은 곳)과 원도심에서 높음"""
    urban = dens / (dens + 4000.0)
    ox, oy = CENTERS["원도심"][:2]
    old_town = np.exp(-((XX - ox) ** 2 + (YY - oy) ** 2) / (2 * 1500.0**2))
    e = 0.10 + 0.20 * (1 - urban) + 0.08 * old_town + 0.03 * smooth_noise("elderly", 1500)
    return np.clip(e, 0.05, 0.45)


# ---------------------------------------------------------------- 3. 행정동
GU_NAMES = ["가람구", "누리구", "다솜구", "라온구", "마루구"]


def make_dong(land: Polygon, dens: np.ndarray, XX, YY, inland: np.ndarray, eld: np.ndarray):
    r = rng("dong")
    # 밀도가 높을수록 촘촘하게 씨앗점을 뿌림 (도심 동은 작고 외곽 동은 큼)
    cand = []
    minx, miny, maxx, maxy = land.bounds
    while len(cand) < 30000:
        p = r.uniform([minx, miny], [maxx, maxy], (5000, 2))
        cand += [q for q in p if land.contains(Point(q))]
    cand = np.array(cand[:30000])
    rad = 1700.0 * (density(cand[:, 0], cand[:, 1]) / 1000.0) ** -0.36
    rad = np.clip(rad, 450, 2800)
    seeds = []
    tree_pts = []
    for i in r.permutation(len(cand)):
        p = cand[i]
        if tree_pts:
            dd = np.hypot(*(np.array(tree_pts) - p).T)
            if np.any(dd < np.maximum(rad[i], np.array([s[1] for s in seeds])) * 0.95):
                continue
        seeds.append((p, rad[i]))
        tree_pts.append(p)
    pts = np.array(tree_pts)
    # 로이드 이완 두 번: 모양을 고르게 하되 크기 차이는 유지
    far = np.array([[X0 - 1e5, Y0 - 1e5], [X0 - 1e5, Y1 + 1e5], [X1 + 1e5, Y0 - 1e5], [X1 + 1e5, Y1 + 1e5]])
    for _ in range(3):
        polys = voronoi_polys(pts, far, land)
        pts = np.array([[pg.centroid.x, pg.centroid.y] for pg in polys])
    polys = voronoi_polys(pts, far, land)
    polys = [pg if isinstance(pg, (Polygon, MultiPolygon)) else pg.buffer(0) for pg in polys]
    gdf = gpd.GeoDataFrame(geometry=polys, crs=CRS)
    gdf = gdf[gdf.area > 1000].reset_index(drop=True)

    # 구: 동 중심점을 다섯 무리로 나눔 (서→동, 북→남 순으로 이름을 붙임)
    from scipy.cluster.vq import kmeans2

    cen = np.c_[gdf.centroid.x, gdf.centroid.y]
    _, lab = kmeans2((cen - cen.mean(0)) / 1000.0, 5, seed=int(r.integers(1e9)), minit="++")
    order = sorted(range(5), key=lambda k: (-cen[lab == k, 1].mean() // 6000, cen[lab == k, 0].mean()))
    gu = np.array([GU_NAMES[order.index(k)] for k in lab])

    # 동 번호: 구마다 북서쪽부터
    gdf["구"] = gu
    gdf["_key"] = -cen[:, 1] // 2500 * 1e6 + cen[:, 0]
    gdf = gdf.sort_values(["구", "_key"]).reset_index(drop=True)
    gdf["동이름"] = gdf["구"].str[:2] + (gdf.groupby("구").cumcount() + 1).astype(str) + "동"
    gdf["동코드"] = [f"HB{k + 1:03d}" for k in range(len(gdf))]
    gdf["면적_km2"] = (gdf.area / 1e6).round(3)

    # 인구: 밀도 표면을 동마다 적분하고, 동마다 ±15% 정도의 차이를 둠
    ids = rasterize(((g, k + 1) for k, g in enumerate(gdf.geometry)), out_shape=(NY, NX),
                    transform=from_origin(X0, Y1, CELL, CELL), fill=0, dtype="int32")
    pop_cell = dens * (CELL * CELL / 1e6)
    raw = ndimage.sum(pop_cell, ids, index=np.arange(1, len(gdf) + 1))
    noise = np.exp(rng("dong_pop").normal(0, 0.15, len(gdf)))
    pop = raw * noise
    pop = pop / pop.sum() * TOTAL_POP
    # 합계가 정확히 TOTAL_POP이 되도록 소수점 아래가 큰 순서로 1명씩 올림
    base = np.floor(pop).astype(int)
    base[np.argsort(-(pop - base))[: TOTAL_POP - base.sum()]] += 1
    gdf["인구"] = base
    # 65세 이상 인구: 동 안의 고령 비율 표면을 인구로 가중 평균하고 동마다 조금씩 흔듦
    share = ndimage.sum(pop_cell * eld, ids, index=np.arange(1, len(gdf) + 1)) / raw
    share = share * np.exp(rng("dong_elderly").normal(0, 0.06, len(gdf)))
    gdf["고령인구"] = np.round(gdf["인구"] * share).astype(int)
    gdf = gdf.drop(columns="_key")
    return gdf[["동코드", "구", "동이름", "인구", "고령인구", "면적_km2", "geometry"]], ids


def voronoi_polys(pts, far, land):
    vor = Voronoi(np.vstack([pts, far]))
    out = []
    for i in range(len(pts)):
        reg = vor.regions[vor.point_region[i]]
        pg = Polygon(vor.vertices[reg]).intersection(land)
        if pg.geom_type == "GeometryCollection":
            pg = unary_union([g for g in pg.geoms if g.area > 0])
        if pg.geom_type == "MultiPolygon":  # 해안선 때문에 쪼개지면 가장 큰 조각만
            pg = max(pg.geoms, key=lambda g: g.area)
        out.append(pg)
    return out


# ---------------------------------------------------------------- 4. 지표온도 래스터
def make_lst(dens, dist_coast, inland, XX, YY):
    urban = dens / (dens + 4000.0)
    fx, fy, fs = FOREST
    forest = np.exp(-((XX - fx) ** 2 + (YY - fy) ** 2) / (2 * (fs * 0.8) ** 2))
    ix, iy, is_ = INDUSTRY
    industry = np.exp(-((XX - ix) ** 2 + (YY - iy) ** 2) / (2 * is_**2))
    coast_cool = np.exp(-dist_coast / 900.0)
    # 큰 규모(도시·산림·해안) + 동네 규모(500 m) + 블록 규모(150 m: 지붕·공원·주차장) + 셀 잡음
    lst = (29.0 + 8.0 * urban - 3.5 * forest + 5.0 * industry - 2.5 * coast_cool
           + 0.9 * smooth_noise("lst_field", 500) + 1.1 * urban * smooth_noise("lst_block", 120)
           + 0.5 * rng("lst_pixel").standard_normal(dens.shape))
    lst = np.where(inland, lst, np.nan).astype("float32")
    return lst


# ---------------------------------------------------------------- 5. 폭염 관련 119 구급 출동 (점 패턴)
def make_events(dens, lst, inland, eld, area_union):
    import shapely

    r = rng("events")
    # 위험 = 인구 × 고령 비율 효과 × 더위 효과
    # 고령 비율 효과 (0.3 + 6e)는 개인 효과와 맥락 효과를 합친 것임: 65세 이상 개인 위험은 65세 미만의 3배이므로
    # 개인 효과는 (1 + 2e)이고, 나머지 (0.3 + 6e) / (1 + 2e)는 고령 동네의 맥락 효과(주거·냉방 여건 등)임 (부록 G)
    lam = dens * (0.3 + 6.0 * eld) * np.exp(0.15 * (np.nan_to_num(lst, nan=30.0) - 32.0))
    # 국지 군집 두 곳 (야외 작업이 많은 산업단지 주변, 전통시장 주변)
    XX, YY = cell_centers()
    for cx, cy, s, w in [(52300, 450200, 500, 9000.0), (39800, 448700, 350, 12000.0)]:
        lam = lam + w * np.exp(-((XX - cx) ** 2 + (YY - cy) ** 2) / (2 * s**2))
    lam = np.where(inland, lam, 0.0)
    p = (lam / lam.sum()).ravel()
    n = r.poisson(1400)
    xs, ys = [], []
    while len(xs) < n:  # 셀 안에서 흩뿌린 점이 해안선·시 경계 밖으로 나가면 다시 뽑음
        m = n - len(xs)
        idx = r.choice(p.size, size=m, p=p)
        iy, ix = np.unravel_index(idx, lam.shape)
        x = X0 + CELL * (ix + r.uniform(0, 1, m))
        y = Y1 - CELL * (iy + r.uniform(0, 1, m))
        ok = shapely.contains_xy(area_union, x, y)
        xs += list(x[ok])
        ys += list(y[ok])
    x, y = np.array(xs), np.array(ys)
    month = r.choice([6, 7, 8], size=n, p=[0.2, 0.45, 0.35])
    day = np.array([r.integers(1, 31 if m == 6 else 32) for m in month])
    date = pd.to_datetime([f"2025-{m:02d}-{d:02d}" for m, d in zip(month, day)])
    # 연령대: 출동 지점의 고령 비율 e에서 65세 이상일 확률 = 3e / (1 + 2e)
    # (65세 이상 한 사람의 위험이 65세 미만의 3배라는 개인 수준의 참값). 65세 미만은 고정 비율로 나눔.
    # 위치·날짜를 바꾸지 않도록 연령대는 따로 된 난수 흐름으로 뽑음
    iy_e = np.clip(((Y1 - y) / CELL).astype(int), 0, NY - 1)
    ix_e = np.clip(((x - X0) / CELL).astype(int), 0, NX - 1)
    e_at = eld[iy_e, ix_e]
    p_old = 3 * e_at / (1 + 2 * e_at)
    ra = rng("events_age")
    u = ra.random(n)
    young = ra.choice(["0-19", "20-39", "40-64"], size=n, p=[0.12, 0.32, 0.56])
    age = np.where(u < p_old, "65+", young)
    order = np.argsort(date.values, kind="stable")
    gdf = gpd.GeoDataFrame(
        {"출동ID": [f"E{k + 1:04d}" for k in range(n)], "출동일": date[order].strftime("%Y-%m-%d"),
         "월": month[order], "연령대": age[order]},
        geometry=[Point(a, b) for a, b in zip(x[order], y[order])], crs=CRS)
    return gdf


# ---------------------------------------------------------------- 6. 기상 관측소 (연속 표면의 표본)
def make_stations(land, lst, inland):
    r = rng("stations")
    pts = []
    minx, miny, maxx, maxy = land.bounds
    inner = land.buffer(-400)
    while len(pts) < 48:
        q = r.uniform([minx, miny], [maxx, maxy])
        if not inner.contains(Point(q)):
            continue
        if pts and np.min(np.hypot(*(np.array(pts) - q).T)) < 2300:
            continue
        pts.append(q)
    pts = np.array(pts)
    # 기온은 지표온도를 넓게 평활한 값을 따르되, 그 폭은 지표온도보다 훨씬 작음
    smooth = ndimage.gaussian_filter(np.nan_to_num(lst, nan=float(np.nanmean(lst))), 1200 / CELL)
    iy = ((Y1 - pts[:, 1]) / CELL).astype(int)
    ix = ((pts[:, 0] - X0) / CELL).astype(int)
    air = 25.5 + 0.45 * (smooth[iy, ix] - 32.0) + rng("stations_err").normal(0, 0.15, len(pts))
    gdf = gpd.GeoDataFrame(
        {"관측소ID": [f"S{k + 1:02d}" for k in range(len(pts))], "기온_8월평균": np.round(air, 2)},
        geometry=[Point(*p) for p in pts], crs=CRS)
    return gdf.sort_values("관측소ID").reset_index(drop=True)


# ---------------------------------------------------------------- 7. 주요 도로 (선)
def make_roads(land):
    r = rng("roads")
    c = {k: v[:2] for k, v in CENTERS.items()}
    routes = [
        ("한빛대로", "간선", [c["원도심"], (37500, 452000), c["신도심"], (29000, 461500)]),
        ("해안로", "간선", [(28000, 444800), (34000, 445800), c["원도심"], (47000, 447800), (53500, 449000), (55200, 452000)]),
        ("동서로", "간선", [c["신도심"], (40000, 455500), c["동부"], (54000, 457000)]),
        ("산성로", "보조", [c["원도심"], (43000, 452000), (44500, 455000), c["동부"]]),
    ]
    rows = []
    for name, grade, pts in routes:
        pts = np.array(pts, dtype=float)
        # 꺾인 점 사이를 촘촘히 채우고 조금 구부림
        dense = np.vstack([np.linspace(pts[i], pts[i + 1], 25, endpoint=False) for i in range(len(pts) - 1)] + [pts[-1:]])
        bend = ndimage.gaussian_filter1d(r.standard_normal((len(dense), 2)), 4, axis=0) * 250
        bend[0] = bend[-1] = 0
        line = LineString(dense + bend).intersection(land)
        rows.append({"도로명": name, "등급": grade, "geometry": line})
    return gpd.GeoDataFrame(rows, crs=CRS)


# ---------------------------------------------------------------- 8. 100 m 격자 인구 (3강에서 추가)
def make_pop_grid(dong, ids, dens, eld, inland):
    """행정동 인구·고령인구를 50 m 셀에 나눠 담고 100 m 격자로 합침.
    동 안에서는 인구 밀도 표면(고령인구는 밀도 × 고령 비율)에 비례해 정수로 나눔(큰 나머지 방식).
    그래서 행정동 경계 안의 셀을 모두 더하면 동 인구와 정확히 같음. 난수는 쓰지 않음"""
    pop50 = np.zeros(ids.shape, dtype=np.int64)
    old50 = np.zeros(ids.shape, dtype=np.int64)

    def allocate(total, w):
        if w.sum() <= 0:
            w = np.ones_like(w)
        q = total * w / w.sum()
        base = np.floor(q).astype(np.int64)
        base[np.argsort(-(q - base))[: int(total - base.sum())]] += 1
        return base

    for k, row in dong.reset_index(drop=True).iterrows():
        m = ids == k + 1
        w = dens[m]
        pop50[m] = allocate(int(row["인구"]), w)
        old50[m] = allocate(int(row["고령인구"]), w * eld[m])
    ny, nx = ids.shape[0] // 2, ids.shape[1] // 2

    def to100(a):
        return a.reshape(ny, 2, nx, 2).sum(axis=(1, 3))

    land100 = to100(inland.astype(int)) > 0
    pop = np.where(land100, to100(pop50), -1).astype("int32")
    old = np.where(land100, to100(old50), -1).astype("int32")
    return pop, old


# ---------------------------------------------------------------- 실행
def main():
    land, coast = land_polygon()
    XX, YY = cell_centers()
    transform = from_origin(X0, Y1, CELL, CELL)
    inland = rasterize([(land, 1)], out_shape=(NY, NX), transform=transform, fill=0, dtype="uint8").astype(bool)
    coast_mask = rasterize([(coast.buffer(CELL), 1)], out_shape=(NY, NX), transform=transform, fill=0, dtype="uint8")
    dist_coast = ndimage.distance_transform_edt(1 - coast_mask) * CELL
    dens = np.where(inland, density(XX, YY), 0.0)

    eld = elderly_share(dens, XX, YY)
    dong, ids = make_dong(land, dens, XX, YY, inland, eld)
    lst = make_lst(dens, dist_coast, inland, XX, YY)
    events = make_events(dens, lst, inland, eld, dong.union_all())
    stations = make_stations(land, lst, inland)
    roads = make_roads(land)

    for name, gdf in [("dong", dong), ("events", events), ("stations", stations), ("roads", roads)]:
        path = os.path.join(OUT, f"hanbit_{name}.gpkg")
        if os.path.exists(path):
            os.remove(path)
        gdf.to_file(path, layer=f"hanbit_{name}", driver="GPKG")
    pop, old = make_pop_grid(dong, ids, dens, eld, inland)
    t100 = from_origin(X0, Y1, 2 * CELL, 2 * CELL)
    with rasterio.open(os.path.join(OUT, "hanbit_pop100.tif"), "w", driver="GTiff", width=NX // 2, height=NY // 2,
                       count=2, dtype="int32", crs=CRS, transform=t100, nodata=-1, compress="deflate", tiled=True) as dst:
        dst.write(pop, 1)
        dst.write(old, 2)
        dst.set_band_description(1, "인구")
        dst.set_band_description(2, "고령인구(65세 이상)")
    with rasterio.open(os.path.join(OUT, "hanbit_lst.tif"), "w", driver="GTiff", width=NX, height=NY, count=1,
                       dtype="float32", crs=CRS, transform=transform, nodata=-9999.0,
                       compress="deflate", predictor=3, tiled=True) as dst:
        dst.write(np.where(np.isnan(lst), -9999.0, lst).astype("float32"), 1)
        dst.set_band_description(1, "지표온도(℃)")

    print(f"행정동 {len(dong)}개, 구 {dong['구'].nunique()}개, 인구 {dong['인구'].sum():,}명, "
          f"면적 {dong['면적_km2'].sum():.1f} ㎢ (최소 {dong['면적_km2'].min():.2f}, 최대 {dong['면적_km2'].max():.2f})")
    print(f"폭염 구급 출동 {len(events)}건, 관측소 {len(stations)}곳, 도로 {len(roads)}개")
    print(f"지표온도 {np.nanmin(lst):.1f}~{np.nanmax(lst):.1f}℃, 평균 {np.nanmean(lst):.2f}")
    print(dong.groupby("구").agg(동수=("동코드", "size"), 인구=("인구", "sum")))


if __name__ == "__main__":
    main()
