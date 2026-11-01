"""Append-only result read envelopes under original canonical MESSAGE admission."""
from dataclasses import asdict
import base64,json
from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from cj_run.core import Binding
from cj_run.scoped_result import descriptor
from .history_config import CursorBinding,CursorResyncRequired
from .history_routes import _query,_number
from .message_routes import _error,_token


def register_scoped_result_routes(app,reader,history_configuration):
    def encode(value,maximum):
        raw=json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
        if len(raw)>maximum:raise ValueError('bounded scoped result response required')
        return raw

    def pointer(ctx,stored,checks):
        r=stored.receipt
        binding=Binding(ctx.scope,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence)
        repository=reader.resolve_run_repository(ctx.principal,ctx.scope)
        first=repository.snapshot_optional(binding)
        checks.append((repository,binding,first))
        return None if first is None else descriptor(first,stored)

    def final(checks):
        for repository,binding,state in checks:
            if repository.snapshot_optional(binding)!=state:raise ValueError('original RUN changed during read')

    async def invoke(request,kind):
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        try:
            if kind in ('draft','display'):
                query=_query(request,('message_id',))
                if not query['message_id'].strip() or len(query['message_id'].encode())>256 or '\0' in query['message_id']:raise ValueError('bounded original ID required')
            elif kind=='status':query=_query(request,('conversation_id',),('message_id',))
            else:
                if history_configuration is None or history_configuration.cursor_policy is None:raise ValueError('explicit history configuration required')
                query=_query(request,('conversation_id','limit'),('cursor',))
                query['limit']=_number(query['limit'],1,history_configuration.max_page_limit)
        except (ValueError,UnicodeError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        def operation():
            if kind=='draft':return reader.read_draft_status_v6(token,query['message_id'],request.state.request_id)
            if kind=='display':return reader.read_result_display(token,query['message_id'],request.state.request_id)
            def protected(ctx):
                checks=[];cid=query['conversation_id']
                if kind=='status':
                    value=ctx.edit_send_status(cid,query.get('message_id'))
                    result=None if value.stored is None else pointer(ctx,value.stored,checks)
                    body=dict(request_id=request.state.request_id,version='MESSAGE-send-status.5',
                        receipt=None if value.stored is None else asdict(value.stored.receipt),
                        reference=None if value.reference is None else value.reference.public_value(),
                        head=None if value.head is None else dict(conversation_id=cid,generation=value.head.generation,last_sequence=value.head.last_sequence),
                        scoped_result=result)
                    maximum=reader.configuration.max_response_bytes
                else:
                    policy=history_configuration.cursor_policy
                    binding=CursorBinding('local',ctx.principal.issuer,ctx.principal.subject,ctx.principal.audience,ctx.scope,'message_history',cid,context=ctx)
                    cursor=policy.decode(query['cursor'],binding) if 'cursor' in query else None
                    rows,nxt=ctx.trip_message_history(cid,cursor,query['limit'])
                    projected=[]
                    for row in rows:
                        version=json.loads(row.original_utf8)['version']
                        original=(ctx.query_edit_message(row.receipt.message_id) if version=='MESSAGE-send.4' else ctx.query_trip_message(row.receipt.message_id) if version=='MESSAGE-send.3' else ctx.query_travel_message(row.receipt.message_id) if version=='MESSAGE-send.2' else None)
                        projected.append(dict(receipt=asdict(row.receipt),original_utf8_base64=base64.b64encode(row.original_utf8).decode('ascii'),
                            text=row.text,reference=None if original is None else original.reference.public_value(),
                            scoped_result=pointer(ctx,original.stored,checks) if version=='MESSAGE-send.4' else None))
                    body=dict(request_id=request.state.request_id,version='MESSAGE-history.4',messages=projected,
                        next_cursor=None if nxt is None else policy.encode(nxt,binding))
                    maximum=history_configuration.max_private_response_bytes
                raw=encode(body,maximum)
                final(checks)
                return raw
            return reader.message_boundary.with_history_context(token,protected)
        try:
            raw=await run_in_threadpool(operation)
            return Response(content=raw,media_type='application/json')
        except CursorResyncRequired:return _error(request,409,'HISTORY_RESYNC_REQUIRED','conflict','failed','retry_safe_read')
        except Exception:return _error(request,503,'SCOPED_RESULT_UNAVAILABLE','dependency','unknown','retry_safe_read')

    @app.get('/v6/run-draft-status')
    async def draft(request:Request):return await invoke(request,'draft')
    @app.get('/v5/run-display')
    async def display(request:Request):return await invoke(request,'display')
    @app.get('/v5/message-send-status')
    async def status(request:Request):return await invoke(request,'status')
    @app.get('/v4/message-history')
    async def history(request:Request):return await invoke(request,'history')
