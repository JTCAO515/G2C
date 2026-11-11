"""Host-only protected locator; no diagnostic metadata is accepted from the client."""
from cj_strict_json import compact
from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from cj_feedback.domain import identifier,InvalidInput
from .message_routes import _token,_error
from .history_routes import _query


def register_feedback_diagnostic_routes(app,reader):
    @app.get('/internal/v1/feedback-diagnostics')
    async def read(request:Request):
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        try:
            query=_query(request,('action_id',));identifier(query['action_id'])
        except (ValueError,UnicodeError,InvalidInput):
            return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        try:
            raw=await run_in_threadpool(reader.read,token,query['action_id'],
                lambda value:compact(dict(request_id=request.state.request_id,**value), ensure_ascii=True, allow_nan=True))
            return Response(raw,media_type='application/json')
        except Exception:
            return _error(request,503,'FEEDBACK_DIAGNOSTIC_UNAVAILABLE','dependency','unknown','retry_safe_read')
