"""P1 기능: 단계구분, 테이블 정렬·필터, 계산 필드, 표 불러오기, 내보내기, 프로젝트."""

from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient


def _open(client: TestClient, auth: dict, path: Path, **extra) -> dict:
    r = client.post("/datasets/open", json={"path": str(path), **extra}, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def _classes(body: dict) -> np.ndarray:
    return np.frombuffer(base64.b64decode(body["classes"]), dtype="<i2")


def _ids(ids: list[int]) -> str:
    return base64.b64encode(np.asarray(ids, dtype="<u4").tobytes()).decode()


# ---- 단계구분 ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "n_classes", "scheme"),
    [
        ("quantile", 4, "sequential"),
        ("equal_interval", 4, "sequential"),
        ("natural_breaks", 4, "sequential"),
        ("std_mean", 6, "diverging"),
        ("percentile", 6, "diverging"),
        ("box_plot", 6, "diverging"),
    ],
)
def test_classify_numeric(client, auth, grid_gpkg, method, n_classes, scheme) -> None:
    ds = _open(client, auth, grid_gpkg)
    r = client.post(
        f"/datasets/{ds['id']}/classify",
        json={"column": "값", "method": method, "k": 4},
        headers=auth,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scheme"] == scheme
    assert len(body["labels"]) == len(body["counts"]) == n_classes
    classes = _classes(body)
    assert classes.size == 20 and classes.min() >= 0 and classes.max() < n_classes
    assert sum(body["counts"]) == 20


def test_classify_quantile_matches_ranks(client, auth, grid_gpkg) -> None:
    ds = _open(client, auth, grid_gpkg)
    body = client.post(
        f"/datasets/{ds['id']}/classify",
        json={"column": "정수", "method": "quantile", "k": 4},
        headers=auth,
    ).json()
    # 0~19 정수를 4분위로 나누면 5개씩 순서대로 들어가야 함
    assert _classes(body).tolist() == [i // 5 for i in range(20)]
    assert body["counts"] == [5, 5, 5, 5]


def test_classify_unique_and_missing(client, auth, tmp_path) -> None:
    path = tmp_path / "cat.gpkg"
    gdf = gpd.GeoDataFrame(
        {"구분": ["가", "나", "가", None]},
        geometry=gpd.points_from_xy([127, 127.1, 127.2, 127.3], [37, 37, 37, 37]),
        crs=4326,
    )
    gdf.to_file(path, engine="pyogrio")
    ds = _open(client, auth, path)
    body = client.post(
        f"/datasets/{ds['id']}/classify",
        json={"column": "구분", "method": "unique_values"},
        headers=auth,
    ).json()
    assert body["labels"] == ["가", "나"]
    assert body["counts"] == [2, 1]
    assert body["n_missing"] == 1
    assert _classes(body).tolist() == [0, 1, 0, -1]


def test_classify_rejects_text_column(client, auth, grid_gpkg) -> None:
    ds = _open(client, auth, grid_gpkg)
    r = client.post(
        f"/datasets/{ds['id']}/classify",
        json={"column": "이름", "method": "quantile"},
        headers=auth,
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "not_numeric"


# ---- 테이블 -----------------------------------------------------------------


def test_rows_sort_and_ids(client, auth, grid_gpkg) -> None:
    ds = _open(client, auth, grid_gpkg)
    url = f"/datasets/{ds['id']}/rows"
    body = client.post(
        url, json={"sort": "정수", "descending": True, "limit": 3}, headers=auth
    ).json()
    assert body["row_ids"] == [19, 18, 17]

    body = client.post(url, json={"ids": _ids([3, 10, 7]), "sort": "정수"}, headers=auth).json()
    assert body["total"] == 3
    assert body["row_ids"] == [3, 7, 10]

    r = client.post(url, json={"ids": _ids([99])}, headers=auth)
    assert r.status_code == 400


# ---- 계산 필드 --------------------------------------------------------------


def test_calculated_field(client, auth, grid_gpkg) -> None:
    ds = _open(client, auth, grid_gpkg)
    url = f"/datasets/{ds['id']}/fields"
    r = client.post(url, json={"name": "두배", "expression": "`값` * 2"}, headers=auth)
    assert r.status_code == 200, r.text
    col = next(c for c in r.json()["columns"] if c["name"] == "두배")
    assert col["derived"] and col["expression"] == "`값` * 2" and col["kind"] == "numeric"

    rows = client.post(f"/datasets/{ds['id']}/rows", json={"limit": 2}, headers=auth).json()
    assert rows["columns"][-1] == "두배" and rows["rows"][1][-1] == 2.0

    # 같은 이름의 계산 필드는 다시 계산함
    r = client.post(url, json={"name": "두배", "expression": "(`값` > 3) * 1"}, headers=auth)
    assert r.status_code == 200
    # 원본 열 이름은 덮어쓸 수 없음
    r = client.post(url, json={"name": "값", "expression": "1"}, headers=auth)
    assert r.json()["error"]["code"] == "name_exists"
    # 잘못된 식·위험한 구문
    for expr in ("`없는열` + 1", "__import__('os')"):
        r = client.post(url, json={"name": "x", "expression": expr}, headers=auth)
        assert r.json()["error"]["code"] == "invalid_expression"

    r = client.delete(f"{url}/두배", headers=auth)
    assert "두배" not in [c["name"] for c in r.json()["columns"]]


# ---- 표(CSV·엑셀) 불러오기 --------------------------------------------------


@pytest.fixture
def points_csv_cp949(tmp_path: Path) -> Path:
    path = tmp_path / "관측소.csv"
    pd.DataFrame(
        {
            "지점명": ["부산", "울산", "포항"],
            "경도": [129.04, 129.31, 129.37],
            "위도": [35.1, 35.54, 36.02],
        }
    ).to_csv(path, index=False, encoding="cp949")
    return path


def test_inspect_csv_guesses_columns(client, auth, points_csv_cp949) -> None:
    r = client.post("/files/inspect", json={"path": str(points_csv_cp949)}, headers=auth)
    body = r.json()
    assert body["kind"] == "table"
    t = body["table"]
    assert t["encoding"] == "CP949"
    assert (t["guess_x"], t["guess_y"], t["guess_epsg"]) == ("경도", "위도", 4326)
    assert t["sample"][0][0] == "부산"


def test_open_csv_points(client, auth, points_csv_cp949) -> None:
    r = client.post("/datasets/open", json={"path": str(points_csv_cp949)}, headers=auth)
    assert r.json()["error"]["code"] == "table_options_required"

    ds = _open(client, auth, points_csv_cp949, table={"x": "경도", "y": "위도", "epsg": 4326})
    assert ds["geometry_type"] == "point" and ds["n_rows"] == 3
    geom = client.get(f"/datasets/{ds['id']}/geometry", headers=auth)
    assert geom.status_code == 200


def test_open_xlsx_points_with_missing_coords(client, auth, tmp_path) -> None:
    path = tmp_path / "points.xlsx"
    df = pd.DataFrame(
        {"name": ["a", "b", "c"], "X": [200000, None, 201000], "Y": [550000, 1, 551000]}
    )
    with pd.ExcelWriter(path) as w:
        df.to_excel(w, sheet_name="관측", index=False)
    info = client.post("/files/inspect", json={"path": str(path)}, headers=auth).json()["table"]
    assert info["sheets"] == ["관측"] and info["guess_epsg"] == 5186

    ds = _open(client, auth, path, table={"x": "X", "y": "Y", "epsg": 5186})
    # 좌표 없는 행도 행 순서 유지를 위해 남김
    assert ds["n_rows"] == 3
    assert client.get(f"/datasets/{ds['id']}/geometry", headers=auth).status_code == 200


def test_inspect_vector_layers(client, auth, grid_gpkg) -> None:
    body = client.post("/files/inspect", json={"path": str(grid_gpkg)}, headers=auth).json()
    assert body == {"path": str(grid_gpkg), "kind": "vector", "layers": ["grid"], "table": None}


# ---- 내보내기 ---------------------------------------------------------------


def test_export_formats(client, auth, grid_shp_cp949, tmp_path) -> None:
    ds = _open(client, auth, grid_shp_cp949)
    client.post(
        f"/datasets/{ds['id']}/fields",
        json={"name": "인구밀도지수", "expression": "`값` / 2"},
        headers=auth,
    )
    url = f"/datasets/{ds['id']}/export"

    r = client.post(url, json={"path": str(tmp_path / "out.gpkg")}, headers=auth).json()
    back = gpd.read_file(r["path"])
    assert "인구밀도지수" in back.columns and back.crs.to_epsg() == 5186

    r = client.post(url, json={"path": str(tmp_path / "out.geojson")}, headers=auth).json()
    assert gpd.read_file(r["path"]).crs.to_epsg() == 4326
    assert r["warnings"]  # WGS84 자동 변환 안내

    r = client.post(
        url,
        json={"path": str(tmp_path / "out.shp"), "encoding": "CP949", "epsg": 5179},
        headers=auth,
    ).json()
    assert any("필드 이름" in w for w in r["warnings"])  # 인구밀도지수는 cp949로 12바이트임
    assert (tmp_path / "out.cpg").exists()
    assert gpd.read_file(r["path"]).crs.to_epsg() == 5179

    r = client.post(url, json={"path": str(tmp_path / "out.csv")}, headers=auth).json()
    text = (tmp_path / "out.csv").read_text(encoding="utf-8-sig")
    assert text.splitlines()[0] == "이름,값,정수,인구밀도지수"

    r = client.post(url, json={"path": str(tmp_path / "out.xyz")}, headers=auth)
    assert r.json()["error"]["code"] == "unsupported_format"


# ---- 프로젝트 ---------------------------------------------------------------


def test_project_roundtrip_after_moving_folder(client, auth, tmp_path, grid_shp_cp949) -> None:
    work = tmp_path / "work"
    work.mkdir()
    for f in grid_shp_cp949.parent.glob(grid_shp_cp949.stem + ".*"):
        shutil.copy(f, work / f.name)
    shp = work / grid_shp_cp949.name

    ds = _open(client, auth, shp)
    client.put(f"/datasets/{ds['id']}/crs", json={"epsg": 5186}, headers=auth)
    client.post(
        f"/datasets/{ds['id']}/fields", json={"name": "z", "expression": "`값` - 1"}, headers=auth
    )
    proj = work / "분석"
    r = client.post(
        "/project/save",
        json={
            "path": str(proj),
            "datasets": [{"id": ds["id"], "ui": {"style": "q5"}}],
            "ui": {"zoom": 9},
        },
        headers=auth,
    ).json()
    saved = Path(r["path"])
    assert saved.suffix == ".gstproj"
    data = json.loads(saved.read_text(encoding="utf-8"))
    assert data["datasets"][0]["source"]["path"] == shp.name  # 상대 경로로 저장됨

    # 폴더째 옮겨도 상대 경로로 다시 열림
    moved = tmp_path / "moved"
    shutil.move(str(work), moved)
    r = client.post("/project/open", json={"path": str(moved / saved.name)}, headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ui"] == {"zoom": 9}
    item = body["datasets"][0]
    assert item["error"] is None and item["ui"] == {"style": "q5"}
    assert "z" in [c["name"] for c in item["info"]["columns"]]
    assert item["info"]["encoding"] == "CP949"
    # 세션을 비우고 다시 열었으므로 데이터셋은 하나뿐임
    assert len(client.get("/datasets", headers=auth).json()) == 1


def test_project_missing_source_is_reported(client, auth, tmp_path, grid_gpkg) -> None:
    ds = _open(client, auth, grid_gpkg)
    proj = tmp_path / "p.gstproj"
    client.post(
        "/project/save", json={"path": str(proj), "datasets": [{"id": ds["id"]}]}, headers=auth
    )
    grid_gpkg.unlink()
    body = client.post("/project/open", json={"path": str(proj)}, headers=auth).json()
    assert body["datasets"][0]["info"] is None
    assert "원본 파일" in body["datasets"][0]["error"]
