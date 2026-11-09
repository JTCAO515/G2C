import json
from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lio_smoke import capture


CHAT = 'lio-dialogue-' + 'a' * 32
ORIGINAL = {'version': 'LIO-message.1', 'message_id': 'lio-smoke-001',
            'text': 'What is the weather in Beijing?', 'locale': 'en'}
RAW = json.dumps(ORIGINAL).encode()


def page(status, answer='', *, text=ORIGINAL['text']):
    row = dict(message_id=ORIGINAL['message_id'], text=text, answer=answer, status=status,
               failure=None, sources=[], trip=None, memory=None)
    return dict(version='LIO-timeline.1', conversation_id=CHAT, messages=[row], next_before=None)


def test_records_first_worker_progress_first_body_and_completion(tmp_path):
    reads = iter((page('sending'), page('answering'), page('answering', 'Weather'),
                  page('completed', 'Weather forecast')))
    calls = []
    def handle(request):
        calls.append(request.method)
        if request.method == 'POST':
            assert request.content == RAW
            assert request.url.path == '/v1/lio/messages'
            return httpx.Response(200, json=dict(version='LIO-message-receipt.1',
                message_id=ORIGINAL['message_id'], conversation_id=CHAT))
        assert request.url.path == '/v1/lio/timeline'
        assert request.url.params['conversation_id'] == CHAT
        return httpx.Response(200, json=next(reads))

    directory = tmp_path / ORIGINAL['message_id']
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = capture(client, RAW, directory, clock=lambda:len(calls), delay=lambda _:None)
    assert calls == ['POST', 'GET', 'GET', 'GET', 'GET']
    assert result['submission'] == 'ACK'
    assert result['first_server_progress_seconds'] == 3
    assert result['first_body_seconds'] == 4
    assert result['complete_seconds'] == 5
    assert (directory / 'intent.utf8').read_bytes() == RAW
    assert json.loads((directory / 'timeline-004.response').read_bytes()) == page('completed', 'Weather forecast')


def test_lost_ack_and_missed_progress_are_preserved(tmp_path):
    calls = []
    def handle(request):
        calls.append(request.method)
        if request.method == 'POST':
            raise httpx.ReadTimeout('synthetic ACK loss')
        return httpx.Response(200, json=page('completed', 'Weather forecast'))
    directory = tmp_path / ORIGINAL['message_id']
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = capture(client, RAW, directory, clock=lambda:len(calls), delay=lambda _:None)
        with pytest.raises(FileExistsError):
            capture(client, RAW, directory)
    assert calls == ['POST', 'GET']
    assert result['submission'] == 'UNKNOWN'
    assert result['first_server_progress_seconds'] is None
    assert result['first_body_seconds'] == result['complete_seconds'] == 2


def test_different_text_for_same_id_withholds_evidence(tmp_path):
    calls = []
    def handle(request):
        calls.append(request.method)
        if request.method == 'POST':
            return httpx.Response(503, json={'failure': 'unavailable'})
        return httpx.Response(200, json=page('completed', 'Weather forecast', text='Different text'))
    directory = tmp_path / ORIGINAL['message_id']
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(ValueError, match='original message'):
            capture(client, RAW, directory, delay=lambda _:None)
    assert calls == ['POST', 'GET']
    assert (directory / 'timeline-001.response').exists()
