"""점 집계·비율 지도·시공간 분석 API."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from geostat_engine import service
from geostat_engine.api.datasets import DatasetInfo, dataset_info
from geostat_engine.api.regression import AnalysisInfo, _analysis_info
from geostat_engine.auth import require_token
from geostat_engine.state import AppState

router = APIRouter(tags=["tools"], dependencies=[Depends(require_token)])


def _state(request: Request) -> AppState:
    return request.app.state.geostat


class AnalysisResponse(BaseModel):
    info: DatasetInfo
    analysis: AnalysisInfo
    notes: list[str] = []


# ---- 점 집계 -------------------------------------------------------------------


class AggregateStat(BaseModel):
    column: str
    stat: Literal["sum", "mean", "min", "max", "median", "std"]


class AggregateRequest(BaseModel):
    source_id: str = Field(description="집계할 점(원본) 데이터셋")
    count: bool = True
    density: bool = Field(default=False, description="㎢당 개수")
    stats: list[AggregateStat] = []
    prefix: str | None = Field(default=None, description="결과 열 접두어 (기본 PT)")


@router.post("/datasets/{dataset_id}/aggregate", response_model=AnalysisResponse)
def aggregate(dataset_id: str, body: AggregateRequest, request: Request) -> AnalysisResponse:
    state = _state(request)
    ds = state.get(dataset_id)
    source = state.get(body.source_id)
    record = service.run_aggregate(ds, source, body.model_dump())
    return AnalysisResponse(
        info=dataset_info(ds),
        analysis=_analysis_info(record),
        notes=list(record.summary.get("notes", [])),
    )


# ---- 비율·EB 평활 --------------------------------------------------------------


class RateRequest(BaseModel):
    method: Literal["raw", "excess_risk", "eb", "spatial_rate", "spatial_eb"]
    event: str = Field(description="분자 (사건 수, 어획량 등)")
    base: str = Field(description="분모 (모집단, 노력량 등)")
    weights_id: str | None = Field(default=None, description="공간 비율·공간 EB에 필요함")
    multiplier: float = Field(default=1.0, gt=0, description="비율에 곱할 값 (예: 1000명당)")
    name: str | None = Field(default=None, description="결과 열 이름")


@router.post("/datasets/{dataset_id}/rates", response_model=AnalysisResponse)
def rates(dataset_id: str, body: RateRequest, request: Request) -> AnalysisResponse:
    ds = _state(request).get(dataset_id)
    record = service.run_rate(ds, body.model_dump())
    return AnalysisResponse(info=dataset_info(ds), analysis=_analysis_info(record))


# ---- 시간 변수 묶음 ----------------------------------------------------------------


class TimeGroupModel(BaseModel):
    name: str
    columns: list[str]
    labels: list[str]


class TimeGroupsRequest(BaseModel):
    groups: list[TimeGroupModel]


@router.put("/datasets/{dataset_id}/time-groups", response_model=DatasetInfo)
def set_time_groups(dataset_id: str, body: TimeGroupsRequest, request: Request) -> DatasetInfo:
    ds = _state(request).get(dataset_id)
    service.set_time_groups(ds, [g.model_dump() for g in body.groups])
    return dataset_info(ds)


@router.get("/datasets/{dataset_id}/time-groups/guess", response_model=list[TimeGroupModel])
def guess_time_groups(dataset_id: str, request: Request) -> list[TimeGroupModel]:
    """열 이름 끝의 연도(값_2022 등)로 시간 변수 묶음 후보를 찾음."""
    from geostat_engine.analysis.timeseries import guess_groups

    ds = _state(request).get(dataset_id)
    numeric = [
        str(c)
        for c in ds.gdf.columns
        if c != ds.gdf.geometry.name and ds.gdf[c].dtype.kind in "iuf"  # 정수·실수 열만
    ]
    return [TimeGroupModel(**g) for g in guess_groups(numeric)]


class MoranSeriesRequest(BaseModel):
    group: str
    weights_id: str
    permutations: int = Field(default=999, ge=0)


@router.post("/datasets/{dataset_id}/timeseries/moran")
def moran_series(dataset_id: str, body: MoranSeriesRequest, request: Request) -> dict[str, Any]:
    ds = _state(request).get(dataset_id)
    return service.moran_series(ds, body.model_dump())


class LisaTimeRequest(BaseModel):
    group: str
    weights_id: str
    permutations: int = Field(default=999, ge=99)
    alpha: float = Field(default=0.05, gt=0, lt=1)
    correction: Literal["none", "fdr", "bonferroni"] = "none"
    prefix: str | None = None


@router.post("/datasets/{dataset_id}/timeseries/lisa", response_model=AnalysisResponse)
def lisa_time(dataset_id: str, body: LisaTimeRequest, request: Request) -> AnalysisResponse:
    ds = _state(request).get(dataset_id)
    record = service.run_lisa_time(ds, body.model_dump())
    return AnalysisResponse(info=dataset_info(ds), analysis=_analysis_info(record))


# ---- 자료 형태 바꾸기 --------------------------------------------------------------


class PivotRequest(BaseModel):
    dataset_id: str
    id_column: str
    time_column: str
    value_columns: list[str] = Field(min_length=1)
    path: str = Field(description="저장할 GeoPackage 경로")
    name: str | None = None


class NewDatasetResponse(BaseModel):
    info: DatasetInfo
    notes: list[str] = []


@router.post("/timeseries/pivot", response_model=NewDatasetResponse)
def pivot(body: PivotRequest, request: Request) -> NewDatasetResponse:
    ds, notes = service.pivot_dataset(_state(request), body.model_dump())
    return NewDatasetResponse(info=dataset_info(ds), notes=notes)


class MergePart(BaseModel):
    dataset_id: str
    id_column: str
    label: str = Field(description="기간 이름 (예: 2023)")


class MergeRequest(BaseModel):
    parts: list[MergePart] = Field(min_length=2, description="첫 자료의 지오메트리를 씀")
    value_columns: list[str] = Field(min_length=1)
    path: str
    name: str | None = None


@router.post("/timeseries/merge", response_model=NewDatasetResponse)
def merge(body: MergeRequest, request: Request) -> NewDatasetResponse:
    ds, notes = service.merge_dataset(_state(request), body.model_dump())
    return NewDatasetResponse(info=dataset_info(ds), notes=notes)


# ---- 분석 보고서 내보내기 -------------------------------------------------------------


class ReportDataset(BaseModel):
    dataset_id: str
    analysis_ids: list[str] | None = Field(default=None, description="없으면 모든 분석을 넣음")


class ReportImage(BaseModel):
    data: str = Field(description="PNG base64")
    caption: str = ""


class ReportExportRequest(BaseModel):
    path: str
    format: Literal["html", "docx"] = "html"
    title: str = "GeoStat 분석 보고서"
    datasets: list[ReportDataset] = Field(min_length=1)
    images: list[ReportImage] = []
    morans: list[dict[str, Any]] = Field(default=[], description="차트 패널의 전역 Moran's I 결과")


@router.post("/report/export")
def export_report(body: ReportExportRequest, request: Request) -> dict[str, str]:
    import base64
    import binascii
    from pathlib import Path

    from geostat_engine import report
    from geostat_engine.errors import EngineError

    state = _state(request)
    items = [(state.get(d.dataset_id), d.analysis_ids) for d in body.datasets]
    images = []
    for img in body.images:
        try:
            png = base64.b64decode(img.data, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise EngineError("invalid_image", "그림 자료를 해석할 수 없음") from exc
        if not png.startswith(b"\x89PNG"):
            raise EngineError("invalid_image", "PNG 그림만 넣을 수 있음")
        images.append((png, img.caption))
    blocks = report.build(body.title, items, images, body.morans)
    path = report.write(Path(body.path).expanduser(), body.format, blocks)
    return {"path": str(path)}
