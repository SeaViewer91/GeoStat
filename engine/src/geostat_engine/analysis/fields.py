"""계산 필드 (속성 테이블에 식으로 새 변수 추가).

pandas eval 문법을 씀. 한글이나 공백이 있는 열 이름은 백틱으로 감쌈.
    `인구` / `면적` * 1000
    log(`소득`)          ← sin, cos, exp, log, sqrt, abs 등 수학 함수 사용 가능
    (`인구` > 5000) * 1   ← 조건식은 0/1 변수로 만들 수 있음
"""

from __future__ import annotations

import re

import geopandas as gpd
import numpy as np
import pandas as pd

from geostat_engine.errors import EngineError

_MAX_NAME_LEN = 64
# 속성 접근·import 등을 막아 식이 계산 이외의 일을 하지 못하게 함
_FORBIDDEN = re.compile(r"__|\bimport\b|\blambda\b|@")


def validate_name(gdf: gpd.GeoDataFrame, name: str, derived: set[str]) -> str:
    name = name.strip()
    if not name:
        raise EngineError("invalid_name", "변수 이름이 비었음")
    if len(name) > _MAX_NAME_LEN:
        raise EngineError("invalid_name", f"변수 이름은 {_MAX_NAME_LEN}자 이하여야 함")
    if name == gdf.geometry.name:
        raise EngineError("invalid_name", "지오메트리 열 이름은 쓸 수 없음")
    if name in gdf.columns and name not in derived:
        raise EngineError("name_exists", f"원본 데이터에 이미 있는 열 이름임: {name}")
    return name


def evaluate(gdf: gpd.GeoDataFrame, expression: str) -> pd.Series:
    expression = expression.strip()
    if not expression:
        raise EngineError("invalid_expression", "식이 비었음")
    if _FORBIDDEN.search(expression):
        raise EngineError("invalid_expression", "식에 쓸 수 없는 구문이 있음")
    frame = pd.DataFrame(gdf.drop(columns=gdf.geometry.name))
    try:
        result = frame.eval(expression, engine="python")
    except Exception as exc:
        raise EngineError("invalid_expression", f"식을 계산하지 못함: {exc}") from exc

    if np.isscalar(result):
        result = pd.Series(result, index=frame.index)
    if not isinstance(result, pd.Series) or len(result) != len(frame):
        raise EngineError("invalid_expression", "식의 결과가 행마다 값 하나인 열이 아님")
    if pd.api.types.is_bool_dtype(result):
        result = result.astype("int8")  # 조건식은 0/1로 저장함 (shapefile 호환)
    if pd.api.types.is_float_dtype(result):
        result = result.replace([np.inf, -np.inf], np.nan)
    return result
