"""FastAPI 앱 구성."""

from __future__ import annotations

import logging
import sys
import threading
import time
import warnings
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from geostat_engine import __version__
from geostat_engine.api import datasets, files, health, project, regression, spatial
from geostat_engine.auth import set_token
from geostat_engine.errors import install_error_handlers
from geostat_engine.jobs import JobManager
from geostat_engine.state import AppState

# WebView 출처 목록. macOS Tauri는 tauri://localhost, 개발 서버는 localhost:1420을 씀
ALLOWED_ORIGINS = [
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "http://localhost:1420",
    "http://127.0.0.1:1420",
]


def create_app(token: str, ready_line: str | None = None, warmup: bool = False) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 서버가 요청을 받을 수 있게 된 시점에 준비 신호를 출력함
        if ready_line:
            print(ready_line, flush=True, file=sys.stdout)
        if warmup:
            threading.Thread(target=_warmup, name="jit-warmup", daemon=True).start()
        yield
        # 엔진이 끝나면 실행 중인 작업 프로세스도 정리함
        app.state.jobs.shutdown()

    app = FastAPI(title="GeoStat Engine", version=__version__, lifespan=lifespan)
    app.state.geostat = AppState()
    app.state.jobs = JobManager()
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
    app.include_router(files.router)
    app.include_router(datasets.router)
    app.include_router(spatial.router)
    app.include_router(regression.router)
    app.include_router(project.router)
    return app


def _warmup() -> None:
    """국지 통계의 numba JIT 컴파일을 미리 해 둠.

    첫 LISA 실행이 컴파일 때문에 수십 초 걸리는 것을 막으려고, 엔진이 뜨자마자 작은 격자로 한 번씩 돌림.
    """
    t0 = time.perf_counter()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import esda
            import libpysal
            import numpy as np

            w = libpysal.weights.lat2W(6, 6)
            w.transform = "r"
            y = np.arange(36, dtype="float64")
            kw = {"permutations": 99, "keep_simulations": False, "seed": 1, "n_jobs": 1}
            esda.Moran_Local(y, w, **kw)
            esda.G_Local(y, w, star=True, **kw)
            esda.Geary_Local(connectivity=w, labels=True, **kw).fit(y)
        logging.getLogger("geostat_engine").info("JIT 준비 완료 (%.1f초)", time.perf_counter() - t0)
    except Exception:  # 준비 단계 실패는 실제 분석 때 다시 드러나므로 기록만 함
        logging.getLogger("geostat_engine").exception("JIT 준비 실패")
