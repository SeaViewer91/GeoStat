"""Bearer 토큰 인증.

엔진은 127.0.0.1에만 바인딩되지만, 같은 PC의 다른 프로세스·웹페이지가 접근하는 것을
막기 위해 앱이 발급한 토큰을 모든 API 요청에 요구함.
"""

from __future__ import annotations

import secrets

from fastapi import FastAPI, HTTPException, Request, status


def set_token(app: FastAPI, token: str) -> None:
    app.state.geostat_token = token


async def require_token(request: Request) -> None:
    expected: str = request.app.state.geostat_token
    header = request.headers.get("authorization", "")
    scheme, _, supplied = header.partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="인증 토큰이 없거나 틀림")
