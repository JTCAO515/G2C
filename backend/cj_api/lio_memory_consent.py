"""The account's consent to Lio memory suggestions (#1970, W4-3b), behind CJ_LIO_MEMORY_CONSENT_REQUIRED.

With the switch off (the default) nothing here is read and Lio behaves as before. With it on, memory
suggestions are generated and shown only while the account's last consent record is `granted`; no
record, or a withdrawal, means no suggestion is generated and none is delivered or accepted.

The record is the server's own, append-only (migration 0060) and written by the account itself
through `PUT /v1/lio/memory/consent`; no request field of any other route carries consent. Every
read fails closed: a read that cannot be completed counts as not consented.
"""
import json
import logging
import os
import re

from cj_message.domain import InvalidInput, unique_fields
from cj_message.postgres import Repository

VERSION = 'LIO-memory-consent.1'
STATES = ('granted', 'withdrawn')
_TEXT_VERSION = re.compile(r'[A-Za-z0-9._:-]{1,64}')
_REQUEST_ID = re.compile(r'[A-Za-z0-9._:-]{1,128}')
_LOGGER = logging.getLogger(__name__)


def consent_required():
    """Server switch; off unless explicitly set to 1."""
    value = os.environ.get('CJ_LIO_MEMORY_CONSENT_REQUIRED', '0')
    if value not in ('0', '1'):
        raise ValueError('explicit memory consent switch value required')
    return value == '1'


class Conflict(Exception):
    """The request id was used for a different consent change."""


class ConsentStore:
    """Reads and appends one account's consent records through the account-scoped connection."""

    def __init__(self, database):
        self.database = database

    def _transaction(self, scope):
        return Repository(lambda: self.database.connect(scope), scope).transaction()

    @staticmethod
    def _current(cur, scope):
        row = cur.execute('SELECT seq,state,consent_text_version,changed_at FROM cj_lio_memory_consent '
                          'WHERE scope=%s ORDER BY seq DESC LIMIT 1', (scope,)).fetchone()
        return None if row is None else dict(seq=row[0], state=row[1], consent_text_version=row[2], changed_at=row[3])

    def current(self, scope):
        """{recorded, state, consent_text_version, changed_at}; an account with no record is not consented."""
        with self._transaction(scope) as tx:
            row = self._current(tx.cur, scope)
        if row is None:
            return dict(recorded=False, state='withdrawn', consent_text_version=None, changed_at=None)
        return dict(recorded=True, state=row['state'], consent_text_version=row['consent_text_version'],
                    changed_at=row['changed_at'])

    def granted(self, scope):
        """True only while the last record says granted. Any failure to read it is a refusal."""
        try:
            return self.current(scope)['state'] == 'granted'
        except Exception as error:
            _LOGGER.warning('lio_memory_consent_unreadable error=%s', type(error).__name__)
            return False

    def record(self, scope, state, consent_text_version, request_id):
        """Append a change and return the current state. The same request id again returns the same
        change; a different change under an old request id is a Conflict; asking for the state the
        account is already in writes nothing."""
        with self._transaction(scope) as tx:
            tx.lock_scope()
            old = tx.cur.execute('SELECT seq,state,consent_text_version FROM cj_lio_memory_consent '
                                 'WHERE scope=%s AND request_id=%s', (scope, request_id)).fetchone()
            if old is not None:
                if (old[1], old[2]) != (state, consent_text_version):
                    raise Conflict('request id used for another consent change')
                return self._shape(self._current(tx.cur, scope))
            last = self._current(tx.cur, scope)
            if last is None or last['state'] != state:
                tx.cur.execute('INSERT INTO cj_lio_memory_consent(scope,seq,state,consent_text_version,request_id) '
                               'VALUES(%s,%s,%s,%s,%s)',
                               (scope, 1 if last is None else last['seq'] + 1, state, consent_text_version, request_id))
                last = self._current(tx.cur, scope)
            return self._shape(last)

    @staticmethod
    def _shape(row):
        return dict(recorded=True, state=row['state'], consent_text_version=row['consent_text_version'],
                    changed_at=row['changed_at'])


def parse_request(raw):
    """A strict PUT body, or ValueError."""
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_fields)
    except (UnicodeError, ValueError, InvalidInput, RecursionError) as error:
        raise ValueError('invalid memory consent request') from error
    if (type(value) is not dict or value.keys() != {'version', 'state', 'consent_text_version', 'request_id'}
            or value['version'] != VERSION or value['state'] not in STATES
            or type(value['consent_text_version']) is not str or _TEXT_VERSION.fullmatch(value['consent_text_version']) is None
            or type(value['request_id']) is not str or _REQUEST_ID.fullmatch(value['request_id']) is None):
        raise ValueError('invalid memory consent request')
    return value['state'], value['consent_text_version'], value['request_id']


def wire(state):
    """The response body for a store result."""
    value = dict(version=VERSION, state=state['state'], recorded=state['recorded'],
                 consent_text_version=state['consent_text_version'])
    value['changed_at'] = None if state['changed_at'] is None else state['changed_at'].isoformat(timespec='milliseconds')
    return value


def register_lio_memory_consent_routes(app, boundary, store):
    """`boundary` is the Lio dialogue boundary (admission and the signed account); `store` a ConsentStore."""
    from fastapi import Request
    from starlette.concurrency import run_in_threadpool
    from cj_message.auth_boundary import AccessBlocked, IdentityChanged
    from .lio_dialogue_routes import _failure, _json
    from .message_routes import BodyError, _read_body, _token

    async def handle(request, write):
        token = _token(request)
        if token is None:
            return _failure(401)
        if request.scope['query_string']:
            return _failure(400)
        try:
            change = parse_request(await _read_body(request, 4096)) if write else None

            def operate(context):
                return store.record(context.scope, *change) if write else store.current(context.scope)

            return _json(wire(await run_in_threadpool(boundary.with_history_context, token, operate)))
        except BodyError as error:
            return _failure(error.status)
        except (ValueError, UnicodeError):
            return _failure(400)
        except Conflict:
            return _failure(409)
        except (AccessBlocked, IdentityChanged):
            return _failure(403)
        except Exception:
            return _failure(503)

    @app.put('/v1/lio/memory/consent')
    async def put_consent(request: Request):
        return await handle(request, True)

    @app.get('/v1/lio/memory/consent')
    async def get_consent(request: Request):
        return await handle(request, False)
