"""파일을 열기 전에 내용을 살펴보는 API (레이어 목록, 표의 좌표 열 추정)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from geostat_engine.auth import require_token
from geostat_engine.errors import EngineError
from geostat_engine.io.raster import is_raster
from geostat_engine.io.table import inspect_table, is_table
from geostat_engine.io.vector import list_layers

router = APIRouter(prefix="/files", tags=["files"], dependencies=[Depends(require_token)])


class InspectRequest(BaseModel):
    path: str
    encoding: str | None = None
    sheet: str | None = None


class TableColumn(BaseModel):
    name: str
    numeric: bool


class TableInfo(BaseModel):
    encoding: str | None
    sheets: list[str]
    sheet: str | None
    columns: list[TableColumn]
    sample: list[list]
    n_rows: int
    guess_x: str | None
    guess_y: str | None
    guess_epsg: int | None


class InspectResponse(BaseModel):
    path: str
    kind: Literal["vector", "table", "raster"]
    layers: list[str] = []
    table: TableInfo | None = None


@router.post("/inspect", response_model=InspectResponse)
def inspect(body: InspectRequest) -> InspectResponse:
    path = Path(body.path).expanduser()
    if not path.exists():
        raise EngineError("file_not_found", f"파일이 없음: {path}")
    if is_raster(path):
        return InspectResponse(path=str(path), kind="raster")
    if is_table(path):
        info = inspect_table(path, encoding=body.encoding, sheet=body.sheet)
        return InspectResponse(path=str(path), kind="table", table=TableInfo(**info.__dict__))
    return InspectResponse(path=str(path), kind="vector", layers=list_layers(path))


# ---- 샘플 데이터 ------------------------------------------------------------------


class SampleInfo(BaseModel):
    id: str
    name: str
    description: str
    file: str


@router.get("/samples", response_model=list[SampleInfo])
def samples() -> list[SampleInfo]:
    from geostat_engine.io.samples import list_samples

    return [SampleInfo(**s) for s in list_samples()]


@router.post("/samples/{sample_id}/copy")
def copy_sample(sample_id: str) -> dict[str, str]:
    """샘플을 문서 폴더로 복사하고 그 경로를 돌려줌 (앱은 이 경로로 파일을 엶)."""
    from geostat_engine.io.samples import copy_sample as _copy

    return {"path": str(_copy(sample_id))}


# ---- 지도 이미지 저장 ---------------------------------------------------------------


class ImageSaveRequest(BaseModel):
    path: str
    data: str  # base64 PNG


@router.post("/save-image")
def save_image(body: ImageSaveRequest) -> dict[str, str]:
    """앱이 그린 지도 PNG를 파일로 씀 (웹뷰는 파일을 직접 쓸 수 없어 엔진이 대신 씀)."""
    import base64
    import binascii

    path = Path(body.path).expanduser()
    if path.suffix.lower() != ".png":
        path = path.with_suffix(".png")
    if not path.parent.exists():
        raise EngineError("folder_not_found", f"폴더가 없음: {path.parent}")
    try:
        data = base64.b64decode(body.data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise EngineError("invalid_image", "이미지 데이터가 올바르지 않음") from exc
    if not data.startswith(b"\x89PNG"):
        raise EngineError("invalid_image", "PNG 이미지가 아님")
    try:
        path.write_bytes(data)
    except OSError as exc:
        raise EngineError("write_failed", f"이미지를 저장하지 못함: {exc}") from exc
    return {"path": str(path)}
