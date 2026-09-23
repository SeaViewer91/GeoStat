#!/usr/bin/env bash
# PyInstaller로 빌드한 엔진 폴더 안의 모든 Mach-O 파일을 서명함
#
# 기본은 ad-hoc 서명(-)임. Apple Developer 인증서 없이 GitHub로 배포하는 현재 정책에 맞춤.
# Apple Silicon은 서명이 전혀 없는 바이너리를 실행하지 않으므로 ad-hoc 서명이라도 반드시 필요함.
#
# 나중에 공증이 필요해지면 APPLE_SIGNING_IDENTITY에 Developer ID를 넣으면 됨.
# 이때는 hardened runtime·타임스탬프·entitlements를 함께 적용함.
#
# 사용: packaging/macos/sign-engine.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENGINE_DIR="$ROOT/packaging/build/engine/geostat-engine"
ENTITLEMENTS="$ROOT/packaging/macos/entitlements.plist"
IDENTITY="${APPLE_SIGNING_IDENTITY:--}"

[[ -x "$ENGINE_DIR/geostat-engine" ]] || { echo "엔진 빌드가 없음. packaging/build-engine.sh를 먼저 실행해야 함" >&2; exit 1; }

if [[ "$IDENTITY" == "-" ]]; then
  echo "ad-hoc 서명함"
  OPTS=(--force --sign -)
  MAIN_OPTS=()
else
  echo "Developer ID로 서명함: $IDENTITY"
  OPTS=(--force --timestamp --options runtime --sign "$IDENTITY")
  MAIN_OPTS=(--entitlements "$ENTITLEMENTS")
fi

# 1. _internal 안의 Mach-O 파일(.so, .dylib, 확장자 없는 Python 라이브러리 등)을 안쪽부터 서명함
count=0
while IFS= read -r -d '' f; do
  if file -b "$f" | grep -q "Mach-O"; then
    codesign "${OPTS[@]}" "$f"
    count=$((count + 1))
  fi
done < <(find "$ENGINE_DIR/_internal" -type f -print0)
echo "내부 바이너리 ${count}개 서명함"

# 2. 주 실행 파일은 마지막에 서명함
codesign "${OPTS[@]}" "${MAIN_OPTS[@]}" "$ENGINE_DIR/geostat-engine"
codesign --verify --strict --verbose=2 "$ENGINE_DIR/geostat-engine"
echo "엔진 서명 완료"
