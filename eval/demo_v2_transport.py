"""Single-write transport and read-only continuation for the Demo v2 smoke."""
from dataclasses import dataclass
import json
import os
import re
import time

import httpx

from demo_v2_evidence import (
    DialogueObservation, MAX_CAPTURE_BYTES, MAX_EVENT_BYTES, MESSAGE_VERSIONS, _object,
    original_action_receipt, original_receipt,
)


BASE = 'https://api-beta.go2china.space'
ROUTES = {
    **{version: ('/v1/demo-dialogue/messages', 'message_id', original_receipt, 16_384)
       for version in MESSAGE_VERSIONS},
    'DEMO-dialogue-action.1': ('/v1/demo-dialogue/actions', 'action_id', original_action_receipt, 32_768),
}


@dataclass(frozen=True)
class Submission:
    started: float
    receipt: dict | None
    state: str


def _write(path, raw):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _journal(path, value):
    _write(path, (json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8'))


def _small_read(client, method, path, directory, label, *, max_bytes=65_536, **kwargs):
    data = bytearray()
    try:
        with client.stream(method, BASE + path, follow_redirects=False, **kwargs) as response:
            status = response.status_code
            for chunk in response.iter_bytes():
                if len(data) + len(chunk) > max_bytes:
                    raise ValueError('bounded dialogue HTTP response required')
                data.extend(chunk)
            media = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
            if status == 200 and media != 'application/json':
                raise ValueError('dialogue response must be JSON')
    except (httpx.HTTPError, ValueError) as error:
        if data:
            _write(directory / (label + '.partial'), bytes(data))
        _journal(directory / (label + '.status'), {'error': type(error).__name__})
        return None, bytes(data)
    raw = bytes(data)
    _write(directory / (label + '.response'), raw)
    _journal(directory / (label + '.status'), {'http_status': status})
    return status, raw


def _command(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 32_768:
        raise ValueError('bounded original dialogue input required')
    value = _object(raw)
    version = value.get('version')
    if not isinstance(version, str) or version not in ROUTES:
        raise ValueError('supported original dialogue version required')
    path, key, verify, limit = ROUTES[version]
    identity = value.get(key)
    if len(raw) > limit or not isinstance(identity, str) or re.fullmatch(r'[A-Za-z0-9_-]{1,128}', identity) is None:
        raise ValueError('bounded original dialogue identity required')
    return path, {key: identity}, verify


def _definite_rejection(raw):
    try:
        failure = _object(raw).get('error')
    except ValueError:
        return False
    return (isinstance(failure, dict) and failure.get('outcome') == 'failed' and
            failure.get('recovery') == 'do_not_retry')


def reconcile_original(client, directory, *, label='original-get'):
    """Only inspect the already journaled original; no permission to re-POST."""
    raw = (directory / 'intent.utf8').read_bytes()
    path, query, verify = _command(raw)
    status, response = _small_read(client, 'GET', path, directory, label, params=query)
    if status != 200:
        return None
    return verify(raw, response)


def submit_once(client, raw, directory, *, clock=time.perf_counter):
    """Record the exact write first. An ambiguous response only permits GET."""
    path, identity, verify = _command(raw)
    if directory.name != next(iter(identity.values())):
        raise ValueError('attempt directory must be named for the original ID')
    directory.mkdir(mode=0o700)
    _write(directory / 'intent.utf8', raw)
    started = clock()
    status, response = _small_read(client, 'POST', path, directory, 'submit', content=raw,
                                   headers={'Content-Type': 'application/octet-stream'})
    if status == 200:
        receipt = verify(raw, response)
        if receipt is not None:
            return Submission(started, receipt, 'ACCEPTED')
    elif status is not None and _definite_rejection(response):
        return Submission(started, None, 'REJECTED')
    receipt = reconcile_original(client, directory)
    return Submission(started, receipt, 'RECOVERED' if receipt is not None else 'UNKNOWN')


class _ObservationEnded(Exception):
    pass


def _lines(response, output, expired):
    pending = b''
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > MAX_CAPTURE_BYTES:
            raise ValueError('bounded dialogue SSE segment required')
        output.write(chunk)
        if expired():
            raise _ObservationEnded
        pending += chunk
        while b'\n' in pending:
            line, _, pending = pending.partition(b'\n')
            yield line
        if len(pending) > MAX_EVENT_BYTES + 8:
            raise ValueError('bounded dialogue SSE line required')
    # EOF can split the final line anywhere, including in the middle of UTF-8.
    # Those bytes are in the raw segment and do not advance the SSE cursor.


def observe(client, submission, directory, *, clock=time.perf_counter, delay=time.sleep,
            max_reads=4, max_seconds=140, required_kinds=frozenset()):
    """Read the original status/body only. An API clock cannot certify App render."""
    receipt = submission.receipt
    if receipt is None:
        raise ValueError('original receipt required before observation')
    directory.mkdir(mode=0o700)
    observed = DialogueObservation(receipt)
    elapsed = lambda: clock() - submission.started
    descriptor = os.open(directory / 'events.jsonl', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb', buffering=0) as events:
        def append(row):
            events.write((json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8'))

        for index in range(1, max_reads + 1):
            remaining = max_seconds - elapsed()
            if remaining <= 0:
                break
            headers = {'Accept': 'text/event-stream'}
            if observed.last_event_id is not None:
                headers['Last-Event-ID'] = observed.last_event_id
            record = {'after': observed.last_event_id, 'http_status': None}
            descriptor = os.open(directory / f'stream-{index}.raw', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'wb', buffering=0) as raw:
                try:
                    with client.stream('GET', BASE + '/v1/demo-dialogue/events', headers=headers,
                        params={'message_id': receipt['message_id']}, follow_redirects=False,
                        timeout=remaining) as response:
                        record['http_status'] = response.status_code
                        if response.status_code == 200:
                            media = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
                            if media != 'text/event-stream':
                                raise ValueError('dialogue SSE response required')
                            observed.read_segment(_lines(response, raw, lambda: elapsed() >= max_seconds),
                                                  elapsed, append=append)
                        else:
                            for _ in _lines(response, raw, lambda: elapsed() >= max_seconds):
                                pass
                except (httpx.HTTPError, _ObservationEnded) as error:
                    record['error'] = type(error).__name__
                except ValueError:
                    record['error'] = 'dialogue_protocol_mismatch'
                    raise
                finally:
                    _journal(directory / f'stream-{index}.status', record)
            kinds = {row['event']['kind'] for row in observed.events}
            if (observed.terminal is not None and required_kinds <= kinds or
                    record['http_status'] not in (None, 200, 503)):
                break
            delay(min(.25, max(0, max_seconds - elapsed())))
    return observed


def terminal_summary(client, observed, directory):
    """Read the original protected display without inferring a missing SSE clock."""
    status, raw = _small_read(client, 'GET', '/v6/run-display', directory, 'terminal-get',
                              max_bytes=MAX_EVENT_BYTES, params={'message_id': observed.original['message_id']})
    display = None
    if status == 200:
        envelope = _object(raw)
        if envelope.get('version') != 'RUN-display.6' or not isinstance(envelope.get('snapshot'), dict):
            raise ValueError('protected original RUN display required')
        display = envelope['snapshot']
    summary = observed.summary(verified_display=display)
    _journal(directory / 'summary.json', summary)
    return summary
