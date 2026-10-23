"""Uniform JSON error responses: {"error": {"code", "message", "hint"}}."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.exceptions import RAGError
from backend.logging_config import redact

logger = logging.getLogger(__name__)


def _body(code: str, message: str, hint: str | None = None) -> dict:
    return {"error": {"code": code, "message": redact(message), "hint": hint}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RAGError)
    async def rag_error(_: Request, exc: RAGError):
        level = logging.WARNING if exc.http_status < 500 else logging.ERROR
        logger.log(level, "%s: %s", exc.code, exc.message)
        headers = {"Retry-After": "30"} if exc.http_status == 429 else None
        return JSONResponse(_body(exc.code, exc.message, exc.hint), status_code=exc.http_status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'] if p != 'body')}: {e['msg']}" for e in exc.errors()
        )
        return JSONResponse(_body("validation_error", f"Invalid request - {problems}"), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return JSONResponse(_body("http_error", str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception):
        logger.exception("Unhandled error")
        return JSONResponse(_body("internal_error", "Unexpected server error.", "See the server log for details."), status_code=500)
