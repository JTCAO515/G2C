"""Owner-confirmed history/draft wire using one public trusted read context."""
import base64
from dataclasses import asdict
import json
import re
from urllib.parse import parse_qsl

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from .history_config import CursorBinding, CursorResyncRequired, CursorUnavailable, HistoryWireConfiguration
from .message_routes import _error, _token
from .generated import (MessageReceipt, ConversationSummary, MessageHistoryItem, MessageDraftSnapshot,
    ConversationPageResponse, MessageHistoryResponse, MessageDraftReadResponse, MessageDraftSaveResponse)

MAX_I64 = (1 << 63) - 1


class PrivateOutputTooLarge(Exception):
    pass


def _int64(value, minimum=0):
    if type(value) is not int or not minimum <= value <= MAX_I64:
        raise ValueError('Invalid internal integer')
    return value


def _raw64(raw):
    if type(raw) is not bytes:
        raise ValueError('Immutable original bytes required')
    raw.decode('utf-8')  # validate only, never reconstitute bytes from text
    encoded = base64.b64encode(raw).decode('ascii')
    decoded = base64.b64decode(encoded,validate=True)
    if decoded != raw or base64.b64encode(decoded).decode('ascii') != encoded:
        raise ValueError('Invalid original-byte encoding')
    return encoded


def _query(request, required, optional=()):
    raw = request.scope['query_string'].decode('ascii')
    if re.search(r'%(?![0-9a-fA-F]{2})',raw):
        raise ValueError('Invalid encoding')
    pairs = parse_qsl(raw,keep_blank_values=True,strict_parsing=True,encoding='utf-8',errors='strict')
    result = {}
    for key,value in pairs:
        if key in result or key not in (*required,*optional) or not value:
            raise ValueError('Unsupported query')
        result[key] = value  # opaque strings preserved, exactly one decode
    if not set(required) <= set(result):
        raise ValueError('Required query missing')
    return result


def _number(raw, minimum, maximum):
    if len(raw) > 19 or re.fullmatch(r'0|[1-9][0-9]*',raw) is None:
        raise ValueError('Invalid integer')
    value = int(raw)
    if not minimum <= value <= maximum:
        raise ValueError('Integer out of bounds')
    return value


def register_history_routes(app, boundary=None, configuration=None, environment=None):
    if configuration is not None:
        if not isinstance(configuration,HistoryWireConfiguration) or environment != 'local' or boundary is None:
            raise ValueError('Explicit local history context/configuration required')
        from cj_auth.interfaces import AdmissionReason, AdmissionStatus
        from cj_message.auth_boundary import AccessBlocked, IdentityChanged
        from cj_message.domain import (ChatSummary, Cursor, ChatListCursor, HistoryMessage, Draft,
                                       CommitUnknown, InputConflict, ResyncRequired)

    def failure(request, write, exc=None):
        if configuration is not None:
            if isinstance(exc,(AccessBlocked,IdentityChanged)):
                if exc.commit_possible or exc.stage == 'commit':
                    return _error(request,503,'HISTORY_OUTCOME_UNKNOWN','dependency','unknown','reconcile_original')
                if isinstance(exc,IdentityChanged):
                    return _error(request,403,'ACCESS_DENIED','access','failed','do_not_retry')
                if exc.status is AdmissionStatus.UNKNOWN:
                    return _error(request,503,'ACCESS_UNKNOWN','access','unknown','retry_safe_read')
                return _error(request,401 if exc.reason is AdmissionReason.IDENTITY_INVALID else 403,
                              'ACCESS_DENIED','access','failed','do_not_retry')
            if isinstance(exc,CommitUnknown):
                return _error(request,503,'DRAFT_OUTCOME_UNKNOWN','dependency','unknown','reconcile_original')
            if isinstance(exc,InputConflict):
                return _error(request,409,'DRAFT_REVISION_CONFLICT','conflict','failed','do_not_retry')
            if isinstance(exc,(ResyncRequired,CursorResyncRequired)):
                return _error(request,409,'HISTORY_RESYNC_REQUIRED','conflict','failed','retry_safe_read')
            if isinstance(exc,PrivateOutputTooLarge) and not write:
                return _error(request,413,'PRIVATE_RESPONSE_TOO_LARGE','input','failed','retry_safe_read')
        return _error(request,503,'HISTORY_UNAVAILABLE','dependency','unknown',
                      'reconcile_original' if write else 'retry_safe_read')

    def prepare(request, required, optional=(), *, paged=False):
        if configuration is None or paged and configuration.cursor_policy is None:
            return failure(request,False)
        token = _token(request)
        if token is None:
            return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        try:
            query = _query(request,required,optional)
            if paged:query['limit'] = _number(query['limit'],1,configuration.max_page_limit)
            if 'expected_revision' in query:
                query['expected_revision'] = _number(query['expected_revision'],0,MAX_I64-1)
        except (ValueError,UnicodeError):
            return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        return token,query

    def materialize(request, model, payload):
        validated = model.model_validate({'request_id':request.state.request_id,**payload})
        response = JSONResponse(validated.model_dump(mode='json'))
        if len(response.body) > configuration.max_private_response_bytes:
            raise PrivateOutputTooLarge()
        return response

    def draft_projection(value,cid,generation):
        if (type(value) is not Draft or value.conversation_id != cid or value.generation != generation):
            raise ValueError('Invalid internal draft')
        _int64(value.revision,1)
        if len(value.original_utf8) > configuration.max_private_response_bytes:
            raise PrivateOutputTooLarge()
        return MessageDraftSnapshot.model_validate({'conversation_id':value.conversation_id,
            'generation':value.generation,'revision':value.revision,
            'original_utf8_base64':_raw64(value.original_utf8)},strict=True)

    async def read(request,kind,*,formal=False):
        required = ('limit',) if kind=='conversations' else ('conversation_id','limit') if kind=='message_history' else ('conversation_id','generation')
        prepared = prepare(request,required,('cursor',) if kind!='draft' else (),paged=kind!='draft')
        if isinstance(prepared,JSONResponse):return prepared
        token,query = prepared
        def operation(context):
            if kind=='draft':
                value = context.read_draft(query['conversation_id'],query['generation'])
                projected = None if value is None else draft_projection(value,query['conversation_id'],query['generation'])
                return materialize(request,MessageDraftReadResponse,{'draft':projected})
            principal = context.principal
            cid = query.get('conversation_id')
            binding = CursorBinding(environment,principal.issuer,principal.subject,principal.audience,
                                    context.scope,kind,cid,context=context)
            policy = configuration.cursor_policy
            cursor = policy.decode(query['cursor'],binding) if 'cursor' in query else None
            expected = ChatListCursor if kind=='conversations' else Cursor
            if 'cursor' in query and (type(cursor) is not expected or cursor.scope != context.scope
                    or kind=='message_history' and cursor.conversation_id != cid):
                raise CursorResyncRequired()
            rows,nxt = context.conversations(cursor,query['limit']) if kind=='conversations' else (context.trip_message_history(cid,cursor,query['limit']) if formal else context.message_history(cid,cursor,query['limit']))
            if nxt is not None and (type(nxt) is not expected or nxt.scope != context.scope
                    or kind=='message_history' and nxt.conversation_id != cid):
                raise ValueError('Invalid internal cursor')
            next_token = policy.encode(nxt,binding) if nxt is not None else None
            projected=[];raw_total=0
            for row in rows:
                if kind=='conversations':
                    if type(row) is not ChatSummary:raise ValueError('Invalid internal summary')
                    _int64(row.epoch);_int64(row.list_sequence,1)
                    projected.append(ConversationSummary.model_validate(asdict(row),strict=True))
                else:
                    if type(row) is not HistoryMessage or row.receipt.conversation_id != cid:
                        raise ValueError('Invalid internal history')
                    raw_total+=len(row.original_utf8)
                    if raw_total > configuration.max_private_response_bytes:raise PrivateOutputTooLarge()
                    _int64(row.receipt.sequence,1)
                    receipt=MessageReceipt.model_validate(asdict(row.receipt),strict=True)
                    item=dict(receipt=receipt.model_dump(mode='json'),original_utf8_base64=_raw64(row.original_utf8),text=row.text)
                    if formal:
                        version=json.loads(row.original_utf8)['version']
                        original=(context.query_trip_message(row.receipt.message_id) if version=='MESSAGE-send.3' else
                                  context.query_travel_message(row.receipt.message_id) if version=='MESSAGE-send.2' else None)
                        item['reference']=None if original is None else original.reference.public_value()
                        projected.append(item)
                    else:
                        projected.append(MessageHistoryItem.model_validate(item,strict=True))
            if formal:
                body=JSONResponse(dict(request_id=request.state.request_id,version='MESSAGE-history.2',messages=projected,next_cursor=next_token))
                if len(body.body)>configuration.max_private_response_bytes:raise PrivateOutputTooLarge()
                return body
            model = ConversationPageResponse if kind=='conversations' else MessageHistoryResponse
            return materialize(request,model,{'conversations' if kind=='conversations' else 'messages':projected,
                                              'next_cursor':next_token})
        try:
            # Codec, read, projection, response bytes and size checks all remain
            # inside this one callback; no private _service or second identity bind.
            return await run_in_threadpool(boundary.with_history_context,token,operation)
        except Exception as exc:return failure(request,False,exc)

    @app.get('/v1/conversations',response_model=ConversationPageResponse)
    async def conversations(request:Request):return await read(request,'conversations')

    @app.get('/v1/message-history',response_model=MessageHistoryResponse)
    async def history(request:Request):return await read(request,'message_history')

    @app.get('/v1/message-drafts',response_model=MessageDraftReadResponse)
    async def draft(request:Request):return await read(request,'draft')

    @app.put('/v1/message-drafts',response_model=MessageDraftSaveResponse)
    async def save(request:Request):
        prepared = prepare(request,('conversation_id','generation','expected_revision'))
        if isinstance(prepared,JSONResponse):return prepared
        token,query = prepared
        media=request.headers.getlist('content-type')
        if (len(media)!=1 or media[0].split(';',1)[0].strip().lower()!='application/octet-stream'
                or request.headers.get('content-encoding','identity').lower()!='identity'):
            return _error(request,415,'UNSUPPORTED_MEDIA_TYPE','input','failed','do_not_retry')
        chunks=[];size=0
        try:
            async for chunk in request.stream():
                size+=len(chunk)
                if size>configuration.max_draft_bytes:
                    return _error(request,413,'BODY_TOO_LARGE','input','failed','do_not_retry')
                chunks.append(chunk)
            raw=b''.join(chunks)
            raw.decode('utf-8')
        except UnicodeError:return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        except Exception:return failure(request,True)
        def write_and_project():
            # Owner's public read context intentionally exposes no write. The
            # public save_draft retains its own entry/transaction/commit/return guards.
            value=boundary.save_draft(token,query['conversation_id'],query['generation'],raw,query['expected_revision'])
            projected=draft_projection(value,query['conversation_id'],query['generation'])
            return materialize(request,MessageDraftSaveResponse,{'draft':projected})
        try:return await run_in_threadpool(write_and_project)
        except Exception as exc:return failure(request,True,exc)

    @app.get('/v2/message-history')
    async def trip_history(request:Request):return await read(request,'message_history',formal=True)
