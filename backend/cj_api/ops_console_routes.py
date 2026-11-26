"""Internal operations console API for SERVICE-REQUEST@1 (#1771). Not a customer surface.

Mounted only when the host passes an OpsConsole and CJ_OPS_CONSOLE_ENABLED=1 (default off);
the flag is checked again on every request. Staff sign in with the App's existing session
credential: the same admission checker as the App verifies the bearer token, then the
verified issuer/subject must be on the server-configured roster. No feishu, no payment.
"""
import json

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .message_routes import _error, _token

PREFIX = '/v1/internal/ops/service-requests'
_MAX_BODY = 8192


def register_ops_console_routes(app, checker, console, roster, *, enabled):
    from cj_auth.interfaces import AdmissionStatus
    from cj_service_request.contract import InvalidInput, InvalidTransition
    from cj_service_request.ops import NotStaff
    from cj_service_request.store import FeatureDisabled, NotFound, Unavailable

    if checker is None or console is None or roster is None or not callable(enabled):
        raise ValueError('Complete operations console configuration required')

    def failure(request, exc, write):
        if isinstance(exc, NotStaff):
            return _error(request, 403, 'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
        if isinstance(exc, NotFound):
            return _error(request, 404, 'NOT_FOUND', 'input', 'failed', 'do_not_retry')
        if isinstance(exc, FeatureDisabled):
            return _error(request, 404, 'FEATURE_DISABLED', 'input', 'failed', 'do_not_retry')
        if isinstance(exc, InvalidTransition):
            return _error(request, 409, 'INVALID_TRANSITION', 'conflict', 'failed', 'do_not_retry')
        if isinstance(exc, InvalidInput):
            code = 'EVIDENCE_REQUIRED' if str(exc) == 'evidence_required' else 'INVALID_INPUT'
            return _error(request, 400, code, 'input', 'failed', 'do_not_retry')
        return _error(request, 503, 'OPS_OUTCOME_UNKNOWN' if write else 'OPS_UNAVAILABLE', 'dependency',
                      'unknown', 'reconcile_original' if write else 'retry_safe_read')

    def staff(request):
        """Return (staff_ref, None) or (None, error response). Errors never echo the token."""
        if not enabled():
            return None, _error(request, 404, 'NOT_FOUND', 'input', 'failed', 'do_not_retry')
        token = _token(request)
        if token is None:
            return None, _error(request, 401, 'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
        try:
            decision = checker.check(token)
        except Exception:
            return None, failure(request, Unavailable(), False)
        if decision.status is AdmissionStatus.DENIED:
            return None, _error(request, 401, 'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
        if decision.status is not AdmissionStatus.ALLOWED or decision.principal is None:
            return None, failure(request, Unavailable(), False)
        try:
            return roster.staff_ref(decision.principal), None
        except NotStaff as exc:
            return None, failure(request, exc, False)

    async def body(request):
        raw = await request.body()
        if len(raw) > _MAX_BODY:
            raise InvalidInput('size')
        try:
            value = json.loads(raw)
        except ValueError:
            raise InvalidInput('json') from None
        if not isinstance(value, dict):
            raise InvalidInput('json')
        return value

    async def run(request, write, fn, *args, **kw):
        try:
            result = await run_in_threadpool(fn, *args, **kw)
        except Exception as exc:
            return failure(request, exc, write)
        return JSONResponse(result)

    @app.get(PREFIX)
    async def ops_list(request: Request):
        ref, denied = staff(request)
        if denied is not None:
            return denied
        return await run(request, False, lambda: {'requests': console.list_requests(ref)})

    @app.get(PREFIX + '/{request_id}')
    async def ops_detail(request: Request, request_id: str):
        ref, denied = staff(request)
        if denied is not None:
            return denied
        return await run(request, False, console.detail, ref, request_id)

    @app.post(PREFIX + '/{request_id}/transitions')
    async def ops_transition(request: Request, request_id: str):
        ref, denied = staff(request)
        if denied is not None:
            return denied
        try:
            value = await body(request)
            if not set(value) <= {'target', 'evidence_body', 'quote', 'escort'} or 'target' not in value:
                raise InvalidInput('fields')
        except InvalidInput as exc:
            return failure(request, exc, False)
        return await run(request, True, console.advance, ref, request_id, value['target'], value.get('evidence_body'),
                         quote=value.get('quote'), escort=value.get('escort'))

    @app.post(PREFIX + '/{request_id}/clear-note')
    async def ops_clear_note(request: Request, request_id: str):
        ref, denied = staff(request)
        if denied is not None:
            return denied
        return await run(request, True, console.clear_note, ref, request_id)
