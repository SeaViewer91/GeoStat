"""시공간 분석.

자료 형태 세 가지를 모두 "넓은 형태(피처 하나에 기간별 열)"로 맞춘 뒤 시간 변수 묶음으로 다룸.
- 넓은 형태: 값_2022, 값_2023 … 열을 시간 변수 묶음으로 지정함
- 긴 형태: (ID, 기간, 값) 행이 반복되는 자료를 ID 기준으로 넓은 형태로 바꿈 (pivot)
- 기간별 파일: 2022.shp, 2023.shp …를 공통 ID로 이어 붙임 (merge)

분석
- 기간별 전역 Moran's I 추이
- 기간별 LISA와 군집 전이표 (앞 기간 → 다음 기간으로 군집이 어떻게 바뀌었는지)
- 차분 Moran·차분 LISA는 esda_ops에 두 열의 차(column − column_base)를 넘겨 계산함
"""

from __future__ import annotations

import re
from itertools import pairwise
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from geostat_engine.errors import EngineError

# LISA 군집 코드 (esda_ops와 같음)
LISA_LABELS = ["유의하지 않음", "High-High", "Low-Low", "Low-High", "High-Low", "이웃 없음"]


def _numeric(series: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)


def _label(value: Any) -> str:
    """기간 값을 열 이름에 붙일 문자열로 바꿈 (2023.0 → 2023, 날짜는 YYYY-MM-DD)."""
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        ts = pd.Timestamp(value)
        return ts.strftime("%Y-%m-%d") if ts == ts.normalize() else ts.strftime("%Y-%m-%dT%H%M")
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = re.sub(r"[^\w\-]+", "_", str(value)).strip("_")
    return text or "NA"


def check_group(gdf: gpd.GeoDataFrame, group: dict[str, Any]) -> dict[str, Any]:
    """시간 변수 묶음 검사: 이름, 2개 이상의 숫자 열, 기간 이름 개수가 맞는지."""
    name = str(group.get("name", "")).strip()
    columns = [str(c) for c in group.get("columns", [])]
    labels = [str(v).strip() for v in group.get("labels", [])] or columns
    if not name:
        raise EngineError("invalid_group", "시간 변수 묶음 이름이 필요함")
    if len(columns) < 2:
        raise EngineError("invalid_group", f"'{name}': 기간이 2개 이상이어야 함")
    if len(labels) != len(columns):
        raise EngineError("invalid_group", f"'{name}': 기간 이름 수가 열 수와 다름")
    if len(set(columns)) != len(columns) or len(set(labels)) != len(labels):
        raise EngineError("invalid_group", f"'{name}': 같은 열이나 기간 이름이 두 번 들어감")
    for c in columns:
        if c not in gdf.columns:
            raise EngineError("column_not_found", f"열이 없음: {c}")
        if not _numeric(gdf[c]):
            raise EngineError("not_numeric", f"숫자 열이 아님: {c}")
    return {"name": name, "columns": columns, "labels": labels}


def guess_groups(columns: list[str]) -> list[dict[str, Any]]:
    """'값_2022, 값_2023'처럼 끝에 기간이 붙은 열을 찾아 시간 변수 묶음 후보를 만듦."""
    pattern = re.compile(r"^(.*?)[_\-. ]?((?:19|20)\d{2}(?:[_\-.]?\d{1,2})?)$")
    found: dict[str, list[tuple[str, str]]] = {}
    for c in columns:
        m = pattern.match(c)
        if m and m.group(1):
            found.setdefault(m.group(1), []).append((m.group(2), c))
    out = []
    for stem, items in found.items():
        if len(items) >= 2:
            items.sort()
            out.append(
                {"name": stem, "columns": [c for _, c in items], "labels": [lb for lb, _ in items]}
            )
    return out


# ---- 긴 형태 → 넓은 형태 ------------------------------------------------------------


def pivot_long(
    gdf: gpd.GeoDataFrame, id_column: str, time_column: str, value_columns: list[str]
) -> tuple[gpd.GeoDataFrame, list[dict[str, Any]], list[str]]:
    """(ID, 기간, 값…) 행을 ID당 한 행으로 바꿈. 지오메트리는 ID의 첫 행 것을 씀."""
    for c in (id_column, time_column, *value_columns):
        if c not in gdf.columns:
            raise EngineError("column_not_found", f"열이 없음: {c}")
    if not value_columns:
        raise EngineError("nothing_to_do", "값 열을 하나 이상 골라야 함")
    for c in value_columns:
        if not _numeric(gdf[c]):
            raise EngineError("not_numeric", f"숫자 열이 아님: {c}")
    notes: list[str] = []
    frame = pd.DataFrame(gdf.drop(columns=gdf.geometry.name))
    if frame[time_column].isna().any():
        raise EngineError("missing_values", f"기간 열('{time_column}')에 값 없는 행이 있음")
    dup = frame.duplicated([id_column, time_column])
    if dup.any():
        notes.append(f"같은 ID·기간 행이 {int(dup.sum())}개 더 있어 평균으로 합침")
    periods = sorted(frame[time_column].unique())
    labels = [_label(p) for p in periods]
    if len(periods) < 2:
        raise EngineError("too_few", "기간이 2개 이상이어야 함")
    if len(set(labels)) != len(labels):
        raise EngineError(
            "invalid_time", "기간 값을 열 이름으로 바꾸면 겹침. 기간 열을 확인해야 함"
        )

    wide = frame.pivot_table(
        index=id_column, columns=time_column, values=value_columns, aggfunc="mean", dropna=False
    )
    geoms = gdf.groupby(id_column, sort=True)[gdf.geometry.name].first()
    out = pd.DataFrame(index=geoms.index)
    groups = []
    for var in value_columns:
        cols = []
        for period, label in zip(periods, labels, strict=True):
            name = f"{var}_{label}"
            out[name] = wide[(var, period)] if (var, period) in wide.columns else np.nan
            cols.append(name)
        groups.append({"name": var, "columns": cols, "labels": labels})
    missing = int(out.isna().sum().sum())
    if missing:
        notes.append(f"관측이 없는 ID·기간 칸 {missing}개는 값 없음으로 둠")
    out = out.reset_index()
    result = gpd.GeoDataFrame(out, geometry=geoms.to_numpy(), crs=gdf.crs)
    return result, groups, notes


# ---- 기간별 파일 이어 붙이기 ----------------------------------------------------------


def merge_periods(
    parts: list[tuple[gpd.GeoDataFrame, str, str]], value_columns: list[str]
) -> tuple[gpd.GeoDataFrame, list[dict[str, Any]], list[str]]:
    """parts: [(자료, ID 열, 기간 이름), …]. 첫 자료의 지오메트리를 기준으로 공통 ID에 값을 붙임."""
    if len(parts) < 2:
        raise EngineError("too_few", "기간별 자료가 2개 이상이어야 함")
    labels = [_label(lb) for _, _, lb in parts]
    if len(set(labels)) != len(labels):
        raise EngineError("invalid_time", "기간 이름이 겹침")
    if not value_columns:
        raise EngineError("nothing_to_do", "값 열을 하나 이상 골라야 함")
    base, base_id, _ = parts[0]
    if base[base_id].duplicated().any():
        raise EngineError("duplicate_id", f"기준 자료의 ID 열('{base_id}')에 중복 값이 있음")
    notes: list[str] = []
    out = gpd.GeoDataFrame(
        {"ID": base[base_id].to_numpy()}, geometry=base.geometry.to_numpy(), crs=base.crs
    )
    key = pd.Index(base[base_id].astype(str).to_numpy())
    groups = {var: {"name": var, "columns": [], "labels": labels} for var in value_columns}
    for (gdf, id_col, _), label in zip(parts, labels, strict=True):
        if id_col not in gdf.columns:
            raise EngineError("column_not_found", f"ID 열이 없음: {id_col}")
        ids = gdf[id_col].astype(str)
        if ids.duplicated().any():
            notes.append(f"{label}: ID가 중복된 행 {int(ids.duplicated().sum())}개는 첫 행만 씀")
        frame = pd.DataFrame(gdf.drop(columns=gdf.geometry.name))
        frame.index = ids.to_numpy()
        frame = frame[~frame.index.duplicated(keep="first")]
        unmatched = int((~key.isin(frame.index)).sum())
        if unmatched:
            notes.append(f"{label}: 기준 자료의 ID {unmatched}개가 없어 값 없음으로 둠")
        for var in value_columns:
            if var not in frame.columns:
                raise EngineError("column_not_found", f"{label} 자료에 열이 없음: {var}")
            if not _numeric(frame[var]):
                raise EngineError("not_numeric", f"{label} 자료의 '{var}'가 숫자 열이 아님")
            name = f"{var}_{label}"
            out[name] = frame[var].reindex(key).to_numpy(dtype="float64", na_value=np.nan)
            groups[var]["columns"].append(name)
    return out, list(groups.values()), notes


# ---- 기간별 LISA 군집 전이 ------------------------------------------------------------


def transitions(clusters: list[np.ndarray], labels: list[str]) -> dict[str, Any]:
    """기간별 LISA 군집 코드로 기간별 개수와 전이표(앞 → 뒤, 모든 인접 기간 합)를 만듦."""
    k = len(LISA_LABELS)
    counts = [np.bincount(np.asarray(c, dtype=int), minlength=k)[:k].tolist() for c in clusters]
    matrix = np.zeros((k, k), dtype=int)
    for a, b in pairwise(clusters):
        np.add.at(matrix, (np.asarray(a, dtype=int), np.asarray(b, dtype=int)), 1)
    stacked = np.vstack(clusters)
    changes = (np.diff(stacked, axis=0) != 0).sum(axis=0)
    always_sig = (stacked != 0).all(axis=0) & (stacked == stacked[0]).all(axis=0)
    return {
        "kind": "lisa_time",
        "labels": labels,
        "categories": LISA_LABELS,
        "counts": counts,
        "matrix": matrix.tolist(),
        "n_changed": int((changes > 0).sum()),
        "n_stable_cluster": int(always_sig.sum()),
        "changes": changes.astype("int16"),
    }
