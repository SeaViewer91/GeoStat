"""비율 지도와 경험적 베이즈(EB) 보정 (GeoDa의 Rates 메뉴와 같은 방법).

분자(사건 수)와 분모(모집단·노력량)로 비율을 구함. 분모가 작은 지역의 비율은 우연에 크게 흔들리므로
전체(EB) 또는 이웃(공간 EB) 평균 쪽으로 당겨 안정화함. CPUE, 발생률, 밀도처럼 분모가 있는 값에 씀.

- raw          : 원비율 e / b
- excess_risk  : 초과위험 = 관측 사건 수 / 기대 사건 수 (기대 = b × 전체 비율). 1보다 크면 평균보다 높음
- eb           : 경험적 베이즈 평활 (전체 평균 쪽으로)
- spatial_rate : 공간 비율 = (자신 + 이웃 사건 합) / (자신 + 이웃 분모 합)
- spatial_eb   : 공간 경험적 베이즈 평활 (이웃 평균 쪽으로)
"""

from __future__ import annotations

import copy
import warnings
from typing import Any, Literal

import numpy as np
import pandas as pd

from geostat_engine.errors import EngineError

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from esda import smoothing

RateMethod = Literal["raw", "excess_risk", "eb", "spatial_rate", "spatial_eb"]

LABELS: dict[str, str] = {
    "raw": "원비율",
    "excess_risk": "초과위험",
    "eb": "경험적 베이즈 평활",
    "spatial_rate": "공간 비율",
    "spatial_eb": "공간 경험적 베이즈 평활",
}
DEFAULT_NAME: dict[str, str] = {
    "raw": "R_RAW",
    "excess_risk": "R_EXCESS",
    "eb": "R_EB",
    "spatial_rate": "R_SPATIAL",
    "spatial_eb": "R_SEB",
}
NEEDS_WEIGHTS = {"spatial_rate", "spatial_eb"}


def _array(series: pd.Series, name: str) -> np.ndarray:
    if not pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
        raise EngineError("not_numeric", f"숫자 열이 아님: {name}")
    values = series.to_numpy(dtype="float64", na_value=np.nan)
    if np.isnan(values).any():
        raise EngineError(
            "missing_values", f"'{name}'에 값 없는 행이 {int(np.isnan(values).sum())}개 있음"
        )
    return values


def check_inputs(event: pd.Series, base: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    e = _array(event, str(event.name))
    b = _array(base, str(base.name))
    if (e < 0).any():
        raise EngineError("negative_event", f"분자('{event.name}')에 음수가 있음")
    if (b <= 0).any():
        raise EngineError(
            "nonpositive_base",
            f"분모('{base.name}')가 0 이하인 행이 {int((b <= 0).sum())}개 있음. 비율을 구할 수 없음",
        )
    return e, b


def compute(
    method: RateMethod,
    event: pd.Series,
    base: pd.Series,
    w: Any | None = None,
    multiplier: float = 1.0,
) -> np.ndarray:
    """비율을 계산함. 초과위험을 뺀 나머지는 multiplier(예: 1,000명당)를 곱함."""
    if method not in LABELS:
        raise EngineError("invalid_method", f"알 수 없는 비율 방법: {method}")
    e, b = check_inputs(event, base)
    if method in NEEDS_WEIGHTS and w is None:
        raise EngineError("weights_required", f"{LABELS[method]}은 공간가중치가 필요함")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if method == "raw":
                r = e / b
            elif method == "excess_risk":
                return np.asarray(smoothing.Excess_Risk(e, b).r, dtype="float64").ravel()
            elif method == "eb":
                r = smoothing.Empirical_Bayes(e, b).r
            else:
                w2 = copy.deepcopy(w)  # esda가 w.transform을 바꾸므로 원본을 지킴
                if not w2.id_order_set:
                    # 가중치 ID는 행 순서(0..n-1)이므로 그 순서를 명시함 (esda 공간 비율이 요구함)
                    w2.id_order = sorted(w2.neighbors)
                if method == "spatial_rate":
                    r = smoothing.Spatial_Rate(e, b, w2).r
                else:
                    r = smoothing.Spatial_Empirical_Bayes(e, b, w2).r
    except EngineError:
        raise
    except Exception as exc:  # esda 내부 오류는 사용자에게 보여줄 수 있는 오류로 바꿈
        raise EngineError(
            "analysis_failed", f"{LABELS[method]} 계산 실패: {type(exc).__name__}: {exc}"
        ) from exc
    return np.asarray(r, dtype="float64").ravel() * float(multiplier)
