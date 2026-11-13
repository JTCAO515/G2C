"""Explicit calendar history and original-action undo, using the existing boundary."""
import json
import re

from fastapi import Request
from starlette.concurrency import run_in_threadpool

from cj_message.domain import unique_fields
from cj_needs.domain import Denied as NeedsDenied
from cj_trip.calendar_history import CalendarUndo
from cj_trip.domain import Conflict, Denied, packed
from cj_trip.operation import OperationWithheld

from .history_routes import _query
from .lio_dialogue_routes import _failure, _json
from .lio_trip_routes import _conversation, _history, _require_selected_trip, _undo
from .message_routes import BodyError, _read_body, _token


def _action(action_id,target):
    original=json.loads(_undo(action_id,target).raw)
    return CalendarUndo.parse(packed(dict(original,version='TRIP-lio-undo.2')))


def _result(action,conversation,committed):
    return packed(dict(version='LIO-trip-undo-receipt.3',conversation_id=conversation,
                       action_id=action.action_id,committed=committed))


def register_lio_calendar_trip_routes(app,boundary):
    async def invoke(token,operation,query=None):
        def perform():
            try:return boundary.with_operation(token,operation)
            except OperationWithheld as error:
                if query is None or not error.commit_possible:raise
                return boundary.with_operation(token,query)
        try:
            value=json.loads(await run_in_threadpool(perform))
            return _failure(503) if query is not None and not value['committed'] else _json(value)
        except Conflict:return _failure(409)
        except (Denied,NeedsDenied):return _failure(403)
        except Exception:return _failure(503)

    def receipt(context,action,conversation):
        _require_selected_trip(context,action,conversation)
        found=context.lio_undo_receipt(action)
        return _result(action,conversation,found is not None)

    @app.get('/v3/lio/trip')
    async def history(request:Request):
        token=_token(request)
        if token is None:return _failure(401)
        try:
            params=_query(request,('conversation_id',),('before',))
            conversation=_conversation(params,True)
            before=params.get('before')
            if before is not None and (re.fullmatch(r'[1-9][0-9]{0,18}',before) is None or int(before)>=2**63):
                raise ValueError('invalid calendar history cursor')
            before=int(before) if before is not None else None
        except ValueError:return _failure(400)
        return await invoke(token,lambda context:_history(context,before,conversation,calendar=True))

    @app.post('/v3/lio/trip-undos')
    async def undo(request:Request):
        token=_token(request)
        if token is None:return _failure(401)
        if request.scope['query_string']:return _failure(400)
        try:
            value=json.loads((await _read_body(request,1024)).decode(),object_pairs_hook=unique_fields)
            if type(value)is not dict or value.keys()!={'version','action_id','target','conversation_id'} or value['version']!='LIO-trip-undo.3':
                raise ValueError('explicit calendar undo required')
            conversation=_conversation(value,True)
            action=_action(value['action_id'],value['target'])
        except BodyError as error:return _failure(error.status)
        except (ValueError,UnicodeError,RecursionError):return _failure(400)

        def apply(context):
            _require_selected_trip(context,action,conversation)
            result=context.undo_calendar(action)
            return _result(result,conversation,True)
        return await invoke(token,apply,lambda context:receipt(context,action,conversation))

    @app.get('/v3/lio/trip-undo-receipts')
    async def lookup(request:Request):
        token=_token(request)
        if token is None:return _failure(401)
        try:
            params=_query(request,('action_id','target','conversation_id'))
            conversation=_conversation(params,True)
            action=_action(params['action_id'],params['target'])
        except (ValueError,UnicodeError,RecursionError):return _failure(400)
        return await invoke(token,lambda context:receipt(context,action,conversation))
