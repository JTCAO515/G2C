"""GET /v1/run-events: server-sent events over the protected RUN display snapshot (P2a).

Every poll goes through the same DisplaySnapshotReader (MESSAGE owner guard + RUN
recovery read) as /v1/run-display, so this route adds no authority of its own.
Event ids are cumulative UTF-8 byte offsets of the answer text; a client resumes
with Last-Event-ID and never receives a byte twice.
"""
import asyncio
from dataclasses import dataclass
import json
import time

from fastapi import Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from .history_routes import _query
from .message_routes import _error, _token

TERMINAL = frozenset({'completed', 'failed', 'cancelled', 'context_invalid', 'unknown'})


@dataclass(frozen=True)
class RunEventsConfiguration:
    poll_interval_seconds: float
    max_stream_seconds: float

    def __post_init__(self):
        if not 0 < self.poll_interval_seconds <= 5 or not 0 < self.max_stream_seconds <= 600:
            raise ValueError('explicit bounded poll interval and stream duration required')


def _sse(event, data, event_id=None):
    lines = [f'event: {event}']
    if event_id is not None:
        lines.append(f'id: {event_id}')
    lines.append('data: ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')))
    return ('\n'.join(lines) + '\n\n').encode('utf-8')


def register_run_events_route(app, reader=None, display_configuration=None, configuration=None):
    def unavailable(request):
        return _error(request, 503, 'RUN_EVENTS_UNAVAILABLE', 'dependency', 'unknown', 'retry_safe_read')

    @app.get('/v1/run-events')
    async def stream(request: Request):
        if reader is None or configuration is None:
            return unavailable(request)
        token = _token(request)
        if token is None:
            return _error(request, 401, 'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
        try:
            mid = _query(request, ('message_id',))['message_id']
            if not mid.strip() or '\x00' in mid or len(mid.encode()) > display_configuration.max_message_id_bytes:
                raise ValueError('invalid message id')
            raw_offset = request.headers.get('last-event-id', '0')
            if not raw_offset.isdigit() or len(raw_offset) > 12:
                raise ValueError('invalid Last-Event-ID')
            offset = int(raw_offset)
        except (ValueError, UnicodeError):
            return _error(request, 400, 'INVALID_INPUT', 'input', 'failed', 'do_not_retry')

        def snapshot():
            payload = json.loads(reader.read(token, mid))
            return payload['status'], payload['text'].encode('utf-8')

        try:
            status, text = await run_in_threadpool(snapshot)
        except Exception:
            # Same withholding as /v1/run-display: absent, foreign and unavailable look alike.
            return unavailable(request)
        if offset > len(text):
            return _error(request, 409, 'RESYNC_REQUIRED', 'input', 'failed', 'retry_safe_read')
        try:
            text[offset:].decode('utf-8')
        except UnicodeDecodeError:
            return _error(request, 400, 'INVALID_INPUT', 'input', 'failed', 'do_not_retry')

        async def events():
            nonlocal status, text
            sent, last_status = offset, None
            deadline = time.monotonic() + configuration.max_stream_seconds
            while True:
                if len(text) > sent:
                    yield _sse('delta', {'text': text[sent:].decode('utf-8')}, len(text))
                    sent = len(text)
                if status != last_status:
                    yield _sse('status', {'status': status}, sent)
                    last_status = status
                if status in TERMINAL or time.monotonic() >= deadline or await request.is_disconnected():
                    return
                await asyncio.sleep(configuration.poll_interval_seconds)
                try:
                    status, text = await run_in_threadpool(snapshot)
                except Exception:
                    yield _sse('status', {'status': 'unavailable'}, sent)
                    return

        return StreamingResponse(events(), media_type='text/event-stream',
                                 headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})
