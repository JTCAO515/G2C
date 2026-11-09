"""Frozen Demo transport fixtures. No public request or model dispatch."""
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from demo_v2_evidence import DialogueObservation, original_receipt


ORIGINAL = dict(message_id='original-m', conversation_id='original-c', run_id='original-r')


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def event(event_id, kind, payload, **changes):
    data = dict(ORIGINAL, version='DEMO-dialogue-event.1', event_id=event_id, kind=kind, payload=payload)
    return encode(dict(data, **changes))


def test_receipt_requires_original_message_conversation_and_exact_bytes():
    request = encode(dict(version='DEMO-dialogue-message.1', message_id=ORIGINAL['message_id'],
                          conversation_id=ORIGINAL['conversation_id'], locale='zh', text='你好'))
    receipt = dict(ORIGINAL, input_sha256=sha256(request).hexdigest())
    envelope = dict(version='DEMO-dialogue-receipt.1', request_id='original-request', receipt=receipt)
    assert original_receipt(request, encode(envelope)) == receipt
    assert original_receipt(request, encode(dict(envelope, receipt=None))) is None
    with pytest.raises(ValueError, match='differs'):
        original_receipt(request+b' ', encode(envelope))
    with pytest.raises(ValueError, match='differs'):
        original_receipt(request, encode(dict(envelope, receipt=dict(receipt, conversation_id='foreign'))))


def test_resume_preserves_first_times_and_reconciles_complete_original():
    observed = DialogueObservation(ORIGINAL)
    progress = event('1', 'status', dict(stage='running', status='running'))
    observed.record('1', progress, .2)
    observed.record('2', event('2', 'source', dict(source_id='s1', label='来源', state='unknown')), .3)
    first = event('3', 'answer_delta', dict(text='你好'))
    observed.record('3', first, .8)
    assert observed.last_event_id == '3'
    assert not observed.record('1', progress, 1.0)
    assert not observed.record('3', first, 1.1)
    assert observed.last_event_id == '3'
    observed.record('4', event('4', 'answer_delta', dict(text='北京')), 1.2)
    observed.record('5', event('5', 'status', dict(stage='completed', status='completed')), 1.5)
    observed.record('6', event('6', 'trip_candidate', dict(card_id='card', version=1, status='pending')), 1.7)
    assert observed.summary()['complete_seconds'] is None
    display = dict(ORIGINAL, text='你好北京', status='completed')
    assert observed.summary(verified_display=dict(display, text='different'))['answer_matches_original'] is False
    with pytest.raises(ValueError, match='another original'):
        observed.summary(verified_display=dict(display, run_id='other'))
    summary = observed.summary(verified_display=display)
    assert summary['first_server_progress_seconds'] == .2
    assert summary['first_app_visible_progress_seconds'] is None
    assert summary['first_body_seconds'] == .8
    assert summary['complete_seconds'] == 1.5
    assert summary['body_sha256'] == sha256('你好北京'.encode()).hexdigest()
    assert len(observed.events) == 6
    assert observed.events[2]['original_utf8'].encode() == first


def test_foreign_event_changed_replay_and_wrong_frame_id_do_not_advance_cursor():
    observed = DialogueObservation(ORIGINAL)
    observed.record('2', event('2', 'status', dict(stage='running', status='running')), .2)
    for frame_id, payload in (
        ('3', event('3', 'answer_delta', dict(text='foreign'), run_id='other')),
        ('3', event('4', 'answer_delta', dict(text='wrong frame'))),
        ('2', event('2', 'status', dict(stage='queued', status='queued'))),
        ('1', event('1', 'status', dict(stage='queued', status='queued'))),
    ):
        with pytest.raises(ValueError):
            observed.record(frame_id, payload, .3)
    assert observed.last_event_id == '2'
    assert len(observed.events) == 1


@pytest.mark.parametrize('terminal', ['completed', 'unknown', 'failed'])
def test_source_or_card_is_not_answer_or_complete_latency(terminal):
    observed = DialogueObservation(ORIGINAL)
    observed.record('1', event('1', 'status', dict(stage='queued', status='queued')), .2)
    observed.record('2', event('2', 'needs_card', dict(card_id='original-card', version=1)), .3)
    observed.record('3', event('3', 'source', dict(source_id='s1', label='来源', state='unknown')), .4)
    observed.record('4', event('4', 'status', dict(stage=terminal, status=terminal)), .6)
    summary = observed.summary(verified_display=dict(ORIGINAL, text='', status=terminal))
    assert summary['terminal']['stage'] == terminal
    assert summary['first_body_seconds'] is None
    assert summary['complete_seconds'] is None
    assert summary['body_bytes'] == 0


def test_sse_uses_last_complete_frame_and_excludes_original_source_prefix():
    observed = DialogueObservation(ORIGINAL)

    def frame(index, kind, payload):
        return [b'event: '+kind.encode(), b'id: '+index.encode(), b'data: '+event(index, kind, payload), b'']

    queued = frame('1', 'status', dict(status='queued', stage='queued'))
    started = frame('3', 'status', dict(status='running', stage='running'))
    prefix = frame('4', 'answer_delta', dict(text='来源：https://example.test/\n'))
    partial = frame('7', 'answer_delta', dict(text='原正文'))
    unfinished = observed.read_segment([b': ready']+queued+started+prefix+partial[:2], iter((.1,.5,.7)).__next__)
    assert unfinished[b'id'] == b'7' and observed.last_event_id == '4'
    assert observed.summary()['first_body_seconds'] is None
    end = frame('9', 'status', dict(status='completed', stage='completed'))
    assert observed.read_segment(prefix+partial+end, iter((.9,1.1,1.2)).__next__) == {}
    summary = observed.summary(verified_display=dict(ORIGINAL, text='来源：https://example.test/\n原正文', status='completed'))
    assert summary['first_server_progress_seconds'] == .1
    assert summary['first_running_or_tool_seconds'] == .5
    assert summary['first_body_seconds'] == 1.1
    assert summary['complete_seconds'] == 1.2
