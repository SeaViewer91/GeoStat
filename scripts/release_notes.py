"""CHANGELOG.md에서 한 버전의 변경 내용을 뽑아 출력함 (릴리스 노트·업데이트 알림용).

사용: python scripts/release_notes.py 0.9.0
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"


def notes(version: str) -> str:
    text = CHANGELOG.read_text(encoding="utf-8")
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", text, re.M | re.S)
    if not m:
        raise SystemExit(f"CHANGELOG.md에 {version} 항목이 없음")
    return m.group(1).strip()


if __name__ == "__main__":
    print(notes(sys.argv[1].removeprefix("v")))
