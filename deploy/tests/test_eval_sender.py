"""Operator-run HK evaluation sender over /v4 (#1868): offline, fake transport only."""
import json
import os

import pytest

from deploy.hk import eval_sender
from deploy.hk.server_smoke import SmokeResult
from eval.release_eval.bank import load_bank
from eval.release_eval import run as runner

CASE = dict(id='case-a', locale='zh', turns=['第一句', '第二句'])


class Clock:
    def __init__(self):self.now=100.0
    def __call__(self):return self.now
    def sleep(self,seconds):self.now+=seconds


class Server:
    """Replays the /v4 contract: an ack, then timeline polls that show text, then completion."""
    def __init__(self, clock, *, polls_to_text=2, polls_to_done=4, status='completed', fail=None):
        self.clock, self.polls_to_text, self.polls_to_done = clock, polls_to_text, polls_to_done
        self.status, self.fail = status, fail
        self.sent, self.polls, self.tokens = [], 0, set()

    def __call__(self, token, route, document=None, timeout=None):
        self.tokens.add(token)
        if self.fail:raise SmokeResult('FAIL', self.fail)
        if route == '/v4/lio/messages':
            self.sent.append(document);self.polls=0
            return dict(conversation_id='conv-1'), None
        assert route.startswith('/v4/lio/timeline?conversation_id=conv-1')
        self.polls += 1
        mid = self.sent[-1]['message_id']
        text = '答案' if self.polls >= self.polls_to_text else ''
        status = self.status if self.polls >= self.polls_to_done else 'running'
        return dict(version='LIO-timeline.4', messages=[dict(message_id=mid, status=status, answer=text)]), None


def sender(server, clock, **kw):
    return eval_sender.HongKongSender('secret-test-token-xyz', {'case-a'}, transport=server, clock=clock, sleep=clock.sleep, **kw)


def test_multi_turn_case_plays_every_turn_in_one_conversation_and_times_the_last():
    clock = Clock();server = Server(clock)
    result = sender(server, clock).send(CASE, list(CASE['turns']))
    assert result == dict(text='答案', first_token_ms=1000, total_ms=2000, error=None)
    first, second = server.sent
    assert first['new_conversation'] is True and 'conversation_id' not in first
    assert second['conversation_id'] == 'conv-1' and 'new_conversation' not in second
    assert {d['version'] for d in server.sent} == {'LIO-message.4'} and {d['locale'] for d in server.sent} == {'zh'}
    assert [d['text'] for d in server.sent] == CASE['turns'] and first['message_id'] != second['message_id']


@pytest.mark.parametrize('kwargs,error', [
    (dict(status='failed'), 'run_failed'), (dict(polls_to_done=10**6), 'answer_timeout'),
    (dict(fail='http_401'), 'http_401'),
])
def test_failures_are_short_codes_without_text(kwargs, error):
    clock = Clock()
    result = sender(Server(clock, **kwargs), clock, turn_seconds=10).send(CASE, list(CASE['turns']))
    assert result == dict(text=None, first_token_ms=None, total_ms=None, error=error)


def test_unknown_case_is_refused_before_any_call():
    clock = Clock();server = Server(clock)
    assert sender(server, clock).send(dict(CASE, id='not-in-bank'), ['x'])['error'] == 'unknown_case'
    assert server.sent == []


def test_runner_integration_counts_sends_and_validates_the_run():
    clock = Clock();server = Server(clock)
    value = runner.execute([CASE], sender(server, clock), repeats=2, max_calls=2)
    assert len(value['answers']['case-a']) == 2 and len(server.sent) == 4
    assert server.tokens == {'secret-test-token-xyz'} and 'secret-test-token-xyz' not in json.dumps(value)


def test_cli_refuses_real_calls_without_every_limit_and_unknown_ids(tmp_path, monkeypatch):
    session = tmp_path / 'session.json';session.write_text(json.dumps(dict(access_token='t', expires_at='2999-01-01T00:00:00Z')))
    session.chmod(0o600)
    known = load_bank()[0]['id']
    base = ['run', '--session-file', str(session), '--output', str(tmp_path / 'out.json')]
    calls = []
    monkeypatch.setattr(eval_sender.HongKongSender, 'send', lambda self, case, turns: calls.append(case) or {})
    with pytest.raises(SystemExit, match='--real'):eval_sender.main(base + ['--cases', known])
    with pytest.raises(SystemExit, match='--real'):eval_sender.main(base + ['--cases', known, '--real', '--max-calls', '1'])
    with pytest.raises(SystemExit, match='未知'):eval_sender.main(base + ['--cases', 'nope', '--real', '--max-calls', '1',
                                                               '--max-cost-cny', '1', '--cost-per-turn-cny', '0.01'])
    with pytest.raises(SystemExit, match='超过 --max-calls'):
        eval_sender.main(base + ['--cases', known, '--repeats', '2', '--real', '--max-calls', '1', '--max-cost-cny', '1',
                                 '--cost-per-turn-cny', '0.01'])
    assert calls == [] and not (tmp_path / 'out.json').exists()


def test_session_and_invite_files_must_be_private(tmp_path):
    path = tmp_path / 'session.json';path.write_text(json.dumps(dict(access_token='t', expires_at='2999-01-01T00:00:00Z')))
    path.chmod(0o644)
    with pytest.raises(ValueError, match='owned_0600'):eval_sender.load_session(path)
    path.chmod(0o600);assert eval_sender.load_session(path) == 't'
    path.write_text(json.dumps(dict(access_token='t', expires_at='2000-01-01T00:00:00Z')))
    with pytest.raises(ValueError, match='expired'):eval_sender.load_session(path)


def test_login_writes_a_private_session_and_never_echoes_the_code(tmp_path, capsys):
    invite = tmp_path / 'code';invite.write_text('D1-' + 'a' * 12 + '.' + 'B' * 22 + '\n');invite.chmod(0o600)
    seen = []
    class Response:
        status = 200
        def __enter__(self):return self
        def __exit__(self, *a):return False
        def read(self, n):return json.dumps(dict(version='DEMO-invite-session.2', access_token='tok', subject='s',
                                                expires_at='2999-01-01T00:00:00Z')).encode()
    class Opener:
        def open(self, request, timeout):seen.append(json.loads(request.data));return Response()
    out = tmp_path / 'session.json'
    assert eval_sender.login(invite, out, opener=Opener()) == '2999-01-01T00:00:00Z'
    assert seen == [dict(version='DEMO-invite-session.2', invite_code='D1-' + 'a' * 12 + '.' + 'B' * 22, consent=True)]
    assert oct(out.stat().st_mode & 0o777) == '0o600' and json.loads(out.read_text())['access_token'] == 'tok'
    assert 'D1-' not in capsys.readouterr().out
