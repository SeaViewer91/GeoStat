"""실제 프로세스로 띄워 앱(Tauri)과의 약속(준비 신호, stdin 종료)을 확인함."""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request

READY = "GEOSTAT_ENGINE_READY "


def _spawn(*extra: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "geostat_engine", "--log-level", "warning", *extra],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _read_ready(proc: subprocess.Popen) -> dict:
    for _ in range(50):
        line = proc.stdout.readline()
        if line.startswith(READY):
            return json.loads(line[len(READY) :])
    raise AssertionError("준비 신호를 받지 못함")


def test_ready_line_and_exit_on_stdin_close() -> None:
    proc = _spawn("--token", "t", "--exit-on-stdin-close")
    try:
        ready = _read_ready(proc)
        assert ready["port"] > 0 and "token" not in ready
        with urllib.request.urlopen(f"http://127.0.0.1:{ready['port']}/health", timeout=5) as r:
            assert json.load(r)["status"] == "ok"

        proc.stdin.close()  # 앱이 종료된 상황을 흉내 냄
        assert proc.wait(timeout=10) == 0
    finally:
        if proc.poll() is None:
            proc.kill()


def test_generated_token_is_reported() -> None:
    proc = _spawn()
    try:
        ready = _read_ready(proc)
        assert len(ready["token"]) >= 32
    finally:
        proc.kill()
        proc.wait()
