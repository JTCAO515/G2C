"""W2-1 (#1727): timeline rows carry layout and followups only for a poll that declared them."""
import json
from types import SimpleNamespace

from cj_api.lio_dialogue_routes import _message
from cj_message.lio_context import LioFollowups, LioLayout
from cj_message.lio_followups import VERSION

BUTTON = dict(tool='payment-guide', parameters={}, label='打开支付开通指南')


def item():
    return SimpleNamespace(message_id='m1', text='怎么用支付宝', locale='zh')


def state(status, text, *effects):
    return SimpleNamespace(status=status, text=text, effects=tuple(effects), draft_outcome=None, budget_exhausted_stage='none')


def row(status, text, *effects, declared=True):
    return _message(item(), state(status, text, *effects), declared=declared)


SPLIT = LioLayout('split').effect()
BUTTONS = LioFollowups((BUTTON,)).effect()


def test_a_poll_that_did_not_declare_gets_the_old_row_byte_for_byte():
    plain = row('completed', '答案', declared=False)
    assert row('completed', '答案', SPLIT, BUTTONS, declared=False) == plain
    assert set(plain) == {'message_id', 'text', 'answer', 'status', 'failure', 'activity', 'sources', 'trip', 'memory'}


def test_layout_is_the_same_from_the_first_text_to_completed():
    streaming = row('running', '先说结论', SPLIT)
    done = row('completed', '先说结论\n\n再说步骤', SPLIT, BUTTONS)
    assert streaming['layout'] == done['layout'] == 'split'
    assert streaming['status'] == 'answering' and 'followups' not in streaming
    assert done['followups'] == dict(version=VERSION, actions=[BUTTON])


def test_a_row_before_the_layout_exists_has_none_but_one_with_text_always_does():
    assert 'layout' not in row('running', '')
    sending = _message(item(), None, declared=True)  # queued: no run state yet
    assert sending['status'] == 'sending' and 'layout' not in sending
    assert row('completed', '好的') ['layout'] == 'single'     # no layout effect: a single bubble
    assert row('running', '部分正文')['layout'] == 'single'
    assert row('failed', '')['layout'] == 'single'


def test_single_layout_and_unknown_values_never_carry_buttons():
    assert 'followups' not in row('completed', '好的', LioLayout('single').effect(), BUTTONS)
    bad = row('completed', '好的', 'lio_layout:wide', BUTTONS)
    assert bad['layout'] == 'single' and 'followups' not in bad


def test_damaged_or_unlisted_buttons_are_dropped_on_read():
    for stored in ('lio_followups:not json', 'lio_followups:{}', 'lio_followups:[]',
                   'lio_followups:' + json.dumps([dict(tool='shell', parameters={}, label='x')]),
                   'lio_followups:' + json.dumps([dict(tool='trip', parameters={}, label='查看行程')]),
                   'lio_followups:' + json.dumps([dict(tool='taxi', parameters={'url': 'http://x'}, label='打车')]),
                   'lio_followups:' + json.dumps([dict(tool='payment-guide', parameters={}, label='')])):
        assert 'followups' not in row('completed', '好的', SPLIT, stored), stored
    mixed = 'lio_followups:' + json.dumps([dict(tool='shell', parameters={}, label='x'), BUTTON])
    assert row('completed', '好的', SPLIT, mixed)['followups']['actions'] == [BUTTON]


def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from cj_api.lio_dialogue_routes import register_lio_dialogue_routes
    page = SimpleNamespace(messages=(), conversation_id='lio-c', next_before=None, requires_new_lio=False)
    context = SimpleNamespace(scope='scope', lio_timeline=lambda *args, **kwargs: page)
    boundary = SimpleNamespace(with_history_context=lambda token, project: project(context))
    app = FastAPI()
    register_lio_dialogue_routes(app, boundary, None, None, prepare_scope=None)
    return TestClient(app)


def test_only_the_v2_timeline_accepts_the_declaration_and_only_with_the_exact_value():
    http = client()
    headers = {'Authorization': 'Bearer t'}
    ok = http.get('/v2/lio/timeline?accepts=' + VERSION, headers=headers)
    assert ok.status_code == 200 and ok.json()['version'] == 'LIO-timeline.2'
    assert http.get('/v2/lio/timeline', headers=headers).json() == ok.json()   # an empty page is unchanged
    for query in ('accepts=', 'accepts=LIO-answer-followups.2', 'accepts=LIO-answer-followups.1,x',
                  'accepts=' + VERSION + '&accepts=' + VERSION, 'accept=' + VERSION):
        assert http.get('/v2/lio/timeline?' + query, headers=headers).status_code == 400, query
    # The v1 timeline never learned the declaration.
    assert http.get('/v1/lio/timeline?accepts=' + VERSION, headers=headers).status_code == 400
    assert http.get('/v1/lio/timeline', headers=headers).status_code == 200


def test_the_contract_examples_match_the_schema_and_the_servers_own_check():
    from pathlib import Path
    import jsonschema
    root = Path(__file__).resolve().parents[3] / 'contracts/message'
    schema = json.loads((root / 'lio-followups-schema.1.json').read_text())
    examples = json.loads((root / 'lio-followups-examples.1.json').read_text())
    from cj_message.lio_followups import wire_followups
    for value in examples['valid']:
        jsonschema.validate(value, schema)
        if 'followups' in value:
            assert wire_followups(value['followups']['actions']) == value['followups']   # the server would send exactly this
    for value in examples['invalid']:
        assert not jsonschema.Draft202012Validator(schema).is_valid(value), value
        if 'followups' in value and value['followups']['version'] == VERSION:
            assert wire_followups(value['followups']['actions']) is None   # and the server's read would drop it
