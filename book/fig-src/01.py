"""1강 그림과 본문 수치. GeoStat 엔진 함수(점 집계·존 통계)로 계산해 앱 결과와 같게 함.

- 01-hanbit.svg : 한빛시 예제 자료 (벡터 레이어와 지표온도 래스터)
- 01-count-vs-rate.svg : 구급 출동 건수(외연량) 지도와 인구 1만 명당 출동률(내포량) 지도
- 01-support.svg : 같은 지표온도를 50 m 셀, 500 m 격자, 행정동 평균으로 본 것

실행 (GeoStat 엔진 환경에서, 먼저 book/data/make_hanbit.py로 자료를 만듦):
    cd engine && uv run python ../book/fig-src/01.py
"""
import io
import os
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from svglib import Svg  # noqa: E402

from geostat_engine.analysis import aggregate as agg  # noqa: E402
from geostat_engine.analysis.classify import classify  # noqa: E402
from geostat_engine.analysis import zonal  # noqa: E402

DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "..", "fig")

dong = gpd.read_file(os.path.join(DATA, "hanbit_dong.gpkg"))
events = gpd.read_file(os.path.join(DATA, "hanbit_events.gpkg"))
stations = gpd.read_file(os.path.join(DATA, "hanbit_stations.gpkg"))
roads = gpd.read_file(os.path.join(DATA, "hanbit_roads.gpkg"))
LST_PATH = os.path.join(DATA, "hanbit_lst.tif")
with rasterio.open(LST_PATH) as src:
    lst = src.read(1, masked=True).filled(np.nan).astype(float)
    T = src.transform
X0, Y1, CELL = T.c, T.f, T.a
NY, NX = lst.shape
X1, Y0 = X0 + NX * CELL, Y1 - NY * CELL

RAMP = np.array([[255, 241, 224], [253, 201, 143], [249, 143, 69], [217, 83, 15], [140, 45, 4]], float)


def ramp_rgb(v, lo, hi):
    """값 → 순차 색 (q0~q4를 이은 연속 색). NaN은 투명"""
    t = np.nan_to_num(np.clip((v - lo) / (hi - lo), 0, 1)) * (len(RAMP) - 1)
    i = np.clip(np.floor(t).astype(int), 0, len(RAMP) - 2)
    f = (t - i)[..., None]
    rgb = RAMP[i] * (1 - f) + RAMP[i + 1] * f
    a = np.where(np.isnan(v), 0, 255)[..., None]
    return np.concatenate([np.nan_to_num(rgb), a], axis=-1).astype(np.uint8)


def png(arr_rgba, width=None):
    """RGBA 배열 → PNG. 파일 크기를 줄이려고 표시 크기의 2배로 줄이고 색을 64개로 줄임"""
    im = Image.fromarray(arr_rgba, "RGBA")
    if width and im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.Resampling.BOX)
    im = im.quantize(64, method=Image.Quantize.FASTOCTREE)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


class MapFrame:
    """도시 범위(X0~X1, Y0~Y1)를 그림 좌표로 바꿈"""

    def __init__(self, x, y, w):
        self.x, self.y, self.w = x, y, w
        self.h = w * (Y1 - Y0) / (X1 - X0)
        self.k = w / (X1 - X0)

    def xy(self, X, Y):
        return self.x + (X - X0) * self.k, self.y + (Y1 - Y) * self.k


def draw_polys(s, fr, geoms, classes=None, cls="s-mu f-sf", width=0.6):
    for i, g in enumerate(geoms):
        c = cls if classes is None else f"s-bg q{classes[i]}"
        s.polygon([fr.xy(x, y) for x, y in g.exterior.coords], cls=c, width=width)


def outline(s, fr, geom, cls="s-fg", width=1.4):
    for g in getattr(geom, "geoms", [geom]):
        d = "M" + " L".join(f"{fr.xy(x, y)[0]:.1f},{fr.xy(x, y)[1]:.1f}" for x, y in g.exterior.coords) + " Z"
        s.path(d, cls=cls, width=width)


def quantile_classes(v, k=5):
    """앱의 분위수 지도와 같은 분류 (엔진의 classify, mapclassify.Quantiles). 가장 높은 계급이 k-1이 되게 맞춤"""
    c = classify(pd.Series(v, name="v"), "quantile", k)
    return c.classes.astype(int) + (k - len(c.breaks))


# ---------------------------------------------------------------- 엔진 계산 (앱과 같은 결과)
res = agg.aggregate(dong, events, stats=[], count=True, density=False)
dong["PT_CNT"] = res.columns["CNT"]
payload = zonal.prepare(dong, type("R", (), {"path": LST_PATH, "info": {"count": 1, "crs": "EPSG:5186"}})(),
                        {"stats": ["mean", "stdev"], "band": 1})
zs = zonal.run(payload, lambda *_: None)["columns"]
dong["ZS_MEAN"], dong["ZS_STD"] = zs["MEAN"], zs["STD"]
dong["밀도"] = dong["인구"] / dong["면적_km2"]
dong["출동률"] = dong["PT_CNT"] / dong["인구"] * 10000


# ---------------------------------------------------------------- 그림 1. 한빛시
def fig_hanbit():
    s = Svg(720, 330, "한빛시 예제 자료. 왼쪽은 행정동(면)·도로(선)·기상 관측소와 폭염 관련 구급 출동 위치(점), 오른쪽은 여름 한낮 지표온도 래스터")
    left, right = MapFrame(20, 40, 330), MapFrame(370, 40, 330)
    s.text(left.x + left.w / 2, 26, "벡터: 점·선·면", size=13, weight="600")
    s.text(right.x + right.w / 2, 26, "래스터: 50 m 셀", size=13, weight="600")
    draw_polys(s, left, dong.geometry, cls="s-mu f-sf", width=0.5)
    for _, sub in dong.groupby("구"):
        outline(s, left, sub.union_all(), cls="s-fg", width=1.2)
    for g in roads.geometry:
        for ln in getattr(g, "geoms", [g]):
            d = "M" + " L".join(f"{left.xy(x, y)[0]:.1f},{left.xy(x, y)[1]:.1f}" for x, y in ln.coords)
            s.path(d, cls="s-ac", width=2.2)
    for p in events.geometry:
        x, y = left.xy(p.x, p.y)
        s.circle(x, y, 0.9, cls="f-bd", width=0)
    for p in stations.geometry:
        x, y = left.xy(p.x, p.y)
        s.polygon([(x, y - 4.2), (x - 3.8, y + 2.6), (x + 3.8, y + 2.6)], cls="s-bg f-fg", width=0.8)
    # 래스터
    s.image_png(right.x, right.y, right.w, right.h, png(ramp_rgb(lst, 24, 36), 2 * right.w))
    outline(s, right, dong.union_all(), cls="s-fg", width=1.0)
    # 범례
    ly = left.y + left.h + 22
    s.polygon([(28, ly - 4), (24, ly + 3), (32, ly + 3)], cls="s-bg f-fg", width=0.8)
    s.text(38, ly + 3, "기상 관측소", size=11, anchor="start", cls="f-mu")
    s.circle(112, ly, 2, cls="f-bd", width=0)
    s.text(118, ly + 3, "구급 출동", size=11, anchor="start", cls="f-mu")
    s.line(180, ly, 196, ly, cls="s-ac", width=2.2)
    s.text(201, ly + 3, "도로", size=11, anchor="start", cls="f-mu")
    s.line(234, ly, 250, ly, cls="s-fg", width=1.2)
    s.text(255, ly + 3, "구 경계", size=11, anchor="start", cls="f-mu")
    bx = right.x + 60
    for i in range(5):
        s.rect(bx + i * 40, ly - 6, 40, 12, cls=f"s-bg q{i}", width=0.5)
    s.text(bx - 6, ly + 4, "24℃", size=11, anchor="end", cls="f-mu")
    s.text(bx + 206, ly + 4, "36℃", size=11, anchor="start", cls="f-mu")
    s.save(os.path.join(OUT, "01-hanbit.svg"))


# ---------------------------------------------------------------- 그림 2. 출동 건수 vs 출동률
def fig_count_rate():
    s = Svg(720, 330, "같은 행정동을 구급 출동 건수(외연량)로 칠한 지도와 인구 1만 명당 출동률(내포량)로 칠한 지도. 건수 지도는 사람이 많이 사는 곳을, 출동률 지도는 주민 한 사람이 겪는 위험을 보여 줌")
    left, right = MapFrame(20, 40, 330), MapFrame(370, 40, 330)
    cc = quantile_classes(dong["PT_CNT"].to_numpy())
    cr = quantile_classes(dong["출동률"].to_numpy())
    s.text(left.x + left.w / 2, 26, "출동 건수 (건)", size=13, weight="600")
    s.text(right.x + right.w / 2, 26, "인구 1만 명당 출동률", size=13, weight="600")
    draw_polys(s, left, dong.geometry, classes=cc, width=0.5)
    draw_polys(s, right, dong.geometry, classes=cr, width=0.5)
    ly = left.y + left.h + 22
    for fr in (left, right):
        bx = fr.x + fr.w / 2 - 100
        for i in range(5):
            s.rect(bx + i * 40, ly - 6, 40, 12, cls=f"s-bg q{i}", width=0.5)
        s.text(bx - 6, ly + 4, "낮음", size=11, anchor="end", cls="f-mu")
        s.text(bx + 206, ly + 4, "높음 (5분위)", size=11, anchor="start", cls="f-mu")
    s.save(os.path.join(OUT, "01-count-vs-rate.svg"))

    print(f"  계급별 동 수: 건수 {np.bincount(cc, minlength=5).tolist()}, 출동률 {np.bincount(cr, minlength=5).tolist()}")
    new = dong[(cr == 4) & (cc < 4)]
    print(f"  출동률에서만 가장 진한 계급인 동 {len(new)}개: 건수 계급 분포 {np.bincount(cc[(cr == 4) & (cc < 4)], minlength=5).tolist()}, "
          f"평균 인구 {new['인구'].mean():,.0f} (전체 {dong['인구'].mean():,.0f}), "
          f"고령비율 합산 {new['고령인구'].sum() / new['인구'].sum():.1%} (도시 전체 {dong['고령인구'].sum() / dong['인구'].sum():.1%}), "
          f"단순 평균 {(new['고령인구'] / new['인구']).mean():.1%} (전체 동 단순 평균 {(dong['고령인구'] / dong['인구']).mean():.1%})")
    top_c = set(dong.loc[cc == 4, "동코드"])
    top_r = set(dong.loc[cr == 4, "동코드"])
    print(f"[그림2] 가장 진한 계급 동 수: 건수 {len(top_c)}, 출동률 {len(top_r)}, 겹치는 동 {len(top_c & top_r)}")
    print(f"  건수와 인구의 상관 r = {np.corrcoef(dong['PT_CNT'], dong['인구'])[0, 1]:.2f}, 출동률과 인구 r = {np.corrcoef(dong['출동률'], dong['인구'])[0, 1]:.2f}")
    print(f"  건수 상위 5분위 동의 인구 합 비율 {dong.loc[cc == 4, '인구'].sum() / dong['인구'].sum():.1%}")
    print(f"  동 인구 {dong['인구'].min():,}~{dong['인구'].max():,}, 평균 {dong['인구'].mean():,.0f}")


# ---------------------------------------------------------------- 그림 3. 지원(support)
def block_mean(a, k):
    ny, nx = a.shape[0] // k, a.shape[1] // k
    b = a[: ny * k, : nx * k].reshape(ny, k, nx, k)
    with np.errstate(all="ignore"):
        return np.nanmean(b, axis=(1, 3))


def fig_support():
    g500 = block_mean(lst, 10)
    s = Svg(720, 300, "같은 지표온도를 50 m 셀, 500 m 격자 평균, 행정동 평균으로 나타낸 지도. 넓은 단위로 평균낼수록 극단적인 값이 사라지고 범위가 좁아지지만, 도시 전체의 표준편차는 거의 그대로임")
    w = 220
    frs = [MapFrame(15 + i * 236, 40, w) for i in range(3)]
    titles = ["50 m 셀", "500 m 격자 평균", "행정동 평균"]
    vals = [lst[~np.isnan(lst)], g500[~np.isnan(g500)], dong["ZS_MEAN"].to_numpy()]
    for fr, t, v in zip(frs, titles, vals):
        s.text(fr.x + fr.w / 2, 26, t, size=13, weight="600")
        s.text(fr.x + fr.w / 2, fr.y + fr.h + 20, f"표준편차 {v.std(ddof=1):.2f}℃", size=12)
        s.text(fr.x + fr.w / 2, fr.y + fr.h + 38, f"범위 {v.min():.1f}~{v.max():.1f}℃", size=11, cls="f-mu")
    s.image_png(frs[0].x, frs[0].y, w, frs[0].h, png(ramp_rgb(lst, 24, 36), 2 * w))
    s.image_png(frs[1].x, frs[1].y, w, frs[1].h, png(ramp_rgb(g500, 24, 36)))
    rgb = ramp_rgb(dong["ZS_MEAN"].to_numpy(), 24, 36)
    for g, c in zip(dong.geometry, rgb):
        pts = " ".join(f"{frs[2].xy(x, y)[0]:.1f},{frs[2].xy(x, y)[1]:.1f}" for x, y in g.exterior.coords)
        s.add(f'<polygon points="{pts}" fill="rgb({c[0]},{c[1]},{c[2]})" class="s-bg" stroke-width="0.4"/>')
    for fr in frs:
        outline(s, fr, dong.union_all(), cls="s-mu", width=0.8)
    ly = frs[0].y + frs[0].h + 62
    bx = 360 - 100
    for i in range(5):
        s.rect(bx + i * 40, ly - 6, 40, 12, cls=f"s-bg q{i}", width=0.5)
    s.text(bx - 6, ly + 4, "24℃", size=11, anchor="end", cls="f-mu")
    s.text(bx + 206, ly + 4, "36℃", size=11, anchor="start", cls="f-mu")
    s.save(os.path.join(OUT, "01-support.svg"))
    print("[그림3] 표준편차·범위")
    print(f"  행정동 안 표준편차(ZS_STD): 평균 {dong['ZS_STD'].mean():.2f}℃, 최대 {dong['ZS_STD'].max():.2f}℃")
    print(f"  가장 뜨거운 50 m 셀 {np.nanmax(lst):.2f}℃ → 그 셀이 든 행정동 평균 {dong.loc[dong.contains(gpd.points_from_xy([X0 + CELL * (np.nanargmax(lst) % NX + 0.5)], [Y1 - CELL * (np.nanargmax(lst) // NX + 0.5)])[0]), 'ZS_MEAN'].iloc[0]:.2f}℃")
    area = dong["면적_km2"].to_numpy()
    print(f"  행정동 평균들의 단순 평균 {dong['ZS_MEAN'].mean():.2f}, 면적 가중 평균 {(dong['ZS_MEAN'] * area).sum() / area.sum():.2f}, 셀 평균 {np.nanmean(lst):.2f}")
    for t, v in zip(titles, vals):
        print(f"  {t}: n={len(v)}, 평균 {v.mean():.2f}, 표준편차 {v.std(ddof=1):.3f}, 범위 {v.min():.2f}~{v.max():.2f}")


# ---------------------------------------------------------------- 본문 예: 이웃한 두 동 합치기
def merge_example():
    best = None
    sidx = dong.sindex
    for i, g in enumerate(dong.geometry):
        for j in sidx.query(g, predicate="touches"):
            if j <= i or dong.loc[i, "구"] != dong.loc[j, "구"]:
                continue
            a, b = dong.loc[i], dong.loc[j]
            ratio = max(a["면적_km2"], b["면적_km2"]) / min(a["면적_km2"], b["면적_km2"])
            dens_ratio = max(a["밀도"], b["밀도"]) / min(a["밀도"], b["밀도"])
            score = min(ratio, 6) * min(dens_ratio, 12)
            if best is None or score > best[0]:
                best = (score, i, j)
    _, i, j = best
    a, b = dong.loc[i], dong.loc[j]
    if a["면적_km2"] > b["면적_km2"]:
        a, b = b, a
    pop = a["인구"] + b["인구"]
    area = a["면적_km2"] + b["면적_km2"]
    print("[본문 예] 이웃한 두 동 합치기")
    for d in (a, b):
        print(f"  {d['동이름']}: 인구 {d['인구']:,}, 면적 {d['면적_km2']:.2f}㎢, 밀도 {d['밀도']:,.0f}, 지표온도 평균 {d['ZS_MEAN']:.2f}, 출동 {d['PT_CNT']}건")
    print(f"  합친 인구 {pop:,}, 면적 {area:.2f}, 밀도 {pop / area:,.0f} (단순 평균 {(a['밀도'] + b['밀도']) / 2:,.0f})")
    lst_w = (a["ZS_MEAN"] * a["면적_km2"] + b["ZS_MEAN"] * b["면적_km2"]) / area
    print(f"  합친 지표온도 {lst_w:.2f} (면적 가중), 단순 평균 {(a['ZS_MEAN'] + b['ZS_MEAN']) / 2:.2f}")
    geom = dong.loc[[dong.index[dong['동코드'] == a['동코드']][0], dong.index[dong['동코드'] == b['동코드']][0]]].union_all()
    gm = zonal.run({**payload, "geometry": gpd.GeoSeries([geom], crs=dong.crs)}, lambda *_: None)["columns"]["MEAN"][0]
    print(f"  (확인) 합친 폴리곤으로 바로 존 통계를 구하면 {gm:.2f}")


def check_numbers():
    print("[해 보기] 점 집계·존 통계")
    print(f"  출동 {res.n_source}건 중 동 안에 든 것 {res.n_matched}건, 출동 0건인 동 {res.n_empty}개")
    top = dong.sort_values("PT_CNT", ascending=False).iloc[0]
    print(f"  출동이 가장 많은 동: {top['동이름']} {top['PT_CNT']}건 (인구 {top['인구']:,})")
    rt = dong.sort_values("출동률", ascending=False).head(3)
    for _, r in rt.iterrows():
        print(f"  출동률 상위: {r['동이름']} {r['출동률']:.2f}/1만 명 (출동 {r['PT_CNT']}건, 인구 {r['인구']:,})")
    for code in ["HB001"]:
        r = dong[dong["동코드"] == code].iloc[0]
        print(f"  {code} {r['동이름']}: PT_CNT {r['PT_CNT']}, ZS_MEAN {r['ZS_MEAN']:.2f}")
    print(f"  인구 합계 {dong['인구'].sum():,}, 동 {len(dong)}개, 인구 최소 동 {dong.loc[dong['인구'].idxmin(), '동이름']} {dong['인구'].min():,}")
    print(f"  동 면적 {dong['면적_km2'].min():.2f}~{dong['면적_km2'].max():.2f}㎢, 평균 {dong['면적_km2'].mean():.2f}")
    print(f"  관측소 기온 {stations['기온_8월평균'].min():.2f}~{stations['기온_8월평균'].max():.2f}, 표준편차 {stations['기온_8월평균'].std():.2f}")
    print(f"  도시 면적 {dong['면적_km2'].sum():.1f}㎢, 래스터 {NX}×{NY} = {NX * NY:,}셀, 값 있는 셀 {int(np.isfinite(lst).sum()):,}")
    print("  처음 세 행:")
    print(dong[["동코드", "구", "동이름", "인구", "고령인구", "면적_km2"]].head(3).to_string(index=False))
    city = dong["PT_CNT"].sum() / dong["인구"].sum() * 1e4
    print(f"  도시 출동률 {city:.2f}/1만 명")
    for gu, m in dong.groupby("구"):
        print(f"  {gu}: 동 {len(m)}개, 합산 출동률 {m['PT_CNT'].sum() / m['인구'].sum() * 1e4:.2f}, 동별 출동률 단순 평균 {m['출동률'].mean():.2f}")
    t = dong.sort_values("출동률", ascending=False).iloc[0]
    print(f"  {t['동이름']}: 출동 {t['PT_CNT']}건 → 2건 적으면 {(t['PT_CNT'] - 2) / t['인구'] * 1e4:.1f} ({1 - (t['PT_CNT'] - 2) / t['PT_CNT']:.0%} 감소), 도시의 {t['출동률'] / city:.1f}배")
    h = dong.sort_values("ZS_MEAN", ascending=False).iloc[0]
    print(f"  지표온도 평균이 가장 높은 동 {h['동이름']} {h['ZS_MEAN']:.2f}")
    a, b = (dong[dong["동이름"] == n].iloc[0] for n in ("마루22동", "마루8동"))
    print(f"  연습 3: {a['고령인구']}/{a['인구']} = {a['고령인구'] / a['인구']:.2%}, {b['고령인구']}/{b['인구']} = {b['고령인구'] / b['인구']:.2%}, "
          f"합산 {(a['고령인구'] + b['고령인구']) / (a['인구'] + b['인구']):.2%}, 단순 평균 {(a['고령인구'] / a['인구'] + b['고령인구'] / b['인구']) / 2:.2%}")


if __name__ == "__main__":
    fig_hanbit()
    fig_count_rate()
    fig_support()
    merge_example()
    check_numbers()
