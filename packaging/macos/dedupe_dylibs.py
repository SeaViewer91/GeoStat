"""macOS 휠의 .dylibs 폴더에 든 동적 라이브러리 이름을 패키지마다 고유하게 바꿈.

문제: pyproj·pyogrio·rasterio 휠은 각자 PROJ·GDAL 등을 delocate로 `<패키지>/.dylibs/`에 넣어 옴.
파일 이름이 같으면(예: libproj.25.9.8.1.dylib) PyInstaller가 하나로 합쳐 버려서,
pyproj가 rasterio의 libproj(기호 이름을 바꿔 빌드한 것)를 불러오다 "Symbol not found"로 죽음.

해결: 번들 빌드 전용 가상환경에서 `<패키지>/.dylibs/libX.dylib` → `<패키지>/.dylibs/<패키지>_libX.dylib`로
이름을 바꾸고, 그 패키지 안의 모든 Mach-O 파일이 참조하는 경로를 install_name_tool로 고친 뒤 ad-hoc 서명함.
(개발용 가상환경이나 uv 캐시는 건드리지 않도록 build-engine.sh가 복사 방식의 별도 환경에서만 부름)

사용: python dedupe_dylibs.py <site-packages 경로>
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def macho_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() and p.suffix in (".so", ".dylib")]


def deps(path: Path) -> list[str]:
    out = subprocess.run(
        ["otool", "-L", str(path)], capture_output=True, text=True, check=True
    ).stdout
    # 첫 줄은 파일 이름, 이후 줄은 "\t<경로> (compatibility ...)"
    return [
        line.strip().split(" (")[0] for line in out.splitlines()[1:] if line.strip()
    ]


def run(*args: str) -> None:
    subprocess.run(args, check=True, capture_output=True)


def main(site: Path) -> None:
    changed_total = 0
    for dylibs in sorted(site.glob("*/.dylibs")):
        pkg_dir = dylibs.parent
        prefix = pkg_dir.name.replace("-", "_")
        rename = {}
        for lib in sorted(dylibs.iterdir()):
            if lib.suffix == ".dylib" and not lib.name.startswith(prefix + "_"):
                rename[lib.name] = f"{prefix}_{lib.name}"
        if not rename:
            continue
        for old, new in rename.items():
            (dylibs / old).rename(dylibs / new)
        for f in macho_files(pkg_dir):
            args: list[str] = []
            if f.parent == dylibs and f.name in rename.values():
                args += ["-id", f"@rpath/{f.name}"]
            for dep in deps(f):
                name = dep.rsplit("/", 1)[-1]
                if name in rename:
                    args += ["-change", dep, dep[: -len(name)] + rename[name]]
            if args:
                run("install_name_tool", *args, str(f))
                run("codesign", "--force", "--sign", "-", str(f))
                changed_total += 1
        print(f"{pkg_dir.name}: 라이브러리 {len(rename)}개 이름 변경")
    print(f"Mach-O 파일 {changed_total}개 수정·재서명함")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
