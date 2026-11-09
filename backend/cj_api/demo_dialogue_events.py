"""Resumable dialogue status and answer events from one protected original RUN."""
import asyncio
from dataclasses import dataclass
import json
import time

from fastapi import Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from cj_message.demo_dialogue import message_id
from cj_run.core import Binding, TERMINAL
from cj_run.display_snapshot import RunSnapshotAdvanced, SnapshotChanged, SnapshotUnavailable
from cj_run.postgres import RunScopeBusy

from .history_routes import _query
from .message_routes import _error, _token, message_failure
from .run_events_routes import _sse


EVENT_VERSION = 'DEMO-dialogue-event.1'
RUN_EVENT_STRIDE = 64


@dataclass(frozen=True)
class EventPage:
    frames: tuple[tuple[int, bytes], ...]
    cursor_known: bool
    terminal: bool
    more: bool


def _project(binding, state, after, *, needs=None, trip=None):
    frames = []
    cursor_known = after == 0
    more = False

    def add(event_id, kind, payload):
        nonlocal cursor_known, more
        if event_id == after:
            cursor_known = True
        if event_id <= after:
            return
        if len(frames) == 128:
            more = True
            return
        event = dict(version=EVENT_VERSION, event_id=str(event_id), conversation_id=binding.conversation_id,
                     message_id=binding.message_id, run_id=binding.run_id, kind=kind, payload=payload)
        frames.append((event_id, _sse(kind, event, event_id)))

    add(1, 'status', dict(status='queued', stage='queued'))
    if state is not None:
        if len(state.text.encode('utf-8')) > 200000:
            raise SnapshotUnavailable('dialogue answer exceeds the protected read bound')
        for event in state.events:
            index = event.sequence * RUN_EVENT_STRIDE
            if event.kind == 'text_delta':
                add(index, 'answer_delta', dict(text=event.value))
            elif event.kind == 'effect_committed' and event.value == 'demo_needs_card':
                if needs is None:
                    raise SnapshotUnavailable('original needs card missing')
                add(index, 'needs_card', needs)
            elif event.kind == 'effect_committed' and event.value.startswith('trip_proposal:') and state.status=='completed':
                card,sources=trip
                add(index,'trip_candidate',card)
                for offset,source in enumerate(sources,1):
                    add(index+offset,'source',source)
            elif event.kind == 'started' or event.kind in TERMINAL:
                status = 'running' if event.kind == 'started' else event.kind
                payload = dict(status=status, stage=status)
                if status == 'failed':
                    payload['error_code'] = ('BUDGET_EXHAUSTED' if state.budget_exhausted_stage == 'answer'
                                             else 'RUN_FAILED')
                elif status == 'unknown':
                    payload['error_code'] = 'RUN_OUTCOME_UNKNOWN'
                elif status == 'context_invalid':
                    payload['error_code'] = 'RUN_CONTEXT_INVALID'
                add(index, 'status', payload)
    return EventPage(tuple(frames), cursor_known, not more and state is not None and state.status in TERMINAL, more)


def _read(boundary, resolve_run_repository, trip_cards, token, mid, after):
    def operation(ctx):
        source = ctx.query_dialogue_message(mid)
        if source is None:
            raise SnapshotUnavailable('original dialogue unavailable')
        receipt = source.stored.receipt
        binding = Binding(ctx.scope, receipt.conversation_id, receipt.generation, receipt.message_id,
                          receipt.run_id, receipt.sequence)
        repository = resolve_run_repository(ctx.scope)
        if repository.scope != ctx.scope:
            raise SnapshotUnavailable('dialogue RUN scope mismatch')
        state = repository.snapshot_optional(binding)
        if state is None:
            page = _project(binding,state,after)
        else:
            needs=(ctx.query_dialogue_needs(binding.message_id,binding.run_id)
                   if 'demo_needs_card' in state.effects else None)
            candidate=next((effect.removeprefix('trip_proposal:') for effect in state.effects
                            if effect.startswith('trip_proposal:')),None)
            trip=(trip_cards.read(token,binding,candidate)
                  if candidate is not None and state.status=='completed' else None)
            page=_project(binding,state,after,needs=needs,trip=trip)
        final = repository.snapshot_optional(binding)
        if ctx.query_dialogue_message(mid) != source:
            raise SnapshotChanged('dialogue source changed')
        if final != state:
            if final is not None and (state is None or final.events[:state.sequence] == state.events
                                      and final.sequence > state.sequence and final.usage == state.usage):
                raise RunSnapshotAdvanced('original RUN advanced during projection')
            raise SnapshotChanged('dialogue RUN changed')
        return page

    return boundary.with_history_context(token, operation)


def register_dialogue_event_stream(app, boundary, resolve_run_repository, trip_cards):
    @app.get('/v1/demo-dialogue/events')
    async def events(request: Request):
        token = _token(request)
        if token is None:
            return _error(request, 401, 'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
        try:
            mid = message_id(_query(request, ('message_id',))['message_id'])
            headers = request.headers.getlist('last-event-id')
            raw = headers[0] if headers else '0'
            if len(headers) > 1 or len(raw) > 12 or not raw.isascii() or not raw.isdigit():
                raise ValueError('invalid dialogue event cursor')
            after = int(raw)
        except (ValueError, UnicodeError):
            return _error(request, 400, 'INVALID_INPUT', 'input', 'failed', 'do_not_retry')

        def read(cursor):
            return _read(boundary, resolve_run_repository, trip_cards, token, mid, cursor)

        try:
            try:
                page = await run_in_threadpool(read, after)
            except (RunSnapshotAdvanced, RunScopeBusy):
                page = await run_in_threadpool(read, after)
        except Exception as exc:
            return message_failure(request, exc, False)
        if not page.cursor_known:
            return _error(request, 409, 'RESYNC_REQUIRED', 'input', 'failed', 'retry_safe_read')

        async def stream():
            nonlocal page
            sent = after
            deadline = time.monotonic() + 120
            while True:
                for index, frame in page.frames:
                    yield frame
                    sent = index
                if page.terminal or time.monotonic() >= deadline or await request.is_disconnected():
                    return
                if not page.more:
                    await asyncio.sleep(0.2)
                try:
                    page = await run_in_threadpool(read, sent)
                except (RunSnapshotAdvanced, RunScopeBusy):
                    try:
                        page = await run_in_threadpool(read, sent)
                    except Exception:
                        return
                except Exception:
                    return
                if not page.cursor_known:
                    return

        return StreamingResponse(stream(), media_type='text/event-stream',
                                 headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})
