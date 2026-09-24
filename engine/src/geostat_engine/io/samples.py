"""앱에 포함된 샘플 데이터 목록 (도움말 → 샘플 데이터 열기)."""

from __future__ import annotations

from pathlib import Path

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "samples"

SAMPLES: list[dict[str, str]] = [
    {
        "id": "georgia",
        "file": "georgia.gpkg",
        "name": "조지아 교육 수준 (GWR 예제)",
        "description": "카운티 159개. PctBach ~ PctRural + PctFB + PctBlack으로 GWR·MGWR 연습",
    },
    {
        "id": "nc_sids",
        "file": "nc_sids.gpkg",
        "name": "노스캐롤라이나 영아 돌연사 (ESDA 예제)",
        "description": "카운티 100개. SIDR74·SIDR79 비율로 Moran's I·LISA 연습",
    },
    {
        "id": "seoul_grid",
        "file": "seoul_grid.shp",
        "name": "서울 가상 격자 (한글 속성)",
        "description": "500 m 격자 900개, cp949 인코딩. 인구·소득·녹지율은 가상 값",
    },
    {
        "id": "terrain",
        "file": "terrain.tif",
        "name": "서울 가상 지형 (래스터)",
        "description": "25 m 해상도 가상 고도. 격자 만들기·존 통계 연습",
    },
]


def list_samples() -> list[dict[str, str]]:
    out = []
    for s in SAMPLES:
        path = SAMPLE_DIR / s["file"]
        if path.exists():
            out.append({**s, "path": str(path)})
    return out


def user_sample_dir() -> Path:
    """샘플을 복사해 둘 사용자 폴더. 앱 번들 안의 원본은 읽기 전용이라 여기로 복사해서 엶."""
    import os

    override = os.environ.get("GEOSTAT_SAMPLE_DIR")
    return Path(override) if override else Path.home() / "Documents" / "GeoStat" / "샘플 데이터"


def copy_sample(sample_id: str) -> Path:
    """샘플을 사용자 폴더로 복사하고 경로를 돌려줌. 이미 있으면 그대로 씀 (사용자가 고친 내용 보존)."""
    import shutil

    from geostat_engine.errors import EngineError, NotFound

    entry = next((s for s in SAMPLES if s["id"] == sample_id), None)
    if entry is None:
        raise NotFound("sample_not_found", f"샘플이 없음: {sample_id}")
    src = SAMPLE_DIR / entry["file"]
    dest_dir = user_sample_dir()
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        # 셰이프파일은 같은 이름의 .dbf·.shx·.prj 등을 함께 복사함
        for f in SAMPLE_DIR.glob(f"{src.stem}.*"):
            target = dest_dir / f.name
            if not target.exists():
                shutil.copy2(f, target)
    except OSError as exc:
        raise EngineError("sample_copy_failed", f"샘플을 복사하지 못함: {exc}") from exc
    return dest_dir / entry["file"]
