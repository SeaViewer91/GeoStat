"""공간군집화(지역화)와 비공간 군집화.

공간 제약 군집(spopt): SKATER, Max-p, AZP, Region K-Means, Ward(공간 제약)
비공간 군집(scikit-learn): K-평균, 계층적 군집(Ward) — 공간 제약 결과와 비교하는 용도임

회귀와 같이 prepare()는 엔진 프로세스에서 입력을 검사하고, run()은 작업 프로세스에서 계산함.
군집 번호는 크기가 큰 순서로 1부터 다시 매김 (GeoDa와 같음).
적합도는 군집에 쓴 값(표준화했으면 표준화 값) 기준의 군집 간 제곱합 / 전체 제곱합 비로 봄.
"""

from __future__ import annotations

import random
import sys
import types
import warnings
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from geostat_engine.errors import EngineError

METHODS: tuple[str, ...] = (
    "skater",
    "maxp",
    "azp",
    "region_kmeans",
    "ward_spatial",
    "kmeans",
    "hierarchical",
)
METHOD_LABELS = {
    "skater": "SKATER (공간 제약)",
    "maxp": "Max-p 지역화 (공간 제약)",
    "azp": "AZP (공간 제약)",
    "region_kmeans": "Region K-Means (공간 제약)",
    "ward_spatial": "Ward 계층 군집 (공간 제약)",
    "kmeans": "K-평균 (비공간)",
    "hierarchical": "계층적 군집 Ward (비공간)",
}
DEFAULT_PREFIX = {
    "skater": "SKATER",
    "maxp": "MAXP",
    "azp": "AZP",
    "region_kmeans": "RKM",
    "ward_spatial": "WARDSP",
    "kmeans": "KMEANS",
    "hierarchical": "HCLUST",
}
SPATIAL = ("skater", "maxp", "azp", "region_kmeans", "ward_spatial")
# 이웃 그래프가 여러 조각으로 나뉘어 있으면 동작하지 않는 방법 (조각을 건너 지역을 만들 수 없음)
NEEDS_CONNECTED = ("maxp", "azp", "region_kmeans")
# 결과 열 이름 접미사: <접두어>_GRP
SUFFIX = "GRP"
# 계산이 오래 걸리는 방법의 권장 최대 관측치 수 (넘으면 경고만 함)
SLOW_WARN_N = {"azp": 1000, "region_kmeans": 1000, "maxp": 500, "skater": 5000}

Progress = Callable[[float | None, str], None]


# ---- 준비 (엔진 프로세스) ------------------------------------------------------


def _components(w) -> int:
    from scipy.sparse.csgraph import connected_components

    n, _labels = connected_components(w.sparse, directed=False)
    return int(n)


def prepare(gdf, spec: dict[str, Any], weights: Any | None) -> dict[str, Any]:
    method = spec.get("method")
    if method not in METHODS:
        raise EngineError("invalid_method", f"알 수 없는 군집 방법: {method}")
    cols = list(dict.fromkeys(spec.get("variables") or []))
    if not cols:
        raise EngineError("missing_variables", "군집에 쓸 변수를 하나 이상 골라야 함")
    frame = gdf.drop(columns=gdf.geometry.name)
    data = {}
    for c in cols:
        if c not in frame.columns:
            raise EngineError("column_not_found", f"열이 없음: {c}")
        s = frame[c]
        if not pd.api.types.is_numeric_dtype(s) or pd.api.types.is_bool_dtype(s):
            raise EngineError("not_numeric", f"숫자 열이 아님: {c}")
        data[c] = s.to_numpy(dtype="float64", na_value=np.nan)
    X = np.column_stack([data[c] for c in cols])
    missing = np.isnan(X).any(axis=1)
    if missing.any():
        raise EngineError(
            "missing_values",
            f"선택한 변수에 값 없는 행이 {int(missing.sum())}개 있음. 군집화는 결측을 허용하지 않음",
        )
    n = X.shape[0]
    notes: list[str] = []

    k = int(spec.get("n_clusters") or 5)
    threshold_col = spec.get("threshold_column")
    threshold_values = None
    threshold = None
    if method == "maxp":
        threshold = spec.get("threshold")
        if threshold is None or float(threshold) <= 0:
            raise EngineError("invalid_threshold", "Max-p는 지역별 최소 합계(임계값)가 필요함")
        threshold = float(threshold)
        if threshold_col:
            if threshold_col not in frame.columns:
                raise EngineError("column_not_found", f"열이 없음: {threshold_col}")
            threshold_values = frame[threshold_col].to_numpy(dtype="float64", na_value=np.nan)
            if np.isnan(threshold_values).any() or (threshold_values < 0).any():
                raise EngineError("invalid_threshold", "임계값 열에 결측이나 음수가 있음")
        else:
            threshold_values = np.ones(n)  # 열을 고르지 않으면 피처 수 기준
        if threshold_values.sum() < threshold:
            raise EngineError(
                "invalid_threshold", "전체 합계가 임계값보다 작아 지역을 하나도 만들 수 없음"
            )
    else:
        if not 2 <= k < n:
            raise EngineError("invalid_k", f"군집 수는 2 이상 관측치 수({n}) 미만이어야 함")

    if method in SPATIAL:
        if weights is None:
            raise EngineError("weights_required", "공간 제약 군집은 공간가중치가 필요함")
        n_comp = _components(weights)
        if n_comp > 1:
            if method in NEEDS_CONNECTED:
                raise EngineError(
                    "disconnected",
                    f"이웃 관계가 {n_comp}개 조각으로 나뉘어 있음 (섬 포함). "
                    "KNN 가중치처럼 모두 연결된 가중치를 쓰거나 SKATER·Ward를 써야 함",
                )
            if method == "skater":
                notes.append(
                    f"이웃 관계가 {n_comp}개 조각으로 나뉘어 있어 조각마다 따로 군집이 생김"
                )
            else:
                notes.append(
                    f"이웃 관계가 {n_comp}개 조각으로 나뉘어 있어 일부 군집은 공간적으로 떨어져 있을 수 있음"
                )
    limit = SLOW_WARN_N.get(method)
    if limit and n > limit:
        notes.append(f"관측치가 {n:,}개라 계산이 오래 걸릴 수 있음 (권장 {limit:,}개 이하)")

    return {
        "method": method,
        "variables": cols,
        "X": X,
        "weights": weights,
        "n_clusters": k,
        "standardize": bool(spec.get("standardize", True)),
        "floor": int(spec.get("floor") or 0),
        "threshold": threshold,
        "threshold_values": threshold_values,
        "threshold_column": threshold_col,
        "seed": int(spec.get("seed", 123456789)),
        "notes": notes,
    }


# ---- 계산 (작업 프로세스) --------------------------------------------------------


def _spopt_region():
    """spopt.region을 불러옴.

    spopt는 패키지를 불러올 때 입지 모듈(locate → pointpats → matplotlib)까지 불러옴.
    앱 번들은 용량 때문에 matplotlib을 빼므로, 그때는 쓰지 않는 입지 모듈을 빈 모듈로 막고 다시 불러옴.
    """
    try:
        from spopt import region
    except ModuleNotFoundError as exc:
        if "matplotlib" not in str(exc):
            raise
        for name in [m for m in sys.modules if m == "spopt" or m.startswith("spopt.")]:
            del sys.modules[name]
        sys.modules["spopt.locate"] = types.ModuleType("spopt.locate")
        from spopt import region
    return region


def _solve(payload: dict[str, Any], Z: np.ndarray, progress: Progress) -> np.ndarray:
    method = payload["method"]
    cols = [f"v{j}" for j in range(Z.shape[1])]
    df = pd.DataFrame(Z, columns=cols)
    w = payload["weights"]
    k = payload["n_clusters"]
    seed = payload["seed"]
    np.random.seed(seed)
    random.seed(seed)
    label = METHOD_LABELS[method]
    progress(None, f"{label} 계산 중")

    if method == "kmeans":
        from sklearn.cluster import KMeans

        return KMeans(n_clusters=k, n_init=50, random_state=seed).fit_predict(Z)
    if method == "hierarchical":
        from sklearn.cluster import AgglomerativeClustering

        return AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(Z)

    # spopt는 이웃 여부만 보므로 이진 가중치로 새로 만듦 (원래 가중치의 변환 상태는 건드리지 않음)
    from libpysal.weights import W

    region = _spopt_region()
    AZP, MaxPHeuristic, Skater, WardSpatial = (
        region.AZP,
        region.MaxPHeuristic,
        region.Skater,
        region.WardSpatial,
    )
    RegionKMeansHeuristic = region.RegionKMeansHeuristic

    w = W(w.neighbors, id_order=w.id_order, silence_warnings=True)
    if method == "skater":
        floor = payload["floor"] or 1
        model = Skater(df, w, cols, n_clusters=k, floor=floor, trace=False, islands="increase")
    elif method == "ward_spatial":
        model = WardSpatial(df, w, cols, n_clusters=k)
    elif method == "azp":
        model = AZP(df, w, cols, n_clusters=k, random_state=seed)
    elif method == "region_kmeans":
        model = RegionKMeansHeuristic(Z, k, w)
    else:  # maxp
        df["_threshold"] = payload["threshold_values"]
        model = MaxPHeuristic(df, w, cols, "_threshold", payload["threshold"], top_n=2)
    model.solve()
    return np.asarray(model.labels_)


def _relabel(labels: np.ndarray) -> np.ndarray:
    """크기가 큰 군집부터 1, 2, ... 로 다시 매김 (같은 크기면 먼저 나온 군집이 앞)."""
    labels = np.asarray(labels).astype("int64")  # AZP는 실수형 라벨을 줌
    uniq, first, counts = np.unique(labels, return_index=True, return_counts=True)
    order = sorted(range(len(uniq)), key=lambda i: (-counts[i], first[i]))
    mapping = {int(uniq[i]): rank + 1 for rank, i in enumerate(order)}
    return np.array([mapping[int(v)] for v in labels], dtype="int32")


def _fragments(labels: np.ndarray, w) -> dict[int, int]:
    """군집마다 공간적으로 이어진 조각 수. 1이면 한 덩어리임."""
    from scipy.sparse.csgraph import connected_components

    A = w.sparse.tocsr()
    out = {}
    for c in np.unique(labels):
        idx = np.flatnonzero(labels == c)
        n_comp, _ = connected_components(A[idx][:, idx], directed=False)
        out[int(c)] = int(n_comp)
    return out


def _f(v: Any) -> float | None:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def run(payload: dict[str, Any], progress: Progress) -> dict[str, Any]:
    X = payload["X"]
    cols = payload["variables"]
    if payload["standardize"]:
        sd = X.std(axis=0)
        sd[sd == 0] = 1.0
        Z = (X - X.mean(axis=0)) / sd
    else:
        Z = X.copy()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = _solve(payload, Z, progress)
    labels = _relabel(raw)
    progress(None, "군집 요약 계산 중")

    total_ss = float(((Z - Z.mean(axis=0)) ** 2).sum())
    # 군집 프로필용 표준화 평균 (표준화 옵션과 관계없이 z점수 기준)
    sd_all = X.std(axis=0)
    sd_all[sd_all == 0] = 1.0
    Xz = (X - X.mean(axis=0)) / sd_all
    clusters = []
    within_total = 0.0
    frags = _fragments(labels, payload["weights"]) if payload["weights"] is not None else None
    for c in range(1, int(labels.max()) + 1):
        mask = labels == c
        zc = Z[mask]
        within = float(((zc - zc.mean(axis=0)) ** 2).sum())
        within_total += within
        clusters.append(
            {
                "id": c,
                "size": int(mask.sum()),
                "within_ss": _f(within),
                "means": [_f(v) for v in X[mask].mean(axis=0)],
                "z_means": [_f(v) for v in Xz[mask].mean(axis=0)],
                "fragments": frags[c] if frags else None,
            }
        )
    between = total_ss - within_total
    ratio = between / total_ss if total_ss > 0 else None
    k = len(clusters)
    method = payload["method"]

    summary: list[list[Any]] = [
        ["관측치", int(X.shape[0])],
        ["군집 수", k],
        ["변수 척도", "표준화 (z)" if payload["standardize"] else "원래 값"],
        ["전체 제곱합", _f(total_ss)],
        ["군집 내 제곱합", _f(within_total)],
        ["군집 간 제곱합", _f(between)],
        ["군집 간 / 전체 비", _f(ratio)],
    ]
    if method == "maxp":
        summary.insert(
            2,
            [
                "지역 최소 합계",
                f"{payload['threshold']:g} ({payload['threshold_column'] or '피처 수'})",
            ],
        )
    notes = list(payload["notes"])
    if method == "maxp":
        notes.append(
            "Max-p는 군집 수를 정하지 않고, 임계값을 만족하는 지역 수가 최대가 되도록 나눔"
        )
    if frags and method not in SPATIAL:
        split = sum(1 for c in clusters if c["fragments"] and c["fragments"] > 1)
        if split:
            notes.append(
                f"비공간 군집이라 {split}개 군집이 공간적으로 여러 조각으로 흩어져 있음 (조각 수 열 참고)"
            )
    report = {
        "kind": "cluster",
        "method": method,
        "title": METHOD_LABELS[method],
        "variables": cols,
        "n": int(X.shape[0]),
        "k": k,
        "summary": summary,
        "clusters": clusters,
        "ratio": _f(ratio),
        "notes": notes,
    }
    return {"report": report, "columns": {SUFFIX: labels}}


# ---- 보고서 텍스트 ---------------------------------------------------------------


def _fmt(v: Any, digits: int = 6) -> str:
    if v is None:
        return "-"
    if isinstance(v, str):
        return v
    if isinstance(v, int) or (isinstance(v, float) and v.is_integer() and abs(v) < 1e12):
        return f"{int(v):,}"
    return f"{v:,.{digits}g}"


def report_text(report: dict[str, Any], description: str = "") -> str:
    lines = [
        "=" * 72,
        f"GeoStat 군집 분석 보고서 — {report['title']}",
        "=" * 72,
        f"변수: {', '.join(report['variables'])}",
    ]
    if description:
        lines.append(f"설정: {description}")
    lines.append("")
    for label, value in report["summary"]:
        lines.append(f"  {label:<24}{_fmt(value)}")
    lines += ["", "-" * 72, "군집별 요약 (평균은 원래 값 기준)", "-" * 72]
    head = f"{'군집':<6}{'크기':>8}{'군집 내 SS':>14}{'조각':>6}"
    head += "".join(f"{v[:12]:>14}" for v in report["variables"])
    lines.append(head)
    for c in report["clusters"]:
        row = f"{c['id']:<6}{c['size']:>8,}{_fmt(c['within_ss'], 5):>14}{_fmt(c['fragments']):>6}"
        row += "".join(f"{_fmt(m, 5):>14}" for m in c["means"])
        lines.append(row)
    if report.get("notes"):
        lines += ["", "참고"] + [f"  · {n}" for n in report["notes"] if n]
    lines.append("")
    return "\n".join(lines)
