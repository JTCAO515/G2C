"""Local TRAVEL-CONTEXT@1 routes; canonical MESSAGE boundary, original bytes only."""
from dataclasses import asdict
import json

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from cj_auth.interfaces import AdmissionReason, AdmissionStatus
from cj_message.auth_boundary import AccessBlocked, IdentityChanged
from cj_message.domain import CommitUnknown, InputConflict, InvalidInput, SequenceConflict
from .message_routes import _error, _token, _read_body, BodyError


def register_travel_routes(app, boundary, max_body_bytes):
    def unavailable(request, write):
        return _error(request, 503, 'TRAVEL_CONTEXT_UNAVAILABLE', 'dependency', 'unknown',
                      'reconcile_original' if write else 'retry_safe_read')

    def failure(request, exc, write):
        if isinstance(exc, (AccessBlocked, IdentityChanged)):
            if exc.commit_possible or exc.stage == 'commit':
                return _error(request, 503, 'TRAVEL_CONTEXT_OUTCOME_UNKNOWN', 'dependency', 'unknown', 'reconcile_original')
            if isinstance(exc, AccessBlocked) and exc.status is AdmissionStatus.UNKNOWN:
                return _error(request, 503, 'ACCESS_UNKNOWN', 'access', 'unknown', 'retry_safe_read')
            status = 401 if isinstance(exc, AccessBlocked) and exc.reason is AdmissionReason.IDENTITY_INVALID else 403
            return _error(request, status, 'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
        if isinstance(exc, CommitUnknown):
            return _error(request, 503, 'TRAVEL_CONTEXT_OUTCOME_UNKNOWN', 'dependency', 'unknown', 'reconcile_original')
        if isinstance(exc, InvalidInput):
            return _error(request, 400, 'INVALID_INPUT', 'input', 'failed', 'do_not_retry')
        if isinstance(exc, InputConflict):
            return _error(request, 409, 'INPUT_CONFLICT', 'conflict', 'failed', 'do_not_retry')
        if isinstance(exc, SequenceConflict):
            return _error(request, 409, 'TRAVEL_CONTEXT_CONFLICT', 'conflict', 'failed', 'reconcile_original')
        return unavailable(request, write)

    async def invoke(request, method, argument, *, write, receipt=False):
        token = _token(request)
        if token is None:
            return _error(request, 401, 'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
        if request.scope['query_string']:
            return _error(request, 400, 'INVALID_INPUT', 'input', 'failed', 'do_not_retry')
        try:
            result = await run_in_threadpool(method, token, argument)
            if receipt:
                # Domain materializes the original receipt under fresh return guard.
                return JSONResponse({'request_id': request.state.request_id,
                                     'receipt': None if result is None else json.loads(result)})
            value = asdict(result)
            value['created_at'] = result.created_at.isoformat()
            return JSONResponse({'request_id': request.state.request_id,
                                 'version': 'TRAVEL-context.1', 'travel_context': value})
        except Exception as exc:
            return failure(request, exc, write)

    @app.post('/v1/travel-context-actions')
    async def action(request: Request):
        if boundary is None:
            return unavailable(request, True)
        if _token(request) is None:
            return _error(request, 401, 'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
        try:
            raw=await _read_body(request,max_body_bytes)
        except BodyError as exc:
            if exc.status==503:return unavailable(request,True)
            return _error(request,exc.status,exc.code,'input','failed','do_not_retry')
        return await invoke(request, boundary.travel_action, raw, write=True, receipt=True)

    @app.get('/v1/travel-context-actions/{action_id:path}')
    async def original(request: Request, action_id: str):
        if boundary is None:
            return unavailable(request, False)
        return await invoke(request, boundary.travel_action_status, action_id, write=False, receipt=True)

    @app.get('/v1/travel-contexts/{context_id}')
    async def context(request: Request, context_id: str):
        if boundary is None:
            return unavailable(request, False)
        return await invoke(request, boundary.travel_context, context_id, write=False)
