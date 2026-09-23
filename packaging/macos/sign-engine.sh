#!/usr/bin/env bash
# PyInstaller로 빌드한 엔진 폴더 안의 모든 Mach-O 파일을 Developer ID로 서명함
#
# Tauri는 앱 번들의 resources 안에 있는 바이너리를 서명하지 않으므로, tauri build 전에 이 스크립트로
# 미리 서명해야 공증(notarization)을 통과함. 안쪽 라이브러리부터 서명하고 주 실행 파일은 마지막에 서명함.
#
# 사용:
#   export APPLE_SIGNING_IDENTITY="Developer ID Application: 이름 (TEAMID)"
#   packaging/macos/sign-engine.sh
#
# ⚠️ 아직 실제 macOS 환경에서 검증하지 않은 초안임 (P0 과제)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENGINE_DIR="$ROOT/packaging/build/engine/geostat-engine"
ENTITLEMENTS="$ROOT/packaging/macos/entitlements.plist"
: "${APPLE_SIGNING_IDENTITY:?APPLE_SIGNING_IDENTITY 환경변수가 필요함}"

[[ -x "$ENGINE_DIR/geostat-engine" ]] || { echo "엔진 빌드가 없음. packaging/build-engine.sh를 먼저 실행해야 함" >&2; exit 1; }

sign() {
  codesign --force --timestamp --options runtime --sign "$APPLE_SIGNING_IDENTITY" "$@"
}

# 1. _internal 안의 Mach-O 파일(.so, .dylib, 확장자 없는 Python 라이브러리 등)을 모두 서명함
count=0
while IFS= read -r -d '' f; do
  if file -b "$f" | grep -q "Mach-O"; then
    sign "$f"
    count=$((count + 1))
  fi
done < <(find "$ENGINE_DIR/_internal" -type f -print0)
echo "내부 바이너리 ${count}개 서명함"

# 2. 주 실행 파일은 entitlements와 함께 서명함
sign --entitlements "$ENTITLEMENTS" "$ENGINE_DIR/geostat-engine"
codesign --verify --strict --verbose=2 "$ENGINE_DIR/geostat-engine"
echo "엔진 서명 완료"
