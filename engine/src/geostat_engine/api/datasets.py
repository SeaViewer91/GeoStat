"""데이터셋 열기·조회 API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import geopandas as gpd
import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pyproj import CRS, Transformer

from geostat_engine.auth import require_token
from geostat_engine.errors import EngineError
from geostat_engine.io.geoarrow import (
    ARROW_STREAM_MEDIA_TYPE,
    geometry_family,
    geometry_to_ipc,
    to_display_crs,
)
from geostat_engine.io.vector import read_vector
from geostat_engine.state import AppState, Dataset

router = APIRouter(prefix="/datasets", tags=["datasets"], dependencies=[Depends(require_token)])


# ---- 요청·응답 모델 ---------------------------------------------------------


class OpenRequest(BaseModel):
    path: str = Field(description="파일 절대 경로")
    layer: str | None = Field(default=None, description="레이어 이름. 없으면 첫 레이어를 엶")
    encoding: str | None = Field(default=None, description="속성 인코딩. 없으면 자동 판별함")


class CrsRequest(BaseModel):
    epsg: int = Field(description="지정할 EPSG 코드 (예: 5186)")


class CrsInfo(BaseModel):
    epsg: int | None
    name: str
    is_geographic: bool


class ColumnInfo(BaseModel):
    name: str
    dtype: str
    kind: Literal["numeric", "string", "boolean", "datetime", "other"]


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


class RowsResponse(BaseModel):
    offset: int
    total: int
    columns: list[str]
    rows: list[list]


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


def _info(ds: Dataset) -> DatasetInfo:
    gdf = ds.gdf
    geom_col = gdf.geometry.name
    columns = [
        ColumnInfo(name=str(c), dtype=str(gdf[c].dtype), kind=_column_kind(gdf[c]))
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
    )


# ---- 엔드포인트 --------------------------------------------------------------


@router.post("/open", response_model=DatasetInfo)
def open_dataset(body: OpenRequest, request: Request) -> DatasetInfo:
    result = read_vector(body.path, layer=body.layer, encoding=body.encoding)
    path = Path(body.path).expanduser()
    name = path.stem if len(result.layers) <= 1 else f"{path.stem}:{result.layer}"
    ds = _state(request).add(
        {
            "name": name,
            "path": path,
            "layer": result.layer,
            "encoding": result.encoding,
            "gdf": result.gdf,
            "layers": result.layers,
        }
    )
    return _info(ds)


@router.get("", response_model=list[DatasetInfo])
def list_datasets(request: Request) -> list[DatasetInfo]:
    return [_info(ds) for ds in _state(request).list()]


@router.get("/{dataset_id}", response_model=DatasetInfo)
def get_dataset(dataset_id: str, request: Request) -> DatasetInfo:
    return _info(_state(request).get(dataset_id))


@router.delete("/{dataset_id}", status_code=204)
def close_dataset(dataset_id: str, request: Request) -> Response:
    _state(request).remove(dataset_id)
    return Response(status_code=204)


@router.put("/{dataset_id}/crs", response_model=DatasetInfo)
def assign_crs(dataset_id: str, body: CrsRequest, request: Request) -> DatasetInfo:
    """좌표계가 없거나 잘못된 경우 좌표 변환 없이 CRS만 지정함."""
    ds = _state(request).get(dataset_id)
    try:
        crs = CRS.from_epsg(body.epsg)
    except Exception as exc:
        raise EngineError("invalid_crs", f"알 수 없는 EPSG 코드: {body.epsg}") from exc
    ds.gdf = ds.gdf.set_crs(crs, allow_override=True)
    ds.invalidate_display()
    return _info(ds)


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


@router.get("/{dataset_id}/rows", response_model=RowsResponse)
def get_rows(
    dataset_id: str,
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=5000),
) -> RowsResponse:
    """속성 테이블 일부를 반환함. 지오메트리 열은 제외함."""
    ds = _state(request).get(dataset_id)
    gdf = ds.gdf
    frame = pd.DataFrame(gdf.drop(columns=gdf.geometry.name)).iloc[offset : offset + limit]
    # NaN·Timestamp 등을 JSON 안전 값으로 바꾸기 위해 pandas 직렬화를 거침
    rows = json.loads(frame.to_json(orient="values", date_format="iso", force_ascii=False))
    return RowsResponse(
        offset=offset, total=len(gdf), columns=[str(c) for c in frame.columns], rows=rows
    )
