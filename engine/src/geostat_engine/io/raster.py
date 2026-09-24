"""래스터(GeoTIFF·COG 등) 읽기와 지도 타일 만들기.

지도 표시는 웹 메르카토르(EPSG:3857) 256px 타일로 함. 타일마다 원본을 WarpedVRT로 재투영해 읽고
색을 입혀 PNG로 보냄. 축소해서 볼 때 원본 해상도를 모두 읽지 않도록 알맞은 오버뷰 단계를 골라 염.
PNG 인코딩은 Pillow 없이 zlib로 직접 함 (번들 의존성을 줄이기 위함).
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path
from typing import Any

import numpy as np

from geostat_engine.errors import EngineError

RASTER_SUFFIXES = {".tif", ".tiff", ".img", ".vrt", ".asc", ".jp2", ".dem", ".nc", ".hdf"}
TILE_SIZE = 256
# 웹 메르카토르 전체 폭의 절반 (m)
_ORIGIN = 20037508.342789244
# 통계를 구할 때 읽는 최대 크기 (긴 변 기준 픽셀). 원본 전체를 읽지 않고 축소본으로 추정함
_STATS_MAX_PX = 1024
# 이 크기(긴 변)를 넘는데 오버뷰가 없으면 앱에서 오버뷰 만들기를 권함
OVERVIEW_ADVISE_PX = 4096


def is_raster(path: Path) -> bool:
    return path.suffix.lower() in RASTER_SUFFIXES


def _open(path: Path, **kwargs):
    import rasterio

    try:
        return rasterio.open(path, **kwargs)
    except rasterio.errors.RasterioIOError as exc:
        raise EngineError("raster_open_failed", f"래스터를 열지 못함: {exc}") from exc


# ---- 정보·통계 ------------------------------------------------------------------


def _band_stats(src) -> list[dict[str, Any]]:
    """축소본을 읽어 밴드별 최솟값·최댓값·2/98 백분위·평균·표준편차를 구함."""
    from rasterio.enums import Resampling

    scale = max(src.width, src.height) / _STATS_MAX_PX
    out_h = max(1, int(src.height / max(scale, 1)))
    out_w = max(1, int(src.width / max(scale, 1)))
    data = src.read(out_shape=(src.count, out_h, out_w), masked=True, resampling=Resampling.nearest)
    stats = []
    for b in range(src.count):
        band = data[b]
        values = band.compressed().astype("float64")
        values = values[np.isfinite(values)]
        if values.size == 0:
            stats.append(
                {"min": None, "max": None, "p2": None, "p98": None, "mean": None, "std": None}
            )
            continue
        p2, p98 = np.percentile(values, [2, 98])
        stats.append(
            {
                "min": float(values.min()),
                "max": float(values.max()),
                "p2": float(p2),
                "p98": float(p98),
                "mean": float(values.mean()),
                "std": float(values.std()),
            }
        )
    return stats


def describe(path: Path) -> dict[str, Any]:
    """래스터 기본 정보. 좌표계가 없으면 지도에 올릴 수 없으므로 오류로 알림."""
    from rasterio.warp import transform_bounds

    with _open(path) as src:
        if src.crs is None:
            raise EngineError(
                "raster_no_crs", "좌표계가 없는 래스터임. GIS 도구에서 좌표계를 지정한 뒤 열어야 함"
            )
        try:
            wgs84 = transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)
        except Exception as exc:
            raise EngineError("raster_crs_failed", f"좌표계를 변환하지 못함: {exc}") from exc
        # 웹 메르카토르 한계(위도 ±85.05°)로 자름
        west, south, east, north = wgs84
        south, north = max(south, -85.05), min(north, 85.05)
        overviews = src.overviews(1) if src.count else []
        epsg = src.crs.to_epsg()
        return {
            "width": src.width,
            "height": src.height,
            "count": src.count,
            "dtype": src.dtypes[0],
            "crs": f"EPSG:{epsg}" if epsg else src.crs.to_string(),
            "crs_name": _crs_name(src.crs),
            "res": [float(abs(src.res[0])), float(abs(src.res[1]))],
            "nodata": None if src.nodata is None or not math.isfinite(src.nodata) else src.nodata,
            "bounds": [float(v) for v in src.bounds],
            "bounds_wgs84": [west, south, east, north],
            "overviews": [int(o) for o in overviews],
            "needs_overviews": not overviews and max(src.width, src.height) > OVERVIEW_ADVISE_PX,
            "band_names": [src.descriptions[i] or f"밴드 {i + 1}" for i in range(src.count)],
            "stats": _band_stats(src),
            "categorical": src.dtypes[0] in ("uint8", "int8", "uint16", "int16")
            and src.count == 1
            and _looks_categorical(src),
        }


def _crs_name(crs) -> str:
    try:
        from pyproj import CRS

        return CRS.from_user_input(crs.to_wkt()).name
    except Exception:  # noqa: BLE001
        return crs.to_string()


def _looks_categorical(src) -> bool:
    """정수형 단일 밴드이고 서로 다른 값이 적으면 토지피복 같은 범주 자료로 봄."""
    from rasterio.enums import Resampling

    scale = max(src.width, src.height) / 512
    shape = (max(1, int(src.height / max(scale, 1))), max(1, int(src.width / max(scale, 1))))
    data = src.read(1, out_shape=shape, masked=True, resampling=Resampling.nearest)
    return np.unique(data.compressed()).size <= 32


def build_overviews(path: Path) -> list[int]:
    """외부 오버뷰(.ovr) 파일을 만듦. 원본 파일 내용은 바꾸지 않음."""
    import rasterio
    from rasterio.enums import Resampling

    with _open(path) as src:
        size = max(src.width, src.height)
        categorical = src.dtypes[0] in ("uint8", "int8") and src.count == 1
    factors = []
    f = 2
    while size / f >= TILE_SIZE / 2:  # 가장 작은 단계가 타일 절반 크기가 될 때까지
        factors.append(f)
        f *= 2
    if not factors:
        return []
    try:
        # TIFF_USE_OVR: 원본 GeoTIFF 안이 아니라 옆의 .ovr 파일에 오버뷰를 씀
        with (
            rasterio.Env(TIFF_USE_OVR=True, COMPRESS_OVERVIEW="DEFLATE"),
            rasterio.open(path, "r+") as src,
        ):
            src.build_overviews(factors, Resampling.nearest if categorical else Resampling.average)
    except Exception as exc:
        raise EngineError(
            "overview_failed", f"오버뷰를 만들지 못함 (폴더 쓰기 권한 확인): {exc}"
        ) from exc
    return factors


# ---- 타일 -----------------------------------------------------------------------


def tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """XYZ 타일의 웹 메르카토르 범위 (서, 남, 동, 북)."""
    span = 2 * _ORIGIN / (1 << z)
    west = -_ORIGIN + x * span
    north = _ORIGIN - y * span
    return west, north - span, west + span, north


def _overview_level(factors: list[int], src_res_m: float, tile_res_m: float) -> int | None:
    """타일 해상도보다 거칠지 않은 오버뷰 중 가장 작은 것(배율이 가장 큰 것)의 단계 번호. 없으면 원본."""
    best = None
    for i, f in enumerate(factors):
        if src_res_m * f <= tile_res_m:
            best = i
    return best


def render_tile(
    path: Path,
    info: dict[str, Any],
    z: int,
    x: int,
    y: int,
    *,
    bands: list[int],
    vmin: list[float],
    vmax: list[float],
    colormap: str = "viridis",
    resampling: str = "bilinear",
) -> bytes | None:
    """타일 하나를 PNG로 만듦. 래스터와 겹치지 않으면 None."""
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.vrt import WarpedVRT
    from rasterio.warp import transform_bounds

    west, south, east, north = tile_bounds(z, x, y)
    rw, rs, re_, rn = info["bounds_wgs84"]
    tb = transform_bounds("EPSG:3857", "EPSG:4326", west, south, east, north)
    if tb[0] >= re_ or tb[2] <= rw or tb[1] >= rn or tb[3] <= rs:
        return None

    # 원본 해상도를 대략 미터로 환산해 오버뷰 단계를 고름
    src_res = info["res"][0]
    if info["crs"] == "EPSG:4326" or src_res < 0.1:  # 경위도 단위
        src_res *= 111_320 * math.cos(math.radians((rs + rn) / 2))
    tile_res = (east - west) / TILE_SIZE * math.cos(math.radians((tb[1] + tb[3]) / 2))
    level = _overview_level(info["overviews"], src_res, tile_res)
    open_kwargs = {} if level is None else {"overview_level": level}

    rs_method = Resampling.nearest if resampling == "nearest" else Resampling.bilinear
    transform = from_bounds(west, south, east, north, TILE_SIZE, TILE_SIZE)
    with (
        _open(path, **open_kwargs) as src,
        WarpedVRT(
            src,
            crs="EPSG:3857",
            transform=transform,
            width=TILE_SIZE,
            height=TILE_SIZE,
            resampling=rs_method,
            add_alpha=src.nodata is None and not _has_mask(src),
        ) as vrt,
    ):
        data = vrt.read(bands).astype("float64")
        mask = vrt.dataset_mask() > 0
    for b, _ in enumerate(bands):
        mask &= np.isfinite(data[b])
        if info.get("nodata") is not None:
            mask &= data[b] != info["nodata"]
    if not mask.any():
        return None

    rgba = np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8)
    if len(bands) >= 3:
        for c in range(3):
            rgba[..., c] = _scale(data[c], vmin[c], vmax[c])
    else:
        lut = colormap_lut(colormap)
        rgba[..., :3] = lut[_scale(data[0], vmin[0], vmax[0])]
    rgba[..., 3] = np.where(mask, 255, 0)
    return encode_png(rgba)


def _has_mask(src) -> bool:
    from rasterio.enums import MaskFlags

    return any(MaskFlags.per_dataset in f or MaskFlags.alpha in f for f in src.mask_flag_enums)


def _scale(band: np.ndarray, lo: float, hi: float) -> np.ndarray:
    if hi <= lo:
        hi = lo + 1e-12
    out = (band - lo) / (hi - lo)
    return np.clip(np.nan_to_num(out, nan=0.0) * 255, 0, 255).astype(np.uint8)


# ---- 색상표 ---------------------------------------------------------------------
# matplotlib 없이 쓰려고 대표 색만 적어 두고 선형 보간해 256단계를 만듦

_COLORMAPS: dict[str, list[str]] = {
    "viridis": [
        "#440154",
        "#482878",
        "#3e4989",
        "#31688e",
        "#26828e",
        "#1f9e89",
        "#35b779",
        "#6ece58",
        "#b5de2b",
        "#fde725",
    ],
    "magma": [
        "#000004",
        "#180f3d",
        "#440f76",
        "#721f81",
        "#9e2f7f",
        "#cd4071",
        "#f1605d",
        "#fd9668",
        "#feca8d",
        "#fcfdbf",
    ],
    "terrain": [
        "#333399",
        "#0294fa",
        "#00c966",
        "#80e680",
        "#fffe99",
        "#bfa76f",
        "#805c54",
        "#bfaeaa",
        "#ffffff",
    ],
    "gray": ["#000000", "#ffffff"],
    "rdylgn": [
        "#a50026",
        "#d73027",
        "#f46d43",
        "#fdae61",
        "#fee08b",
        "#d9ef8b",
        "#a6d96a",
        "#66bd63",
        "#1a9850",
        "#006837",
    ],
    "spectral": [
        "#9e0142",
        "#d53e4f",
        "#f46d43",
        "#fdae61",
        "#fee08b",
        "#e6f598",
        "#abdda4",
        "#66c2a5",
        "#3288bd",
        "#5e4fa2",
    ],
    "blues": [
        "#f7fbff",
        "#deebf7",
        "#c6dbef",
        "#9ecae1",
        "#6baed6",
        "#4292c6",
        "#2171b5",
        "#08519c",
        "#08306b",
    ],
    "rdbu_r": [
        "#053061",
        "#2166ac",
        "#4393c3",
        "#92c5de",
        "#d1e5f0",
        "#fddbc7",
        "#f4a582",
        "#d6604d",
        "#b2182b",
        "#67001f",
    ],
}
COLORMAPS = tuple(_COLORMAPS)
_LUT_CACHE: dict[str, np.ndarray] = {}


def colormap_lut(name: str) -> np.ndarray:
    if name not in _COLORMAPS:
        raise EngineError("invalid_colormap", f"알 수 없는 색상표: {name}")
    if name not in _LUT_CACHE:
        stops = np.array(
            [[int(h[i : i + 2], 16) for i in (1, 3, 5)] for h in _COLORMAPS[name]], float
        )
        pos = np.linspace(0, 1, len(stops))
        t = np.linspace(0, 1, 256)
        _LUT_CACHE[name] = (
            np.stack([np.interp(t, pos, stops[:, c]) for c in range(3)], axis=1)
            .round()
            .astype(np.uint8)
        )
    return _LUT_CACHE[name]


def encode_png(rgba: np.ndarray) -> bytes:
    """RGBA 배열(높이×폭×4, uint8)을 PNG 바이트로 만듦."""
    h, w, _ = rgba.shape
    raw = np.zeros((h, w * 4 + 1), dtype=np.uint8)  # 각 줄 앞에 필터 종류(0) 1바이트
    raw[:, 1:] = rgba.reshape(h, w * 4)

    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))

    header = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw.tobytes(), 6))
        + chunk(b"IEND", b"")
    )
