"""Additive Demo dialogue message admission and original read."""
from dataclasses import asdict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from cj_message.demo_dialogue import RECEIPT_VERSION, message_id
from cj_message.demo_needs_cards import RECEIPT_VERSION as ACTION_RECEIPT_VERSION

from .demo_dialogue_events import register_dialogue_event_stream
from .history_routes import _query
from .message_routes import BodyError, _body_error, _error, _read_body, _token, message_failure


def register_demo_dialogue_routes(app, boundary, resolve_run_repository, trip_cards):
    register_dialogue_event_stream(app,boundary,resolve_run_repository,trip_cards)
    def response(request, receipt):
        return JSONResponse(dict(request_id=request.state.request_id, version=RECEIPT_VERSION,
                                 receipt=asdict(receipt) if receipt is not None else None))

    @app.post('/v1/demo-dialogue/messages')
    async def send(request: Request):
        token = _token(request)
        if token is None:
            return _error(request, 401, 'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
        if request.scope['query_string']:
            return _error(request, 400, 'INVALID_INPUT', 'input', 'failed', 'do_not_retry')
        try:
            raw = await _read_body(request, 16384)
        except BodyError as exc:
            if exc.status == 503:
                return message_failure(request, exc, True)
            return _body_error(request, exc)
        try:
            receipt = await run_in_threadpool(boundary.receive_dialogue, token, raw)
            return response(request, receipt)
        except Exception as exc:
            return message_failure(request, exc, True)

    @app.get('/v1/demo-dialogue/messages')
    async def original(request: Request):
        token = _token(request)
        if token is None:
            return _error(request, 401, 'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
        try:
            mid = message_id(_query(request, ('message_id',))['message_id'])
        except (ValueError, UnicodeError):
            return _error(request, 400, 'INVALID_INPUT', 'input', 'failed', 'do_not_retry')
        try:
            receipt = await run_in_threadpool(boundary.query_dialogue, token, mid)
            return response(request, receipt)
        except Exception as exc:
            return message_failure(request, exc, False)


    def action_response(request, receipt):
        return JSONResponse(dict(request_id=request.state.request_id,version=ACTION_RECEIPT_VERSION,receipt=receipt))

    @app.post('/v1/demo-dialogue/actions')
    async def act(request: Request):
        token = _token(request)
        if token is None:
            return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        if request.scope['query_string']:
            return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        try:
            raw = await _read_body(request,32768)
        except BodyError as exc:
            if exc.status == 503:
                return message_failure(request,exc,True)
            return _body_error(request,exc)
        try:
            receipt = await run_in_threadpool(boundary.act_dialogue,token,raw,trip_cards)
            return action_response(request,receipt)
        except Exception as exc:
            return message_failure(request,exc,True)

    @app.get('/v1/demo-dialogue/actions')
    async def original_action(request: Request):
        token = _token(request)
        if token is None:
            return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        try:
            aid = message_id(_query(request,('action_id',))['action_id'])
        except (ValueError,UnicodeError):
            return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        try:
            receipt = await run_in_threadpool(boundary.query_dialogue_action,token,aid,trip_cards)
            return action_response(request,receipt)
        except Exception as exc:
            return message_failure(request,exc,False)
