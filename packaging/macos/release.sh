#!/usr/bin/env bash
# macOS 릴리스 빌드: 엔진 빌드 → 엔진 서명 → Tauri 앱 빌드 → .dmg 생성
#
# 기본은 ad-hoc 서명임 (Apple Developer 인증서 불필요, GitHub Releases 배포용).
# 받은 사람은 첫 실행 때 "그래도 열기"를 한 번 해야 함 (README 설치 안내 참고).
#
# 결과: apps/desktop/src-tauri/target/release/bundle/{macos,dmg}/
# 사용: packaging/macos/release.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

"$ROOT/packaging/build-engine.sh"
"$ROOT/packaging/macos/sign-engine.sh"

cd "$ROOT/apps/desktop"
npm ci
npm run tauri build -- --config src-tauri/tauri.bundle-engine.conf.json

echo "빌드 결과:"
ls -1 src-tauri/target/release/bundle/*/
