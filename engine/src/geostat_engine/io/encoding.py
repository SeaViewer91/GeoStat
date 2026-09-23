"""Shapefile DBF 문자 인코딩 판별.

국내 shp는 .cpg 없이 cp949(EUC-KR 확장)로 저장된 경우가 많음. GDAL은 .cpg가 없으면
DBF 헤더의 LDID 값을 보고 판단하는데, 대부분 LDID가 비어 있어 ISO-8859-1로 읽혀 한글이 깨짐.
따라서 .cpg가 없을 때는 DBF 레코드 일부를 직접 읽어 UTF-8 → CP949 순으로 디코딩을 시도함.
"""

from __future__ import annotations

import struct
from pathlib import Path

# 판별에 쓸 최대 바이트 수. 수십만 행 파일도 앞부분만 보면 충분함
_SAMPLE_BYTES = 512 * 1024

# .cpg에 흔히 적히는 값 → GDAL/Python 인코딩 이름
_CPG_ALIASES = {
    "utf-8": "UTF-8",
    "utf8": "UTF-8",
    "65001": "UTF-8",
    "cp949": "CP949",
    "949": "CP949",
    "euc-kr": "CP949",
    "euckr": "CP949",
    "ks_c_5601-1987": "CP949",
}


def _sibling(path: Path, suffix: str) -> Path | None:
    # 확장자 대소문자가 섞인 경우(.DBF, .Cpg 등)도 찾음
    for cand in (path.with_suffix(suffix), path.with_suffix(suffix.upper())):
        if cand.exists():
            return cand
    for cand in path.parent.glob(path.stem + ".*"):
        if cand.suffix.lower() == suffix:
            return cand
    return None


def read_cpg(shp_path: Path) -> str | None:
    """.cpg 파일이 있으면 그 내용을 정규화해 반환함."""
    cpg = _sibling(shp_path, ".cpg")
    if cpg is None:
        return None
    raw = cpg.read_text(encoding="ascii", errors="ignore").strip()
    if not raw:
        return None
    return _CPG_ALIASES.get(raw.lower(), raw)


def detect_dbf_encoding(dbf_path: Path) -> str | None:
    """DBF 레코드 영역을 표본 추출해 인코딩을 추정함.

    반환값
      - "UTF-8" / "CP949": 비ASCII 문자가 있고 해당 인코딩으로 문제없이 디코딩됨
      - None: 전부 ASCII이거나 판별 불가 → GDAL 기본 동작에 맡김
    """
    with dbf_path.open("rb") as f:
        header = f.read(32)
        if len(header) < 32:
            return None
        n_records = struct.unpack("<I", header[4:8])[0]
        header_len, record_len = struct.unpack("<HH", header[8:12])
        if n_records == 0 or record_len <= 1:
            return None
        f.seek(header_len)
        n_sample = max(1, min(n_records, _SAMPLE_BYTES // record_len))
        data = f.read(n_sample * record_len)

    records = [data[i : i + record_len] for i in range(0, len(data), record_len)]
    non_ascii = [r for r in records if any(b >= 0x80 for b in r)]
    if not non_ascii:
        return None

    for enc in ("utf-8", "cp949"):
        failures = sum(1 for r in non_ascii if not _decodes(r, enc))
        # 필드 폭 때문에 다바이트 문자가 잘린 레코드가 드물게 있으므로 1% 이하 실패는 허용함
        if failures <= max(1, len(non_ascii) // 100):
            return "UTF-8" if enc == "utf-8" else "CP949"
    return None


def _decodes(raw: bytes, enc: str) -> bool:
    try:
        raw.decode(enc)
        return True
    except UnicodeDecodeError:
        return False


def resolve_shapefile_encoding(shp_path: Path) -> str | None:
    """.cpg → DBF 표본 판별 순으로 인코딩을 결정함. None이면 GDAL 기본값을 씀."""
    cpg = read_cpg(shp_path)
    if cpg:
        return cpg
    dbf = _sibling(shp_path, ".dbf")
    if dbf is None:
        return None
    return detect_dbf_encoding(dbf)
