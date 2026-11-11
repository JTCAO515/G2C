"""Explicit host-only MESSAGE-SOURCE@1 routes; no default consent authority."""
from cj_strict_json import compact
import base64
from dataclasses import asdict
import json

from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from cj_message.domain import InvalidInput
from cj_message.source import SourceQuery, EndQuery, VERSION
from cj_strict_json import reject_duplicates
from .message_routes import _token, _read_body, _body_error, _error, BodyError


def _parse(raw, fields):
    try:
        obj = json.loads(raw.decode('utf-8'), object_pairs_hook=reject_duplicates(InvalidInput, 'duplicate source field'))
        if type(obj) is not dict or set(obj) != fields | {'version'} or obj['version'] != VERSION:
            raise InvalidInput('invalid source request')
        return {k: v for k, v in obj.items() if k != 'version'}
    except (UnicodeError, ValueError, RecursionError):
        raise InvalidInput('invalid source request') from None


def _encode(value):
    return compact(value, ensure_ascii=True, allow_nan=True)


def _snapshot(value):
    return dict(version=VERSION, conversation_type='travel',
        cursor={k: v for k, v in asdict(value.cursor).items() if k != 'scope'},
        source_version=value.source_version, withdrawal_epoch=value.withdrawal_epoch,
        end=asdict(value.end) if value.end is not None else None,
        messages=[dict(receipt=asdict(m.receipt), original_utf8_base64=base64.b64encode(m.original_utf8).decode('ascii')) for m in value.messages])


def register_message_source_routes(app, boundary, policy):
    """Only trusted composition calls this; policy never comes from an HTTP body.

    App clients keep their existing routes. C may install its canonical SourcePolicy
    here or consume HistoryReadContext.with_enabled_source directly.
    """
    async def handle(request, *, finish):
        token = _token(request)
        if token is None:
            return _error(request, 401, 'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
        try:
            if request.scope['query_string']:
                raise InvalidInput('unexpected source query')
            raw = await _read_body(request, 16384)
            if finish:
                value = _parse(raw, {'conversation_id', 'generation', 'epoch', 'through', 'conversation_type'})
                if value.pop('conversation_type') != 'travel':
                    raise InvalidInput('service conversations unavailable')
                query = EndQuery(**value)
                encoded = await run_in_threadpool(boundary.finish_conversation, token, query,
                    lambda end: _encode(dict(request_id=request.state.request_id, version=VERSION, end=asdict(end))))
            else:
                query = SourceQuery(**_parse(raw, set(SourceQuery.__dataclass_fields__)))
                encoded = await run_in_threadpool(boundary.with_history_context, token,
                    lambda ctx: ctx.with_enabled_source(query, policy,
                        lambda snap: _encode(dict(request_id=request.state.request_id, **_snapshot(snap)))))
            return Response(encoded, media_type='application/json')
        except BodyError as exc:
            return _body_error(request, exc)
        except InvalidInput:
            return _error(request, 400, 'INVALID_SOURCE_REQUEST', 'input', 'failed', 'do_not_retry')
        except Exception:
            return _error(request, 503, 'MESSAGE_SOURCE_UNAVAILABLE', 'dependency',
                'unknown' if finish else 'failed', 'reconcile_original' if finish else 'retry_safe_read')

    @app.post('/internal/v1/message-source/read')
    async def read(request: Request):
        return await handle(request, finish=False)

    @app.post('/internal/v1/conversation-end')
    async def finish(request: Request):
        return await handle(request, finish=True)
