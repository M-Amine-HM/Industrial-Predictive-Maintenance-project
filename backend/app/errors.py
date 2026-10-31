"""Uniform JSON error responses. Every invalid input is answered with 400 Bad Request."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .monitoring import VALIDATION_ERRORS

ERROR_CODES = {400: "bad_request", 401: "unauthorized", 404: "not_found", 405: "method_not_allowed",
               413: "payload_too_large", 429: "rate_limited", 500: "internal_error"}


class InputError(Exception):
    """Raised for invalid uploads / payloads; rendered as 400 with per-field details."""

    def __init__(self, message: str, details: list[dict] | None = None, status_code: int = 400):
        self.message, self.details, self.status_code = message, details or [], status_code


def _body(request: Request, error: str, message: str, details: list[dict] | None = None) -> dict:
    return {"error": error, "message": message, "details": details or [],
            "request_id": getattr(request.state, "request_id", None)}


def _loc(loc: tuple) -> str:
    # Drop the "body"/"query" prefix; keep list indexes and field names readable
    parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    return ".".join(parts) or "body"


def pydantic_details(errors: list[dict], row_offset: int | None = None) -> list[dict]:
    out = []
    for e in errors:
        loc = list(e.get("loc", ()))
        row = None
        if row_offset is not None and loc and isinstance(loc[0], int):
            row = loc.pop(0) + row_offset
        out.append({"field": _loc(tuple(loc)), "message": e.get("msg", "invalid"), "row": row})
    return out


def register(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def on_validation(request: Request, exc: RequestValidationError):
        VALIDATION_ERRORS.labels(source="request").inc()
        details = pydantic_details(exc.errors())
        msg = "Invalid request body" if details else "Invalid request"
        if len(details) == 1:
            msg = f"Invalid value for '{details[0]['field']}': {details[0]['message']}"
        return JSONResponse(status_code=400, content=_body(request, "validation_error", msg, details))

    @app.exception_handler(InputError)
    async def on_input(request: Request, exc: InputError):
        VALIDATION_ERRORS.labels(source="upload").inc()
        code = "validation_error" if exc.status_code == 400 else ERROR_CODES.get(exc.status_code, "error")
        return JSONResponse(status_code=exc.status_code, content=_body(request, code, exc.message, exc.details))

    @app.exception_handler(StarletteHTTPException)
    async def on_http(request: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, headers=getattr(exc, "headers", None),
                            content=_body(request, ERROR_CODES.get(exc.status_code, "error"), str(exc.detail)))
