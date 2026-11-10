"""Display C's original memory candidates and apply only an explicit Lio choice."""
import base64
import binascii
from hashlib import sha256
import json
import re

from fastapi import Request
from starlette.concurrency import run_in_threadpool

from cj_memory_jobs.candidate import CandidateAction
from cj_memory_jobs.codec import Conflict, Unavailable, job_identity
from cj_memory_jobs.postgres import encode
from cj_memory_jobs.service import OperationWithheld
from cj_message.auth_boundary import AccessBlocked, IdentityChanged
from cj_message.demo_dialogue import message_id
from cj_message.domain import unique_fields

from .lio_dialogue_routes import _failure, _json
from .message_routes import BodyError, _read_body, _token


_TARGET_FIELDS = {'message_id', 'job_id', 'attempt_id', 'candidate_id', 'expected_candidate_version',
                  'expected_memory_epoch', 'kind', 'text', 'occurred_at'}
_REVIEW_CONTENT = ('kind', 'text', 'occurred_at')
_MAX_TARGET_BYTES = 262144


def _encode_target(value):
    return base64.urlsafe_b64encode(encode(value)).decode().rstrip('=')


def _decode_target(token):
    if (type(token) is not str or not 0 < len(token) <= _MAX_TARGET_BYTES
            or re.fullmatch(r'[A-Za-z0-9_-]+', token) is None):
        raise ValueError('invalid memory target')
    try:
        raw = base64.b64decode(token + '=' * (-len(token) % 4), altchars=b'-_', validate=True)
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_fields)
    except (binascii.Error, UnicodeError) as error:
        raise ValueError('invalid memory target') from error
    if (type(value) is not dict or value.keys() != _TARGET_FIELDS or token != _encode_target(value)
            or value['kind'] not in ('fact', 'preference')):
        raise ValueError('invalid memory target')
    message_id(value['message_id'])
    return value


def _action(action_id, operation, target):
    value = {key: target[key] for key in _TARGET_FIELDS - {'message_id', *_REVIEW_CONTENT}}
    internal_id = 'lio-memory-' + sha256(job_identity(action_id).encode()).hexdigest()
    value.update(version='MEMORY-CANDIDATE@1', action_id=internal_id,
                 operation='confirm' if operation == 'remember' else 'reject')
    if operation == 'remember':
        value.update({key: target[key] for key in _REVIEW_CONTENT})
        value.update(extent='long_term', context=None)
    original = encode(value)
    CandidateAction.parse(original)
    return internal_id, original


def _tags(projected, mid):
    for candidate in projected['candidates']:
        target = _encode_target(dict(
            message_id=mid, **candidate['review'],
            candidate_id=candidate['candidate_id'], expected_candidate_version=candidate['version'],
            expected_memory_epoch=projected['memory_epoch'],
            **{key: candidate[key] for key in _REVIEW_CONTENT}))
        yield dict(id=candidate['candidate_id'], kind=candidate['kind'], text=candidate['text'], target=target)


class LioMemoryCards:
    """Mount only with a trusted C reader that accepts original Lio Travel messages."""

    def __init__(self, collection, read_current):
        self.collection = collection
        self.read_current = read_current

    def project(self, context, token, mid, run_id=None):
        stored = context.query_lio_message(mid)
        if stored is None or run_id is not None and run_id != stored.receipt.run_id:
            raise Unavailable('original Lio memory message unavailable')
        projected = self.read_current(context, token, mid, stored.receipt.run_id)
        if projected is None:
            return None
        tags = list(_tags(json.loads(projected), mid))
        return dict(tags=tags) if tags else None

    def decide(self, token, request, *, read_only=False):
        action_id, operation, encoded = request['action_id'], request['operation'], request['target']
        target = _decode_target(encoded)
        internal_id, original = _action(action_id, operation, target)
        receipt = json.loads(self.collection.query_candidate_action(token, internal_id))
        if receipt is None and not read_only:
            current = self.collection.boundary.with_history_context(
                token, lambda context: self.project(context, token, target['message_id']))
            if current is None or not any(tag['target'] == encoded for tag in current['tags']):
                raise Conflict('original Lio memory suggestion changed')
            try:
                receipt = json.loads(self.collection.apply_candidate(token, original))
            except OperationWithheld:
                receipt = json.loads(self.collection.query_candidate_action(token, internal_id))
        status = 'pending'
        if receipt is not None:
            if receipt['input_sha256'] != sha256(original).hexdigest():
                raise Conflict('original Lio memory choice changed')
            status = 'remembered' if operation == 'remember' else 'dismissed'
        return dict(version='LIO-memory-action-receipt.1', action_id=action_id, status=status)


def register_lio_memory_routes(app, memory_cards):
    async def invoke(request, *, read_only):
        token = _token(request)
        if token is None:
            return _failure(401)
        if request.scope['query_string']:
            return _failure(400)
        try:
            raw = await _read_body(request, _MAX_TARGET_BYTES + 4096)
            value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_fields)
            if (type(value) is not dict or value.keys() != {'version', 'action_id', 'operation', 'target'}
                    or value['version'] != 'LIO-memory-action.1'
                    or value['operation'] not in ('remember', 'dismiss')):
                raise ValueError('invalid Lio memory choice')
            return _json(await run_in_threadpool(memory_cards.decide, token, value, read_only=read_only))
        except BodyError as error:
            return _failure(error.status)
        except (ValueError, UnicodeError, RecursionError):
            return _failure(400)
        except Conflict:
            return _failure(409)
        except (AccessBlocked, IdentityChanged):
            return _failure(403)
        except Exception:
            return _failure(503)

    @app.post('/v1/lio/memory/actions')
    async def decide(request: Request):
        return await invoke(request, read_only=False)

    @app.post('/v1/lio/memory/receipt')
    async def receipt(request: Request):
        # This route is read-only. The original target is carried in the body,
        # not the URL, because it includes the exact text the user reviewed.
        return await invoke(request, read_only=True)
