"""회귀 분석·작업(진행률·취소)·분석 기록 API."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from geostat_engine import service
from geostat_engine.analysis import regression
from geostat_engine.api.datasets import dataset_info
from geostat_engine.auth import require_token
from geostat_engine.errors import EngineError
from geostat_engine.jobs import JobManager
from geostat_engine.state import AppState, Dataset

router = APIRouter(tags=["regression"], dependencies=[Depends(require_token)])


def _state(request: Request) -> AppState:
    return request.app.state.geostat


def _jobs(request: Request) -> JobManager:
    return request.app.state.jobs


class RegressionRequest(BaseModel):
    model: Literal["ols", "lag", "error", "lag_gm", "error_gm", "gwr", "mgwr"]
    y: str
    x: list[str] = Field(min_length=1)
    weights_id: str | None = Field(
        default=None,
        description="OLS 공간진단·공간시차·공간오차에 쓸 가중치. GWR·MGWR은 잔차 Moran's I에만 씀",
    )
    kernel: Literal["bisquare", "gaussian", "exponential"] = "bisquare"
    fixed: bool = Field(default=False, description="고정 대역폭 (False면 적응: 이웃 수)")
    criterion: Literal["AICc", "AIC", "BIC", "CV"] = "AICc"
    bandwidth: float | None = Field(default=None, gt=0, description="GWR 대역폭 직접 지정")
    alpha: float = Field(default=0.05, gt=0, lt=1)
    white_test: bool = True
    robust: Literal["white"] | None = Field(default=None, description="OLS 강건 표준오차")
    prefix: str | None = None


class JobInfo(BaseModel):
    id: str
    kind: str
    title: str
    dataset_id: str
    status: Literal["running", "done", "failed", "cancelled"]
    progress: float | None
    message: str
    elapsed: float
    result: Any = None
    error: dict[str, str] | None = None


class AnalysisInfo(BaseModel):
    id: str
    method: str
    description: str
    outputs: list[str]
    params: dict[str, Any]
    report: dict[str, Any] | None = None


class ReportSaveRequest(BaseModel):
    path: str


def _analysis_info(a) -> AnalysisInfo:
    params = {k: v for k, v in a.params.items() if not k.startswith("_")}
    return AnalysisInfo(
        id=a.id,
        method=a.method,
        description=a.description,
        outputs=a.outputs,
        params=params,
        report=a.summary.get("report"),
    )


@router.post("/datasets/{dataset_id}/regression", response_model=JobInfo)
def start_regression(dataset_id: str, body: RegressionRequest, request: Request) -> JobInfo:
    ds: Dataset = _state(request).get(dataset_id)
    spec = body.model_dump()
    if body.model in regression.WEIGHTS_REQUIRED and not body.weights_id:
        raise EngineError("weights_required", "공간시차·공간오차 모형은 공간가중치가 필요함")
    # GWR·MGWR은 좌표로 커널 가중치를 따로 만들고, 지정한 공간가중치는 잔차 Moran's I에만 씀
    payload = service.prepare_regression(ds, spec)

    def on_done(result: dict[str, Any]) -> dict[str, Any]:
        record = service.apply_regression(ds, spec, result)
        return {
            "info": dataset_info(ds).model_dump(),
            "analysis": _analysis_info(record).model_dump(),
        }

    job = _jobs(request).start(
        "regression",
        payload,
        kind=body.model,
        title=f"{regression.MODEL_LABELS[body.model]}: {body.y}",
        dataset_id=dataset_id,
        on_done=on_done,
    )
    return JobInfo(**job.public())


@router.get("/jobs", response_model=list[JobInfo])
def list_jobs(request: Request) -> list[JobInfo]:
    return [JobInfo(**j.public()) for j in _jobs(request).list()]


@router.get("/jobs/{job_id}", response_model=JobInfo)
def get_job(job_id: str, request: Request) -> JobInfo:
    return JobInfo(**_jobs(request).get(job_id).public())


@router.delete("/jobs/{job_id}", response_model=JobInfo)
def cancel_job(job_id: str, request: Request) -> JobInfo:
    return JobInfo(**_jobs(request).cancel(job_id).public())


@router.get("/datasets/{dataset_id}/analyses", response_model=list[AnalysisInfo])
def list_analyses(dataset_id: str, request: Request) -> list[AnalysisInfo]:
    return [_analysis_info(a) for a in _state(request).get(dataset_id).analyses]


@router.post("/datasets/{dataset_id}/analyses/{analysis_id}/report")
def save_report(
    dataset_id: str, analysis_id: str, body: ReportSaveRequest, request: Request
) -> dict[str, str]:
    ds = _state(request).get(dataset_id)
    record = next((a for a in ds.analyses if a.id == analysis_id), None)
    if record is None or "report" not in record.summary:
        raise EngineError("report_not_found", "보고서가 있는 분석이 아님")
    path = Path(body.path).expanduser()
    if not path.parent.exists():
        raise EngineError("folder_not_found", f"폴더가 없음: {path.parent}")
    if record.method == "cluster":
        from geostat_engine.analysis import cluster

        text = cluster.report_text(record.summary["report"], record.description)
    elif record.method == "lisa_time":
        from geostat_engine.report import lisa_time_text

        text = lisa_time_text(record.summary["report"], record.description)
    else:
        text = regression.report_text(record.summary["report"], record.description)
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise EngineError("write_failed", f"보고서를 저장하지 못함: {exc}") from exc
    return {"path": str(path)}
