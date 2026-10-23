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
               _memory_boundary=None, _memory_configuration=None,
               _trip_boundary=None, _trip_configuration=None, _trip_modules=None,
               _needs_boundary=None, _needs_configuration=None, _needs_modules=None,
               _feedback_boundary=None, _feedback_configuration=None, _feedback_modules=None,
               _run_display_reader=None, _run_display_configuration=None, _run_display_modules=None,
               _manual_preview_boundary=None, _manual_preview_configuration=None, _manual_preview_modules=None,
               _usage_status_configuration=None, _usage_status_dependencies=None,
               _original_usage_reader=None, _original_usage_configuration=None, _original_usage_modules=None,
               _cleanup_progress_configuration=None, _cleanup_progress_dependencies=None,
               _memory_management_boundary=None, _memory_management_configuration=None):
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
    from .trip_routes import register_trip_routes
    register_trip_routes(app, _trip_boundary, _trip_configuration, _trip_modules)
    from .needs_routes import register_needs_routes
    register_needs_routes(app, _needs_boundary, _needs_configuration, _needs_modules)
    from .feedback_routes import register_feedback_routes
    register_feedback_routes(app, _feedback_boundary, _feedback_configuration, _feedback_modules)
    from .run_display_routes import register_run_display_route
    register_run_display_route(app, _run_display_reader, _run_display_configuration, _run_display_modules)
    from .manual_preview_routes import register_manual_preview
    register_manual_preview(app, _manual_preview_boundary, _manual_preview_configuration, _manual_preview_modules)
    from .usage_status_routes import register_usage_status
    register_usage_status(app, _usage_status_configuration, _usage_status_dependencies)
    from .original_usage_routes import register_original_usage
    register_original_usage(app, _original_usage_reader, _original_usage_configuration, _original_usage_modules)
    from .cleanup_progress_routes import register_cleanup_progress
    register_cleanup_progress(app, _cleanup_progress_configuration, _cleanup_progress_dependencies)
    from .memory_management_routes import register_memory_management
    register_memory_management(app, _memory_management_boundary, _memory_management_configuration)
    return app
