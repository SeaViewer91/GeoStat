"""프로젝트 저장·열기 API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from geostat_engine import service
from geostat_engine.api.datasets import DatasetInfo, dataset_info
from geostat_engine.auth import require_token
from geostat_engine.errors import EngineError
from geostat_engine.project import (
    EXTENSION,
    build_project,
    read_project,
    resolve_source_path,
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


class OpenResponse(BaseModel):
    path: str
    ui: Any = None
    datasets: list[OpenedDataset]


def _state(request: Request) -> AppState:
    return request.app.state.geostat


@router.post("/save", response_model=SaveResponse)
def save(body: SaveRequest, request: Request) -> SaveResponse:
    state = _state(request)
    path = Path(body.path).expanduser()
    if path.suffix.lower() != EXTENSION:
        path = path.with_suffix(EXTENSION)
    items = [(state.get(d.id), d.ui) for d in body.datasets]
    write_project(path, build_project(path, items, body.ui))
    return SaveResponse(path=str(path), n_datasets=len(items))


@router.post("/open", response_model=OpenResponse)
def open_project(body: OpenRequest, request: Request) -> OpenResponse:
    """현재 세션을 비우고 프로젝트의 데이터셋을 다시 열어 작업을 재적용함."""
    state = _state(request)
    path = Path(body.path).expanduser()
    project = read_project(path)
    state.clear()

    opened: list[OpenedDataset] = []
    for entry in project.get("datasets", []):
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
        for f in entry.get("fields", []):
            try:
                service.set_field(ds, f["name"], f["expression"])
            except EngineError as exc:
                warnings.append(f"계산 필드 '{f.get('name')}' 재계산 실패: {exc.message}")
        opened.append(OpenedDataset(info=dataset_info(ds), ui=entry.get("ui"), warnings=warnings))

    return OpenResponse(path=str(path), ui=project.get("ui"), datasets=opened)
