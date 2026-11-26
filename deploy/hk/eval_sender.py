"""Operator-run Hong Kong evaluation sender for the release evaluation (#1868, for #1761).

Runs on the operator's Mac against the public API (``server_smoke.ORIGIN``), the same Lio
dialogue route the App uses (``/v4/lio/messages`` and ``/v4/lio/timeline``). It adds no server
endpoint and holds no credential: the operator supplies a 0600 file with a session for the
dedicated internal-test evaluation account at run time.

    python -B -m deploy.hk.eval_sender login --invite-file CODE_FILE --session-out SESSION_FILE
    python -B -m deploy.hk.eval_sender run --session-file SESSION_FILE --cases ID[,ID...] \\
        --repeats 1 --real --max-calls N --max-cost-cny X --cost-per-turn-cny P --output RUN.json

``run`` refuses real calls unless ``--real``, ``--max-calls``, ``--max-cost-cny`` and
``--cost-per-turn-cny`` are all given and the plan fits (``eval.release_eval.run``). Only case
ids that ``eval.release_eval.bank.load_bank`` returns are accepted. Each send opens a new
conversation and plays every turn in it; only the last turn's answer and timing are returned.
Timing is what the client sees: ``first_token_ms`` is the first timeline poll that shows answer
text after the last turn was sent, so it is accurate to one poll interval.
Errors are short codes; tokens, invite codes and response bodies never appear in output.
"""
import argparse
from datetime import datetime, timezone
import http.client
import json
import os
from pathlib import Path
import stat
import sys
import time
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, build_opener
import uuid

from cj_strict_json import reject_duplicates

from .server_smoke import ORIGIN, NoRedirect, SmokeResult, request

MESSAGE_VERSION = 'LIO-message.4'
TIMELINE_VERSION = 'LIO-timeline.4'
TERMINAL = frozenset({'completed', 'failed', 'cancelled'})
POLL_SECONDS = 0.5
TURN_SECONDS = 420
INVITE_VERSION = 'DEMO-invite-session.2'
POLL_RETRIES = 3


def _private_read(path, limit=8192):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('owned_0600_file_required')
        raw = source.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('bounded_private_file_required')
    return raw


def _reserve(path):
    """Create the private output first, so a run never spends calls it cannot record."""
    return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)


def _finish(descriptor, raw):
    with os.fdopen(descriptor, 'wb') as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())


def _private_write(path, raw):
    _finish(_reserve(path), raw)


def login(invite_file, session_out, *, opener=None):
    """Exchange the evaluation account's invite code for a rolling session (no output of either)."""
    code = _private_read(invite_file).decode('ascii').strip()
    descriptor = _reserve(session_out)  # before the exchange: an existing file costs no exchange
    try:
        body = json.dumps(dict(version=INVITE_VERSION, invite_code=code, consent=True)).encode()
        opener = opener or build_opener(NoRedirect())
        try:
            with opener.open(Request(ORIGIN + '/v2/demo-invite-sessions', data=body,
                                     headers={'Content-Type': 'application/json', 'Accept': 'application/json'}),
                             timeout=15) as response:
                raw = response.read(65537)
                status = response.status
        except HTTPError as error:
            code_value = error.code
            error.close()
            raise SmokeResult('FAIL', f'login_http_{code_value}') from None
        except (OSError, http.client.HTTPException):
            raise SmokeResult('UNKNOWN', 'login_unavailable') from None
        if status != 200 or len(raw) > 65536:
            raise SmokeResult('FAIL', f'login_http_{status}')
        value = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate login field'))
        if (type(value) is not dict or value.get('version') != INVITE_VERSION
                or type(value.get('access_token')) is not str or type(value.get('expires_at')) is not str):
            raise SmokeResult('FAIL', 'login_response_invalid')
    except BaseException:
        os.close(descriptor)
        os.unlink(session_out)
        raise
    _finish(descriptor, json.dumps(dict(access_token=value['access_token'], expires_at=value['expires_at'])).encode())
    return value['expires_at']


def load_session(path):
    value = json.loads(_private_read(path), object_pairs_hook=reject_duplicates(ValueError, 'duplicate session field'))
    if type(value) is not dict or set(value) != {'access_token', 'expires_at'} or type(value['access_token']) is not str:
        raise ValueError('evaluation_session_invalid')
    expires = datetime.fromisoformat(value['expires_at'].replace('Z', '+00:00'))
    if expires <= datetime.now(timezone.utc):
        raise ValueError('evaluation_session_expired')
    return value['access_token']


class HongKongSender:
    """`eval.release_eval.run.Sender` over the public /v4 Lio dialogue routes."""
    name = 'hk-v4'

    def __init__(self, token, allowed_ids, *, transport=request, clock=time.monotonic, sleep=time.sleep,
                 poll_seconds=POLL_SECONDS, turn_seconds=TURN_SECONDS):
        self.token, self.allowed = token, frozenset(allowed_ids)
        self.transport, self.clock, self.sleep = transport, clock, sleep
        self.poll_seconds, self.turn_seconds = poll_seconds, turn_seconds

    def _call(self, route, document=None):
        if document is None:
            return self.transport(self.token, route)[0]
        return self.transport(self.token, route, document=document, timeout=30)[0]

    def _turn(self, text, locale, conversation):
        mid = str(uuid.uuid4())
        body = dict(version=MESSAGE_VERSION, message_id=mid, text=text, locale=locale)
        if conversation is None:
            body['new_conversation'] = True
        else:
            body['conversation_id'] = conversation
        started = self.clock()
        ack = self._call('/v4/lio/messages', body)
        conversation = ack.get('conversation_id')
        if type(conversation) is not str or not conversation:
            raise ValueError('message_ack')
        first = None
        misses = 0
        while self.clock() - started < self.turn_seconds:
            self.sleep(self.poll_seconds)
            try:
                value = self._call('/v4/lio/timeline?' + urlencode({'conversation_id': conversation}))
            except SmokeResult as error:
                # A read is safe to repeat: tolerate a few transient poll failures in a row.
                misses += 1
                if misses > POLL_RETRIES or not (error.reason in ('http_timeout', 'http_incomplete_body',
                                                                   'transport_unavailable') or error.reason.startswith('http_5')):
                    raise
                continue
            misses = 0
            if value.get('version') != TIMELINE_VERSION:
                raise ValueError('timeline_version')
            rows = [row for row in value.get('messages') or [] if row.get('message_id') == mid]
            row = rows[0] if rows else None
            answer = row.get('answer') if row else None
            if first is None and type(answer) is str and answer.strip():
                first = self.clock()
            if row is not None and row.get('status') in TERMINAL:
                return conversation, row, started, first, self.clock()
        return conversation, None, started, first, None

    def send(self, case, turn_texts):
        empty = dict(text=None, first_token_ms=None, total_ms=None)
        if case.get('id') not in self.allowed or not turn_texts:
            return dict(empty, error='unknown_case')
        conversation = None
        try:
            for text in turn_texts:
                conversation, row, started, first, ended = self._turn(text, case['locale'], conversation)
                if row is None:
                    return dict(empty, error='answer_timeout')
                if row.get('status') != 'completed':
                    return dict(empty, error='run_' + str(row.get('status')))
        except SmokeResult as error:
            return dict(empty, error=error.reason)
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            return dict(empty, error='response_' + type(error).__name__)
        except (OSError, http.client.HTTPException):
            return dict(empty, error='transport_unavailable')
        answer = row.get('answer')
        return dict(text=answer if type(answer) is str else None,
                    first_token_ms=None if first is None else round((first - started) * 1000),
                    total_ms=round((ended - started) * 1000), error=None)


def main(argv=None):
    from eval.release_eval.bank import load_bank
    from eval.release_eval import run as runner

    parser = argparse.ArgumentParser(prog='python -B -m deploy.hk.eval_sender')
    sub = parser.add_subparsers(dest='command', required=True)
    sign = sub.add_parser('login')
    sign.add_argument('--invite-file', required=True)
    sign.add_argument('--session-out', required=True)
    go = sub.add_parser('run')
    go.add_argument('--session-file', required=True)
    go.add_argument('--cases', required=True, help='comma-separated bank case ids')
    go.add_argument('--repeats', type=int, default=1)
    go.add_argument('--real', action='store_true')
    go.add_argument('--max-calls', type=int)
    go.add_argument('--max-cost-cny', type=float)
    go.add_argument('--cost-per-turn-cny', type=float)
    go.add_argument('--output', required=True)
    go.add_argument('--source-sha')
    args = parser.parse_args(argv)
    if args.command == 'login':
        print(json.dumps(dict(result='SESSION_WRITTEN', expires_at=login(args.invite_file, args.session_out))))
        return 0
    bank = {case['id']: case for case in load_bank()}
    ids = [item for item in args.cases.split(',') if item]
    unknown = sorted(set(ids) - set(bank))
    if not ids or unknown or len(set(ids)) != len(ids) or args.repeats < 1:
        raise SystemExit('拒绝：题号必须来自题库、不重复，且 repeats ≥ 1' + (f'（未知：{unknown}）' if unknown else ''))
    cases = [bank[item] for item in ids]
    planned = runner.plan(cases, args.repeats, args.cost_per_turn_cny)
    refusal = runner.REAL_REQUIRED if not args.real else runner.real_refusal(planned, args.max_calls, args.max_cost_cny)
    if refusal:
        raise SystemExit(refusal)
    token = load_session(args.session_file)
    output = _reserve(args.output)  # fails before any call if the output exists or cannot be created
    try:
        value = runner.execute(cases, HongKongSender(token, bank), args.repeats,
                               meta=dict(source_sha=args.source_sha, plan=planned), max_calls=args.max_calls)
    except BaseException:
        os.close(output)
        os.unlink(args.output)
        raise
    _finish(output, json.dumps(value, ensure_ascii=False, indent=2).encode())
    errors = sum(1 for items in value['answers'].values() for item in items if item['error'])
    print(json.dumps(dict(result='RUN_WRITTEN', cases=len(cases), sends=len(cases) * args.repeats, errors=errors)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
