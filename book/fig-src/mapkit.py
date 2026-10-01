"""3부 이후 그림에서 함께 쓰는 지도 도구. 한빛시 행정동을 svglib.Svg 위에 그림."""
import os

import geopandas as gpd
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")


def load_dong():
    return gpd.read_file(os.path.join(DATA, "hanbit_dong.gpkg"))


class MapFrame:
    """bounds(x0, y0, x1, y1) 범위를 그림의 (x, y)에서 너비 w로 그림"""

    def __init__(self, bounds, x, y, w):
        self.X0, self.Y0, self.X1, self.Y1 = bounds
        self.x, self.y, self.w = x, y, w
        self.k = w / (self.X1 - self.X0)
        self.h = (self.Y1 - self.Y0) * self.k

    def xy(self, X, Y):
        return self.x + (X - self.X0) * self.k, self.y + (self.Y1 - Y) * self.k


def polys(g):
    return list(getattr(g, "geoms", [g]))


def draw(s, fr, geoms, css, width=0.4, stroke="s-bg", fills=None):
    """geoms마다 css 클래스(문자열 목록)로 칠함. fills가 있으면 fill 속성으로 직접 칠함(색 견본용)"""
    for i, g in enumerate(geoms):
        for p in polys(g):
            pts = [fr.xy(x, y) for x, y in p.exterior.coords]
            if fills is not None:
                s.polygon(pts, cls=stroke, width=width, fill=fills[i])
            else:
                s.polygon(pts, cls=f"{stroke} {css[i]}", width=width)


def outline(s, fr, geom, cls="s-fg", width=1.4, stroke=None):
    """테두리. stroke를 주면 모드와 관계없이 그 색으로 그림(밝은 색으로 칠한 지도 위에 그릴 때)"""
    for p in polys(geom):
        d = "M" + " L".join(f"{fr.xy(x, y)[0]:.1f},{fr.xy(x, y)[1]:.1f}" for x, y in p.exterior.coords) + " Z"
        if stroke:
            s.add(f'<path d="{d}" stroke="{stroke}" stroke-width="{width}" fill="none"/>')
        else:
            s.path(d, cls=cls, width=width)


def legend_row(s, x, y, items, box=12, gap=8, size=11):
    """items = [(css, 라벨)] 를 한 줄로 그림. 끝 x 좌표를 돌려줌"""
    for css, label in items:
        s.rect(x, y - box + 2, box, box, cls=f"s-mu {css}", width=0.5)
        s.text(x + box + 4, y, label, size=size, anchor="start")
        x += box + 4 + len(label) * size * 0.62 + gap + 6
    return x


def quantile5(v):
    """분위수 5계급 번호 (엔진 classify와 같은 mapclassify.Quantiles)"""
    import pandas as pd

    from geostat_engine.analysis.classify import classify

    c = classify(pd.Series(np.asarray(v, float), name="v"), "quantile", 5)
    return c.classes.astype(int) + (5 - len(c.breaks))


def dong_vars():
    """행정동에 1·5·8강에서 만든 변수를 붙여 돌려줌 (엔진의 점 집계·존 통계로 계산해 앱과 같음)"""
    import warnings

    from geostat_engine.analysis import aggregate as agg
    from geostat_engine.analysis import zonal

    warnings.filterwarnings("ignore")
    dong = load_dong()
    events = gpd.read_file(os.path.join(DATA, "hanbit_events.gpkg"))
    lst = os.path.join(DATA, "hanbit_lst.tif")
    dong["PT_CNT"] = agg.aggregate(dong, events, stats=[], count=True, density=False).columns["CNT"]
    pl = zonal.prepare(dong, type("R", (), {"path": lst, "info": {"count": 1, "crs": "EPSG:5186"}})(), {"stats": ["mean"], "band": 1})
    dong["ZS_MEAN"] = zonal.run(pl, lambda *_: None)["columns"]["MEAN"]
    dong["출동률"] = dong["PT_CNT"] / dong["인구"] * 10000
    dong["고령비율"] = dong["고령인구"] / dong["인구"] * 100
    return dong


# ---------------------------------------------------------------- 래스터 그림 (4·5부)
RAMP = np.array([[255, 241, 224], [253, 201, 143], [249, 143, 69], [217, 83, 15], [140, 45, 4]], float)  # q0~q4
DRAMP = np.array([[33, 102, 172], [103, 169, 207], [209, 229, 240], [247, 247, 247], [253, 219, 199], [239, 138, 98], [178, 24, 43]], float)


def _ramp(v, lo, hi, ramp):
    t = np.nan_to_num(np.clip((v - lo) / (hi - lo), 0, 1)) * (len(ramp) - 1)
    i = np.clip(np.floor(t).astype(int), 0, len(ramp) - 2)
    f = (t - i)[..., None]
    rgb = ramp[i] * (1 - f) + ramp[i + 1] * f
    a = np.where(np.isnan(v), 0, 255)[..., None]
    return np.concatenate([np.nan_to_num(rgb), a], axis=-1).astype(np.uint8)


def ramp_rgb(v, lo, hi):
    """값 → 순차 색(q0~q4를 이은 연속 색). NaN은 투명"""
    return _ramp(v, lo, hi, RAMP)


def div_rgb(v, lo, hi):
    """값 → 발산 색(파랑~흰색~빨강, 가운데가 (lo+hi)/2). NaN은 투명"""
    return _ramp(v, lo, hi, DRAMP)


def png(arr_rgba, width=None):
    """RGBA 배열 → PNG. 표시 크기의 2배로 줄이고 색을 64개로 줄여 파일을 작게 함"""
    import io

    from PIL import Image

    im = Image.fromarray(arr_rgba, "RGBA")
    if width and im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.Resampling.BOX)
    im = im.quantize(64, method=Image.Quantize.FASTOCTREE)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def to_array(values, inside):
    """창 안 격자점의 값(1차원) → 2차원 배열(위쪽 행이 북쪽). 창 밖은 NaN"""
    a = np.full(inside.shape, np.nan)
    a[inside] = values
    return a[::-1]


def colorbar(s, x, y, w, lo, hi, ticks, label, diverging=False, fmt=lambda t: f"{t:g}"):
    """가로 색 막대"""
    v = np.linspace(lo, hi, 200)[None, :].repeat(6, 0)
    rgb = (div_rgb if diverging else ramp_rgb)(v, lo, hi)
    s.image_png(x, y, w, 10, png(rgb))
    for t in ticks:
        X = x + (t - lo) / (hi - lo) * w
        s.line(X, y + 10, X, y + 14, cls="s-mu", width=1)
        s.text(X, y + 25, fmt(t).replace("-", "−"), size=10, cls="f-mu")
    s.text(x + w / 2, y - 5, label, size=10, cls="f-mu")
