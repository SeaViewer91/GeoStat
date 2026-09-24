"""군집 분석 API. 계산은 회귀와 같은 작업 큐(별도 프로세스)에서 함."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from geostat_engine import service
from geostat_engine.analysis import cluster
from geostat_engine.api.datasets import dataset_info
from geostat_engine.api.regression import JobInfo, _analysis_info, _jobs, _state
from geostat_engine.auth import require_token
from geostat_engine.errors import EngineError
from geostat_engine.state import Dataset

router = APIRouter(tags=["cluster"], dependencies=[Depends(require_token)])


class ClusterRequest(BaseModel):
    method: Literal[
        "skater", "maxp", "azp", "region_kmeans", "ward_spatial", "kmeans", "hierarchical"
    ]
    variables: list[str] = Field(min_length=1)
    n_clusters: int = Field(default=5, ge=2, description="군집 수 (Max-p는 쓰지 않음)")
    weights_id: str | None = Field(
        default=None, description="공간 제약 군집에 필수. 비공간 군집은 조각 수 계산에만 씀"
    )
    standardize: bool = Field(default=True, description="변수를 z점수로 표준화한 뒤 군집화")
    floor: int | None = Field(default=None, ge=1, description="SKATER 군집별 최소 피처 수")
    threshold_column: str | None = Field(
        default=None, description="Max-p 임계값 열 (없으면 피처 수)"
    )
    threshold: float | None = Field(default=None, gt=0, description="Max-p 지역별 최소 합계")
    seed: int | None = None
    prefix: str | None = None


@router.post("/datasets/{dataset_id}/cluster", response_model=JobInfo)
def start_cluster(dataset_id: str, body: ClusterRequest, request: Request) -> JobInfo:
    ds: Dataset = _state(request).get(dataset_id)
    spec: dict[str, Any] = body.model_dump(exclude_none=True)
    if body.method in cluster.SPATIAL and not body.weights_id:
        raise EngineError("weights_required", "공간 제약 군집은 공간가중치가 필요함")
    payload = service.prepare_cluster(ds, spec)

    def on_done(result: dict[str, Any]) -> dict[str, Any]:
        record = service.apply_cluster(ds, spec, result)
        return {
            "info": dataset_info(ds).model_dump(),
            "analysis": _analysis_info(record).model_dump(),
        }

    job = _jobs(request).start(
        "cluster",
        payload,
        kind=body.method,
        title=f"{cluster.METHOD_LABELS[body.method]}: {', '.join(body.variables)}",
        dataset_id=dataset_id,
        on_done=on_done,
    )
    return JobInfo(**job.public())
