#!/usr/bin/env bash
# macOS 릴리스 빌드: 엔진 빌드 → 엔진 서명 → Tauri 앱 빌드 → .dmg·업데이트 파일 정리
#
# 기본은 ad-hoc 서명임 (Apple Developer 인증서 불필요, GitHub Releases 배포용).
# 받은 사람은 첫 실행 때 "그래도 열기"를 한 번 해야 함 (README 설치 안내 참고).
#
# 자동 업데이트 파일(.app.tar.gz, .sig, latest.json)은 업데이트 서명키가 있을 때만 만듦.
#   TAURI_SIGNING_PRIVATE_KEY, TAURI_SIGNING_PRIVATE_KEY_PASSWORD 환경변수 (GitHub Actions 비밀값)
# 서명키 없이 로컬에서 빌드하면 .dmg만 만듦.
#
# 결과: packaging/build/release/ (dmg, app.tar.gz, sig, latest.json, SHA256SUMS)
# 사용: packaging/macos/release.sh [--skip-engine]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/packaging/build/release"
VERSION="$(python3 "$ROOT/scripts/version.py" | awk 'NR==1 {print $2}')"
ARCH="$(uname -m | sed 's/arm64/aarch64/')"
REPO_URL="https://github.com/SeaViewer91/GeoStat"

if [[ "${1:-}" != "--skip-engine" ]]; then
  "$ROOT/packaging/build-engine.sh"
  "$ROOT/packaging/macos/sign-engine.sh"
fi

cd "$ROOT/apps/desktop"
npm ci
CONFIG="src-tauri/tauri.bundle-engine.conf.json"
if [[ -z "${TAURI_SIGNING_PRIVATE_KEY:-}" ]]; then
  echo "업데이트 서명키가 없어 자동 업데이트 파일은 만들지 않음 (.dmg만 만듦)"
  CONFIG="$(mktemp -t geostat-conf).json"
  python3 - "$ROOT/apps/desktop/src-tauri/tauri.bundle-engine.conf.json" "$CONFIG" <<'PY'
import json, sys
conf = json.load(open(sys.argv[1]))
conf["bundle"]["createUpdaterArtifacts"] = False
json.dump(conf, open(sys.argv[2], "w"))
PY
fi
npm run tauri build -- --config "$CONFIG"

BUNDLE="$ROOT/apps/desktop/src-tauri/target/release/bundle"
rm -rf "$OUT" && mkdir -p "$OUT"
cp "$BUNDLE"/dmg/*.dmg "$OUT/GeoStat_${VERSION}_${ARCH}.dmg"
if [[ -f "$BUNDLE/macos/GeoStat.app.tar.gz.sig" ]]; then
  TARBALL="GeoStat_${VERSION}_${ARCH}.app.tar.gz"
  cp "$BUNDLE/macos/GeoStat.app.tar.gz" "$OUT/$TARBALL"
  cp "$BUNDLE/macos/GeoStat.app.tar.gz.sig" "$OUT/$TARBALL.sig"
  # 앱이 확인하는 업데이트 매니페스트 (releases/latest/download/latest.json)
  python3 - "$VERSION" "$ARCH" "$OUT/$TARBALL.sig" "$REPO_URL/releases/download/v$VERSION/$TARBALL" "$ROOT" > "$OUT/latest.json" <<'PY'
import datetime, json, subprocess, sys
version, arch, sig, url, root = sys.argv[1:]
notes = subprocess.run(
    [sys.executable, f"{root}/scripts/release_notes.py", version], capture_output=True, text=True
).stdout.strip()
print(json.dumps({
    "version": version,
    "notes": notes,
    "pub_date": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "platforms": {f"darwin-{arch}": {"signature": open(sig).read().strip(), "url": url}},
}, ensure_ascii=False, indent=2))
PY
fi
(cd "$OUT" && shasum -a 256 GeoStat_* > SHA256SUMS)

echo "릴리스 파일:"
ls -lh "$OUT"
