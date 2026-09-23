#!/usr/bin/env bash
# macOS 릴리스 빌드: 엔진 빌드 → 엔진 서명 → Tauri 앱 빌드·서명·공증 → .dmg 생성
#
# 필요 환경변수
#   APPLE_SIGNING_IDENTITY  "Developer ID Application: 이름 (TEAMID)"
#   공증용(택1)
#     APPLE_ID, APPLE_PASSWORD(앱 전용 암호), APPLE_TEAM_ID
#     APPLE_API_ISSUER, APPLE_API_KEY, APPLE_API_KEY_PATH
#   서명 없이 로컬 테스트용 번들만 만들려면 --unsigned 옵션을 줌
#
# 결과: apps/desktop/src-tauri/target/release/bundle/{macos,dmg}/
#
# ⚠️ 아직 실제 macOS 환경에서 검증하지 않은 초안임 (P0 과제)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
UNSIGNED=false
[[ "${1:-}" == "--unsigned" ]] && UNSIGNED=true

"$ROOT/packaging/build-engine.sh"

if $UNSIGNED; then
  echo "서명 생략 (--unsigned)"
  unset APPLE_SIGNING_IDENTITY APPLE_ID APPLE_PASSWORD APPLE_TEAM_ID || true
else
  "$ROOT/packaging/macos/sign-engine.sh"
fi

cd "$ROOT/apps/desktop"
npm ci
npm run tauri build -- --config src-tauri/tauri.bundle-engine.conf.json

echo "빌드 결과:"
ls -1 src-tauri/target/release/bundle/*/
