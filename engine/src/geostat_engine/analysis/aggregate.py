"""점 → 폴리곤 집계 (공간 결합).

조사 지점·탐지 결과 같은 점 자료를 격자나 행정구역으로 모아 개수·합계·평균 등을 구함.
집계 결과는 대상(폴리곤) 데이터셋의 열이 되어 LISA·GWR에 바로 쓸 수 있음.

- 두 자료의 좌표계가 다르면 원본(점)을 대상 좌표계로 바꿔 계산함
- 점이 아닌 원본(선·폴리곤)은 대표점(representative point)으로 바꿔 셈
- 폴리곤 경계 위에 놓인 점은 한 폴리곤에만 셈 (중복 집계 방지)
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from typing import Any, Literal

import geopandas as gpd
import numpy as np
import pandas as pd

from geostat_engine.errors import EngineError

Stat = Literal["sum", "mean", "min", "max", "median", "std"]

# 통계 이름 → (열 이름 약어, 보고용 한글 이름)
STATS: dict[str, tuple[str, str]] = {
    "sum": ("SUM", "합계"),
    "mean": ("MEAN", "평균"),
    "min": ("MIN", "최솟값"),
    "max": ("MAX", "최댓값"),
    "median": ("MED", "중앙값"),
    "std": ("STD", "표준편차"),
}


@dataclass
class AggregateResult:
    columns: dict[str, np.ndarray]  # 열 이름 접미사 → 값
    n_source: int  # 원본 피처 수
    n_matched: int  # 대상 폴리곤 안에 든 원본 피처 수
    n_empty: int  # 점이 하나도 없는 폴리곤 수
    notes: list[str]


def _safe(name: str) -> str:
    """열 이름에 쓸 수 없는 문자를 밑줄로 바꿈 (한글은 그대로 둠)."""
    return re.sub(r"[^\w]+", "_", name).strip("_") or "VAL"


def aggregate(
    target: gpd.GeoDataFrame,
    source: gpd.GeoDataFrame,
    stats: list[dict[str, str]],
    count: bool = True,
    density: bool = False,
) -> AggregateResult:
    """source 피처를 target 폴리곤에 모아 통계를 구함.

    stats: [{"column": 원본 열, "stat": sum|mean|min|max|median|std}, ...]
    반환 열 접미사: CNT(개수), DENS(㎢당 개수), <통계>_<열>
    """
    if not count and not density and not stats:
        raise EngineError("nothing_to_do", "집계할 항목을 하나 이상 골라야 함")
    if target.crs is None or source.crs is None:
        raise EngineError("missing_crs", "두 자료 모두 좌표계가 있어야 집계할 수 있음")
    kinds = set(target.geom_type.dropna())
    if not kinds or not kinds <= {"Polygon", "MultiPolygon"}:
        raise EngineError("not_polygon", "집계 대상은 폴리곤 레이어여야 함 (격자·행정구역 등)")
    for spec in stats:
        col, stat = spec.get("column"), spec.get("stat")
        if stat not in STATS:
            raise EngineError("invalid_stat", f"알 수 없는 통계: {stat}")
        if col not in source.columns or col == source.geometry.name:
            raise EngineError("column_not_found", f"원본에 열이 없음: {col}")
        s = source[col]
        if not pd.api.types.is_numeric_dtype(s) or pd.api.types.is_bool_dtype(s):
            raise EngineError("not_numeric", f"숫자 열이 아님: {col}")

    notes: list[str] = []
    geom = source.geometry
    if not set(geom.geom_type.dropna()) <= {"Point"}:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            geom = geom.representative_point()
        notes.append("원본이 점이 아니라 각 피처의 대표점으로 셈")
    if source.crs != target.crs:
        geom = geom.to_crs(target.crs)
        notes.append(f"원본 좌표계를 대상 좌표계({target.crs.name})로 바꿔 계산함")

    valid = geom.notna() & ~geom.is_empty
    pts = gpd.GeoDataFrame(
        {"_src": np.flatnonzero(valid.to_numpy())},
        geometry=geom[valid].reset_index(drop=True),
        crs=target.crs,
    )
    polys = gpd.GeoDataFrame(geometry=target.geometry.reset_index(drop=True), crs=target.crs)
    joined = gpd.sjoin(pts, polys, how="inner", predicate="intersects")
    # 경계 위의 점은 여러 폴리곤과 만나므로 번호가 가장 작은 폴리곤 하나에만 넣음
    joined = joined.sort_values(["_src", "index_right"]).drop_duplicates("_src", keep="first")
    poly_idx = joined["index_right"].to_numpy()
    src_idx = joined["_src"].to_numpy()
    n = len(target)

    out: dict[str, np.ndarray] = {}
    counts = np.bincount(poly_idx, minlength=n).astype("int64")
    if count:
        out["CNT"] = counts
    if density:
        area = _area_km2(target)
        with np.errstate(divide="ignore", invalid="ignore"):
            out["DENS"] = np.where(area > 0, counts / area, np.nan)
    if stats:
        frame = pd.DataFrame({"_poly": poly_idx})
        for spec in stats:
            frame[spec["column"]] = source[spec["column"]].to_numpy(
                dtype="float64", na_value=np.nan
            )[src_idx]
        grouped = frame.groupby("_poly")
        used: set[str] = set()
        for spec in stats:
            col, stat = spec["column"], spec["stat"]
            key = f"{STATS[stat][0]}_{_safe(col)}"
            if key in used:
                continue
            used.add(key)
            series = getattr(grouped[col], stat)()
            values = np.full(n, np.nan)
            values[series.index.to_numpy()] = series.to_numpy()
            if stat == "sum":
                values[counts == 0] = 0.0  # 점이 없는 곳의 합계는 0
            out[key] = values

    n_matched = len(src_idx)
    if n_matched < int(valid.sum()):
        notes.append(
            f"대상 폴리곤 밖에 있는 원본 피처 {int(valid.sum()) - n_matched}개는 세지 않음"
        )
    return AggregateResult(
        columns=out,
        n_source=len(source),
        n_matched=n_matched,
        n_empty=int((counts == 0).sum()),
        notes=notes,
    )


def _area_km2(gdf: gpd.GeoDataFrame) -> np.ndarray:
    """폴리곤 면적(㎢). 경위도면 UTM으로 바꿔 계산함."""
    geom = gdf.geometry
    if gdf.crs.is_geographic:
        geom = geom.to_crs(gdf.estimate_utm_crs())
    factor = 1.0
    if geom.crs is not None and geom.crs.axis_info:
        factor = float(geom.crs.axis_info[0].unit_conversion_factor or 1.0)
    return geom.area.to_numpy() * factor * factor / 1e6


def describe(params: dict[str, Any], source_name: str) -> str:
    parts = []
    if params.get("count", True):
        parts.append("개수")
    if params.get("density"):
        parts.append("밀도")
    parts += [f"{s['column']} {STATS[s['stat']][1]}" for s in params.get("stats", [])]
    return f"점 집계: {source_name} → {', '.join(parts)}"
