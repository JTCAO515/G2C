"""Frozen r1 input boundaries; all identities/data are synthetic."""
import json
import pytest
from cj_message.domain import Command, InvalidInput
from cj_message.travel import Action, Selection


def command(**change):
    value = dict(version='MESSAGE-send.2', conversation_id='c', message_id='m', text='合成 Beijing',
                 trip_id=None, creation_intent='none', expected_generation='g', expected_sequence=0,
                 travel_context=None, needs_reference=None)
    value.update(change)
    return value


def test_v2_requires_explicit_choice_and_preserves_original_bytes():
    value = command(travel_context={'id': 'a'*32, 'expected_version': 1})
    raw = json.dumps(value, indent=2).encode()
    parsed = Command.parse_v2(raw)
    assert parsed.raw is raw and parsed.travel_context == Selection('a'*32, 1)
    with pytest.raises(InvalidInput):
        Command.parse(raw)  # old public send.1 stays closed to the new version
    with pytest.raises(InvalidInput):
        Command.parse_stored(raw)  # old wire does not silently strip the reference
    for field in ('travel_context', 'needs_reference'):
        missing = dict(value); del missing[field]
        with pytest.raises(InvalidInput):
            Command.parse_v2(json.dumps(missing).encode())


@pytest.mark.parametrize('value', [True, 1.0, 0, -1, 2**63, '1', None])
def test_travel_version_is_real_positive_int64(value):
    with pytest.raises(InvalidInput):
        Selection.parse({'id': 'a'*32, 'expected_version': value})


def test_needs_choice_is_explicit_without_long_term_promotion():
    parsed = Command.parse_v2(json.dumps(command(creation_intent='consider_trip',
        needs_reference={'id': 'needs-1', 'expected_version': 2})).encode())
    assert parsed.travel_context is None and parsed.needs_reference == ('needs-1', 2)
    for value in (command(creation_intent='consider_trip'),
                  command(needs_reference={'id': 'n', 'expected_version': 1}),
                  command(creation_intent='consider_trip', needs_reference={'id': 'n', 'expected_version': True}),
                  command(creation_intent='consider_trip', needs_reference={'id': 'wrong owner', 'expected_version': 1})):
        with pytest.raises(InvalidInput):
            Command.parse_v2(json.dumps(value).encode())


def test_action_rejects_duplicate_fields_owner_and_unknown_transitions():
    value = dict(version='TRAVEL-context-action.1', action_id='synthetic', operation='create', travel_context=None)
    assert Action.parse(json.dumps(value).encode()).travel_context is None
    for change in (dict(owner='another'), dict(operation='reactivate'),
                   dict(action_id=' '), dict(action_id='中文'), dict(travel_context={'id':'a'*32,'expected_version':1})):
        with pytest.raises(InvalidInput):
            Action.parse(json.dumps({**value, **change}).encode())
    raw = json.dumps(value).encode().replace(b'"create"', b'"create", "operation":"create"')
    with pytest.raises(InvalidInput):
        Action.parse(raw)
