"""파일을 열기 전에 내용을 살펴보는 API (레이어 목록, 표의 좌표 열 추정)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from geostat_engine.auth import require_token
from geostat_engine.errors import EngineError
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
    kind: Literal["vector", "table"]
    layers: list[str] = []
    table: TableInfo | None = None


@router.post("/inspect", response_model=InspectResponse)
def inspect(body: InspectRequest) -> InspectResponse:
    path = Path(body.path).expanduser()
    if not path.exists():
        raise EngineError("file_not_found", f"파일이 없음: {path}")
    if is_table(path):
        info = inspect_table(path, encoding=body.encoding, sheet=body.sheet)
        return InspectResponse(path=str(path), kind="table", table=TableInfo(**info.__dict__))
    return InspectResponse(path=str(path), kind="vector", layers=list_layers(path))
