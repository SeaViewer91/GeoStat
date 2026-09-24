"""래스터 API: 열기, 지도 타일, 오버뷰 만들기, 존 통계, 격자 만들기."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field

from geostat_engine import service
from geostat_engine.analysis import zonal
from geostat_engine.api.datasets import DatasetInfo, dataset_info
from geostat_engine.api.regression import JobInfo, _analysis_info, _jobs, _state
from geostat_engine.auth import require_token
from geostat_engine.errors import EngineError
from geostat_engine.io import raster as raster_io
from geostat_engine.state import RasterEntry

router = APIRouter(tags=["rasters"], dependencies=[Depends(require_token)])


class BandStats(BaseModel):
    min: float | None
    max: float | None
    p2: float | None
    p98: float | None
    mean: float | None
    std: float | None


class RasterInfo(BaseModel):
    id: str
    name: str
    path: str
    width: int
    height: int
    count: int
    dtype: str
    crs: str
    crs_name: str
    res: list[float]
    nodata: float | None
    bounds: list[float]
    bounds_wgs84: list[float]
    overviews: list[int]
    needs_overviews: bool
    band_names: list[str]
    stats: list[BandStats]
    categorical: bool


def raster_info(entry: RasterEntry) -> RasterInfo:
    return RasterInfo(id=entry.id, name=entry.name, path=str(entry.path), **entry.info)


class RasterOpenRequest(BaseModel):
    path: str
    name: str | None = None


@router.post("/rasters/open", response_model=RasterInfo)
def open_raster(body: RasterOpenRequest, request: Request) -> RasterInfo:
    return raster_info(service.open_raster(_state(request), body.path, name=body.name))


@router.get("/rasters", response_model=list[RasterInfo])
def list_rasters(request: Request) -> list[RasterInfo]:
    return [raster_info(r) for r in _state(request).list_rasters()]


@router.delete("/rasters/{raster_id}", status_code=204)
def close_raster(raster_id: str, request: Request) -> Response:
    _state(request).remove_raster(raster_id)
    return Response(status_code=204)


@router.post("/rasters/{raster_id}/overviews", response_model=RasterInfo)
def build_overviews(raster_id: str, request: Request) -> RasterInfo:
    """축소 표시를 빠르게 하려고 원본 옆에 .ovr 파일을 만듦."""
    entry = _state(request).get_raster(raster_id)
    raster_io.build_overviews(entry.path)
    entry.info = raster_io.describe(entry.path)
    return raster_info(entry)


@router.get("/rasters/{raster_id}/tiles/{z}/{x}/{y}.png")
def tile(
    raster_id: str,
    z: int,
    x: int,
    y: int,
    request: Request,
    bands: str = Query(default="1", description="쉼표로 구분한 밴드 번호 (3개면 RGB)"),
    vmin: str = Query(description="밴드별 최솟값 (쉼표 구분)"),
    vmax: str = Query(description="밴드별 최댓값 (쉼표 구분)"),
    colormap: str = "viridis",
    resampling: Literal["bilinear", "nearest"] = "bilinear",
) -> Response:
    entry = _state(request).get_raster(raster_id)
    try:
        band_list = [int(b) for b in bands.split(",")]
        lo = [float(v) for v in vmin.split(",")]
        hi = [float(v) for v in vmax.split(",")]
    except ValueError:
        raise EngineError("invalid_query", "밴드·범위 값이 숫자가 아님") from None
    if len(band_list) not in (1, 3) or len(lo) != len(band_list) or len(hi) != len(band_list):
        raise EngineError("invalid_query", "밴드는 1개 또는 3개(RGB)이고 범위 값 개수가 같아야 함")
    if any(not 1 <= b <= entry.info["count"] for b in band_list):
        raise EngineError("invalid_band", f"밴드 번호는 1~{entry.info['count']} 사이여야 함")
    png = raster_io.render_tile(
        entry.path,
        entry.info,
        z,
        x,
        y,
        bands=band_list,
        vmin=lo,
        vmax=hi,
        colormap=colormap,
        resampling=resampling,
    )
    if png is None:
        return Response(status_code=204)
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "max-age=60"})


# ---- 존 통계 ---------------------------------------------------------------------


class ZonalRequest(BaseModel):
    raster_id: str
    band: int = Field(default=1, ge=1)
    stats: list[str] = Field(default_factory=lambda: list(zonal.DEFAULT_STATS), min_length=1)
    prefix: str | None = None


@router.post("/datasets/{dataset_id}/zonal", response_model=JobInfo)
def start_zonal(dataset_id: str, body: ZonalRequest, request: Request) -> JobInfo:
    state = _state(request)
    ds = state.get(dataset_id)
    raster = state.get_raster(body.raster_id)
    # 프로젝트를 다시 열 때 래스터 경로로 재계산할 수 있게 경로·이름도 기록함
    spec: dict[str, Any] = {
        **body.model_dump(exclude_none=True),
        "raster_path": str(raster.path),
        "raster_name": raster.name,
    }
    payload = service.prepare_zonal(state, ds, spec)

    def on_done(result: dict[str, Any]) -> dict[str, Any]:
        record = service.apply_zonal(ds, spec, result)
        return {
            "info": dataset_info(ds).model_dump(),
            "analysis": _analysis_info(record).model_dump(),
        }

    job = _jobs(request).start(
        "zonal",
        payload,
        kind="zonal",
        title=f"존 통계: {raster.name} → {ds.name}",
        dataset_id=dataset_id,
        on_done=on_done,
    )
    return JobInfo(**job.public())


# ---- 격자 ------------------------------------------------------------------------


class FishnetRequest(BaseModel):
    dataset_id: str | None = Field(default=None, description="범위로 쓸 벡터 데이터셋")
    raster_id: str | None = Field(default=None, description="범위로 쓸 래스터")
    cell_size: float = Field(gt=0, description="셀 크기 (m). 육각형은 한 변 길이")
    shape: Literal["square", "hexagon"] = "square"
    clip: bool = Field(default=True, description="폴리곤 자료와 겹치는 셀만 남김")
    path: str = Field(description="저장할 GeoPackage 경로")
    name: str | None = None


@router.post("/grid/fishnet", response_model=DatasetInfo)
def fishnet(body: FishnetRequest, request: Request) -> DatasetInfo:
    if bool(body.dataset_id) == bool(body.raster_id):
        raise EngineError("invalid_source", "범위로 쓸 데이터셋이나 래스터 중 하나를 골라야 함")
    ds = service.make_fishnet(_state(request), body.model_dump())
    return dataset_info(ds)
