"""Shared App-authenticated boundary and metadata-only plugin call counts."""

from contextlib import closing
from datetime import datetime
from hashlib import sha256
import json
import re
import sqlite3
from zoneinfo import ZoneInfo

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from starlette.requests import ClientDisconnect

from cj_auth.interfaces import AdmissionReason, AdmissionStatus
from cj_strict_json import reject_duplicates


SHANGHAI = ZoneInfo('Asia/Shanghai')
MAX_BODY = 4096
BEARER = re.compile(r'Bearer ([A-Za-z0-9._~-]{1,4096})')


class PluginError(Exception):
    def __init__(self, status, code):
        super().__init__(code)
        self.status = status
        self.code = code


class PluginCalls:
    """A committed count survives restarts and precedes every provider dispatch."""

    def __init__(self, path, *, clock=lambda: datetime.now(SHANGHAI)):
        self.path = path
        self.clock = clock

    def reserve(self, principal, operation, limit):
        subject = json.dumps([principal.issuer, principal.subject], separators=(',', ':'))
        owner = sha256(subject.encode()).hexdigest()
        day = self.clock().astimezone(SHANGHAI).date().isoformat()
        try:
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute("""CREATE TABLE IF NOT EXISTS plugin_call (
                    day TEXT NOT NULL, owner TEXT NOT NULL, operation TEXT NOT NULL,
                    used INTEGER NOT NULL, PRIMARY KEY (day, owner, operation))""")
                changed = db.execute("""INSERT INTO plugin_call VALUES (?, ?, ?, 1)
                    ON CONFLICT (day, owner, operation) DO UPDATE SET used = used + 1
                    WHERE ? IS NULL OR used < ?""", (day, owner, operation, limit, limit)).rowcount
                if changed != 1:
                    raise PluginError(429, 'quota_exceeded')
        except sqlite3.Error:
            raise PluginError(503, 'unavailable') from None


def _authorize(checker, token, internal):
    decision = checker.check(token)
    if decision.status is AdmissionStatus.DENIED:
        if decision.reason in (AdmissionReason.NOT_INVITED, AdmissionReason.NOT_CJ_MEMBER):
            raise PluginError(403, 'not_enabled')
        raise PluginError(401, 'sign_in_required')
    if decision.status is not AdmissionStatus.ALLOWED or decision.principal is None:
        raise PluginError(503, 'unavailable')
    if decision.principal.subject not in internal:
        raise PluginError(403, 'not_enabled')
    return decision.principal


async def _bounded_body(request):
    if request.headers.get('content-type', '').partition(';')[0].strip().lower() != 'application/json':
        raise PluginError(400, 'invalid_request')
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_BODY:
            raise PluginError(413, 'request_too_large')
        data.extend(chunk)
    return data


def register_plugin(app, path, model, operation, *, enabled, checker, internal, calls, limit):
    @app.post(path)
    async def execute(request: Request):
        try:
            authorization = request.headers.getlist('authorization')
            match = BEARER.fullmatch(authorization[0]) if len(authorization) == 1 else None
            if match is None:
                raise PluginError(401, 'sign_in_required')
            if not enabled:
                raise PluginError(403, 'not_enabled')

            token = match[1]
            principal = await run_in_threadpool(_authorize, checker, token, internal)
            raw = await _bounded_body(request)
            try:
                data = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate plugin field'))
                arguments = model.model_validate(data)
            except (ValueError, RecursionError):
                raise PluginError(400, 'invalid_request') from None

            def run():
                current = _authorize(checker, token, internal)
                if (current.issuer, current.subject) != (principal.issuer, principal.subject):
                    raise PluginError(401, 'sign_in_required')
                calls.reserve(current, path, limit)
                return operation(arguments)

            status, body = 200, await run_in_threadpool(run)
        except ClientDisconnect:
            status, body = 400, {'error': 'invalid_request'}
        except PluginError as error:
            status, body = error.status, {'error': error.code}
        return JSONResponse(body, status_code=status, headers={'Cache-Control': 'no-store'})
