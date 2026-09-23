"""상태 확인 API. 인증 없이 호출 가능하며 민감 정보를 담지 않음."""

from __future__ import annotations

import platform

import pyogrio
import pyproj
from fastapi import APIRouter

from geostat_engine import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "python": platform.python_version(),
        "gdal": pyogrio.__gdal_version_string__,
        "proj": pyproj.proj_version_str,
    }
