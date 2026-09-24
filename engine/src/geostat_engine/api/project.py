"""프로젝트 저장·열기 API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from geostat_engine import service
from geostat_engine.api.datasets import DatasetInfo, dataset_info
from geostat_engine.api.rasters import RasterInfo, raster_info
from geostat_engine.auth import require_token
from geostat_engine.errors import EngineError
from geostat_engine.project import (
    EXTENSION,
    build_project,
    read_cache,
    read_project,
    resolve_source_path,
    write_cache,
    write_project,
)
from geostat_engine.state import AppState

router = APIRouter(prefix="/project", tags=["project"], dependencies=[Depends(require_token)])


class DatasetUi(BaseModel):
    id: str
    ui: Any = None


class SaveRequest(BaseModel):
    path: str
    datasets: list[DatasetUi] = Field(description="저장할 데이터셋 순서와 각 데이터셋의 화면 설정")
    rasters: list[DatasetUi] = Field(default=[], description="저장할 래스터와 표시 설정")
    ui: Any = Field(default=None, description="앱 전체 화면 설정 (지도 위치, 배경지도 등)")


class SaveResponse(BaseModel):
    path: str
    n_datasets: int


class OpenRequest(BaseModel):
    path: str


class OpenedDataset(BaseModel):
    info: DatasetInfo | None
    ui: Any = None
    error: str | None = None
    warnings: list[str] = []


class OpenedRaster(BaseModel):
    info: RasterInfo | None
    ui: Any = None
    error: str | None = None


class OpenResponse(BaseModel):
    path: str
    ui: Any = None
    datasets: list[OpenedDataset]
    rasters: list[OpenedRaster] = []


def _state(request: Request) -> AppState:
    return request.app.state.geostat


@router.post("/save", response_model=SaveResponse)
def save(body: SaveRequest, request: Request) -> SaveResponse:
    state = _state(request)
    path = Path(body.path).expanduser()
    if path.suffix.lower() != EXTENSION:
        path = path.with_suffix(EXTENSION)
    items = [(state.get(d.id), d.ui) for d in body.datasets]
    raster_items = [(state.get_raster(r.id), r.ui) for r in body.rasters]
    write_project(path, build_project(path, items, body.ui, raster_items))
    write_cache(path, [ds for ds, _ui in items])
    return SaveResponse(path=str(path), n_datasets=len(items))


@router.post("/open", response_model=OpenResponse)
def open_project(body: OpenRequest, request: Request) -> OpenResponse:
    """현재 세션을 비우고 프로젝트의 데이터셋을 다시 열어 작업을 재적용함."""
    state = _state(request)
    path = Path(body.path).expanduser()
    project = read_project(path)
    state.clear()

    rasters: list[OpenedRaster] = []
    for entry in project.get("rasters", []):
        try:
            src_path = resolve_source_path(path, entry)
            r = service.open_raster(state, src_path, name=entry.get("name"))
            rasters.append(OpenedRaster(info=raster_info(r), ui=entry.get("ui")))
        except EngineError as exc:
            rasters.append(OpenedRaster(info=None, ui=entry.get("ui"), error=exc.message))

    opened: list[OpenedDataset] = []
    for index, entry in enumerate(project.get("datasets", [])):
        source = entry.get("source", {})
        try:
            src_path = resolve_source_path(path, source)
            ds = service.open_source(
                state,
                src_path,
                layer=source.get("layer"),
                encoding=source.get("encoding"),
                table=source.get("table"),
                name=entry.get("name"),
            )
        except EngineError as exc:
            opened.append(OpenedDataset(info=None, ui=entry.get("ui"), error=exc.message))
            continue

        warnings: list[str] = []
        if entry.get("crs_override"):
            try:
                service.assign_crs(ds, int(entry["crs_override"]))
            except EngineError as exc:
                warnings.append(f"좌표계 지정 실패: {exc.message}")
        # 계산 필드 → 가중치 → 분석 순으로 재적용함. 분석 결과 열을 쓰는 계산 필드는 분석 뒤에 한 번 더 시도함
        pending_fields = []
        for f in entry.get("fields", []):
            try:
                service.set_field(ds, f["name"], f["expression"])
            except EngineError:
                pending_fields.append(f)
        for wspec in entry.get("weights", []):
            spec = dict(wspec.get("spec", {}))
            if spec.get("type") == "file":
                # 상대 경로 → 절대 경로 순으로 찾음
                cand = path.parent / spec.get("path", "")
                spec["path"] = str(cand if cand.exists() else Path(spec.get("abs_path", "")))
                spec.pop("abs_path", None)
            try:
                service.create_weights(ds, spec, name=wspec.get("name"), weights_id=wspec.get("id"))
            except EngineError as exc:
                warnings.append(f"공간가중치 '{wspec.get('name')}' 재생성 실패: {exc.message}")
        for a in entry.get("analyses", []):
            try:
                if a.get("method") in ("regression", "cluster"):
                    _restore_job_result(path, index, ds, a, warnings)
                elif a.get("method") == "zonal":
                    _restore_zonal(path, index, ds, a, warnings)
                else:
                    service.run_local(ds, a["params"], record_id=a.get("id"))
            except EngineError as exc:
                warnings.append(f"분석 '{a.get('method')}' 재실행 실패: {exc.message}")
        for f in pending_fields:
            try:
                service.set_field(ds, f["name"], f["expression"])
            except EngineError as exc:
                warnings.append(f"계산 필드 '{f.get('name')}' 재계산 실패: {exc.message}")
        opened.append(OpenedDataset(info=dataset_info(ds), ui=entry.get("ui"), warnings=warnings))

    return OpenResponse(path=str(path), ui=project.get("ui"), datasets=opened, rasters=rasters)


def _restore_job_result(path: Path, index: int, ds, entry: dict, warnings: list[str]) -> None:
    """회귀·군집 결과: 저장된 결과 캐시가 맞으면 그대로 붙이고, 아니면 다시 계산함."""
    method = entry["method"]
    params = entry["params"]
    outputs = entry.get("outputs", [])
    prefix = params.get("prefix", "")
    apply = service.apply_regression if method == "regression" else service.apply_cluster
    run_sync = service.run_regression_sync if method == "regression" else service.run_cluster_sync
    cached = read_cache(path, index, len(ds.gdf), outputs) if outputs else None
    if cached is not None and entry.get("report"):
        keys = {c[len(prefix) + 1 :]: v for c, v in cached.items()}
        apply(ds, params, {"report": entry["report"], "columns": keys}, record_id=entry.get("id"))
        return
    name = params.get("model") or params.get("method") or method
    warnings.append(f"{name} 결과 캐시가 없어 다시 계산함")
    run_sync(ds, params, record_id=entry.get("id"))


def _restore_zonal(path: Path, index: int, ds, entry: dict, warnings: list[str]) -> None:
    """존 통계: 캐시가 있으면 붙이고, 없으면 기록된 래스터 경로로 다시 계산함."""
    params = entry["params"]
    outputs = entry.get("outputs", [])
    prefix = params.get("prefix", "")
    cached = read_cache(path, index, len(ds.gdf), outputs) if outputs else None
    if cached is not None:
        keys = {c[len(prefix) + 1 :]: v for c, v in cached.items()}
        service.apply_zonal(ds, params, {"columns": keys}, record_id=entry.get("id"))
        return
    warnings.append("존 통계 결과 캐시가 없어 다시 계산함")
    service.run_zonal_sync(ds, params, record_id=entry.get("id"))
