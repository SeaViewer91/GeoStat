"""공간가중치·공간자기상관(ESDA)·차트용 열 데이터 API."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
import pyarrow as pa
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from geostat_engine import service
from geostat_engine.analysis import esda_ops
from geostat_engine.analysis import weights as weights_mod
from geostat_engine.api.datasets import DatasetInfo, dataset_info
from geostat_engine.auth import require_token
from geostat_engine.errors import EngineError
from geostat_engine.io.geoarrow import ARROW_STREAM_MEDIA_TYPE
from geostat_engine.state import AppState, Dataset, WeightsEntry

router = APIRouter(
    prefix="/datasets/{dataset_id}", tags=["spatial"], dependencies=[Depends(require_token)]
)


def _ds(request: Request, dataset_id: str) -> Dataset:
    state: AppState = request.app.state.geostat
    return state.get(dataset_id)


def _b64_f64(values: np.ndarray) -> str:
    return base64.b64encode(np.asarray(values, dtype="<f8").tobytes()).decode("ascii")


def _decode_ids(encoded: str, n: int) -> np.ndarray:
    try:
        ids = np.frombuffer(base64.b64decode(encoded), dtype="<u4").astype(np.int64)
    except Exception as exc:
        raise EngineError("invalid_ids", "행 번호 목록을 해석할 수 없음") from exc
    if ids.size and ids.max() >= n:
        raise EngineError("invalid_ids", "범위를 벗어난 행 번호가 있음")
    return ids


# ---- 공간가중치 ---------------------------------------------------------------


class WeightsRequest(BaseModel):
    type: Literal["queen", "rook", "knn", "distance", "kernel"]
    name: str | None = None
    order: int = Field(default=1, ge=1, le=10, description="인접 차수 (queen·rook)")
    include_lower: bool = Field(default=True, description="하위 차수 이웃 포함")
    k: int = Field(default=6, ge=1, description="이웃 수 (knn·kernel)")
    threshold: float | None = Field(default=None, description="거리 임계값. 없으면 최소 거리 사용")
    inverse: bool = Field(default=False, description="역거리 가중")
    power: float = Field(default=1.0, gt=0)
    function: Literal["triangular", "uniform", "quadratic", "quartic", "gaussian"] = "triangular"
    fixed: bool = Field(default=False, description="고정 대역폭 (False면 적응 대역폭)")


class WeightsFileRequest(BaseModel):
    path: str
    name: str | None = None


class WeightsInfo(BaseModel):
    id: str
    name: str
    type: str
    description: str
    spec: dict[str, Any]
    summary: dict[str, Any]


class NeighborsRequest(BaseModel):
    ids: str = Field(description="Uint32 리틀엔디언 행 번호 배열의 base64")


def _weights_info(entry: WeightsEntry) -> WeightsInfo:
    return WeightsInfo(
        id=entry.id,
        name=entry.name,
        type=str(entry.spec.get("type")),
        description=entry.description,
        spec=entry.spec,
        summary=entry.summary,
    )


def _spec_from_request(body: WeightsRequest) -> dict[str, Any]:
    keys = {
        "queen": ("order", "include_lower"),
        "rook": ("order", "include_lower"),
        "knn": ("k",),
        "distance": ("threshold", "inverse", "power"),
        "kernel": ("function", "k", "fixed"),
    }[body.type]
    return {"type": body.type, **{k: getattr(body, k) for k in keys}}


@router.post("/weights", response_model=WeightsInfo)
def create_weights(dataset_id: str, body: WeightsRequest, request: Request) -> WeightsInfo:
    ds = _ds(request, dataset_id)
    entry = service.create_weights(ds, _spec_from_request(body), name=body.name)
    return _weights_info(entry)


@router.post("/weights/load", response_model=WeightsInfo)
def load_weights(dataset_id: str, body: WeightsFileRequest, request: Request) -> WeightsInfo:
    ds = _ds(request, dataset_id)
    path = str(Path(body.path).expanduser().resolve())
    entry = service.create_weights(ds, {"type": "file", "path": path}, name=body.name)
    return _weights_info(entry)


@router.get("/weights", response_model=list[WeightsInfo])
def list_weights(dataset_id: str, request: Request) -> list[WeightsInfo]:
    return [_weights_info(e) for e in _ds(request, dataset_id).weights.values()]


@router.delete("/weights/{weights_id}", status_code=204)
def delete_weights(dataset_id: str, weights_id: str, request: Request) -> Response:
    service.remove_weights(_ds(request, dataset_id), weights_id)
    return Response(status_code=204)


@router.get("/weights-threshold")
def weights_threshold(dataset_id: str, request: Request) -> dict[str, Any]:
    """모든 피처가 이웃을 하나 이상 갖는 최소 거리 (거리 가중치 기본값)."""
    return weights_mod.suggest_threshold(_ds(request, dataset_id).gdf)


@router.post("/weights/{weights_id}/neighbors")
def neighbors(dataset_id: str, weights_id: str, body: NeighborsRequest, request: Request) -> dict:
    ds = _ds(request, dataset_id)
    entry = ds.get_weights(weights_id)
    ids = _decode_ids(body.ids, len(ds.gdf))
    out = weights_mod.neighbors_of(entry.w, ids)
    return {
        "ids": base64.b64encode(out.astype("<u4").tobytes()).decode("ascii"),
        "count": int(out.size),
    }


@router.post("/weights/{weights_id}/save")
def save_weights(
    dataset_id: str, weights_id: str, body: WeightsFileRequest, request: Request
) -> dict:
    ds = _ds(request, dataset_id)
    entry = ds.get_weights(weights_id)
    path = Path(body.path).expanduser()
    weights_mod.write_file(entry.w, path)
    return {"path": str(path)}


# ---- 전역 공간자기상관 ------------------------------------------------------------


class MoranRequest(BaseModel):
    column: str
    column_y: str | None = Field(default=None, description="이변량 Moran의 두 번째 변수")
    weights_id: str
    permutations: int = Field(default=999, ge=0)
    seed: int | None = service.DEFAULT_SEED


class MoranResponse(BaseModel):
    column: str
    column_y: str | None
    weights: str
    I: float
    expected: float
    variance_norm: float | None
    z_norm: float | None
    p_norm: float | None
    z_sim: float | None
    p_sim: float | None
    permutations: int
    n: int
    sim_hist: dict[str, list[float]] | None
    z: str = Field(description="표준화 변수 (Float64 base64)")
    lag: str = Field(description="공간 시차 (Float64 base64)")


def _finite(v: float) -> float | None:
    return None if v is None or not np.isfinite(v) else float(v)


@router.post("/esda/moran", response_model=MoranResponse)
def global_moran(dataset_id: str, body: MoranRequest, request: Request) -> MoranResponse:
    ds = _ds(request, dataset_id)
    entry = ds.get_weights(body.weights_id)
    x = service._column(ds, body.column)
    y = service._column(ds, body.column_y) if body.column_y else None
    r = esda_ops.moran(x, entry.w, body.permutations, body.seed, y=y)
    return MoranResponse(
        column=body.column,
        column_y=body.column_y,
        weights=entry.name,
        I=r.I,
        expected=r.expected,
        variance_norm=_finite(r.variance_norm),
        z_norm=_finite(r.z_norm),
        p_norm=_finite(r.p_norm),
        z_sim=_finite(r.z_sim) if r.z_sim is not None else None,
        p_sim=r.p_sim,
        permutations=r.permutations,
        n=r.n,
        sim_hist=r.sim_hist,
        z=_b64_f64(r.z),
        lag=_b64_f64(r.lag),
    )


class JoinCountRequest(BaseModel):
    column: str
    weights_id: str
    permutations: int = Field(default=999, ge=0)


@router.post("/esda/joincount")
def join_count(dataset_id: str, body: JoinCountRequest, request: Request) -> dict[str, Any]:
    ds = _ds(request, dataset_id)
    entry = ds.get_weights(body.weights_id)
    return esda_ops.join_counts(service._column(ds, body.column), entry.w, body.permutations)


# ---- 국지 공간통계 ------------------------------------------------------------


class LocalRequest(BaseModel):
    method: Literal["lisa", "lisa_bv", "gi_star", "local_geary"]
    column: str
    column_y: str | None = None
    weights_id: str
    permutations: int = Field(default=999, ge=99)
    seed: int | None = service.DEFAULT_SEED
    alpha: float = Field(default=0.05, gt=0, lt=1)
    correction: Literal["none", "fdr", "bonferroni"] = "none"
    prefix: str | None = Field(default=None, description="결과 열 이름 접두어 (예: LISA)")


class LocalResponse(BaseModel):
    info: DatasetInfo
    analysis_id: str
    outputs: list[str] = Field(description="[통계량 열, 군집 코드 열, p값 열]")
    cluster_method: str = Field(description="군집 지도를 그릴 때 쓸 분류 방법")
    description: str
    threshold: float
    counts: dict[int, int]
    n_islands: int


@router.post("/esda/local", response_model=LocalResponse)
def local_stats(dataset_id: str, body: LocalRequest, request: Request) -> LocalResponse:
    ds = _ds(request, dataset_id)
    record = service.run_local(ds, body.model_dump())
    return LocalResponse(
        info=dataset_info(ds),
        analysis_id=record.id,
        outputs=record.outputs,
        cluster_method=esda_ops.CLUSTER_METHOD[record.method],
        description=record.description,
        threshold=record.summary["threshold"],
        counts=record.summary["counts"],
        n_islands=record.summary["n_islands"],
    )


# ---- 차트용 열 데이터 ------------------------------------------------------------


class ColumnsRequest(BaseModel):
    names: list[str] = Field(min_length=1, max_length=16)


@router.post("/columns")
def columns(dataset_id: str, body: ColumnsRequest, request: Request) -> Response:
    """숫자 열을 Float64 Arrow IPC로 보냄 (값 없음은 NaN). 차트 연동용."""
    ds = _ds(request, dataset_id)
    arrays, names = [], []
    for name in body.names:
        series = service._column(ds, name)
        if not pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
            raise EngineError("not_numeric", f"숫자 열이 아님: {name}")
        arrays.append(pa.array(series.to_numpy(dtype="float64", na_value=np.nan), pa.float64()))
        names.append(name)
    table = pa.table(arrays, names=names)
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    return Response(content=sink.getvalue().to_pybytes(), media_type=ARROW_STREAM_MEDIA_TYPE)
