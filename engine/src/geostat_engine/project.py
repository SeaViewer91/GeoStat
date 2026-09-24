"""프로젝트 파일(.gstproj) 저장·열기.

프로젝트 파일은 JSON이며 데이터 자체는 담지 않고 "원본 경로 + 적용한 작업"만 기록함.
열 때는 원본을 다시 읽고 좌표계 지정·계산 필드를 순서대로 재적용하므로 분석 과정을 재현할 수 있음.
원본 경로는 프로젝트 파일 기준 상대 경로와 절대 경로를 함께 저장해, 폴더째 옮겨도 열리게 함.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from geostat_engine import __version__
from geostat_engine.errors import EngineError
from geostat_engine.state import Dataset

FORMAT = "geostat-project"
VERSION = 1
EXTENSION = ".gstproj"


def build_project(
    project_path: Path, datasets: list[tuple[Dataset, Any]], ui: Any
) -> dict[str, Any]:
    base = project_path.parent
    entries = []
    for ds, ds_ui in datasets:
        source = ds.source_spec()
        abs_path = Path(source["path"]).resolve()
        try:
            rel = os.path.relpath(abs_path, base.resolve())
        except ValueError:  # 드라이브가 다른 경우 (Windows)
            rel = None
        entries.append(
            {
                "name": ds.name,
                "source": {**source, "path": rel or str(abs_path), "abs_path": str(abs_path)},
                "crs_override": ds.crs_override,
                "fields": [{"name": f.name, "expression": f.expression} for f in ds.fields],
                "weights": [
                    {"id": e.id, "name": e.name, "spec": _portable_spec(e.spec, base)}
                    for e in ds.weights.values()
                ],
                "analyses": [
                    {
                        "id": a.id,
                        "method": a.method,
                        "params": a.params,
                        "outputs": a.outputs,
                        **({"report": a.summary["report"]} if "report" in a.summary else {}),
                    }
                    for a in ds.analyses
                ],
                "ui": ds_ui,
            }
        )
    return {
        "format": FORMAT,
        "version": VERSION,
        "app_version": __version__,
        "saved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "datasets": entries,
        "ui": ui,
    }


def _portable_spec(spec: dict[str, Any], base: Path) -> dict[str, Any]:
    """가중치 파일 경로는 프로젝트 기준 상대 경로로 바꿔 저장함."""
    if spec.get("type") != "file":
        return spec
    abs_path = Path(spec["path"]).resolve()
    try:
        rel = os.path.relpath(abs_path, base.resolve())
    except ValueError:
        rel = str(abs_path)
    return {**spec, "path": rel, "abs_path": str(abs_path)}


def write_project(path: Path, project: dict[str, Any]) -> None:
    if path.suffix.lower() != EXTENSION:
        path = path.with_suffix(EXTENSION)
    try:
        path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        raise EngineError("write_failed", f"프로젝트를 저장하지 못함: {exc}") from exc


def read_project(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise EngineError("file_not_found", f"파일이 없음: {path}") from None
    except (OSError, json.JSONDecodeError) as exc:
        raise EngineError("invalid_project", f"프로젝트 파일을 읽지 못함: {exc}") from exc
    if data.get("format") != FORMAT:
        raise EngineError("invalid_project", "GeoStat 프로젝트 파일이 아님")
    if int(data.get("version", 0)) > VERSION:
        raise EngineError("unsupported_version", "더 새로운 버전의 GeoStat에서 만든 프로젝트임")
    return data


def resolve_source_path(project_path: Path, source: dict[str, Any]) -> Path:
    """상대 경로 → 절대 경로 순으로 존재하는 원본 파일을 찾음."""
    candidates = [project_path.parent / source.get("path", ""), Path(source.get("abs_path", ""))]
    for cand in candidates:
        if str(cand) and cand.exists():
            return cand.resolve()
    raise EngineError("source_missing", f"원본 파일을 찾을 수 없음: {source.get('abs_path')}")


# ---- 결과 캐시 ------------------------------------------------------------------
# 회귀(특히 MGWR)·군집(AZP 등)은 다시 계산하는 데 오래 걸리므로 결과 열을 프로젝트 옆 폴더에 Parquet으로 저장함.
# 열 때 행 수와 열 이름이 맞으면 캐시를 쓰고, 없거나 맞지 않으면 다시 계산함.


CACHED_METHODS = ("regression", "cluster")


def cache_dir(project_path: Path) -> Path:
    return project_path.with_suffix(".gstcache")


def write_cache(project_path: Path, datasets: list[Dataset]) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    folder = cache_dir(project_path)
    for index, ds in enumerate(datasets):
        cols = [c for a in ds.analyses if a.method in CACHED_METHODS for c in a.outputs]
        target = folder / f"dataset{index}.parquet"
        if not cols:
            target.unlink(missing_ok=True)
            continue
        folder.mkdir(exist_ok=True)
        table = pa.table({c: ds.gdf[c].to_numpy() for c in cols})
        pq.write_table(table, target)


def read_cache(
    project_path: Path, index: int, n_rows: int, columns: list[str]
) -> dict[str, Any] | None:
    import pyarrow.parquet as pq

    target = cache_dir(project_path) / f"dataset{index}.parquet"
    if not target.exists():
        return None
    try:
        table = pq.read_table(target, columns=columns)
    except Exception:  # noqa: BLE001 - 파일이 깨졌거나 열이 없으면 다시 계산함
        return None
    if table.num_rows != n_rows:
        return None
    return {c: table.column(c).to_numpy() for c in columns}
