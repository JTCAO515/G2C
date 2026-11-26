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


def _cli(tmp_path, monkeypatch, sent):
    session = tmp_path / 'session.json'
    session.write_text(json.dumps(dict(access_token='t', expires_at='2999-01-01T00:00:00Z')));session.chmod(0o600)
    known = load_bank()[0]['id']
    monkeypatch.setattr(eval_sender.HongKongSender, 'send',
                        lambda self, case, turns: sent.append(case['id']) or dict(text='答', first_token_ms=1, total_ms=2, error=None))
    return ['run', '--session-file', str(session), '--cases', known, '--real', '--max-calls', '1',
            '--max-cost-cny', '1', '--cost-per-turn-cny', '0.01'], known


def test_existing_or_unwritable_output_stops_before_any_call(tmp_path, monkeypatch):
    sent = [];args, _ = _cli(tmp_path, monkeypatch, sent)
    existing = tmp_path / 'out.json';existing.write_text('keep')
    with pytest.raises(FileExistsError):eval_sender.main(args + ['--output', str(existing)])
    with pytest.raises(FileNotFoundError):eval_sender.main(args + ['--output', str(tmp_path / 'missing' / 'out.json')])
    assert sent == [] and existing.read_text() == 'keep'


def test_cli_happy_path_writes_a_private_validated_run(tmp_path, monkeypatch, capsys):
    sent = [];args, known = _cli(tmp_path, monkeypatch, sent)
    out = tmp_path / 'out.json'
    assert eval_sender.main(args + ['--output', str(out), '--source-sha', 'a' * 40]) == 0
    value = json.loads(out.read_text())
    assert sent == [known] and value['answers'][known][0]['text'] == '答' and value['run']['source_sha'] == 'a' * 40
    assert oct(out.stat().st_mode & 0o777) == '0o600'
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1]) == dict(result='RUN_WRITTEN', cases=1, sends=1, errors=0)


class FlakyServer(Server):
    def __init__(self, clock, failures, reason='http_503', **kw):
        super().__init__(clock, **kw);self.failures, self.reason = failures, reason

    def __call__(self, token, route, document=None, timeout=None):
        if route.startswith('/v4/lio/timeline') and self.failures:
            self.failures -= 1
            raise SmokeResult('FAIL', self.reason)
        return super().__call__(token, route, document, timeout)


def test_transient_timeline_failures_are_retried_but_not_forever():
    clock = Clock()
    ok = sender(FlakyServer(clock, eval_sender.POLL_RETRIES), clock).send(CASE, ['一句'])
    assert ok['error'] is None and ok['text'] == '答案'
    clock = Clock()
    bad = sender(FlakyServer(clock, eval_sender.POLL_RETRIES + 1), clock).send(CASE, ['一句'])
    assert bad == dict(text=None, first_token_ms=None, total_ms=None, error='http_503')
    clock = Clock()
    denied = sender(FlakyServer(clock, 1, reason='http_401'), clock).send(CASE, ['一句'])
    assert denied['error'] == 'http_401'


def test_message_ack_without_conversation_is_an_error():
    clock = Clock()
    class NoConversation(Server):
        def __call__(self, token, route, document=None, timeout=None):
            if route == '/v4/lio/messages':return dict(), None
            return super().__call__(token, route, document, timeout)
    assert sender(NoConversation(clock), clock).send(CASE, ['一句'])['error'] == 'response_ValueError'


def test_login_reports_http_status_and_never_spends_an_exchange_on_an_existing_file(tmp_path):
    from urllib.error import HTTPError
    invite = tmp_path / 'code';invite.write_text('D1-' + 'a' * 12 + '.' + 'B' * 22);invite.chmod(0o600)
    calls = []
    class Denied:
        def open(self, request, timeout):
            calls.append(1);raise HTTPError(request.full_url, 401, 'denied', {}, None)
    out = tmp_path / 'session.json'
    with pytest.raises(SmokeResult) as raised:eval_sender.login(invite, out, opener=Denied())
    assert raised.value.reason == 'login_http_401' and not out.exists() and calls == [1]
    out.write_text('existing');out.chmod(0o600)
    with pytest.raises(FileExistsError):eval_sender.login(invite, out, opener=Denied())
    assert calls == [1] and out.read_text() == 'existing'
