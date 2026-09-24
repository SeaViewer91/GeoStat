"""주제도 단계 구분 (GeoDa 지도 유형과 같은 7종).

mapclassify로 계급 경계를 구하고, 피처별 계급 번호와 범례용 라벨을 만듦.
값이 없는 피처(NaN)의 계급 번호는 -1임.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from geostat_engine.errors import EngineError

with warnings.catch_warnings():
    # numba가 없으면 FisherJenks가 순수 파이썬으로 동작한다는 경고임. 표본 추출로 속도를 맞추므로 무시함
    warnings.simplefilter("ignore")
    import mapclassify as mc

Method = Literal[
    "quantile",
    "equal_interval",
    "natural_breaks",
    "std_mean",
    "percentile",
    "box_plot",
    "unique_values",
    "lisa_cluster",
    "gi_cluster",
    "geary_cluster",
    "significance",
]
SchemeType = Literal["sequential", "diverging", "qualitative"]

# Fisher-Jenks는 O(k·n²)라 이 개수를 넘으면 표본으로 경계를 구함
_JENKS_MAX_SAMPLE = 3000
# 고유값 지도에서 개별 색을 줄 최대 범주 수. 나머지는 "기타"로 묶음
_UNIQUE_MAX = 12


@dataclass
class Classification:
    method: str
    column: str
    scheme: SchemeType
    breaks: list[float]  # 계급별 상한값 (고유값 지도는 빈 목록)
    labels: list[str]
    counts: list[int]
    classes: np.ndarray  # int16, 피처별 계급 번호 (-1 = 값 없음)
    n_missing: int
    colors: list[str] | None = None  # 고정 색 (군집·유의성 지도). None이면 앱이 색상표로 칠함


def _fmt(v: float) -> str:
    if not np.isfinite(v):
        return str(v)
    a = abs(v)
    if a != 0 and (a >= 1e7 or a < 1e-3):
        return f"{v:.3g}"
    if float(v).is_integer():
        return f"{int(v):,}"
    return f"{v:,.4g}" if a < 1000 else f"{v:,.1f}"


def _range_labels(lower: float, bins: np.ndarray) -> list[str]:
    edges = [lower, *bins.tolist()]
    return [f"{_fmt(edges[i])} – {_fmt(edges[i + 1])}" for i in range(len(bins))]


def classify(series: pd.Series, method: Method, k: int = 5) -> Classification:
    name = str(series.name)
    if method == "unique_values":
        return _unique(series, name)
    if method in _CODE_MAPS:
        return _code_map(series, name, method)
    if method == "significance":
        return _significance(series, name)

    if not pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
        raise EngineError("not_numeric", f"숫자 열이 아님: {name}")
    values = series.to_numpy(dtype="float64", na_value=np.nan)
    valid = np.isfinite(values)
    y = values[valid]
    if y.size == 0:
        raise EngineError("no_values", f"값이 있는 행이 없음: {name}")
    if not 2 <= k <= 12:
        raise EngineError("invalid_k", "계급 수는 2~12 사이여야 함")

    scheme: SchemeType = "sequential"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # 동일 값이 많을 때 계급 수가 줄었다는 경고 등
        if method == "quantile":
            c = mc.Quantiles(y, k=k)
            labels = _range_labels(y.min(), c.bins)
        elif method == "equal_interval":
            c = mc.EqualInterval(y, k=k)
            labels = _range_labels(y.min(), c.bins)
        elif method == "natural_breaks":
            if y.size > _JENKS_MAX_SAMPLE:
                c = mc.FisherJenksSampled(y, k=k, pct=_JENKS_MAX_SAMPLE / y.size)
            else:
                c = mc.FisherJenks(y, k=k)
            labels = _range_labels(y.min(), c.bins)
        elif method in _FIXED_SCHEMES:
            # 계급 수가 고정된 GeoDa 지도 유형. mapclassify는 빈 계급을 없애 라벨과 어긋나므로 직접 계산함
            return _fixed_scheme(method, name, values, valid, y)
        else:
            raise EngineError("invalid_method", f"알 수 없는 분류 방법: {method}")

    classes = np.full(values.size, -1, dtype=np.int16)
    classes[valid] = c.yb
    n = len(c.bins)
    counts = np.bincount(c.yb, minlength=n)[:n]
    return Classification(
        method=method,
        column=name,
        scheme=scheme,
        breaks=[float(b) for b in c.bins],
        labels=labels[:n],
        counts=[int(v) for v in counts],
        classes=classes,
        n_missing=int((~valid).sum()),
    )


_FIXED_SCHEMES = {
    "std_mean": ["< -2σ", "-2σ ~ -1σ", "-1σ ~ 평균", "평균 ~ +1σ", "+1σ ~ +2σ", "> +2σ"],
    "percentile": ["< 1%", "1% ~ 10%", "10% ~ 50%", "50% ~ 90%", "90% ~ 99%", "> 99%"],
    "box_plot": ["하위 이상치", "< 25%", "25% ~ 50%", "50% ~ 75%", "> 75%", "상위 이상치"],
}


def _fixed_scheme(
    method: str, name: str, values: np.ndarray, valid: np.ndarray, y: np.ndarray
) -> Classification:
    """표준편차·백분위·박스 지도. 항상 6계급이며 비어 있는 계급도 유지함."""
    if method == "std_mean":
        edges = y.mean() + np.array([-2, -1, 0, 1, 2]) * y.std(ddof=1 if y.size > 1 else 0)
        yb = np.searchsorted(edges, y, side="right")
    elif method == "percentile":
        edges = np.percentile(y, [1, 10, 50, 90, 99])
        yb = np.searchsorted(edges, y, side="right")
    else:  # box_plot: 사분위수와 1.5×IQR 울타리 기준
        q1, q2, q3 = np.percentile(y, [25, 50, 75])
        iqr = q3 - q1
        edges = np.array([q1 - 1.5 * iqr, q1, q2, q3, q3 + 1.5 * iqr])
        yb = np.searchsorted(edges[:4], y, side="right")
        yb[y > edges[4]] = 5
    classes = np.full(values.size, -1, dtype=np.int16)
    classes[valid] = yb
    return Classification(
        method=method,
        column=name,
        scheme="diverging",
        breaks=[float(e) for e in edges],
        labels=_FIXED_SCHEMES[method],
        counts=[int(v) for v in np.bincount(yb, minlength=6)],
        classes=classes,
        n_missing=int((~valid).sum()),
    )


# 군집 지도: 저장된 군집 코드 → (라벨, 색). 색은 GeoDa 관례를 따름
_CODE_MAPS: dict[str, list[tuple[int, str, str]]] = {
    "lisa_cluster": [
        (0, "유의하지 않음", "#eeeeee"),
        (1, "High-High", "#ff0000"),
        (2, "Low-Low", "#0000ff"),
        (3, "Low-High", "#a7adf9"),
        (4, "High-Low", "#f4ada8"),
        (5, "이웃 없음", "#464646"),
    ],
    "gi_cluster": [
        (0, "유의하지 않음", "#eeeeee"),
        (1, "핫스팟 (High)", "#ff0000"),
        (2, "콜드스팟 (Low)", "#0000ff"),
        (5, "이웃 없음", "#464646"),
    ],
    "geary_cluster": [
        (0, "유의하지 않음", "#eeeeee"),
        (1, "High-High", "#b2182b"),
        (2, "Low-Low", "#ef8a62"),
        (3, "기타 양(+)의 연관", "#fddbc7"),
        (4, "음(-)의 연관", "#67adc7"),
        (5, "이웃 없음", "#464646"),
    ],
}

# 유의성 지도: p값 구간 (GeoDa와 같은 경계)
_SIG_LEVELS = [
    (0.0001, "p ≤ 0.0001", "#1a9641"),
    (0.001, "p ≤ 0.001", "#3ca94f"),
    (0.01, "p ≤ 0.01", "#76c35b"),
    (0.05, "p ≤ 0.05", "#a6d96a"),
]


def _code_map(series: pd.Series, name: str, method: str) -> Classification:
    entries = _CODE_MAPS[method]
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype="float64", na_value=np.nan)
    lookup = {code: i for i, (code, _l, _c) in enumerate(entries)}
    classes = np.full(values.size, -1, dtype=np.int16)
    for code, idx in lookup.items():
        classes[values == code] = idx
    counts = np.bincount(classes[classes >= 0], minlength=len(entries))
    return Classification(
        method=method,
        column=name,
        scheme="qualitative",
        breaks=[],
        labels=[label for _c, label, _col in entries],
        counts=[int(c) for c in counts],
        classes=classes,
        n_missing=int((classes < 0).sum()),
        colors=[color for _c, _l, color in entries],
    )


def _significance(series: pd.Series, name: str) -> Classification:
    p = pd.to_numeric(series, errors="coerce").to_numpy(dtype="float64", na_value=np.nan)
    if np.nanmax(p, initial=0) > 1 or np.nanmin(p, initial=0) < 0:
        raise EngineError("not_pvalue", f"p값(0~1) 열이 아님: {name}")
    classes = np.full(p.size, -1, dtype=np.int16)
    valid = ~np.isnan(p)
    classes[valid] = len(_SIG_LEVELS)  # 유의하지 않음
    # 큰 기준부터 덮어써서 가장 작은 구간이 남게 함
    for i in range(len(_SIG_LEVELS) - 1, -1, -1):
        classes[valid & (p <= _SIG_LEVELS[i][0])] = i
    labels = [label for _t, label, _c in _SIG_LEVELS] + ["유의하지 않음"]
    colors = [c for _t, _l, c in _SIG_LEVELS] + ["#eeeeee"]
    counts = np.bincount(classes[classes >= 0], minlength=len(labels))
    return Classification(
        method="significance",
        column=name,
        scheme="qualitative",
        breaks=[t for t, _l, _c in _SIG_LEVELS],
        labels=labels,
        counts=[int(c) for c in counts],
        classes=classes,
        n_missing=int((~valid).sum()),
        colors=colors,
    )


def _unique(series: pd.Series, name: str) -> Classification:
    missing = series.isna().to_numpy()
    counts = series[~missing].astype(str).value_counts()
    top = counts.index[:_UNIQUE_MAX].tolist()
    lookup = {v: i for i, v in enumerate(top)}
    other = len(top)
    as_str = series.astype(str).to_numpy()
    classes = np.array(
        [-1 if m else lookup.get(v, other) for v, m in zip(as_str, missing, strict=True)],
        dtype=np.int16,
    )
    labels = [str(v) for v in top]
    class_counts = [int(counts[v]) for v in top]
    if len(counts) > _UNIQUE_MAX:
        labels.append(f"기타 ({len(counts) - _UNIQUE_MAX}개 범주)")
        class_counts.append(int(counts.iloc[_UNIQUE_MAX:].sum()))
    return Classification(
        method="unique_values",
        column=name,
        scheme="qualitative",
        breaks=[],
        labels=labels,
        counts=class_counts,
        classes=classes,
        n_missing=int(missing.sum()),
    )
