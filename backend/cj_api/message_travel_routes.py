"""MESSAGE-send.2 original acceptance/status, no live permission in the response."""
from dataclasses import asdict
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from cj_message.domain import Unavailable
from cj_message.travel_reference import ContextConflict
from .history_routes import _query
from .message_routes import _error,_token,_read_body,BodyError


def register_message_travel_routes(app,boundary,max_body_bytes,message_failure):
    def unavailable(request,write):
        return _error(request,503,'MESSAGE_CONTEXT_UNAVAILABLE','dependency','unknown',
                      'reconcile_original' if write else 'retry_safe_read')

    def failure(request,exc,write):
        if isinstance(exc,ContextConflict):
            return _error(request,409,'MESSAGE_CONTEXT_CONFLICT','conflict','failed','reconcile_original')
        if isinstance(exc,Unavailable):
            return unavailable(request,write)
        return message_failure(request,exc,write)

    @app.post('/v2/messages')
    async def send(request:Request):
        if boundary is None:return unavailable(request,True)
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        if request.scope['query_string']:
            return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        try:
            raw=await _read_body(request,max_body_bytes)
        except BodyError as exc:
            if exc.status==503:return unavailable(request,True)
            return _error(request,exc.status,exc.code,'input','failed','do_not_retry')
        try:
            value=await run_in_threadpool(boundary.receive_v2,token,raw)
            return JSONResponse(dict(request_id=request.state.request_id,version='MESSAGE-accept.2',
                receipt=asdict(value.receipt),reference=value.reference.public_value()))
        except Exception as exc:
            return failure(request,exc,True)

    @app.get('/v2/message-send-status')
    async def status(request:Request):
        if boundary is None:return unavailable(request,False)
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        try:
            query=_query(request,('conversation_id',),('message_id',))
        except (ValueError,UnicodeError):
            return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        try:
            value=await run_in_threadpool(boundary.send_status_v2,token,query['conversation_id'],query.get('message_id'))
            head=None if value.head is None else dict(conversation_id=query['conversation_id'],
                generation=value.head.generation,last_sequence=value.head.last_sequence)
            return JSONResponse(dict(request_id=request.state.request_id,version='MESSAGE-send-status.2',
                receipt=None if value.stored is None else asdict(value.stored.receipt),head=head,
                reference=None if value.reference is None else value.reference.public_value()))
        except Exception as exc:
            return failure(request,exc,False)
