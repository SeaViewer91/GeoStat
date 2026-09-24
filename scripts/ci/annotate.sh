#!/usr/bin/env bash
# 명령을 실행하고, 실패하면 출력 끝부분을 GitHub Actions 주석(annotation)으로 남김.
# 로그를 내려받지 않고도 실패 원인을 볼 수 있게 하려는 것임.
# 사용: scripts/ci/annotate.sh "<제목>" <명령> [인수...]
set -uo pipefail
title="$1"
shift
log="$(mktemp)"
"$@" 2>&1 | tee "$log"
status=${PIPESTATUS[0]}
if [[ $status -ne 0 ]]; then
  body="$(grep -v "replacing existing signature" "$log" | tail -n 45 | cut -c1-300 | sed 's/%/%25/g' | awk '{printf "%s%%0A", $0}')"
  echo "::error title=${title}::${body}"
fi
exit "$status"
