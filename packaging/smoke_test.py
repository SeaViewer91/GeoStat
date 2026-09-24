"""빌드된 엔진 실행 파일의 기본 동작 확인.

확인 항목: 준비 신호, /health, cp949 shapefile 열기, EPSG:5186→4326 변환, stdin 종료.
사용: python smoke_test.py <엔진 실행 파일 경로>
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

READY = "GEOSTAT_ENGINE_READY "
TOKEN = "smoke"


def call(port: int, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def main(exe: str) -> None:
    tmp = Path(tempfile.mkdtemp())
    shp = tmp / "한글_격자.shp"
    # 6×6 격자 (국지 통계는 5개, GWR은 20개 이상 필요함)
    cells = [
        box(200000 + i * 1000, 550000 + j * 1000, 201000 + i * 1000, 551000 + j * 1000)
        for j in range(6)
        for i in range(6)
    ]
    gpd.GeoDataFrame(
        {
            "이름": ["가"] + ["나"] * 35,
            "값": [float(v % 7) + v * 0.1 for v in range(36)],
            "X좌표": [float(v % 6) for v in range(36)],
        },
        geometry=cells,
        crs=5186,
    ).to_file(shp, encoding="CP949", engine="pyogrio")
    shp.with_suffix(".cpg").unlink(missing_ok=True)

    t0 = time.time()
    proc = subprocess.Popen(
        [exe, "--exit-on-stdin-close", "--log-level", "warning"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env={
            "GEOSTAT_ENGINE_TOKEN": TOKEN,
            "PATH": "/usr/bin:/bin",
            "GEOSTAT_SAMPLE_DIR": str(tmp / "samples"),
        },
    )
    try:
        line = proc.stdout.readline()
        assert line.startswith(READY), f"준비 신호 없음: {line!r}"
        port = json.loads(line[len(READY) :])["port"]
        print(f"준비 신호 수신 {time.time() - t0:.1f}초, 포트 {port}")

        health = call(port, "/health")
        print(f"health: {health}")

        info = call(port, "/datasets/open", {"path": str(shp)})
        assert info["encoding"] == "CP949", info
        minx, miny, _, _ = info["bounds_wgs84"]
        assert 126 < minx < 128 and 37 < miny < 38, info["bounds_wgs84"]
        rows = call(port, f"/datasets/{info['id']}/rows", {})
        assert rows["rows"][0][0] == "가", rows
        print("shapefile 열기·인코딩·좌표 변환 확인함")

        for method in ("quantile", "natural_breaks", "box_plot"):
            body = call(
                port,
                f"/datasets/{info['id']}/classify",
                {"column": "값", "method": method, "k": 2},
            )
            assert body["counts"], body
        print("단계 구분(mapclassify) 확인함")

        w = call(port, f"/datasets/{info['id']}/weights", {"type": "rook"})
        assert w["summary"]["n"] == 36, w
        lisa = call(
            port,
            f"/datasets/{info['id']}/esda/local",
            {
                "method": "lisa",
                "column": "값",
                "weights_id": w["id"],
                "permutations": 99,
            },
        )
        assert lisa["outputs"] == ["LISA_I", "LISA_CL", "LISA_P"], lisa
        print("공간가중치·LISA(libpysal, esda, numba) 확인함")

        # 회귀는 별도 작업 프로세스(multiprocessing spawn)에서 돌아가므로 번들에서 따로 확인함
        wid = {"weights_id": w["id"]}
        for model, extra in (("ols", wid), ("lag_gm", wid), ("gwr", wid)):
            job = call(
                port,
                f"/datasets/{info['id']}/regression",
                {"model": model, "y": "값", "x": ["X좌표"], **extra},
            )
            t_job = time.time()
            while job["status"] == "running" and time.time() - t_job < 120:
                time.sleep(0.3)
                job = call(port, f"/jobs/{job['id']}")
            assert job["status"] == "done", job
            fit = job["result"]["analysis"]["report"]["fit"]
            assert fit["moran_i"] is not None, fit  # 잔차 Moran's I (esda) 자동 계산
        print("회귀 작업 프로세스(spreg, mgwr) 확인함")

        for method in ("skater", "azp", "kmeans"):
            job = call(
                port,
                f"/datasets/{info['id']}/cluster",
                {
                    "method": method,
                    "variables": ["값", "X좌표"],
                    "n_clusters": 3,
                    **wid,
                },
            )
            t_job = time.time()
            while job["status"] == "running" and time.time() - t_job < 120:
                time.sleep(0.3)
                job = call(port, f"/jobs/{job['id']}")
            assert job["status"] == "done", job
            assert job["result"]["analysis"]["report"]["k"] == 3
        print("군집 작업 프로세스(spopt, scikit-learn) 확인함")

        # 래스터: 격자와 같은 범위의 GeoTIFF → 타일 PNG, 존 통계(exactextract), 격자 만들기
        import numpy as np
        import rasterio
        from rasterio.transform import from_origin

        tif = tmp / "고도.tif"
        with rasterio.open(
            tif,
            "w",
            driver="GTiff",
            width=600,
            height=600,
            count=1,
            dtype="float32",
            crs="EPSG:5186",
            transform=from_origin(200000, 556000, 10, 10),
            nodata=-9999,
        ) as dst:
            dst.write(np.tile(np.arange(600, dtype="float32"), (600, 1)), 1)
        r = call(port, "/rasters/open", {"path": str(tif)})
        assert r["count"] == 1 and r["crs"] == "EPSG:5186", r
        import math

        lon = (r["bounds_wgs84"][0] + r["bounds_wgs84"][2]) / 2
        lat = (r["bounds_wgs84"][1] + r["bounds_wgs84"][3]) / 2
        tx = int((lon + 180) / 360 * 4096)
        ty = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * 4096)
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/rasters/{r['id']}/tiles/12/{tx}/{ty}.png?vmin=0&vmax=599",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            png = resp.read()
            assert resp.status == 200 and png[:4] == b"\x89PNG", resp.status
        ovr = call(port, f"/rasters/{r['id']}/overviews", {})
        assert ovr["overviews"], ovr
        job = call(
            port,
            f"/datasets/{info['id']}/zonal",
            {"raster_id": r["id"], "stats": ["mean"]},
        )
        t_job = time.time()
        while job["status"] == "running" and time.time() - t_job < 120:
            time.sleep(0.3)
            job = call(port, f"/jobs/{job['id']}")
        assert job["status"] == "done", job
        grid = call(
            port,
            "/grid/fishnet",
            {
                "raster_id": r["id"],
                "cell_size": 1000,
                "shape": "hexagon",
                "path": str(tmp / "hex.gpkg"),
            },
        )
        assert grid["n_rows"] > 0, grid
        print("래스터 타일·오버뷰·존 통계·격자(rasterio, exactextract) 확인함")

        samples = call(port, "/files/samples")
        assert len(samples) == 4, samples
        for sample in samples:
            path = call(port, f"/files/samples/{sample['id']}/copy", {})["path"]
            if sample["id"] == "terrain":
                call(port, "/rasters/open", {"path": path})
            else:
                call(port, "/datasets/open", {"path": path})
        print("샘플 데이터 4종 복사·열기 확인함")

        csv = tmp / "점.csv"
        csv.write_text("이름,경도,위도\n가,129.0,35.1\n", encoding="cp949")
        insp = call(port, "/files/inspect", {"path": str(csv)})
        assert insp["table"]["guess_x"] == "경도", insp
        xlsx = tmp / "점.xlsx"
        import pandas as pd

        pd.DataFrame({"x": [127.0], "y": [37.0]}).to_excel(xlsx, index=False)
        insp = call(port, "/files/inspect", {"path": str(xlsx)})
        assert insp["table"]["guess_epsg"] == 4326, insp
        print("CSV·엑셀 불러오기 확인함")

        proc.stdin.close()
        assert proc.wait(timeout=10) == 0
        print("stdin 종료 동작 확인함\n스모크 테스트 통과")
    finally:
        if proc.poll() is None:
            proc.kill()


if __name__ == "__main__":
    main(sys.argv[1])
