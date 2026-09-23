#!/usr/bin/env bash
# 엔진을 PyInstaller onedir로 빌드하고 기본 동작을 확인함
#
# 결과: packaging/build/engine/geostat-engine/geostat-engine
# 사용: packaging/build-engine.sh [--skip-smoke-test]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/packaging/build"

cd "$ROOT/engine"
uv sync --group build --frozen 2>/dev/null || uv sync --group build

rm -rf "$OUT/engine" "$OUT/work"
uv run pyinstaller "$ROOT/packaging/engine.spec" \
  --distpath "$OUT/engine" \
  --workpath "$OUT/work" \
  --noconfirm \
  --log-level WARN

EXE="$OUT/engine/geostat-engine/geostat-engine"
echo "빌드 완료: $EXE ($(du -sh "$OUT/engine/geostat-engine" | cut -f1))"

if [[ "${1:-}" != "--skip-smoke-test" ]]; then
  uv run python "$ROOT/packaging/smoke_test.py" "$EXE"
fi
