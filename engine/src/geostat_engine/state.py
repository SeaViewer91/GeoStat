"""엔진 세션 상태. 불러온 데이터셋을 메모리에 보관함."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import geopandas as gpd

from geostat_engine.errors import NotFound


@dataclass
class DerivedField:
    """계산 필드. 프로젝트를 다시 열 때 같은 식으로 재계산해 재현성을 확보함."""

    name: str
    expression: str


@dataclass
class WeightsEntry:
    """공간가중치. spec으로 다시 만들 수 있으므로 프로젝트에는 spec만 저장함."""

    id: str
    name: str
    spec: dict[str, Any]
    description: str
    w: Any = field(repr=False)
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisRecord:
    """결과를 열로 저장한 분석 (LISA 등). 프로젝트를 다시 열 때 같은 설정으로 재실행함."""

    id: str
    method: str
    params: dict[str, Any]
    outputs: list[str]
    description: str
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class Dataset:
    id: str
    name: str
    path: Path
    layer: str | None
    encoding: str | None
    gdf: gpd.GeoDataFrame
    layers: list[str] = field(default_factory=list)
    # CSV·엑셀처럼 좌표 열로 점을 만든 경우의 옵션 (x, y, crs, sheet)
    table: dict[str, Any] | None = None
    # 사용자가 직접 지정한 EPSG (원본 .prj를 덮어씀)
    crs_override: int | None = None
    fields: list[DerivedField] = field(default_factory=list)
    weights: dict[str, WeightsEntry] = field(default_factory=dict)
    analyses: list[AnalysisRecord] = field(default_factory=list)
    # 표시용 WGS84 사본과 대표점. 첫 요청 때 만들고 CRS가 바뀌면 비움
    _display: gpd.GeoDataFrame | None = field(default=None, repr=False)

    def invalidate_display(self) -> None:
        self._display = None

    def get_weights(self, weights_id: str) -> WeightsEntry:
        try:
            return self.weights[weights_id]
        except KeyError:
            raise NotFound("weights_not_found", f"공간가중치가 없음: {weights_id}") from None

    def source_spec(self) -> dict[str, Any]:
        """원본을 다시 여는 데 필요한 정보 (프로젝트 저장용)."""
        return {
            "path": str(self.path),
            "layer": self.layer,
            "encoding": self.encoding,
            "table": self.table,
        }


class AppState:
    def __init__(self) -> None:
        self._datasets: dict[str, Dataset] = {}
        self._lock = threading.Lock()

    def add(self, ds_kwargs: dict) -> Dataset:
        ds = Dataset(id=uuid.uuid4().hex[:12], **ds_kwargs)
        with self._lock:
            self._datasets[ds.id] = ds
        return ds

    def get(self, dataset_id: str) -> Dataset:
        try:
            return self._datasets[dataset_id]
        except KeyError:
            raise NotFound("dataset_not_found", f"데이터셋이 없음: {dataset_id}") from None

    def remove(self, dataset_id: str) -> None:
        with self._lock:
            self._datasets.pop(dataset_id, None)

    def list(self) -> list[Dataset]:
        return list(self._datasets.values())

    def clear(self) -> None:
        with self._lock:
            self._datasets.clear()
