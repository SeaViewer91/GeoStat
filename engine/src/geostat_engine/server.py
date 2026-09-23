"""FastAPI 앱 구성."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from geostat_engine import __version__
from geostat_engine.api import datasets, health
from geostat_engine.auth import set_token
from geostat_engine.errors import install_error_handlers
from geostat_engine.state import AppState

# WebView 출처 목록. macOS Tauri는 tauri://localhost, 개발 서버는 localhost:1420을 씀
ALLOWED_ORIGINS = [
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "http://localhost:1420",
    "http://127.0.0.1:1420",
]


def create_app(token: str, ready_line: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 서버가 요청을 받을 수 있게 된 시점에 준비 신호를 출력함
        if ready_line:
            print(ready_line, flush=True, file=sys.stdout)
        yield

    app = FastAPI(title="GeoStat Engine", version=__version__, lifespan=lifespan)
    app.state.geostat = AppState()
    set_token(app, token)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-GeoStat-Rows"],
    )
    install_error_handlers(app)

    app.include_router(health.router)
    app.include_router(datasets.router)
    return app
