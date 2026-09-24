"""앱 버전을 한곳에서 바꾸고 확인하는 스크립트.

버전이 들어 있는 곳: tauri.conf.json, Cargo.toml, package.json, engine/pyproject.toml, 엔진 __init__.py
릴리스 워크플로는 태그(v1.2.3)와 이 버전들이 모두 같은지 확인함.

사용:
  python scripts/version.py              # 현재 버전 출력 (서로 다르면 오류)
  python scripts/version.py 1.0.0        # 모두 1.0.0으로 바꿈
  python scripts/version.py --check v1.0.0  # 태그와 같은지 확인 (릴리스 워크플로용)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "tauri.conf.json": ROOT / "apps/desktop/src-tauri/tauri.conf.json",
    "Cargo.toml": ROOT / "apps/desktop/src-tauri/Cargo.toml",
    "package.json": ROOT / "apps/desktop/package.json",
    "pyproject.toml": ROOT / "engine/pyproject.toml",
    "__init__.py": ROOT / "engine/src/geostat_engine/__init__.py",
}
# 파일마다 버전이 적힌 첫 줄의 패턴
PATTERNS = {
    "tauri.conf.json": r'("version":\s*")([^"]+)(")',
    "Cargo.toml": r'(?m)^(version\s*=\s*")([^"]+)(")',
    "package.json": r'("version":\s*")([^"]+)(")',
    "pyproject.toml": r'(?m)^(version\s*=\s*")([^"]+)(")',
    "__init__.py": r'(__version__\s*=\s*")([^"]+)(")',
}
SEMVER = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?$")


def current() -> dict[str, str]:
    out = {}
    for name, path in FILES.items():
        m = re.search(PATTERNS[name], path.read_text(encoding="utf-8"))
        if not m:
            raise SystemExit(f"{name}에서 버전을 찾지 못함")
        out[name] = m.group(2)
    return out


def set_version(version: str) -> None:
    if not SEMVER.match(version):
        raise SystemExit(f"버전 형식이 아님: {version} (예: 1.0.0)")
    for name, path in FILES.items():
        text = path.read_text(encoding="utf-8")
        new = re.sub(PATTERNS[name], rf"\g<1>{version}\g<3>", text, count=1)
        path.write_text(new, encoding="utf-8")
    print(f"버전을 {version}(으)로 바꿈. engine/uv.lock·Cargo.lock·package-lock.json도 갱신해야 함")


def main(argv: list[str]) -> None:
    if not argv:
        versions = current()
        for name, v in versions.items():
            print(f"{name:<16}{v}")
        if len(set(versions.values())) != 1:
            raise SystemExit("버전이 서로 다름")
    elif argv[0] == "--check":
        tag = argv[1].removeprefix("refs/tags/").removeprefix("v")
        versions = current()
        wrong = {k: v for k, v in versions.items() if v != tag}
        if wrong:
            raise SystemExit(f"태그 v{tag}와 버전이 다른 파일: {wrong}")
        print(f"버전 확인: {tag}")
    else:
        set_version(argv[0])


if __name__ == "__main__":
    main(sys.argv[1:])
