"""Confirmed narrow wire. Authentication is injected, never taken from caller owner fields."""
from dataclasses import asdict
import re
from urllib.parse import parse_qsl

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from .generated import ErrorResponse, MessageReceipt, MessageReceiveResponse, MessageReceiptQueryResponse


def _error(request, status, code, category, outcome, recovery):
    body = ErrorResponse.model_validate({'request_id':request.state.request_id, 'error':{
        'code':code, 'category':category, 'message_en':'Request unavailable', 'message_zh':'请求不可用',
        'outcome':outcome, 'recovery':recovery}})
    return JSONResponse(body.model_dump(mode='json'), status_code=status)


def _token(request):
    values = request.headers.getlist('authorization')
    if len(values) != 1:
        return None
    scheme, separator, token = values[0].partition(' ')
    if (scheme.lower() != 'bearer' or not separator or not token or ',' in token
            or any(c.isspace() for c in token)):
        return None
    return token


def register_message_routes(app, boundary=None, max_body_bytes=None):
    if boundary is not None:
        from cj_auth.interfaces import AdmissionReason, AdmissionStatus
        from cj_message.auth_boundary import Boundary, AccessBlocked, IdentityChanged
        from cj_message.domain import CommitUnknown, InputConflict, InvalidInput, Stored, Receipt
        if (not isinstance(boundary, Boundary) or type(max_body_bytes) is not int or max_body_bytes <= 0):
            raise ValueError('Explicit pinned MESSAGE boundary and body limit required')

    def unavailable(request, write):
        return _error(request, 503, 'MESSAGE_UNAVAILABLE', 'dependency', 'unknown',
                      'reconcile_original' if write else 'retry_safe_read')

    async def invoke(request, token, write, argument):
        try:
            value = await run_in_threadpool(boundary.receive if write else boundary.query, token, argument)
            if not write:
                if value is None:
                    return MessageReceiptQueryResponse.model_validate({
                        'request_id':request.state.request_id, 'receipt':None})
                if type(value) is not Stored:
                    raise ValueError('Invalid internal result')
                value = value.receipt  # never serialize Stored or its private original bytes
            if type(value) is not Receipt:
                raise ValueError('Invalid internal receipt')
            receipt = MessageReceipt.model_validate(asdict(value), strict=True)
            response_type = MessageReceiveResponse if write else MessageReceiptQueryResponse
            return response_type.model_validate({'request_id':request.state.request_id, 'receipt':receipt})
        except Exception as exc:
            return failure(request, exc, write)

    def failure(request, exc, write):
        if isinstance(exc, (AccessBlocked, IdentityChanged)):
            # Fixed repository does not expose a proven rollback result after commit-stage denial.
            # Preserve possible prior effects before considering an ordinary identity refusal.
            if exc.commit_possible or exc.stage == 'commit':
                return _error(request, 503, 'MESSAGE_OUTCOME_UNKNOWN', 'dependency', 'unknown', 'reconcile_original')
            if isinstance(exc, IdentityChanged):
                return _error(request, 403, 'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
            if exc.status is AdmissionStatus.UNKNOWN:
                return _error(request, 503, 'ACCESS_UNKNOWN', 'access', 'unknown', 'retry_safe_read')
            status = 401 if exc.reason is AdmissionReason.IDENTITY_INVALID else 403
            return _error(request, status, 'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
        if isinstance(exc, CommitUnknown):
            return _error(request, 503, 'MESSAGE_OUTCOME_UNKNOWN', 'dependency', 'unknown', 'reconcile_original')
        if isinstance(exc, InvalidInput):
            return _error(request, 400, 'INVALID_INPUT', 'input', 'failed', 'do_not_retry')
        if isinstance(exc, InputConflict):
            return _error(request, 409, 'INPUT_CONFLICT', 'conflict', 'failed', 'do_not_retry')
        # Includes unavailable repositories and invalid projection after a possible commit.
        return unavailable(request, write)

    @app.put('/v1/conversations')
    async def open_conversation(request: Request):
        """Idempotent create of an active conversation (P2a); first message needs one."""
        if boundary is None:
            return unavailable(request, True)
        token = _token(request)
        if token is None:
            return _error(request, 401, 'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
        try:
            pairs = parse_qsl(request.scope['query_string'].decode('ascii'), keep_blank_values=True,
                              strict_parsing=True, encoding='utf-8', errors='strict')
            if len(pairs) != 1 or pairs[0][0] != 'conversation_id':
                raise ValueError('One conversation ID required')
        except (ValueError, UnicodeError):
            return _error(request, 400, 'INVALID_INPUT', 'input', 'failed', 'do_not_retry')
        try:
            chat = await run_in_threadpool(boundary.open_conversation, token, pairs[0][1])
        except Exception as exc:
            return failure(request, exc, True)
        return JSONResponse({'request_id': request.state.request_id, 'conversation_id': pairs[0][1],
                             'generation': chat.generation, 'last_sequence': chat.last_sequence})

    @app.post('/v1/messages', response_model=MessageReceiveResponse)
    async def receive(request: Request):
        if boundary is None:
            return unavailable(request, True)
        token = _token(request)
        if token is None:
            return _error(request, 401, 'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
        media = request.headers.getlist('content-type')
        if (len(media) != 1 or media[0].split(';',1)[0].strip().lower() != 'application/octet-stream'
                or request.headers.get('content-encoding', 'identity').lower() != 'identity'):
            return _error(request, 415, 'UNSUPPORTED_MEDIA_TYPE', 'input', 'failed', 'do_not_retry')
        chunks, total = [], 0
        try:
            async for chunk in request.stream():
                total += len(chunk)
                if total > max_body_bytes:
                    return _error(request, 413, 'BODY_TOO_LARGE', 'input', 'failed', 'do_not_retry')
                chunks.append(chunk)
        except Exception:
            return unavailable(request, True)
        return await invoke(request, token, True, b''.join(chunks))

    @app.get('/v1/message-receipts', response_model=MessageReceiptQueryResponse)
    async def query(request: Request):
        if boundary is None:
            return unavailable(request, False)
        token = _token(request)
        if token is None:
            return _error(request, 401, 'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
        try:
            raw_query = request.scope['query_string'].decode('ascii')
            if re.search(r'%(?![0-9a-fA-F]{2})', raw_query):
                raise ValueError('Invalid query encoding')
            pairs = parse_qsl(raw_query, keep_blank_values=True, strict_parsing=True,
                              encoding='utf-8', errors='strict')
            if (len(pairs) != 1 or pairs[0][0] != 'message_id' or not pairs[0][1].strip()):
                raise ValueError('One original message ID required')
            message_id = pairs[0][1]  # decoded exactly once, never normalized or stripped
        except (ValueError, UnicodeError):
            return _error(request, 400, 'INVALID_INPUT', 'input', 'failed', 'do_not_retry')
        return await invoke(request, token, False, message_id)
