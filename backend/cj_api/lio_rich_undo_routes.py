"""Bind the native4 undo snapshot to C's existing protected undo operation.

`POST /v4/lio/trip-undos` and `GET /v4/lio/trip-undo-receipts` carry two requests told apart by `version`
(LIO-answer-rich.1 `trip_receipt`): `LIO-trip-undo.4` restores the previous version (unchanged), and
`LIO-trip-undo.5` withdraws a Trip whose creating automatic save is undone (`undo.kind = withdraw_created`,
ADR-0012 revision 1, #1994). The receipt query of .5 adds `version=LIO-trip-undo.5`; without `version` it is
.4 exactly as before. Both answer `LIO-trip-undo-receipt.4` (the contract defines no other receipt shape).
With CJ_LIO_TRIP_AUTOSAVE on, both routes answer only the accounts on the autosave list (#2051 P2-1).
"""
from hashlib import sha256
import json
import re

from fastapi import Request
from starlette.concurrency import run_in_threadpool

from cj_message.domain import unique_fields
from cj_message.lio_plan_needs import lio_needs_id
from cj_message.needs_binding import needs_scope_for
from cj_needs.domain import Denied as NeedsDenied
from cj_trip.domain import Conflict, Denied, packed
from cj_trip.operation import OperationWithheld
from cj_trip.rich_undo import RichUndo
from cj_trip.withdrawal import Withdraw

from .history_routes import _query
from .lio_dialogue_routes import _failure, _json
from .local_app import scope_for
from .lio_trip_routes import _conversation, _require_selected_trip, _rich_target
from .message_routes import BodyError, _read_body, _token


RESTORE, WITHDRAW = 'LIO-trip-undo.4', 'LIO-trip-undo.5'
CURRENT_FIELDS = ('trip_id', 'expected_version', 'original_hash', 'content_version')
PREVIOUS_FIELDS = ('restore_version', 'restore_hash', 'restore_content_version')
CONTENT_VERSIONS = ('structured.1', 'structured.2', 'structured.3', 'structured.4')
MAX_UNDO_BYTES = 2048


def _original(payload):
    if (type(payload) is not dict or payload.keys() != {'version', 'action_id', 'target', 'conversation_id'}
            or payload['version'] not in (RESTORE, WITHDRAW)):
        raise ValueError('explicit native4 undo required')
    if payload['version'] == WITHDRAW:
        return _created(payload)
    cid = _conversation(payload, True)
    target = payload['target']
    if (type(target) is not dict or target.keys() != {*CURRENT_FIELDS, *PREVIOUS_FIELDS}
            or type(target['restore_version']) is not int or target['restore_version'] < 1
            or type(target['restore_hash']) is not str or re.fullmatch('[0-9a-f]{64}', target['restore_hash']) is None
            or target['restore_content_version'] not in CONTENT_VERSIONS):
        raise ValueError('exact native4 restore target required')
    current = {key: target[key] for key in CURRENT_FIELDS}
    action = RichUndo.parse(packed(dict(current, version='TRIP-lio-undo.3', action_id=payload['action_id'])))
    if target['restore_version'] != action.expected_version - 1:
        raise ValueError('restore target must be the immediate previous version')
    return action, cid, target


def _created(payload):
    """LIO-trip-undo.5: the receipt's `withdraw_created` target, exactly the four fields of version 1."""
    cid = _conversation(payload, True)
    target = payload['target']
    if (type(target) is not dict or target.keys() != set(CURRENT_FIELDS) or type(target['expected_version']) is not int
            or target['expected_version'] != 1 or type(target['original_hash']) is not str
            or re.fullmatch('[0-9a-f]{64}', target['original_hash']) is None
            or target['content_version'] not in CONTENT_VERSIONS):
        raise ValueError('exact created-Trip withdrawal target required')
    action = Withdraw.build(payload['action_id'], target['trip_id'], 1, target['original_hash'],
                            target['content_version'])
    return action, cid, target


def _created_target(trip):
    return dict(trip_id=trip.trip_id, expected_version=trip.version, original_hash=sha256(trip.content).hexdigest(),
                content_version=json.loads(trip.content)['content_version'])


def _check_created(context, action, cid, target):
    """Before the withdrawal: still the conversation's selected Trip, and its version 1 is the target."""
    _require_selected_trip(context, action, cid)
    versions = context.lio_revisions(action.trip_id, before=2, limit=1)
    if len(versions) != 1 or _created_target(versions[0]) != target:
        raise Conflict('created Trip withdrawal snapshot changed')


def _needs(context, cid):
    principal = context.metadata.principal
    scope = scope_for(principal.issuer, principal.subject)
    return needs_scope_for(scope), lio_needs_id(scope, cid)


def _admitted(context):
    """#2051 P2-1: with CJ_LIO_TRIP_AUTOSAVE on, the undo routes answer only the accounts on its list."""
    from .lio_trip_autosave import autosave_for, autosave_mode
    if autosave_mode() == 'on':
        principal = context.metadata.principal
        if autosave_for(scope_for(principal.issuer, principal.subject)) is not True:
            raise Denied('automatic save undo is not enabled for this account')


def _check_original(context, action, cid, target):
    _require_selected_trip(context, action, cid)
    # Accepted revisions are immutable. Use the request's version even after
    # the current head advances, so receipt lookup checks the same two bytes.
    versions = context.lio_revisions(action.trip_id, before=action.expected_version + 1, limit=2)
    if len(versions) != 2 or _rich_target(*versions) != target:
        raise Conflict('native4 undo snapshot changed')


def register_lio_rich_undo_routes(app, boundary):
    async def invoke(token, original, *, write=False):
        action, cid, target = original

        def result(committed):
            return packed(dict(version='LIO-trip-undo-receipt.4', conversation_id=cid,
                               action_id=action.action_id, committed=committed))

        def receipt(context):
            _admitted(context)
            if isinstance(action, Withdraw):
                # After the withdrawal the Trip is no longer selected: the committed one is found by its own
                # mark and source association; otherwise it must still be the selected version 1.
                found = context.withdraw_receipt(action, *_needs(context, cid))
                if found is None:
                    _check_created(context, action, cid, target)
                return result(found is not None)
            _check_original(context, action, cid, target)
            return result(context.rich_undo_receipt(action) is not None)

        def apply(context):
            _admitted(context)
            if isinstance(action, Withdraw):
                # A replay returns the committed withdrawal (the Trip is no longer selected by then).
                if context.withdraw_receipt(action, *_needs(context, cid)) is None:
                    _check_created(context, action, cid, target)
                    context.withdraw_created(action)
                return result(True)
            _check_original(context, action, cid, target)
            context.undo_rich(action)
            return result(True)

        def perform():
            if not write:
                return boundary.with_operation(token, receipt)
            try:
                return boundary.with_operation(token, apply)
            except OperationWithheld as error:
                if not error.commit_possible:
                    raise
                return boundary.with_operation(token, receipt)

        try:
            value = json.loads(await run_in_threadpool(perform))
        except Conflict:
            return _failure(409)
        except (Denied, NeedsDenied):
            return _failure(403)
        except Exception:
            return _failure(503)
        if write and not value['committed']:
            return _failure(503)
        return _json(value)

    @app.post('/v4/lio/trip-undos')
    async def undo(request: Request):
        token = _token(request)
        if token is None:
            return _failure(401)
        if request.scope['query_string']:
            return _failure(400)
        try:
            raw = await _read_body(request, MAX_UNDO_BYTES)
            original = _original(json.loads(raw.decode('utf-8'), object_pairs_hook=unique_fields))
        except BodyError as error:
            return _failure(error.status)
        except (ValueError, UnicodeError, RecursionError):
            return _failure(400)
        return await invoke(token, original, write=True)

    @app.get('/v4/lio/trip-undo-receipts')
    async def lookup(request: Request):
        token = _token(request)
        if token is None:
            return _failure(401)
        try:
            params = _query(request, ('action_id', 'target', 'conversation_id'), ('version',))
            if len(params['target'].encode('utf-8')) > MAX_UNDO_BYTES:
                raise ValueError('bounded original restore target required')
            # No `version`: LIO-trip-undo.4 as before. Only .5 is ever sent as a query value.
            if params.get('version', WITHDRAW) != WITHDRAW:
                raise ValueError('only LIO-trip-undo.5 is named in a receipt query')
            version = params.pop('version', RESTORE)
            target = json.loads(params.pop('target'), object_pairs_hook=unique_fields)
            original = _original(dict(params, version=version, target=target))
        except (ValueError, UnicodeError, RecursionError):
            return _failure(400)
        return await invoke(token, original)
