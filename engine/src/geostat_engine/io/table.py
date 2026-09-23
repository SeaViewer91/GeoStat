"""좌표 열이 있는 표(CSV·엑셀) 읽기.

국내 CSV는 엑셀에서 저장한 cp949 파일이 많으므로 UTF-8(BOM 포함) → CP949 순으로 시도함.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS

from geostat_engine.errors import EngineError

TABLE_EXTENSIONS = {".csv", ".tsv", ".txt", ".xlsx", ".xls"}

# 열 이름으로 X(경도)·Y(위도)를 추정할 때 쓰는 패턴. 앞쪽일수록 우선함
_X_PATTERNS = [
    r"^x$",
    r"^lon(gitude)?$",
    r"^lng$",
    r"경도",
    r"x좌표",
    r"^x[_ ]?coord",
    r"^coord[_ ]?x$",
    r"^x",
]
_Y_PATTERNS = [
    r"^y$",
    r"^lat(itude)?$",
    r"위도",
    r"y좌표",
    r"^y[_ ]?coord",
    r"^coord[_ ]?y$",
    r"^y",
]

_SAMPLE_ROWS = 20


@dataclass
class TableInspection:
    encoding: str | None
    sheets: list[str]
    sheet: str | None
    columns: list[dict]
    sample: list[list]
    n_rows: int
    guess_x: str | None
    guess_y: str | None
    guess_epsg: int | None


def is_table(path: Path) -> bool:
    return path.suffix.lower() in TABLE_EXTENSIONS


def _read_csv(path: Path, encoding: str | None) -> tuple[pd.DataFrame, str]:
    sep = "\t" if path.suffix.lower() == ".tsv" else None  # None이면 구분자를 자동 추정함
    candidates = [encoding] if encoding else ["utf-8-sig", "cp949"]
    last_error: Exception | None = None
    for enc in candidates:
        try:
            df = pd.read_csv(path, sep=sep, engine="python", encoding=enc)
            return df, "UTF-8" if enc.lower().startswith("utf") else enc.upper()
        except UnicodeDecodeError as exc:
            last_error = exc
        except Exception as exc:
            raise EngineError("read_failed", f"CSV를 읽지 못함: {exc}") from exc
    raise EngineError("encoding_unknown", f"인코딩을 판별하지 못함: {last_error}")


def read_dataframe(
    path: Path, encoding: str | None = None, sheet: str | None = None
) -> tuple[pd.DataFrame, str | None, list[str], str | None]:
    """표 파일을 읽어 (데이터프레임, 인코딩, 시트 목록, 사용한 시트)를 반환함."""
    if not path.exists():
        raise EngineError("file_not_found", f"파일이 없음: {path}")
    if path.suffix.lower() in {".xlsx", ".xls"}:
        try:
            book = pd.ExcelFile(path)
        except Exception as exc:
            raise EngineError("read_failed", f"엑셀 파일을 읽지 못함: {exc}") from exc
        sheets = [str(s) for s in book.sheet_names]
        sheet = sheet or sheets[0]
        if sheet not in sheets:
            raise EngineError("sheet_not_found", f"시트가 없음: {sheet}", sheets=sheets)
        return book.parse(sheet), None, sheets, sheet
    df, enc = _read_csv(path, encoding)
    return df, enc, [], None


def _guess(columns: list[str], patterns: list[str], numeric: set[str]) -> str | None:
    for pat in patterns:
        for c in columns:
            if c in numeric and re.search(pat, c.strip().lower()):
                return c
    return None


def _guess_epsg(df: pd.DataFrame, x: str | None, y: str | None) -> int | None:
    if not x or not y:
        return None
    xs = pd.to_numeric(df[x], errors="coerce")
    ys = pd.to_numeric(df[y], errors="coerce")
    both = xs.notna() & ys.notna()  # 한쪽 좌표만 있는 행은 추정에서 뺌
    xs, ys = xs[both], ys[both]
    if xs.empty:
        return None
    if xs.between(-180, 180).all() and ys.between(-90, 90).all():
        return 4326
    # 국내 TM 좌표 범위로 보이면 가장 흔한 중부원점(5186)을 제안함. 확정은 사용자가 함
    if xs.between(100_000, 700_000).all() and ys.between(100_000, 800_000).all():
        return 5186
    if xs.between(700_000, 1_400_000).all() and ys.between(1_400_000, 2_300_000).all():
        return 5179
    return None


def inspect_table(
    path: Path, encoding: str | None = None, sheet: str | None = None
) -> TableInspection:
    df, enc, sheets, used_sheet = read_dataframe(path, encoding, sheet)
    columns = [str(c) for c in df.columns]
    df.columns = columns
    numeric = {c for c in columns if pd.api.types.is_numeric_dtype(df[c])}
    gx = _guess(columns, _X_PATTERNS, numeric)
    gy = _guess([c for c in columns if c != gx], _Y_PATTERNS, numeric)
    sample = df.head(_SAMPLE_ROWS).astype(object).where(df.head(_SAMPLE_ROWS).notna(), None)
    return TableInspection(
        encoding=enc,
        sheets=sheets,
        sheet=used_sheet,
        columns=[{"name": c, "numeric": c in numeric} for c in columns],
        sample=[[_jsonable(v) for v in row] for row in sample.itertuples(index=False)],
        n_rows=len(df),
        guess_x=gx,
        guess_y=gy,
        guess_epsg=_guess_epsg(df, gx, gy),
    )


def _jsonable(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, (pd.Timestamp,)):
        return v.isoformat()
    return v


def read_table_points(
    path: Path,
    x: str,
    y: str,
    epsg: int,
    encoding: str | None = None,
    sheet: str | None = None,
) -> tuple[gpd.GeoDataFrame, str | None, str | None]:
    """좌표 열로 점 레이어를 만듦. 좌표가 비었거나 숫자가 아닌 행도 행 순서 유지를 위해 빈 점으로 남김."""
    df, enc, _sheets, used_sheet = read_dataframe(path, encoding, sheet)
    df.columns = [str(c) for c in df.columns]
    for col in (x, y):
        if col not in df.columns:
            raise EngineError("column_not_found", f"열이 없음: {col}")
    try:
        crs = CRS.from_epsg(epsg)
    except Exception as exc:
        raise EngineError("invalid_crs", f"알 수 없는 EPSG 코드: {epsg}") from exc
    xs = pd.to_numeric(df[x], errors="coerce")
    ys = pd.to_numeric(df[y], errors="coerce")
    if xs.notna().sum() == 0:
        raise EngineError("no_coordinates", "좌표 값이 있는 행이 없음")
    geom = gpd.points_from_xy(xs, ys)
    geom[(xs.isna() | ys.isna()).to_numpy()] = None
    gdf = gpd.GeoDataFrame(df, geometry=geom, crs=crs)
    return gdf, enc, used_sheet
