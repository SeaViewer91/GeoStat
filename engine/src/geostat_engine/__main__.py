"""엔진 실행 진입점.

앱(Tauri)은 이 프로세스를 띄운 뒤 stdout의 준비 신호 한 줄을 읽어 포트를 알아냄.
    GEOSTAT_ENGINE_READY {"port": 51234, "pid": 1234, "version": "0.0.1"}
"""

from __future__ import annotations

import argparse
import logging
import os
import secrets
import socket
import sys
import threading

import uvicorn

from geostat_engine import __version__
from geostat_engine.server import create_app

READY_PREFIX = "GEOSTAT_ENGINE_READY"

log = logging.getLogger("geostat_engine")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="geostat-engine", description="GeoStat 분석 엔진")
    p.add_argument(
        "--host", default="127.0.0.1", help="바인딩 주소 (외부 노출 금지, 기본 127.0.0.1)"
    )
    p.add_argument("--port", type=int, default=0, help="포트 번호. 0이면 OS가 빈 포트를 배정함")
    p.add_argument(
        "--token",
        default=os.environ.get("GEOSTAT_ENGINE_TOKEN"),
        help="API 인증 토큰. 없으면 임의로 생성하고 준비 신호에 포함함",
    )
    p.add_argument(
        "--exit-on-stdin-close",
        action="store_true",
        help="stdin이 닫히면 종료함. 앱이 비정상 종료돼도 엔진이 남지 않게 하는 용도임",
    )
    p.add_argument("--log-level", default="info")
    return p.parse_args(argv)


def _watch_stdin() -> None:
    # 부모 프로세스가 죽으면 파이프가 닫혀 read()가 EOF를 반환함 → 즉시 종료
    try:
        while sys.stdin.buffer.read(1024):
            pass
    finally:
        os._exit(0)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    token_generated = args.token is None
    token = args.token or secrets.token_urlsafe(32)

    # 소켓을 직접 열어 OS가 배정한 포트를 확정한 뒤 uvicorn에 넘김 (포트 경합 방지)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.host, args.port))
    port = sock.getsockname()[1]

    ready = {"port": port, "pid": os.getpid(), "version": __version__}
    if token_generated:
        ready["token"] = token

    app = create_app(token=token, ready_line=f"{READY_PREFIX} {_json(ready)}")

    if args.exit_on_stdin_close:
        threading.Thread(target=_watch_stdin, name="stdin-watch", daemon=True).start()

    config = uvicorn.Config(app, log_level=args.log_level, access_log=False)
    server = uvicorn.Server(config)
    server.run(sockets=[sock])


def _json(obj: dict) -> str:
    import json

    return json.dumps(obj, separators=(",", ":"))


if __name__ == "__main__":
    main()
