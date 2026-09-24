"""대용량 성능 측정 스크립트 (개발 계획서 3.7 성능 목표 확인용).

엔진 API를 같은 프로세스에서 호출해 단계별 시간을 잼. 네트워크·화면 그리기 시간은 빠짐.
자료는 임의 점의 보로노이 폴리곤(실제 행정구역처럼 이웃 수가 제각각인 모양)으로 만듦.

실행: cd engine && uv run python ../scripts/benchmark.py [--n 100000] [--gwr-n 10000] [--skip-gwr]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely

warnings.simplefilter("ignore")

TOKEN = "bench"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def voronoi_polygons(n: int, seed: int = 0) -> gpd.GeoDataFrame:
    """n개 보로노이 폴리곤. 값은 평활한 잡음이라 공간 자기상관이 있음 (EPSG:5179, 약 100 km 범위)."""
    rng = np.random.default_rng(seed)
    size = 100_000.0
    pts = rng.uniform(0, size, (n, 2)) + [900_000, 1_700_000]
    polys = shapely.voronoi_polygons(shapely.multipoints(pts), extend_to=shapely.box(*pts.min(0), *pts.max(0)))
    polys = shapely.get_parts(polys)
    frame = shapely.box(*pts.min(0), *pts.max(0))
    polys = shapely.intersection(polys, frame)
    c = shapely.centroid(polys)
    x, y = shapely.get_x(c), shapely.get_y(c)
    field = np.sin(x / 7000) + np.cos(y / 9000) + rng.normal(0, 0.5, len(polys))
    return gpd.GeoDataFrame(
        {"value": field, "x1": rng.normal(size=len(polys)), "x2": x / 1e5 + rng.normal(0, 0.1, len(polys))},
        geometry=polys,
        crs=5179,
    )


class Timer:
    def __init__(self) -> None:
        self.rows: list[tuple[str, float, str]] = []

    def run(self, label: str, fn, target: str = ""):
        t0 = time.perf_counter()
        out = fn()
        dt = time.perf_counter() - t0
        self.rows.append((label, dt, target))
        print(f"  {label:<40}{dt:8.2f}초  {target}", flush=True)
        return out


def wait_job(client, job_id: str) -> dict:
    while True:
        job = client.get(f"/jobs/{job_id}", headers=AUTH).json()
        if job["status"] != "running":
            assert job["status"] == "done", job
            return job
        time.sleep(0.2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100_000)
    ap.add_argument("--gwr-n", type=int, default=10_000)
    ap.add_argument("--skip-gwr", action="store_true")
    args = ap.parse_args()

    from fastapi.testclient import TestClient

    from geostat_engine.server import create_app

    tmp = Path(tempfile.mkdtemp(prefix="geostat-bench-"))
    print(f"자료 생성 중 (보로노이 {args.n:,}개)…", flush=True)
    gdf = voronoi_polygons(args.n)
    path = tmp / "bench.gpkg"
    gdf.to_file(path, layer="bench", engine="pyogrio")

    client = TestClient(create_app(token=TOKEN))
    t = Timer()
    print(f"\n[{len(gdf):,}개 폴리곤]")
    ds = t.run(
        "열기 (GeoPackage 읽기)",
        lambda: client.post("/datasets/open", json={"path": str(path)}, headers=AUTH).json(),
        "목표: 열기+지오메트리 < 5초",
    )
    geo = t.run("지오메트리 전송 (GeoArrow IPC)", lambda: client.get(f"/datasets/{ds['id']}/geometry", headers=AUTH))
    print(f"    지오메트리 {len(geo.content) / 1e6:,.1f} MB")
    t.run(
        "주제도 분류 (자연 분류 5단계)",
        lambda: client.post(
            f"/datasets/{ds['id']}/classify",
            json={"column": "value", "method": "natural_breaks", "k": 5},
            headers=AUTH,
        ).json(),
    )
    w = t.run(
        "Queen 가중치",
        lambda: client.post(f"/datasets/{ds['id']}/weights", json={"type": "queen"}, headers=AUTH).json(),
        "목표: < 10초",
    )
    t.run(
        "LISA (순열 999회)",
        lambda: client.post(
            f"/datasets/{ds['id']}/esda/local",
            json={"method": "lisa", "column": "value", "weights_id": w["id"], "permutations": 999},
            headers=AUTH,
        ).json(),
        "목표: < 30초",
    )

    if not args.skip_gwr:
        small = gdf.sample(n=min(args.gwr_n, len(gdf)), random_state=1)
        spath = tmp / "gwr.gpkg"
        small.to_file(spath, layer="gwr", engine="pyogrio")
        sds = client.post("/datasets/open", json={"path": str(spath)}, headers=AUTH).json()
        print(f"\n[GWR {len(small):,}개]")

        def gwr():
            job = client.post(
                f"/datasets/{sds['id']}/regression",
                json={"model": "gwr", "y": "value", "x": ["x1", "x2"]},
                headers=AUTH,
            ).json()
            return wait_job(client, job["id"])

        t.run("GWR (적응 bisquare, AICc 대역폭 탐색)", gwr, "목표: < 1분")

    print("\n| 작업 | 시간(초) | 목표 |\n|---|---:|---|")
    for label, dt, target in t.rows:
        print(f"| {label} | {dt:.2f} | {target.replace('목표: ', '')} |")
    import os

    print(f"\nCPU {os.cpu_count()}개, Python {sys.version.split()[0]}")


if __name__ == "__main__":
    main()
