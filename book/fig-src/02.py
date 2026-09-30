"""2강 그림과 본문 수치.

- 02-degree-neighbors.svg : 경위도 숫자로 거리를 재면 '원'이 남북으로 늘어난 타원이 됨 (한빛시 행정동 중심점)
- 02-mercator.svg : 웹 메르카토르(EPSG:3857)의 거리·면적 부풀림 (한국의 위도 범위)

실행 (GeoStat 엔진 환경에서):
    cd engine && uv run python ../book/fig-src/02.py
"""
import os
import sys
import warnings

import geopandas as gpd
import numpy as np
from pyproj import CRS, Geod, Transformer
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import weights as gw  # noqa: E402

warnings.filterwarnings("ignore")
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "..", "fig")
GEOD = Geod(ellps="GRS80")

dong = gpd.read_file(os.path.join(DATA, "hanbit_dong.gpkg"))
stations = gpd.read_file(os.path.join(DATA, "hanbit_stations.gpkg"))
cen = dong.geometry.centroid
dong_ll = dong.to_crs(4326)
cen_ll = cen.to_crs(4326)
XY = np.c_[cen.x, cen.y]  # m (EPSG:5186)
LL = np.c_[cen_ll.x, cen_ll.y]  # 도 (경도, 위도)
LAT0 = float(LL[:, 1].mean())


def to(epsg, x, y, src=5186):
    return Transformer.from_crs(src, epsg, always_xy=True).transform(x, y)


# ---------------------------------------------------------------- 1. 같은 점, 여러 좌표계
def same_point():
    p = stations.geometry.iloc[0]
    print(f"[1] 관측소 {stations['관측소ID'].iloc[0]}")
    for e in (5186, 4326, 5179, 3857, 32651):
        x, y = to(e, p.x, p.y)
        print(f"  EPSG:{e} {CRS(e).name}: ({x:.6f}, {y:.6f})" if e == 4326 else f"  EPSG:{e} {CRS(e).name}: ({x:,.1f}, {y:,.1f})")


# ---------------------------------------------------------------- 2. 경위도 1도의 길이
def degree_length():
    print("[2] 경도·위도 1도의 길이 (GRS80 측지선, km)")
    for lat in (33.0, 35.0, LAT0, 38.0):
        lon_km = GEOD.inv(127, lat, 128, lat)[2] / 1000
        lat_km = GEOD.inv(127, lat - 0.5, 127, lat + 0.5)[2] / 1000
        print(f"  위도 {lat:.2f}°: 경도 1° = {lon_km:.2f} km, 위도 1° = {lat_km:.2f} km, 비 {lon_km / lat_km:.3f}")


# ---------------------------------------------------------------- 3. 두 관측소 사이 거리
def two_stations():
    s = stations.set_index("관측소ID")
    pts = np.c_[s.geometry.x, s.geometry.y]
    i, j = np.unravel_index(np.argmax(((pts[:, None] - pts[None]) ** 2).sum(-1)), (len(pts), len(pts)))
    a, b = s.index[i], s.index[j]
    pa, pb = s.geometry.iloc[i], s.geometry.iloc[j]
    (lo1, la1), (lo2, la2) = [to(4326, q.x, q.y) for q in (pa, pb)]
    geo = GEOD.inv(lo1, la1, lo2, la2)[2]
    R = 6371008.8
    hav = 2 * R * np.arcsin(np.sqrt(np.sin(np.radians(la2 - la1) / 2) ** 2
                                    + np.cos(np.radians(la1)) * np.cos(np.radians(la2)) * np.sin(np.radians(lo2 - lo1) / 2) ** 2))
    print(f"[3] 가장 먼 두 관측소 {a}–{b}")
    print(f"  경위도: {a} ({lo1:.5f}, {la1:.5f}), {b} ({lo2:.5f}, {la2:.5f})")
    print(f"  측지선(GRS80) {geo / 1000:.3f} km, 하버사인(구) {hav / 1000:.3f} km")
    for e in (5186, 5179, 32651, 3857):
        (x1, y1), (x2, y2) = to(e, pa.x, pa.y), to(e, pb.x, pb.y)
        dd = np.hypot(x2 - x1, y2 - y1)
        print(f"  EPSG:{e} 평면 거리 {dd / 1000:.3f} km (측지선 대비 {dd / geo - 1:+.3%})")
    naive = np.hypot(lo2 - lo1, la2 - la1)
    print(f"  경위도 숫자 그대로: {naive:.4f} '도' → ×111 km = {naive * 111:.3f} km (측지선 대비 {naive * 111000 / geo - 1:+.1%})")
    print(f"    차이 성분: 동서 {lo2 - lo1:+.4f}°, 남북 {la2 - la1:+.4f}°")


# ---------------------------------------------------------------- 4. 면적
def areas():
    union = dong.union_all()
    g = gpd.GeoSeries([union], crs=5186)
    print("[4] 한빛시 면적")
    for e in (5186, 5179, 32651, 3857):
        print(f"  EPSG:{e}: {g.to_crs(e).area.iloc[0] / 1e6:.2f} ㎢")
    geo_area, _ = GEOD.geometry_area_perimeter(g.to_crs(4326).iloc[0])
    print(f"  타원체 면적(측지): {abs(geo_area) / 1e6:.2f} ㎢")
    print(f"  경위도 숫자 그대로: {g.to_crs(4326).area.iloc[0]:.5f} '제곱도'")


# ---------------------------------------------------------------- 5. 경위도 그대로 이웃 찾기
def neighbors_compare():
    n = len(XY)
    k = 6
    _, nn_m = cKDTree(XY).query(XY, k + 1)
    _, nn_d = cKDTree(LL).query(LL, k + 1)
    diff = sum(set(nn_m[i, 1:]) != set(nn_d[i, 1:]) for i in range(n))
    changed = sum(len(set(nn_m[i, 1:]) - set(nn_d[i, 1:])) for i in range(n))
    print(f"[5] KNN k={k}: 이웃 집합이 달라진 동 {diff}/{n}, 바뀐 이웃 수 합계 {changed} (전체 {n * k}개 중 {changed / (n * k):.1%})")
    # 남북 방향 이웃 비율
    def ns_share(nn, P):
        v = np.concatenate([XY[nn[i, 1:]] - XY[i] for i in range(n)])
        return np.mean(np.abs(v[:, 1]) > np.abs(v[:, 0]))
    print(f"  이웃 방향이 남북 쪽인 비율: 평면(m) {ns_share(nn_m, XY):.1%}, 경위도 숫자 {ns_share(nn_d, LL):.1%}")

    # 거리 기준: 3 km와 0.03도
    t_m = 3000.0
    t_d = 0.03
    cnt_m = np.array([len(x) - 1 for x in cKDTree(XY).query_ball_point(XY, t_m)])
    cnt_d = np.array([len(x) - 1 for x in cKDTree(LL).query_ball_point(LL, t_d)])
    print(f"  거리 기준 3 km: 평균 이웃 {cnt_m.mean():.2f}, 이웃 없는 동 {(cnt_m == 0).sum()}")
    print(f"  경위도 0.03도: 평균 이웃 {cnt_d.mean():.2f}, 이웃 없는 동 {(cnt_d == 0).sum()}")
    lon_km = GEOD.inv(125.2, LAT0, 126.2, LAT0)[2] / 1000
    lat_km = GEOD.inv(125.2, LAT0 - 0.5, 125.2, LAT0 + 0.5)[2] / 1000
    print(f"  0.03도 = 동서 {0.03 * lon_km:.2f} km, 남북 {0.03 * lat_km:.2f} km")

    # 엔진의 거리 기준 제안값: 5186 원본과 4326으로 변환한 자료
    s_m = gw.suggest_threshold(dong)
    s_ll = gw.suggest_threshold(dong_ll)
    import math
    print(f"  GeoStat 제안 최소 거리(대화상자 표시값, 소수 셋째 자리 올림): 5186 → {math.ceil(s_m['threshold'] * 1000) / 1000} ({s_m['note']})")
    print(f"                        4326 → {math.ceil(s_ll['threshold'] * 1000) / 1000} ({s_ll['note']})")
    import libpysal.weights as lw
    print(f"  (참고) 경위도 숫자로 바로 계산한 최소 거리: {lw.min_threshold_distance(LL):.5f} '도'")
    return lon_km, lat_km


def fig_degree_neighbors(lon_km, lat_km):
    """가운데 한 동을 골라, 3 km 원과 '0.03도 원'(실제로는 타원)을 그림"""
    # 도심 쪽에서 이웃이 많은 동을 고름: 원도심과 신도심 사이 가운데에 가까운 동
    target = np.array([37000.0, 451500.0])
    center = int(np.argmin(((XY - target) ** 2).sum(1)))
    c = XY[center]
    R_m = 3000.0
    rx, ry = 0.03 * lon_km * 1000, 0.03 * lat_km * 1000
    in_m = np.hypot(*(XY - c).T) <= R_m
    d_ll = np.hypot(*(LL - LL[center]).T)
    in_d = d_ll <= 0.03
    s = Svg(720, 360, "한빛시 행정동 중심점과 가운데 동에서 반경 3 km 원(실선), 경위도 숫자로 반경 0.03도를 잰 범위(점선). 경위도 그대로 재면 남북으로 늘어난 타원이 되어 이웃이 달라짐")
    # 지도 틀: 가운데 동 주변 16 km × 12 km
    W, H = 440, 330
    x0, y0 = 20, 20
    span_x = 16000.0
    k = W / span_x
    X0, Y1 = c[0] - span_x / 2, c[1] + (H / k) / 2

    def xy(X, Y):
        return x0 + (X - X0) * k, y0 + (Y1 - Y) * k

    s.add(f'<clipPath><rect x="{x0}" y="{y0}" width="{W}" height="{H}"/></clipPath>')
    s.rect(x0, y0, W, H, cls="s-mu f-sf", width=1)
    for g in dong.geometry:
        pts = [xy(px, py) for px, py in g.exterior.coords]
        if all(not (x0 <= u <= x0 + W and y0 <= v <= y0 + H) for u, v in pts):
            continue
        pts = [(min(max(u, x0), x0 + W), min(max(v, y0), y0 + H)) for u, v in pts]
        s.polygon(pts, cls="s-mu f-sf", width=0.5)
    cx, cy = xy(*c)
    s.add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{R_m * k:.1f}" class="s-ac" stroke-width="2" fill="none"/>')
    s.add(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx * k:.1f}" ry="{ry * k:.1f}" class="s-bd" stroke-width="2" stroke-dasharray="6 4" fill="none"/>')
    for i, (X, Y) in enumerate(XY):
        u, v = xy(X, Y)
        if not (x0 <= u <= x0 + W and y0 <= v <= y0 + H):
            continue
        if i == center:
            s.circle(u, v, 5, cls="f-fg")
        elif in_m[i] and in_d[i]:
            s.circle(u, v, 4, cls="f-fg")
        elif in_m[i]:
            s.circle(u, v, 4.5, cls="f-ac")
        elif in_d[i]:
            s.circle(u, v, 4.5, cls="f-bd")
        else:
            s.circle(u, v, 2.2, cls="f-mu")
    # 축척 막대
    s.line(x0 + 12, y0 + H - 14, x0 + 12 + 2000 * k, y0 + H - 14, cls="s-fg", width=2)
    s.text(x0 + 12 + 1000 * k, y0 + H - 20, "2 km", size=11)
    # 설명
    lx = 490
    s.text(lx, 50, "가운데 동에서 이웃 찾기", size=13, anchor="start", weight="600")
    s.add(f'<circle cx="{lx + 8}" cy="80" r="10" class="s-ac" stroke-width="2" fill="none"/>')
    s.text(lx + 26, 84, "평면 좌표(m)로 3 km", size=12, anchor="start")
    s.add(f'<ellipse cx="{lx + 8}" cy="110" rx="8" ry="10" class="s-bd" stroke-width="2" stroke-dasharray="4 3" fill="none"/>')
    s.text(lx + 26, 114, "경위도 숫자로 0.03도", size=12, anchor="start")
    s.text(lx + 26, 131, f"(동서 {rx / 1000:.2f} km, 남북 {ry / 1000:.2f} km)", size=11, anchor="start", cls="f-mu")
    s.circle(lx + 8, 160, 4, cls="f-fg")
    s.text(lx + 26, 164, f"둘 다 이웃: {int((in_m & in_d).sum()) - 1}개", size=12, anchor="start")
    s.circle(lx + 8, 184, 4.5, cls="f-ac")
    s.text(lx + 26, 188, f"3 km 원에만 듦: {int((in_m & ~in_d).sum())}개", size=12, anchor="start")
    s.circle(lx + 8, 208, 4.5, cls="f-bd")
    s.text(lx + 26, 212, f"0.03도 범위에만 듦: {int((~in_m & in_d).sum())}개", size=12, anchor="start")
    s.circle(lx + 8, 232, 2.2, cls="f-mu")
    s.text(lx + 26, 236, "행정동 중심점", size=12, anchor="start", cls="f-mu")
    s.save(os.path.join(OUT, "02-degree-neighbors.svg"))
    name = dong.loc[center, "동이름"]
    print(f"[그림1] 가운데 동 {name}: 3 km 이웃 {int(in_m.sum()) - 1}, 0.03도 이웃 {int(in_d.sum()) - 1}, "
          f"둘 다 {int((in_m & in_d).sum()) - 1}, 원에만 {int((in_m & ~in_d).sum())}, 타원에만 {int((~in_m & in_d).sum())}")


# ---------------------------------------------------------------- 6. 웹 메르카토르
def fig_mercator():
    lats = np.linspace(33, 38.5, 56)
    kd = 1 / np.cos(np.radians(lats))
    s = Svg(720, 300, "웹 메르카토르(EPSG:3857)에서 잰 거리와 면적이 실제보다 커지는 배율. 한국의 위도에서 거리는 1.19~1.28배, 면적은 1.42~1.63배로 부풀려짐")
    gx, gy, gw, gh = 70, 40, 400, 200
    ymin, ymax = 1.0, 1.7
    X = lambda v: gx + (v - 33) / 5.5 * gw  # noqa: E731
    Y = lambda v: gy + gh - (v - ymin) / (ymax - ymin) * gh  # noqa: E731
    for t in (1.0, 1.2, 1.4, 1.6):
        s.line(gx, Y(t), gx + gw, Y(t), cls="s-mu", width=0.5, dash="2 3" if t > 1 else None)
        s.text(gx - 8, Y(t) + 4, f"{t:.1f}배", size=11, anchor="end", cls="f-mu")
    for t in (33, 34, 35, 36, 37, 38):
        s.text(X(t), gy + gh + 18, f"{t}°N", size=11, cls="f-mu")
    s.text(gx + gw / 2, gy + gh + 38, "위도", size=11, cls="f-mu")
    s.path("M" + " L".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in zip(lats, kd)), cls="s-ac", width=2.5)
    s.path("M" + " L".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in zip(lats, kd**2)), cls="s-bd", width=2.5)
    s.text(X(38.5) + 6, Y(kd[-1]) + 4, "거리", size=12, anchor="start", cls="f-ac", weight="600")
    s.text(X(38.5) + 6, Y(kd[-1] ** 2) + 4, "면적", size=12, anchor="start", cls="f-bd", weight="600")
    marks = [(33.5, "제주"), (35.1, "부산"), (37.55, "서울"), (LAT0, "한빛시")]
    for lat, name in marks:
        k = 1 / np.cos(np.radians(lat))
        s.line(X(lat), gy, X(lat), gy + gh, cls="s-mu", width=0.8, dash="3 3")
        s.text(X(lat), gy - 6, name, size=11, cls="f-mu" if name != "한빛시" else "f-fg")
        s.circle(X(lat), Y(k), 3, cls="f-ac")
        s.circle(X(lat), Y(k * k), 3, cls="f-bd")
    s.text(565, 60, "3857에서 잰 값", size=13, anchor="start", weight="600")
    rows = []
    for lat, name in marks:
        k = 1 / np.cos(np.radians(lat))
        rows.append((name, k, k * k))
    for i, (name, k, a) in enumerate(rows):
        yy = 90 + i * 40
        s.text(565, yy, name, size=12, anchor="start")
        s.text(565, yy + 17, f"거리 ×{k:.2f}, 면적 ×{a:.2f}", size=11, anchor="start", cls="f-mu")
    s.save(os.path.join(OUT, "02-mercator.svg"))
    print("[그림2] 3857 배율")
    for name, k, a in rows:
        print(f"  {name}: 거리 {k:.3f}, 면적 {a:.3f}")
    print(f"  33°: {1 / np.cos(np.radians(33)):.3f}/{1 / np.cos(np.radians(33)) ** 2:.3f}, 38.5°: {kd[-1]:.3f}/{kd[-1] ** 2:.3f}")


# ---------------------------------------------------------------- 7. 좌표계를 잘못 지정하면
def mislabel():
    p = cen.iloc[len(cen) // 2]
    real = to(4326, p.x, p.y, 5186)
    print("[7] 같은 좌표 숫자를 다른 좌표계로 읽으면")
    for e in (5174, 5181, 5179):
        ll = Transformer.from_crs(e, 4326, always_xy=True).transform(p.x, p.y)
        az, _, dist = GEOD.inv(real[0], real[1], ll[0], ll[1])
        print(f"  5186 숫자를 EPSG:{e}로 읽음: {dist / 1000:,.1f} km 이동 (방위각 {az:.0f}°)")
    for x, y in [(200000.0, 500000.0), (153523.0, 347836.0)]:
        a = Transformer.from_crs(5174, 4326, always_xy=True).transform(x, y)
        b = Transformer.from_crs(5181, 4326, always_xy=True).transform(x, y)
        az, _, dist = GEOD.inv(b[0], b[1], a[0], a[1])
        print(f"  같은 숫자 ({x:,.0f}, {y:,.0f})를 5174(Bessel)와 5181(GRS80)로 읽은 차이: {dist:.0f} m, 방위각 {az:.0f}°")
    for e in (5174, 5181, 5185, 5186, 5187, 5188, 5179):
        d = CRS(e).to_dict()
        print(f"  EPSG:{e} {CRS(e).name}: 원점 경도 {d.get('lon_0')}, 위도 {d.get('lat_0')}, k={d.get('k')}, "
              f"가산 ({d.get('x_0')}, {d.get('y_0')}), 타원체 {d.get('ellps')}")


def tm_scale():
    """횡메르카토르 축척 오차: 중앙 자오선에서 떨어진 거리별"""
    R = 6371.0
    print("[8] TM 축척 계수 근사 k ≈ k0(1 + x²/2R²)")
    for x in (50, 100, 150, 200, 250):
        print(f"  중앙 자오선에서 {x} km: k0=1 → {1 + x**2 / (2 * R**2):.6f}, k0=0.9996 → {0.9996 * (1 + x**2 / (2 * R**2)):.6f}")
    lon_c = float(LL[:, 0].mean())
    print(f"  한빛시 중심 경도 {lon_c:.3f}° (5186 중앙 자오선 127°에서 {GEOD.inv(lon_c, LAT0, 127, LAT0)[2] / 1000:.0f} km)")


if __name__ == "__main__":
    same_point()
    degree_length()
    two_stations()
    areas()
    lon_km, lat_km = neighbors_compare()
    fig_degree_neighbors(lon_km, lat_km)
    fig_mercator()
    mislabel()
    tm_scale()
