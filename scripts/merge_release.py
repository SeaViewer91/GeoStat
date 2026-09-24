"""플랫폼별 빌드 결과(macOS·Windows)를 한 릴리스용으로 합침 (릴리스 워크플로용).

각 플랫폼 폴더에는 설치 파일, 업데이트 파일, 그 플랫폼만 담긴 latest.json, SHA256SUMS가 있음.
latest.json의 platforms를 합치고 SHA256SUMS를 이어 붙여 출력 폴더에 모음.

사용: python scripts/merge_release.py <출력 폴더> <플랫폼 폴더> [<플랫폼 폴더> ...]
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def main(out: Path, parts: list[Path]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    manifest: dict | None = None
    sums: list[str] = []
    for part in parts:
        for f in sorted(part.iterdir()):
            if f.name == "latest.json":
                data = json.loads(f.read_text(encoding="utf-8"))
                if manifest is None:
                    manifest = data
                else:
                    if data["version"] != manifest["version"]:
                        raise SystemExit(
                            f"플랫폼별 버전이 다름: {data['version']} / {manifest['version']}"
                        )
                    manifest["platforms"].update(data["platforms"])
            elif f.name == "SHA256SUMS":
                sums += [
                    line
                    for line in f.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            else:
                shutil.copy2(f, out / f.name)
    if manifest is not None:
        (out / "latest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print("업데이트 대상 플랫폼:", ", ".join(sorted(manifest["platforms"])))
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    for f in sorted(out.iterdir()):
        print(f"{f.stat().st_size / 1_048_576:10.1f} MB  {f.name}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), [Path(p) for p in sys.argv[2:]])
