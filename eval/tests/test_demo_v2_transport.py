"""Offline HTTP fixtures for original dispatch, readback and SSE continuation."""
from hashlib import sha256
import itertools
import json
from pathlib import Path
import stat
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from demo_v2_evidence import original_action_receipt
from demo_v2_transport import Submission, observe, submit_once, terminal_summary


ORIGINAL = {'message_id': 'original-message', 'conversation_id': 'demo-dialogue-original',
            'run_id': 'original-run'}


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def message():
    return encode(dict(version='DEMO-dialogue-message.1', message_id=ORIGINAL['message_id'],
                       text='合成问题', locale='zh'))


def envelope(receipt, version='DEMO-dialogue-receipt.1'):
    return httpx.Response(200, json=dict(version=version, request_id='original-request', receipt=receipt))


def test_timeout_only_queries_same_message_and_preserves_exact_intent(tmp_path):
    raw = message()
    directory = tmp_path / ORIGINAL['message_id']
    receipt = dict(ORIGINAL, input_sha256=sha256(raw).hexdigest())
    calls = []

    def handle(request):
        calls.append(request.method)
        assert request.url.host == 'api-beta.go2china.space'
        assert request.url.path == '/v1/demo-dialogue/messages'
        assert (directory/'intent.utf8').read_bytes() == raw
        if request.method == 'POST':
            assert request.headers['Content-Type'] == 'application/octet-stream'
            assert request.content == raw
            raise httpx.ReadTimeout('no original receipt observed', request=request)
        assert request.url.params['message_id'] == ORIGINAL['message_id']
        return envelope(receipt)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        assert submit_once(client, raw, directory, clock=lambda: 12) == Submission(12, receipt, 'RECOVERED')
        with pytest.raises(FileExistsError):
            submit_once(client, raw, directory)
    assert calls == ['POST', 'GET']
    assert stat.S_IMODE((directory/'intent.utf8').stat().st_mode) == 0o600
    assert json.loads((directory/'submit.status').read_bytes()) == {'error': 'ReadTimeout'}


def test_action_receipt_binds_child_and_refuses_changed_original(tmp_path):
    action = dict(version='DEMO-dialogue-action.1', action_id='original-action',
                  conversation_id=ORIGINAL['conversation_id'], card_id='original-card',
                  expected_version=1, operation='confirm_needs')
    raw = encode(action)
    receipt = dict(ORIGINAL, action_id=action['action_id'], card_id=action['card_id'],
                   operation=action['operation'], version=2, input_sha256=sha256(raw).hexdigest())
    calls = []

    def handle(request):
        calls.append(request.method)
        assert request.url.path == '/v1/demo-dialogue/actions' and request.content == raw
        return envelope(receipt, 'DEMO-dialogue-action-receipt.1')

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        accepted = submit_once(client, raw, tmp_path/'original-action')
    assert accepted.receipt['message_id'] == ORIGINAL['message_id']
    assert accepted.receipt['run_id'] == ORIGINAL['run_id']
    foreign = envelope(dict(receipt, card_id='foreign-card'), 'DEMO-dialogue-action-receipt.1')
    with pytest.raises(ValueError, match='differs'):
        original_action_receipt(raw, foreign.content)
    assert calls == ['POST']


def test_null_original_stays_unknown(tmp_path):
    calls = []

    def handle(request):
        calls.append(request.method)
        return (httpx.Response(503, json={'error': {'outcome': 'unknown', 'recovery': 'reconcile_original'}})
                if request.method == 'POST' else envelope(None))

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = submit_once(client, message(), tmp_path/ORIGINAL['message_id'])
    assert result.state == 'UNKNOWN' and result.receipt is None
    assert calls == ['POST', 'GET']


def frame(number, kind, payload):
    event = dict(ORIGINAL, version='DEMO-dialogue-event.1', event_id=str(number), kind=kind, payload=payload)
    return f'event: {kind}\nid: {number}\ndata: '.encode() + encode(event) + b'\n\n'


class Chunks(httpx.SyncByteStream):
    def __init__(self, *chunks):
        self.chunks = chunks

    def __iter__(self):
        yield from self.chunks


def test_split_sse_continues_by_cursor_and_waits_for_required_card(tmp_path):
    prefix = '来源：https://example.test/\n'
    body = '这是真实原件夹具正文'
    source = frame(3, 'answer_delta', {'text': prefix})
    answer = frame(4, 'answer_delta', {'text': body})
    first = frame(1, 'status', {'status': 'queued', 'stage': 'queued'}) + source + answer[:20]
    finished = source + answer + frame(6, 'status', {'status': 'completed', 'stage': 'completed'})
    card = frame(7, 'needs_card', {'card_id': 'original-card', 'version': 1, 'status': 'pending'})
    replies = [first, finished, card]
    calls = []

    def handle(request):
        assert request.method == 'GET' and request.url.params['message_id'] == ORIGINAL['message_id']
        if request.url.path == '/v6/run-display':
            return httpx.Response(200, json=dict(version='RUN-display.6',
                snapshot=dict(ORIGINAL, status='completed', text=prefix+body)))
        assert request.url.path == '/v1/demo-dialogue/events'
        calls.append(request.headers.get('Last-Event-ID'))
        raw = replies[len(calls)-1]
        return httpx.Response(200, headers={'Content-Type': 'text/event-stream'}, stream=Chunks(raw[:23], raw[23:]))

    directory = tmp_path/'observation'
    clock = itertools.count(0, .05)
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        observed = observe(client, Submission(0, ORIGINAL, 'ACCEPTED'), directory,
                           clock=lambda: next(clock), delay=lambda _: None, required_kinds={'needs_card'})
        summary = terminal_summary(client, observed, directory)
    assert calls == [None, '3', '6']
    assert summary['last_event_id'] == '7'
    assert summary['first_body_seconds'] < summary['complete_seconds']
    assert summary['first_app_visible_progress_seconds'] is None
    assert summary['answer_matches_original'] is True
    assert (directory/'stream-1.raw').read_bytes() == first
    assert len((directory/'events.jsonl').read_bytes().splitlines()) == 5


def test_resync_required_does_not_restart_original(tmp_path):
    calls = []

    def handle(request):
        calls.append((request.method, request.headers.get('Last-Event-ID')))
        return httpx.Response(409, json={'error': {'code': 'RESYNC_REQUIRED'}})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        observed = observe(client, Submission(0, ORIGINAL, 'ACCEPTED'), tmp_path/'resync', clock=lambda: 1)
    assert calls == [('GET', None)]
    assert observed.summary()['complete_seconds'] is None
