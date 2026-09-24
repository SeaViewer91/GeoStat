"""공간가중치 생성·요약·파일 입출력 (libpysal).

지원 유형 (GeoDa와 같은 이름을 씀)
  queen / rook : 면 인접 (차수·하위 차수 포함 선택)
  knn          : k개 최근접 이웃 (중심점 기준)
  distance     : 거리 임계값 이내 (이진 또는 역거리)
  kernel       : 커널 가중치 (고정·적응 대역폭)
  file         : GeoDa .gal / .gwt 파일

거리 계산은 투영 좌표계 단위(보통 m)로 함. 경위도 자료는 UTM 좌표계로 임시 변환해 계산함.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
from pyproj import CRS

from geostat_engine.errors import EngineError

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import libpysal
    from libpysal import weights as lw

WEIGHT_TYPES = ("queen", "rook", "knn", "distance", "kernel", "file")
KERNEL_FUNCTIONS = ("triangular", "uniform", "quadratic", "quartic", "gaussian")


def _metric_points(gdf: gpd.GeoDataFrame) -> tuple[np.ndarray, str]:
    """거리 계산용 중심점 좌표와 사용한 좌표계 설명을 반환함."""
    geom = gdf.geometry
    if geom.isna().any() or geom.is_empty.any():
        raise EngineError(
            "empty_geometry", "지오메트리가 없는 행이 있어 거리 기반 가중치를 만들 수 없음"
        )
    crs_note = ""
    if gdf.crs is None:
        crs_note = "좌표계 없음 (좌표 단위 그대로 계산)"
    elif gdf.crs.is_geographic:
        utm = gdf.estimate_utm_crs()
        geom = geom.to_crs(utm)
        crs_note = f"경위도 자료라 {utm.name}(EPSG:{utm.to_epsg()})로 변환해 m 단위로 계산함"
    else:
        unit = gdf.crs.axis_info[0].unit_name if gdf.crs.axis_info else "좌표 단위"
        crs_note = f"{gdf.crs.name} ({unit})"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # 투영 좌표계가 아닐 때의 중심점 경고
        pts = geom.centroid
    return np.column_stack([pts.x.to_numpy(), pts.y.to_numpy()]), crs_note


def suggest_threshold(gdf: gpd.GeoDataFrame) -> dict[str, Any]:
    """모든 피처가 이웃을 하나 이상 갖는 최소 거리 (GeoDa의 기본 제안값과 같음)."""
    pts, note = _metric_points(gdf)
    if len(pts) < 2:
        raise EngineError("too_few", "피처가 2개 이상이어야 함")
    min_threshold = float(lw.min_threshold_distance(pts))
    return {"threshold": min_threshold, "note": note}


def build(
    gdf: gpd.GeoDataFrame, spec: dict[str, Any], base_dir: Path | None = None
) -> tuple[Any, str]:
    """명세(spec)로 가중치를 만들고 (W, 설명)을 반환함. W의 id는 행 번호(0..n-1)임."""
    kind = spec.get("type")
    if kind not in WEIGHT_TYPES:
        raise EngineError("invalid_weights", f"알 수 없는 가중치 유형: {kind}")
    n = len(gdf)
    ids = list(range(n))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # 섬(이웃 없는 피처) 경고는 요약 정보로 따로 알려줌
        if kind in ("queen", "rook"):
            families = set(gdf.geometry.geom_type.dropna().unique())
            if not families <= {"Polygon", "MultiPolygon"}:
                raise EngineError(
                    "contiguity_needs_polygons",
                    "인접 가중치는 면(폴리곤) 자료에만 쓸 수 있음. 점·선 자료는 KNN이나 거리 가중치를 써야 함",
                )
            cls = lw.Queen if kind == "queen" else lw.Rook
            w = cls.from_dataframe(gdf, use_index=False, silence_warnings=True)
            order = int(spec.get("order", 1))
            if order > 1:
                w = lw.higher_order(
                    w,
                    k=order,
                    lower_order=bool(spec.get("include_lower", True)),
                    silence_warnings=True,
                )
            desc = f"{'퀸' if kind == 'queen' else '룩'} 인접 {order}차" + (
                " (하위 차수 포함)" if order > 1 and spec.get("include_lower", True) else ""
            )
        elif kind == "knn":
            k = int(spec.get("k", 6))
            if not 1 <= k < n:
                raise EngineError("invalid_k", f"k는 1 이상 {n - 1} 이하여야 함")
            pts, note = _metric_points(gdf)
            w = lw.KNN(pts, k=k, ids=ids)
            desc = f"{k}-최근접 이웃 · {note}"
        elif kind == "distance":
            pts, note = _metric_points(gdf)
            threshold = spec.get("threshold")
            if threshold is None:
                threshold = float(lw.min_threshold_distance(pts))
            threshold = float(threshold)
            if threshold <= 0:
                raise EngineError("invalid_threshold", "거리 임계값은 0보다 커야 함")
            inverse = bool(spec.get("inverse", False))
            power = float(spec.get("power", 1))
            w = lw.DistanceBand(
                pts,
                threshold=threshold,
                binary=not inverse,
                alpha=-power,
                ids=ids,
                silence_warnings=True,
            )
            desc = (
                f"거리 {threshold:,.1f} 이내"
                + (f" · 역거리^{power:g}" if inverse else "")
                + f" · {note}"
            )
        elif kind == "kernel":
            pts, note = _metric_points(gdf)
            function = spec.get("function", "triangular")
            if function not in KERNEL_FUNCTIONS:
                raise EngineError("invalid_kernel", f"알 수 없는 커널 함수: {function}")
            k = int(spec.get("k", 6))
            fixed = bool(spec.get("fixed", False))
            w = lw.Kernel(pts, k=k, function=function, fixed=fixed, diagonal=True, ids=ids)
            desc = f"커널({function}) · {'고정' if fixed else '적응'} 대역폭 k={k} · {note}"
        else:  # file
            path = Path(spec.get("path", ""))
            if base_dir and not path.is_absolute():
                path = base_dir / path
            w = read_file(path, n)
            desc = f"파일 {path.name}"
    return w, desc


def read_file(path: Path, n: int) -> Any:
    """GeoDa .gal / .gwt 파일을 읽어 행 번호(0..n-1) 기준 W로 바꿈."""
    if not path.exists():
        raise EngineError("file_not_found", f"파일이 없음: {path}")
    if path.suffix.lower() not in {".gal", ".gwt", ".kwt"}:
        raise EngineError("unsupported_format", "가중치 파일은 .gal, .gwt, .kwt만 지원함")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            w = libpysal.io.open(str(path)).read()
    except Exception as exc:
        raise EngineError("read_failed", f"가중치 파일을 읽지 못함: {exc}") from exc
    if w.n != n:
        raise EngineError(
            "weights_mismatch", f"가중치 파일의 관측치 수({w.n})가 데이터 행 수({n})와 다름"
        )
    # GeoDa는 ID 변수 값(보통 1..n)을 씀. 0..n-1 또는 1..n이면 행 번호로 맞춤
    keys = sorted(int(k) for k in w.id_order)
    if keys == list(range(n)):
        offset = 0
    elif keys == list(range(1, n + 1)):
        offset = 1
    else:
        raise EngineError(
            "weights_ids",
            "가중치 파일의 ID가 0..n-1 또는 1..n 순번이 아님. 행 순서 ID로 만든 파일만 지원함",
        )
    neighbors = {int(k) - offset: [int(j) - offset for j in w.neighbors[k]] for k in w.neighbors}
    weights = {int(k) - offset: list(w.weights[k]) for k in w.weights}
    return lw.W(neighbors, weights, id_order=list(range(n)), silence_warnings=True)


def write_file(w: Any, path: Path) -> None:
    """GeoDa 호환 .gal(이진 인접) 또는 .gwt(가중치 포함)로 저장함. ID는 1..n으로 씀."""
    ext = path.suffix.lower()
    if ext not in {".gal", ".gwt"}:
        raise EngineError("unsupported_format", "가중치는 .gal 또는 .gwt로 저장함")
    neighbors = {i + 1: [j + 1 for j in w.neighbors[i]] for i in w.neighbors}
    weights = {i + 1: list(w.weights[i]) for i in w.weights}
    out = lw.W(neighbors, weights, id_order=[i + 1 for i in range(w.n)], silence_warnings=True)
    try:
        f = libpysal.io.open(str(path), "w")
        try:
            f.write(out)
        finally:
            f.close()
    except Exception as exc:
        raise EngineError("write_failed", f"가중치를 저장하지 못함: {exc}") from exc


def summarize(w: Any) -> dict[str, Any]:
    """이웃 수 분포와 섬(이웃 없는 피처) 정보."""
    card = np.array([w.cardinalities[i] for i in range(w.n)])
    counts = np.bincount(card)
    islands = [int(i) for i in np.flatnonzero(card == 0)]
    return {
        "n": int(w.n),
        "min_neighbors": int(card.min()),
        "max_neighbors": int(card.max()),
        "mean_neighbors": float(card.mean()),
        "median_neighbors": float(np.median(card)),
        "pct_nonzero": float(w.pct_nonzero),
        "n_islands": len(islands),
        "islands": islands[:1000],
        "histogram": [
            {"neighbors": int(k), "count": int(c)} for k, c in enumerate(counts) if c > 0
        ],
        "symmetric": bool(_is_symmetric(w)),
    }


def _is_symmetric(w: Any) -> bool:
    try:
        s = w.sparse
        return (s != s.T).nnz == 0
    except Exception:  # noqa: BLE001 - 대칭 여부는 참고 정보라 실패해도 무시함
        return False


def neighbors_of(w: Any, ids: np.ndarray) -> np.ndarray:
    """주어진 피처들의 이웃 행 번호 (자기 자신 제외, 중복 제거)."""
    s = w.sparse.tocsr()
    rows = s[ids]
    out = np.unique(rows.indices)
    return np.setdiff1d(out, ids).astype(np.uint32)


def geodetic_hint(crs: CRS | None) -> str | None:
    if crs is not None and crs.is_geographic:
        return "경위도 자료는 거리 계산 시 UTM 좌표계로 임시 변환함"
    return None
