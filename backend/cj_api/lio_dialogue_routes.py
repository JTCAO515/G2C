"""User-facing send and polling routes over the original dialogue service."""
import json

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from cj_message.demo_dialogue import LIO_CHAT_PATTERN, message_id
from cj_message.domain import InvalidInput
from cj_message.lio_context import SOURCE_EFFECT
from cj_message.lio_plan_needs import BOUND_EFFECT
from cj_run.core import Binding
from cj_run.display_snapshot import SnapshotTooLarge

from .history_routes import _query
from .message_routes import BodyError, _read_body, _token, message_failure


TIMELINE_VERSION = 'LIO-timeline.1'
RECEIPT_VERSION = 'LIO-message-receipt.1'


def _json(value, status=200):
    return JSONResponse(value, status_code=status, headers={'Cache-Control': 'no-store'})


def _failure(status):
    return _json({'failure': 'quota' if status == 429 else 'unavailable'}, status)


def _message(item, state, *, expired=False, trip=None):
    failure = None
    if trip is not None:
        status = 'completed'
    elif expired:
        status, failure = 'failed', 'unavailable'
    elif state is None or state.status == 'queued':
        status = 'sending'
    elif state.status == 'running':
        status = 'answering'
    elif state.status == 'completed' and state.draft_outcome is None:
        status = 'completed'
    else:
        status = 'failed'
        failure = ('quota' if state.budget_exhausted_stage != 'none'
                   else 'unavailable')
    sources = []
    if state is not None:
        for effect in state.effects:
            if effect.startswith(SOURCE_EFFECT):
                citation = json.loads(effect.removeprefix(SOURCE_EFFECT))
                sources.append(dict(title=citation['title'], url=citation['url'],
                                    observed_at=citation['observed_at']))
    return dict(message_id=item.message_id, text=item.text, answer=state.text if state else '',
                status=status, failure=failure, sources=sources, trip=trip, memory=None)


def _timeline(boundary, resolve_runs, trip_cards, token, conversation_id, before):
    def project(context):
        page = context.lio_timeline(conversation_id, before)
        messages = []
        if page.messages:
            repository = resolve_runs(context.scope)
            bindings = [Binding(context.scope, page.conversation_id, page.generation,
                                item.message_id, item.run_id, item.sequence) for item in page.messages]
            snapshots = repository.lio_timeline(bindings)
            for item, binding, (state, expired) in zip(page.messages, bindings, snapshots, strict=True):
                trip = (trip_cards.read(token, binding)
                        if state is not None and BOUND_EFFECT in state.effects else None)
                messages.append(_message(item, state, expired=expired, trip=trip))
        response = _json(dict(version=TIMELINE_VERSION, conversation_id=page.conversation_id,
                              messages=messages, next_before=page.next_before))
        if len(response.body) > 4_500_000:
            raise SnapshotTooLarge('Lio timeline exceeds response bound')
        if context.lio_timeline(conversation_id, before) != page:
            return _failure(503)
        return response

    return boundary.with_history_context(token, project)


def register_lio_dialogue_routes(app, boundary, resolve_runs, trip_cards):
    @app.post('/v1/lio/messages')
    async def send(request: Request):
        token = _token(request)
        if token is None:
            return _failure(401)
        if request.scope['query_string']:
            return _failure(400)
        try:
            raw = await _read_body(request, 16384)
            receipt = await run_in_threadpool(boundary.receive_lio, token, raw)
        except BodyError as exc:
            return _failure(exc.status)
        except Exception as exc:
            return _failure(message_failure(request, exc, True).status_code)
        return _json(dict(version=RECEIPT_VERSION, message_id=receipt.message_id,
                          conversation_id=receipt.conversation_id))

    @app.get('/v1/lio/timeline')
    async def timeline(request: Request):
        token = _token(request)
        if token is None:
            return _failure(401)
        try:
            params = _query(request, (), ('conversation_id', 'before'))
            conversation = params.get('conversation_id')
            if conversation is not None and not LIO_CHAT_PATTERN.fullmatch(conversation):
                raise InvalidInput('invalid Lio conversation identifier')
            before = message_id(params['before']) if 'before' in params else None
        except (ValueError, UnicodeError):
            return _failure(400)
        try:
            return await run_in_threadpool(_timeline, boundary, resolve_runs, trip_cards, token,
                                           conversation, before)
        except Exception as exc:
            return _failure(message_failure(request, exc, False).status_code)
