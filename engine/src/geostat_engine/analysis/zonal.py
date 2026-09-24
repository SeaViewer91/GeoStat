"""존 통계: 폴리곤마다 래스터 값을 요약해 속성 열로 붙임 (exactextract).

exactextract는 폴리곤이 걸친 셀의 면적 비율로 가중해 계산하므로, 셀보다 작은 폴리곤도 값을 얻음.
폴리곤은 엔진 프로세스에서 래스터 좌표계로 변환해 넘기고, 계산은 작업 프로세스에서 나눠서 함.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from geostat_engine.errors import EngineError

# 앱에서 고르는 통계 이름 → (exactextract 연산, 결과 열 접미사, 한글 이름)
STATS: dict[str, tuple[str, str, str]] = {
    "mean": ("mean", "MEAN", "평균"),
    "sum": ("sum", "SUM", "합계"),
    "min": ("min", "MIN", "최솟값"),
    "max": ("max", "MAX", "최댓값"),
    "stdev": ("stdev", "STD", "표준편차"),
    "median": ("median", "MEDIAN", "중앙값"),
    "q25": ("quantile(q=0.25)", "Q25", "하위 25%"),
    "q75": ("quantile(q=0.75)", "Q75", "상위 25%"),
    "count": ("count", "COUNT", "셀 수(면적 가중)"),
    "majority": ("majority", "MAJORITY", "최빈값"),
    "variety": ("variety", "VARIETY", "값 종류 수"),
}
DEFAULT_STATS = ("mean", "min", "max", "stdev", "count")
# 작업 진행률을 알리려고 이만큼씩 나눠 계산함
CHUNK = 5000

Progress = Callable[[float | None, str], None]


def prepare(gdf, raster, spec: dict[str, Any]) -> dict[str, Any]:
    if gdf.crs is None:
        raise EngineError("missing_crs", "좌표계가 없는 데이터는 래스터와 겹쳐 볼 수 없음")
    geom_types = set(gdf.geom_type.dropna().unique())
    if not geom_types or not geom_types <= {"Polygon", "MultiPolygon"}:
        raise EngineError("not_polygon", "존 통계는 폴리곤 데이터에만 쓸 수 있음")
    stats = list(dict.fromkeys(spec.get("stats") or DEFAULT_STATS))
    unknown = [s for s in stats if s not in STATS]
    if unknown:
        raise EngineError("invalid_stat", f"알 수 없는 통계: {', '.join(unknown)}")
    band = int(spec.get("band") or 1)
    if not 1 <= band <= raster.info["count"]:
        raise EngineError("invalid_band", f"밴드 번호는 1~{raster.info['count']} 사이여야 함")
    geoms = gdf.geometry.to_crs(raster.info["crs"])
    return {
        "raster_path": str(raster.path),
        "band": band,
        "stats": stats,
        "geometry": geoms.reset_index(drop=True),
    }


def run(payload: dict[str, Any], progress: Progress) -> dict[str, Any]:
    import geopandas as gpd
    import rasterio
    from exactextract import exact_extract
    from exactextract.raster import RasterioRasterSource

    stats = payload["stats"]
    ops = [STATS[s][0] for s in stats]
    geoms = payload["geometry"]
    n = len(geoms)
    parts: dict[str, list[np.ndarray]] = {STATS[s][1]: [] for s in stats}
    with rasterio.open(payload["raster_path"]) as src:
        source = RasterioRasterSource(src, payload["band"])
        for start in range(0, n, CHUNK):
            progress(start / n, f"존 통계 계산 중 ({start:,}/{n:,})")
            chunk = gpd.GeoDataFrame(
                geometry=geoms.iloc[start : start + CHUNK].values, crs=geoms.crs
            )
            df = exact_extract(source, chunk, ops, output="pandas")
            # exactextract 결과 열 이름은 연산 이름과 같음 (quantile은 quantile_25 형태)
            for s, col in zip(stats, df.columns, strict=True):
                parts[STATS[s][1]].append(df[col].to_numpy(dtype="float64"))
    columns = {key: np.concatenate(values) for key, values in parts.items()}
    # 래스터 밖이거나 값 없는 셀만 걸친 폴리곤은 평균 등이 NaN이 됨
    empty = (
        int(np.isnan(columns[STATS[stats[0]][1]]).sum())
        if "count" not in stats
        else int((columns["COUNT"] == 0).sum())
    )
    return {"columns": columns, "summary": {"n": n, "n_empty": empty}}
