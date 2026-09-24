"""탐색적 공간자료분석 (esda).

전역: Moran's I (단변량·이변량), Join Count
국지: LISA (단변량·이변량), Getis-Ord Gi*, Local Geary

군집 코드는 GeoDa와 같게 맞춤
  LISA   : 0 비유의, 1 High-High, 2 Low-Low, 3 Low-High, 4 High-Low, 5 이웃 없음
  Gi*    : 0 비유의, 1 핫스팟(High), 2 콜드스팟(Low), 5 이웃 없음
  Geary  : 0 비유의, 1 High-High, 2 Low-Low, 3 기타 양(+), 4 음(-)의 연관, 5 이웃 없음
"""

from __future__ import annotations

import copy
import warnings
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd

from geostat_engine.errors import EngineError

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import esda

LocalMethod = Literal["lisa", "lisa_bv", "gi_star", "local_geary"]
Correction = Literal["none", "fdr", "bonferroni"]

ISLAND = 5
MAX_PERMUTATIONS = 99999
# 이 피처 수 이상이면 순열 검정을 여러 프로세스로 나눠 계산함
PARALLEL_MIN_N = 20000


def _values(series: pd.Series, name: str) -> np.ndarray:
    if not pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
        raise EngineError("not_numeric", f"숫자 열이 아님: {name}")
    y = series.to_numpy(dtype="float64", na_value=np.nan)
    if np.isnan(y).any():
        raise EngineError(
            "missing_values",
            f"'{name}'에 값 없는 행이 {int(np.isnan(y).sum())}개 있음. 공간 통계는 결측을 허용하지 않음",
        )
    if np.nanstd(y) == 0:
        raise EngineError("constant", f"'{name}'의 값이 모두 같아 계산할 수 없음")
    return y


def _check_permutations(permutations: int) -> int:
    if (
        permutations not in (0, 99, 199, 499, 999, 9999, 99999)
        and not 0 <= permutations <= MAX_PERMUTATIONS
    ):
        raise EngineError("invalid_permutations", "순열 횟수가 올바르지 않음")
    return int(permutations)


def _row_standardized(w: Any) -> Any:
    """원본 W를 바꾸지 않도록 복사해 행 표준화함 (esda는 transform을 제자리에서 바꿈)."""
    w2 = copy.deepcopy(w)
    w2.transform = "r"
    return w2


def _islands(w: Any) -> np.ndarray:
    return np.array([w.cardinalities[i] == 0 for i in range(w.n)])


# ---- 전역 --------------------------------------------------------------------


@dataclass
class GlobalMoran:
    I: float
    expected: float
    variance_norm: float
    z_norm: float
    p_norm: float
    z_sim: float | None
    p_sim: float | None
    permutations: int
    n: int
    z: np.ndarray  # 표준화한 변수
    lag: np.ndarray  # 표준화한 (두 번째) 변수의 공간 시차
    sim_hist: dict[str, list[float]] | None


def moran(
    x: pd.Series, w: Any, permutations: int, seed: int | None, y: pd.Series | None = None
) -> GlobalMoran:
    permutations = _check_permutations(permutations)
    xv = _values(x, str(x.name))
    wr = _row_standardized(w)
    if seed is not None:
        np.random.seed(seed)  # esda의 전역 Moran은 seed 인자가 없어 전역 난수를 고정함
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if y is None:
            m = esda.Moran(xv, wr, transformation="r", permutations=permutations)
            z_src = xv
            z_lag = xv
            expected, var, zn, pn = m.EI, m.VI_norm, m.z_norm, m.p_norm
        else:
            yv = _values(y, str(y.name))
            m = esda.Moran_BV(xv, yv, wr, transformation="r", permutations=permutations)
            z_src = xv
            z_lag = yv
            expected = -1.0 / (len(xv) - 1)
            var, zn, pn = np.nan, np.nan, np.nan

    zx = (z_src - z_src.mean()) / z_src.std()
    zy = (z_lag - z_lag.mean()) / z_lag.std()
    lag = wr.sparse @ zy
    sim_hist = None
    if permutations and getattr(m, "sim", None) is not None:
        counts, edges = np.histogram(m.sim, bins=40)
        sim_hist = {"counts": counts.tolist(), "edges": edges.tolist()}
    return GlobalMoran(
        I=float(m.I),
        expected=float(expected),
        variance_norm=float(var),
        z_norm=float(zn),
        p_norm=float(pn),
        z_sim=float(m.z_sim) if permutations else None,
        p_sim=float(m.p_sim) if permutations else None,
        permutations=permutations,
        n=len(xv),
        z=zx,
        lag=lag,
        sim_hist=sim_hist,
    )


def join_counts(x: pd.Series, w: Any, permutations: int) -> dict[str, Any]:
    """이진(0/1) 변수의 Join Count 통계."""
    permutations = _check_permutations(permutations)
    yv = _values(x, str(x.name))
    uniq = np.unique(yv)
    if not set(uniq.tolist()) <= {0.0, 1.0}:
        raise EngineError("not_binary", "Join Count는 0/1 이진 변수에만 쓸 수 있음")
    wb = copy.deepcopy(w)
    wb.transform = "b"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        jc = esda.Join_Counts(yv, wb, permutations=permutations)
    out = {"bb": float(jc.bb), "bw": float(jc.bw), "ww": float(jc.ww), "joins": float(jc.J)}
    if permutations:
        out.update(
            {
                "p_sim_bb": float(jc.p_sim_bb),
                "p_sim_bw": float(jc.p_sim_bw),
                "mean_bb": float(jc.mean_bb),
                "mean_bw": float(jc.mean_bw),
            }
        )
    return out


# ---- 국지 --------------------------------------------------------------------


@dataclass
class LocalResult:
    method: str
    stat: np.ndarray  # 국지 통계량 (LISA I, Gi* z, Local Geary C)
    p: np.ndarray  # 순열 검정 유사 p값
    cluster: np.ndarray  # 군집 코드 (int)
    threshold: float  # 유의 판정에 쓴 p 기준 (보정 반영)
    alpha: float
    correction: str
    permutations: int
    n_islands: int
    counts: dict[int, int]


def _threshold(p: np.ndarray, alpha: float, correction: Correction) -> float:
    if correction == "bonferroni":
        return alpha / len(p)
    if correction == "fdr":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return float(esda.fdr(p, alpha))
    return alpha


def local(
    method: LocalMethod,
    x: pd.Series,
    w: Any,
    permutations: int,
    seed: int | None,
    alpha: float = 0.05,
    correction: Correction = "none",
    y: pd.Series | None = None,
) -> LocalResult:
    permutations = _check_permutations(permutations)
    if permutations < 99:
        raise EngineError("invalid_permutations", "국지 통계는 순열 99회 이상이 필요함")
    if not 0 < alpha < 1:
        raise EngineError("invalid_alpha", "유의수준은 0과 1 사이여야 함")
    xv = _values(x, str(x.name))
    if len(xv) < 5:
        raise EngineError("too_few", "국지 통계는 피처가 5개 이상이어야 함")
    wr = _row_standardized(w)
    islands = _islands(wr)
    # 큰 자료에서 순열 결과를 모두 보관하면 메모리가 크게 늘어나므로 보관하지 않음.
    # 병렬 처리는 하위 프로세스마다 JIT 컴파일을 다시 하므로 큰 자료에서만 씀
    n_jobs = -1 if len(xv) >= PARALLEL_MIN_N else 1
    common = {
        "permutations": permutations,
        "keep_simulations": False,
        "seed": seed,
        "n_jobs": n_jobs,
    }

    try:
        stat, p, quad = _run_local(method, xv, w, wr, y, common)
    except EngineError:
        raise
    except Exception as exc:  # esda 내부 오류는 사용자에게 보여줄 수 있는 오류로 바꿈
        raise EngineError(
            "analysis_failed", f"국지 통계 계산 실패: {type(exc).__name__}: {exc}"
        ) from exc
    return _finish(method, stat, p, quad, islands, alpha, correction, permutations)


def _run_local(method: str, xv: np.ndarray, w: Any, wr: Any, y: pd.Series | None, common: dict):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if method == "lisa":
            r = esda.Moran_Local(xv, wr, transformation="r", geoda_quads=True, **common)
            stat, p, quad = r.Is, r.p_sim, r.q
        elif method == "lisa_bv":
            if y is None:
                raise EngineError("missing_y", "이변량 LISA는 두 번째 변수가 필요함")
            yv = _values(y, str(y.name))
            r = esda.Moran_Local_BV(xv, yv, wr, transformation="r", geoda_quads=True, **common)
            stat, p, quad = r.Is, r.p_sim, r.q
        elif method == "gi_star":
            wb = copy.deepcopy(w)
            wb.transform = "b"
            r = esda.G_Local(xv, wb, transform="B", star=True, **common)
            stat, p = r.Zs, r.p_sim
            quad = np.where(r.Zs > 0, 1, 2)
        elif method == "local_geary":
            r = esda.Geary_Local(connectivity=wr, labels=True, **common).fit(xv)
            stat, p = r.localG, r.p_sim
            quad = np.asarray(r.labs)
        else:
            raise EngineError("invalid_method", f"알 수 없는 국지 통계: {method}")
    return stat, p, quad


def _finish(
    method: str,
    stat,
    p,
    quad,
    islands: np.ndarray,
    alpha: float,
    correction: Correction,
    permutations: int,
) -> LocalResult:
    stat = np.array(stat, dtype="float64")  # esda 결과가 읽기 전용일 수 있어 복사함
    p = np.array(p, dtype="float64")
    threshold = _threshold(p, alpha, correction)
    cluster = np.where(p <= threshold, np.asarray(quad, dtype=int), 0)
    cluster[islands] = ISLAND
    p = p.copy()
    p[islands] = np.nan
    stat[islands] = np.nan
    codes, counts = np.unique(cluster, return_counts=True)
    return LocalResult(
        method=method,
        stat=stat,
        p=p,
        cluster=cluster.astype("int16"),
        threshold=float(threshold),
        alpha=alpha,
        correction=correction,
        permutations=permutations,
        n_islands=int(islands.sum()),
        counts={int(c): int(n) for c, n in zip(codes, counts, strict=True)},
    )


# 결과 열 이름 접미사: 통계량, 군집 코드, p값
LOCAL_SUFFIXES = {
    "lisa": ("I", "CL", "P"),
    "lisa_bv": ("I", "CL", "P"),
    "gi_star": ("Z", "CL", "P"),
    "local_geary": ("C", "CL", "P"),
}
LOCAL_DEFAULT_PREFIX = {
    "lisa": "LISA",
    "lisa_bv": "BLISA",
    "gi_star": "GISTAR",
    "local_geary": "LGEARY",
}
CLUSTER_METHOD = {
    "lisa": "lisa_cluster",
    "lisa_bv": "lisa_cluster",
    "gi_star": "gi_cluster",
    "local_geary": "geary_cluster",
}
