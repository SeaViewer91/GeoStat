"""데이터셋 열기·조회·변경 API."""

from __future__ import annotations

import base64
import json
from typing import Any, Literal

import geopandas as gpd
import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pyproj import CRS, Transformer

from geostat_engine import service
from geostat_engine.analysis.classify import classify
from geostat_engine.auth import require_token
from geostat_engine.errors import EngineError
from geostat_engine.io.export import export_dataset
from geostat_engine.io.geoarrow import (
    ARROW_STREAM_MEDIA_TYPE,
    geometry_family,
    geometry_to_ipc,
    to_display_crs,
)
from geostat_engine.state import AppState, Dataset

router = APIRouter(prefix="/datasets", tags=["datasets"], dependencies=[Depends(require_token)])


# ---- 요청·응답 모델 ---------------------------------------------------------


class TableOptions(BaseModel):
    x: str = Field(description="X(경도) 열 이름")
    y: str = Field(description="Y(위도) 열 이름")
    epsg: int = Field(description="좌표 열의 좌표계")
    sheet: str | None = Field(default=None, description="엑셀 시트 이름")


class OpenRequest(BaseModel):
    path: str = Field(description="파일 절대 경로")
    layer: str | None = Field(default=None, description="레이어 이름. 없으면 첫 레이어를 엶")
    encoding: str | None = Field(default=None, description="속성 인코딩. 없으면 자동 판별함")
    table: TableOptions | None = Field(default=None, description="CSV·엑셀일 때 좌표 열 지정")


class CrsRequest(BaseModel):
    epsg: int = Field(description="지정할 EPSG 코드 (예: 5186)")


class FieldRequest(BaseModel):
    name: str
    expression: str = Field(description="pandas eval 식. 한글 열 이름은 `백틱`으로 감쌈")


class ClassifyRequest(BaseModel):
    column: str
    method: Literal[
        "quantile",
        "equal_interval",
        "natural_breaks",
        "std_mean",
        "percentile",
        "box_plot",
        "unique_values",
    ]
    k: int = Field(default=5, ge=2, le=12, description="계급 수 (분위·등간격·자연 분류만 해당)")


class RowsRequest(BaseModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=200, ge=1, le=5000)
    sort: str | None = Field(default=None, description="정렬 열 이름")
    descending: bool = False
    ids: str | None = Field(
        default=None, description="이 행 번호들만 조회 (Uint32 리틀엔디언 배열의 base64)"
    )


class ExportRequest(BaseModel):
    path: str
    epsg: int | None = Field(default=None, description="저장할 좌표계. 없으면 현재 좌표계 유지")
    encoding: str | None = Field(default=None, description="shapefile 인코딩 (UTF-8 또는 CP949)")


class CrsInfo(BaseModel):
    epsg: int | None
    name: str
    is_geographic: bool


class ColumnInfo(BaseModel):
    name: str
    dtype: str
    kind: Literal["numeric", "string", "boolean", "datetime", "other"]
    derived: bool = False
    expression: str | None = None


class DatasetInfo(BaseModel):
    id: str
    name: str
    path: str
    layer: str | None
    layers: list[str]
    encoding: str | None
    n_rows: int
    geometry_type: Literal["point", "line", "polygon"]
    crs: CrsInfo | None
    bounds_wgs84: tuple[float, float, float, float] | None
    columns: list[ColumnInfo]
    table: dict[str, Any] | None = None


class RowsResponse(BaseModel):
    offset: int
    total: int
    columns: list[str]
    row_ids: list[int]
    rows: list[list]


class ClassifyResponse(BaseModel):
    column: str
    method: str
    scheme: Literal["sequential", "diverging", "qualitative"]
    breaks: list[float]
    labels: list[str]
    counts: list[int]
    n_missing: int
    classes: str = Field(
        description="피처별 계급 번호. Int16 리틀엔디언 배열의 base64 (-1 = 값 없음)"
    )


class ExportResponse(BaseModel):
    path: str
    format: str
    n_rows: int
    warnings: list[str]


# ---- 헬퍼 -------------------------------------------------------------------


def _state(request: Request) -> AppState:
    return request.app.state.geostat


def _column_kind(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_string_dtype(series) or series.dtype == object:
        return "string"
    return "other"


def _crs_info(crs: CRS | None) -> CrsInfo | None:
    if crs is None:
        return None
    return CrsInfo(epsg=crs.to_epsg(), name=crs.name, is_geographic=crs.is_geographic)


def _bounds_wgs84(gdf: gpd.GeoDataFrame) -> tuple[float, float, float, float] | None:
    minx, miny, maxx, maxy = (float(v) for v in gdf.total_bounds)
    if not np.all(np.isfinite([minx, miny, maxx, maxy])):
        return None
    if gdf.crs is None:
        looks_geographic = -180 <= minx <= maxx <= 180 and -90 <= miny <= maxy <= 90
        return (minx, miny, maxx, maxy) if looks_geographic else None
    if gdf.crs.to_epsg() == 4326:
        return (minx, miny, maxx, maxy)
    # 전체 지오메트리 변환 없이 범위만 변환함 (densify로 곡률 오차 보정)
    tf = Transformer.from_crs(gdf.crs, 4326, always_xy=True)
    return tuple(float(v) for v in tf.transform_bounds(minx, miny, maxx, maxy, densify_pts=21))


def dataset_info(ds: Dataset) -> DatasetInfo:
    gdf = ds.gdf
    geom_col = gdf.geometry.name
    derived = {f.name: f.expression for f in ds.fields}
    columns = [
        ColumnInfo(
            name=str(c),
            dtype=str(gdf[c].dtype),
            kind=_column_kind(gdf[c]),
            derived=c in derived,
            expression=derived.get(c),
        )
        for c in gdf.columns
        if c != geom_col
    ]
    return DatasetInfo(
        id=ds.id,
        name=ds.name,
        path=str(ds.path),
        layer=ds.layer,
        layers=ds.layers,
        encoding=ds.encoding,
        n_rows=len(gdf),
        geometry_type=geometry_family(gdf),
        crs=_crs_info(gdf.crs),
        bounds_wgs84=_bounds_wgs84(gdf),
        columns=columns,
        table=ds.table,
    )


def _column(ds: Dataset, name: str) -> pd.Series:
    if name not in ds.gdf.columns or name == ds.gdf.geometry.name:
        raise EngineError("column_not_found", f"열이 없음: {name}")
    return ds.gdf[name]


def _decode_ids(encoded: str, n_rows: int) -> np.ndarray:
    try:
        ids = np.frombuffer(base64.b64decode(encoded), dtype="<u4")
    except Exception as exc:
        raise EngineError("invalid_ids", "행 번호 목록을 해석할 수 없음") from exc
    if ids.size and ids.max() >= n_rows:
        raise EngineError("invalid_ids", "범위를 벗어난 행 번호가 있음")
    return ids


# ---- 엔드포인트 --------------------------------------------------------------


@router.post("/open", response_model=DatasetInfo)
def open_dataset(body: OpenRequest, request: Request) -> DatasetInfo:
    ds = service.open_source(
        _state(request),
        body.path,
        layer=body.layer,
        encoding=body.encoding,
        table=body.table.model_dump() if body.table else None,
    )
    return dataset_info(ds)


@router.get("", response_model=list[DatasetInfo])
def list_datasets(request: Request) -> list[DatasetInfo]:
    return [dataset_info(ds) for ds in _state(request).list()]


@router.get("/{dataset_id}", response_model=DatasetInfo)
def get_dataset(dataset_id: str, request: Request) -> DatasetInfo:
    return dataset_info(_state(request).get(dataset_id))


@router.delete("/{dataset_id}", status_code=204)
def close_dataset(dataset_id: str, request: Request) -> Response:
    _state(request).remove(dataset_id)
    return Response(status_code=204)


@router.put("/{dataset_id}/crs", response_model=DatasetInfo)
def assign_crs(dataset_id: str, body: CrsRequest, request: Request) -> DatasetInfo:
    """좌표계가 없거나 잘못된 경우 좌표 변환 없이 CRS만 지정함."""
    ds = _state(request).get(dataset_id)
    service.assign_crs(ds, body.epsg)
    return dataset_info(ds)


@router.get("/{dataset_id}/geometry")
def get_geometry(dataset_id: str, request: Request) -> Response:
    ds = _state(request).get(dataset_id)
    if ds._display is None:
        ds._display = to_display_crs(ds.gdf)
    payload = geometry_to_ipc(ds._display)
    return Response(
        content=payload,
        media_type=ARROW_STREAM_MEDIA_TYPE,
        headers={"X-GeoStat-Rows": str(len(ds.gdf))},
    )


@router.post("/{dataset_id}/rows", response_model=RowsResponse)
def query_rows(dataset_id: str, body: RowsRequest, request: Request) -> RowsResponse:
    """속성 테이블 일부를 반환함. 정렬·행 번호 필터(선택 항목만 보기)를 지원함."""
    ds = _state(request).get(dataset_id)
    gdf = ds.gdf
    frame = pd.DataFrame(gdf.drop(columns=gdf.geometry.name))

    order = np.arange(len(frame))
    if body.ids is not None:
        order = _decode_ids(body.ids, len(frame))
    if body.sort:
        col = _column(ds, body.sort).iloc[order]
        # 안정 정렬로 같은 값끼리는 원래 순서를 유지하고, 값 없음(NaN)은 항상 뒤로 보냄
        ranked = col.sort_values(ascending=not body.descending, kind="stable", na_position="last")
        order = order[col.index.get_indexer(ranked.index)] if len(order) else order

    page = order[body.offset : body.offset + body.limit]
    sub = frame.iloc[page]
    # NaN·Timestamp 등을 JSON 안전 값으로 바꾸기 위해 pandas 직렬화를 거침
    rows = json.loads(sub.to_json(orient="values", date_format="iso", force_ascii=False))
    return RowsResponse(
        offset=body.offset,
        total=len(order),
        columns=[str(c) for c in frame.columns],
        row_ids=[int(i) for i in page],
        rows=rows,
    )


@router.post("/{dataset_id}/classify", response_model=ClassifyResponse)
def classify_column(dataset_id: str, body: ClassifyRequest, request: Request) -> ClassifyResponse:
    ds = _state(request).get(dataset_id)
    result = classify(_column(ds, body.column), body.method, k=body.k)
    return ClassifyResponse(
        column=result.column,
        method=result.method,
        scheme=result.scheme,
        breaks=result.breaks,
        labels=result.labels,
        counts=result.counts,
        n_missing=result.n_missing,
        classes=base64.b64encode(result.classes.astype("<i2").tobytes()).decode("ascii"),
    )


@router.post("/{dataset_id}/fields", response_model=DatasetInfo)
def add_field(dataset_id: str, body: FieldRequest, request: Request) -> DatasetInfo:
    ds = _state(request).get(dataset_id)
    service.set_field(ds, body.name, body.expression)
    return dataset_info(ds)


@router.delete("/{dataset_id}/fields/{name}", response_model=DatasetInfo)
def delete_field(dataset_id: str, name: str, request: Request) -> DatasetInfo:
    ds = _state(request).get(dataset_id)
    service.remove_field(ds, name)
    return dataset_info(ds)


@router.post("/{dataset_id}/export", response_model=ExportResponse)
def export(dataset_id: str, body: ExportRequest, request: Request) -> ExportResponse:
    ds = _state(request).get(dataset_id)
    result = export_dataset(ds.gdf, body.path, epsg=body.epsg, encoding=body.encoding)
    return ExportResponse(**result)
