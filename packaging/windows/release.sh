#!/usr/bin/env bash
# Windows 릴리스 빌드 (Git Bash): 엔진 빌드 → Tauri 앱·NSIS 설치 프로그램 → 업데이트 파일 정리
#
# 코드 서명 인증서가 없어 서명하지 않음. 받은 사람은 첫 실행 때 "Windows의 PC 보호"에서
# "추가 정보 → 실행"을 한 번 눌러야 함 (README 설치 안내 참고).
# 자동 업데이트 파일(.sig, latest.json)은 업데이트 서명키 환경변수가 있을 때만 만듦 (macos/release.sh와 같음).
#
# 결과: packaging/build/release/ (설치 프로그램, sig, latest.json, SHA256SUMS)
# 사용: packaging/windows/release.sh [--skip-engine]
set -euo pipefail
# Windows 콘솔 기본 인코딩(cp1252 등)에서도 한글 출력이 깨지지 않게 함
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/packaging/build/release"
# Windows의 python3는 Microsoft Store 바로 가기일 수 있어 uv가 관리하는 파이썬을 씀
py() { uv run --no-project python "$@"; }
VERSION="$(py "$ROOT/scripts/version.py" | awk 'NR==1 {print $2}')"
REPO_URL="https://github.com/SeaViewer91/GeoStat"

if [[ "${1:-}" != "--skip-engine" ]]; then
  "$ROOT/packaging/build-engine.sh"
fi

cd "$ROOT/apps/desktop"
npm ci
CONFIG="src-tauri/tauri.bundle-engine.conf.json"
if [[ -z "${TAURI_SIGNING_PRIVATE_KEY:-}" ]]; then
  echo "업데이트 서명키가 없어 자동 업데이트 파일은 만들지 않음 (설치 프로그램만 만듦)"
  CONFIG="$ROOT/packaging/build/tauri-no-updater.json"
  mkdir -p "$(dirname "$CONFIG")"
  py - "$ROOT/apps/desktop/src-tauri/tauri.bundle-engine.conf.json" "$CONFIG" <<'PY'
import json, sys
conf = json.load(open(sys.argv[1], encoding="utf-8"))
conf["bundle"]["createUpdaterArtifacts"] = False
json.dump(conf, open(sys.argv[2], "w", encoding="utf-8"))
PY
fi
npm run tauri build -- --config "$CONFIG"

BUNDLE="$ROOT/apps/desktop/src-tauri/target/release/bundle/nsis"
SETUP="GeoStat_${VERSION}_x64-setup.exe"
rm -rf "$OUT" && mkdir -p "$OUT"
cp "$BUNDLE"/*-setup.exe "$OUT/$SETUP"
if ls "$BUNDLE"/*-setup.exe.sig >/dev/null 2>&1; then
  cp "$BUNDLE"/*-setup.exe.sig "$OUT/$SETUP.sig"
  py - "$VERSION" "$OUT/$SETUP.sig" "$REPO_URL/releases/download/v$VERSION/$SETUP" "$ROOT" > "$OUT/latest.json" <<'PY'
import datetime, json, subprocess, sys
version, sig, url, root = sys.argv[1:]
notes = subprocess.run(
    [sys.executable, f"{root}/scripts/release_notes.py", version], capture_output=True, text=True, encoding="utf-8"
).stdout.strip()
print(json.dumps({
    "version": version,
    "notes": notes,
    "pub_date": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "platforms": {"windows-x86_64": {"signature": open(sig).read().strip(), "url": url}},
}, ensure_ascii=False, indent=2))
PY
fi
(cd "$OUT" && sha256sum GeoStat_* > SHA256SUMS)

echo "릴리스 파일:"
ls -lh "$OUT"
