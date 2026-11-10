"""Lio history and explicit undo over the original source-bound Trip authority."""
import base64
import binascii
import json
import re

from fastapi import Request
from starlette.concurrency import run_in_threadpool

from cj_agent.draft import trip_scope_for
from cj_message.demo_dialogue import LIO_CHAT_PATTERN, lio_conversation
from cj_message.domain import unique_fields
from cj_message.lio_plan_needs import lio_needs_id
from cj_message.needs_binding import needs_scope_for
from cj_needs.domain import Denied as NeedsDenied
from cj_trip.auth_boundary import Boundary
from cj_trip.current_needs_source import CurrentNeedsSource
from cj_trip.domain import Conflict, Denied, packed
from cj_trip.lio_history import Undo
from cj_trip.needs_edit_store import NeedsEdits
from cj_trip.operation import OperationWithheld

from .history_routes import _query
from .lio_dialogue_routes import _failure, _json
from .lio_trip_cards import _card
from .local_app import scope_for
from .local_needs import protected_reader
from .message_routes import BodyError, _read_body, _token


def _target(head):
    data = packed(dict(trip_id=head.trip_id, expected_version=head.version,
                       original_hash=head.content_sha256))
    return base64.urlsafe_b64encode(data).decode().rstrip('=')


def _undo(action_id, target):
    if type(target) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,512}', target) is None:
        raise ValueError('invalid undo target')
    try:
        data = base64.b64decode(target + '=' * (-len(target) % 4), altchars=b'-_', validate=True)
        value = json.loads(data.decode('utf-8'), object_pairs_hook=unique_fields)
    except (binascii.Error, UnicodeError) as error:
        raise ValueError('invalid undo target') from error
    if (type(value) is not dict or value.keys() != {'trip_id', 'expected_version', 'original_hash'}
            or data != packed(value) or target != base64.urlsafe_b64encode(data).decode().rstrip('=')):
        raise ValueError('invalid undo target')
    return Undo.parse(packed(dict(value, version='TRIP-lio-undo.1', action_id=action_id)))


class LioTripBoundary(Boundary):
    def __init__(self, database, checker, confirmation_signer):
        self.database = database
        self.reader = protected_reader(database, checker)

        def resolve(principal):
            owner = scope_for(principal.issuer, principal.subject)
            return lambda: database.connect(owner), trip_scope_for(owner)

        super().__init__(checker, resolve, confirmation_signer, structured=True)

    def _bind(self, token):
        repository, principal, check = super()._bind(token)
        edits = NeedsEdits(CurrentNeedsSource(self.database, self.checker, token, self.reader))
        repository.needs_edits = edits

        def guard(stage):
            check(stage)
            if repository.needs_edits is not edits:
                raise Denied('Lio source binding changed')

        return repository, principal, guard


def _head(context, conversation):
    principal = context.metadata.principal
    scope = scope_for(principal.issuer, principal.subject)
    return context.lio_current_trip(needs_scope_for(scope), lio_needs_id(scope, conversation or lio_conversation(scope)))


def _history(context, before, conversation):
    head = _head(context, conversation)
    current = None
    target = None
    revisions = ()
    if head is not None:
        if before is None:
            snapshot = context.lio_revisions(head.trip_id)
            current = _card(snapshot[0])
            target = _target(head) if head.version > 1 else None
            revisions = snapshot[1:]
        elif before <= head.version:
            revisions = context.lio_revisions(head.trip_id, before=before)
        else:
            raise Conflict('Lio history changed')
        if _head(context, conversation) != head:
            raise Conflict('Lio history changed')
    next_before = str(revisions[-1].version) if revisions and revisions[-1].version > 1 else None
    value = dict(version='LIO-trip-history.1', current=current, history=[_card(v) for v in revisions],
                 undo_target=target, next_before=next_before)
    if conversation is not None:
        value.update(version='LIO-trip-history.2', conversation_id=conversation)
    response = packed(value)
    if len(response) > 4_500_000:
        raise ValueError('Lio history response exceeds its bound')
    return response


def _undo_result(action_id, committed, conversation):
    value = dict(version='LIO-trip-undo-receipt.1', action_id=action_id, committed=committed)
    if conversation is not None:
        value.update(version='LIO-trip-undo-receipt.2', conversation_id=conversation)
    return packed(value)


def _require_selected_trip(context, action, conversation):
    head = _head(context, conversation)
    if head is None or head.trip_id != action.trip_id:
        raise Denied('original Lio trip unavailable')


def _receipt(context, action, conversation):
    if conversation is not None:
        _require_selected_trip(context, action, conversation)
    receipt = context.lio_undo_receipt(action)
    return _undo_result(action.action_id, receipt is not None, conversation)


def _apply(context, action, conversation):
    _require_selected_trip(context, action, conversation)
    receipt = context.undo_lio(action)
    return _undo_result(receipt.action_id, True, conversation)


def _conversation(params, multiple):
    if not multiple:
        return None
    value = params['conversation_id']
    if type(value) is not str or not LIO_CHAT_PATTERN.fullmatch(value):
        raise ValueError('invalid Lio conversation identifier')
    return value


def register_lio_trip_routes(app, boundary):
    async def invoke(token, operation, *, reconcile=None):
        def perform():
            try:
                return boundary.with_operation(token, operation)
            except OperationWithheld as error:
                if reconcile is None or not error.commit_possible:
                    raise
                return boundary.with_operation(token, reconcile)

        try:
            value = json.loads(await run_in_threadpool(perform))
            return _failure(503) if reconcile is not None and not value['committed'] else _json(value)
        except Conflict:
            return _failure(409)
        except (Denied, NeedsDenied):
            return _failure(403)
        except Exception:
            return _failure(503)

    async def history(request, multiple):
        token = _token(request)
        if token is None:
            return _failure(401)
        try:
            params = _query(request, ('conversation_id',) if multiple else (), ('before',))
            conversation = _conversation(params, multiple)
            value = params.get('before')
            if value is not None and (re.fullmatch(r'[1-9][0-9]{0,18}', value) is None or int(value) >= 2**63):
                raise ValueError('invalid Lio history cursor')
            before = int(value) if value is not None else None
        except ValueError:
            return _failure(400)
        return await invoke(token, lambda context: _history(context, before, conversation))

    async def undo(request, multiple):
        token = _token(request)
        if token is None:
            return _failure(401)
        if request.scope['query_string']:
            return _failure(400)
        try:
            raw = await _read_body(request, 1024)
            value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_fields)
            fields = {'version', 'action_id', 'target', 'conversation_id'} if multiple else {
                'version', 'action_id', 'target'}
            version = 'LIO-trip-undo.2' if multiple else 'LIO-trip-undo.1'
            if type(value) is not dict or value.keys() != fields or value['version'] != version:
                raise ValueError('invalid undo request')
            conversation = _conversation(value, multiple)
            action = _undo(value['action_id'], value['target'])
        except BodyError as error:
            return _failure(error.status)
        except (ValueError, UnicodeError, RecursionError):
            return _failure(400)

        return await invoke(token, lambda context: _apply(context, action, conversation),
                            reconcile=lambda context: _receipt(context, action, conversation))

    async def receipt(request, multiple):
        token = _token(request)
        if token is None:
            return _failure(401)
        try:
            fields = ('action_id', 'target', 'conversation_id') if multiple else ('action_id', 'target')
            params = _query(request, fields)
            conversation = _conversation(params, multiple)
            action = _undo(params['action_id'], params['target'])
        except (ValueError, UnicodeError, RecursionError):
            return _failure(400)
        return await invoke(token, lambda context: _receipt(context, action, conversation))

    @app.get('/v1/lio/trip')
    async def history_default(request: Request):
        return await history(request, False)

    @app.get('/v2/lio/trip')
    async def history_conversation(request: Request):
        return await history(request, True)

    @app.post('/v1/lio/trip/undo')
    async def undo_default(request: Request):
        return await undo(request, False)

    @app.post('/v2/lio/trip/undo')
    async def undo_conversation(request: Request):
        return await undo(request, True)

    @app.get('/v1/lio/trip/undo')
    async def receipt_default(request: Request):
        return await receipt(request, False)

    @app.get('/v2/lio/trip/undo')
    async def receipt_conversation(request: Request):
        return await receipt(request, True)
