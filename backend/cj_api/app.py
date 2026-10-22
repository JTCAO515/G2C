"""Local foundation only: no business data or external provider access."""
import os
from pathlib import Path
import json
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from fastapi.responses import JSONResponse
from .generated import ProbeResponse, ErrorResponse

ROOT = Path(__file__).resolve().parents[2]

def error_body(request_id, code, category, en, zh, recovery="do_not_retry"):
    return ErrorResponse.model_validate({"request_id": request_id, "error": {
        "code": code, "category": category, "message_en": en, "message_zh": zh,
        "outcome": "failed", "recovery": recovery
    }}).model_dump(mode="json")

def create_app(*, _message_boundary=None, _max_body_bytes=None, _history_configuration=None, _history_environment=None,
               _memory_boundary=None, _memory_configuration=None):
    if os.environ.get("CJ_ENV") != "local":
        raise RuntimeError("CJ_ENV must explicitly be local; other environments are not configured")
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    app.openapi = lambda: json.loads((ROOT / "contracts/api/openapi.json").read_text())

    @app.middleware("http")
    async def trace(request: Request, call_next):
        # Do not echo untrusted IDs or log request URLs, headers, bodies or exception strings.
        request.state.request_id = str(uuid4())
        try:
            response = await call_next(request)
        except Exception:
            response = JSONResponse(error_body(request.state.request_id, "INTERNAL_ERROR", "internal",
                                               "Request failed", "请求失败"), status_code=500)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        return JSONResponse(error_body(request.state.request_id, code, "routing",
                                      "Request unavailable", "请求不可用"), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError):
        return JSONResponse(error_body(request.state.request_id, "INVALID_INPUT", "input",
                                      "Invalid request", "请求无效"), status_code=422)

    @app.get("/v1/probe", response_model=ProbeResponse)
    async def probe(request: Request):
        return ProbeResponse.model_validate({"contract_version": "1.0.0", "status": "ok",
                                             "request_id": request.state.request_id})
    from .message_routes import register_message_routes
    register_message_routes(app, _message_boundary, _max_body_bytes)
    from .history_routes import register_history_routes
    register_history_routes(app, _message_boundary, _history_configuration, _history_environment)
    from .memory_routes import register_memory_routes
    register_memory_routes(app, _memory_boundary, _memory_configuration)
    return app
