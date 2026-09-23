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
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main(exe: str) -> None:
    tmp = Path(tempfile.mkdtemp())
    shp = tmp / "한글_격자.shp"
    gpd.GeoDataFrame(
        {"이름": ["가", "나"]}, geometry=[box(200000, 550000, 201000, 551000), box(201000, 550000, 202000, 551000)], crs=5186
    ).to_file(shp, encoding="CP949", engine="pyogrio")
    shp.with_suffix(".cpg").unlink(missing_ok=True)

    t0 = time.time()
    proc = subprocess.Popen(
        [exe, "--exit-on-stdin-close", "--log-level", "warning"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        env={"GEOSTAT_ENGINE_TOKEN": TOKEN, "PATH": "/usr/bin:/bin"},
    )
    try:
        line = proc.stdout.readline()
        assert line.startswith(READY), f"준비 신호 없음: {line!r}"
        port = json.loads(line[len(READY):])["port"]
        print(f"준비 신호 수신 {time.time() - t0:.1f}초, 포트 {port}")

        health = call(port, "/health")
        print(f"health: {health}")

        info = call(port, "/datasets/open", {"path": str(shp)})
        assert info["encoding"] == "CP949", info
        minx, miny, _, _ = info["bounds_wgs84"]
        assert 126 < minx < 128 and 37 < miny < 38, info["bounds_wgs84"]
        rows = call(port, f"/datasets/{info['id']}/rows")
        assert rows["rows"][0][0] == "가", rows
        print("shapefile 열기·인코딩·좌표 변환 확인함")

        proc.stdin.close()
        assert proc.wait(timeout=10) == 0
        print("stdin 종료 동작 확인함\n스모크 테스트 통과")
    finally:
        if proc.poll() is None:
            proc.kill()


if __name__ == "__main__":
    main(sys.argv[1])
