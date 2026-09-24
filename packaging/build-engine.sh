#!/usr/bin/env bash
# 엔진을 PyInstaller onedir로 빌드하고 기본 동작을 확인함
#
# 결과: packaging/build/engine/geostat-engine/geostat-engine (Windows는 .exe)
# macOS·Linux·Windows(Git Bash) 공통
# 사용: packaging/build-engine.sh [--skip-smoke-test]
set -euo pipefail
# Windows 콘솔 기본 인코딩(cp1252 등)에서도 한글 출력이 깨지지 않게 함
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/packaging/build"

cd "$ROOT/engine"
if [[ "$(uname)" == "Darwin" ]]; then
  # macOS: 휠마다 들고 오는 같은 이름의 dylib(libproj 등)이 번들에서 충돌하지 않도록
  # 번들 전용 가상환경을 복사 방식으로 만들고 dylib 이름을 패키지별로 바꿈 (개발 환경·uv 캐시는 그대로 둠)
  export UV_PROJECT_ENVIRONMENT="$OUT/venv"
  export UV_LINK_MODE=copy
  rm -rf "$OUT/venv"
  uv sync --group build --frozen 2>/dev/null || uv sync --group build
  SITE="$(uv run python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
  uv run python "$ROOT/packaging/macos/dedupe_dylibs.py" "$SITE"
else
  uv sync --group build --frozen 2>/dev/null || uv sync --group build
fi

rm -rf "$OUT/engine" "$OUT/work"
uv run pyinstaller "$ROOT/packaging/engine.spec" \
  --distpath "$OUT/engine" \
  --workpath "$OUT/work" \
  --noconfirm \
  --log-level WARN

EXE="$OUT/engine/geostat-engine/geostat-engine"
case "$(uname -s)" in MINGW* | MSYS* | CYGWIN*) EXE="$EXE.exe" ;; esac  # Windows(Git Bash)
echo "빌드 완료: $EXE ($(du -sh "$OUT/engine/geostat-engine" | cut -f1))"

if [[ "${1:-}" != "--skip-smoke-test" ]]; then
  uv run python "$ROOT/packaging/smoke_test.py" "$EXE"
fi
