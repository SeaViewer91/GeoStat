"""엔진 세션 상태. 불러온 데이터셋을 메모리에 보관함."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd

from geostat_engine.errors import NotFound


@dataclass
class Dataset:
    id: str
    name: str
    path: Path
    layer: str | None
    encoding: str | None
    gdf: gpd.GeoDataFrame
    layers: list[str] = field(default_factory=list)
    # 표시용 WGS84 사본. 첫 요청 때 만들고 CRS가 바뀌면 비움
    _display: gpd.GeoDataFrame | None = field(default=None, repr=False)

    def invalidate_display(self) -> None:
        self._display = None


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
