"""New frozen wire carries exact originals; data never supplies source authority."""
import base64
import copy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from cj_needs import contract_v1 as codec
from cj_needs.domain import Command, InvalidInput, Revision, Snapshot

EXAMPLES = json.loads((Path(__file__).resolve().parents[3] / 'contracts/needs/v1-examples.json').read_text())


def wire(value): return json.dumps(value, ensure_ascii=False).encode('utf8')


def test_published_versions_and_lossless_originals():
    assert codec.VERSION == 'NEEDS@1.0'
    for kind in ('command', 'snapshot', 'revision'):
        value = EXAMPLES['valid'][kind]
        decoded = getattr(codec, 'decode_' + kind)(wire(value))
        assert json.loads(getattr(codec, 'encode_' + kind)(decoded)) == value
    snapshot = codec.decode_snapshot(wire(EXAMPLES['valid']['snapshot']))
    fields = snapshot.fields
    assert fields['budget_total'] == {'state': 'unknown'}
    assert fields['budget_paid'] == {'state': 'missing'}
    assert fields['budget_per_person']['value'] == '1000.50'
    assert fields['budget_basis']['value'] == 'per_person'
    assert fields['arrival']['date']['value'] == '2026-11-02'
    assert fields['arrival']['time']['value'] == '09:30'
    assert fields['arrival']['timezone']['value'] == 'Asia/Shanghai'
    assert fields['temporary_conditions'][0]['applies_to'] == ['companion:mother']
    assert fields['fixed_items'][0]['locked'] == {'state': 'known', 'value': True}
    assert snapshot.source_kind == 'user_provided'


@pytest.mark.parametrize('case', EXAMPLES['invalid'], ids=lambda case: case['name'])
def test_published_negative_vectors(case):
    with pytest.raises(InvalidInput):
        getattr(codec, 'decode_' + case['kind'])(wire(case['value']))


@pytest.mark.parametrize('raw', [b'{}', b'[]', b'\xff', b'{"version":NaN}',
    b'{"version":"NEEDS-snapshot.1","version":"NEEDS-snapshot.1"}',
    b'x' * (codec.MAX_BYTES + 1)])
def test_strict_bounded_envelope(raw):
    with pytest.raises(InvalidInput): codec.decode_snapshot(raw)


@pytest.mark.parametrize('content', [b'{"owner":"foreign"}', b'{"party_size":{"state":"known","value":true}}',
    b'{"budget_total":{"state":"known","value":0}}', b'{"party_size":{"state":"unknown","value":3}}',
    b'{"pace":{"state":"known","value":"\\ud800"}}', b'{"pace":{"state":"unknown"},"pace":{"state":"missing"}}',
    b'{"temporary_conditions":[{"condition_id":"x","applies_to":["companion:absent"],"description":"x"}]}'])
def test_valid_hash_cannot_legitimize_invalid_persisted_content(content):
    value = dict(EXAMPLES['valid']['snapshot'], content_utf8_base64=base64.b64encode(content).decode(),
                 content_sha256=sha256(content).hexdigest())
    with pytest.raises(InvalidInput): codec.decode_snapshot(wire(value))
    with pytest.raises(InvalidInput): codec.encode_snapshot(Snapshot('x', 1, content))


def test_history_preserves_original_bytes_after_partial_correction():
    first = codec.decode_snapshot(wire(EXAMPLES['valid']['snapshot']))
    original = b' {"action_id":"correction","needs_id":"synthetic-visit","expected_version":1, "source":{"kind":"manual","text":"explicit correction"},"changes":{"pace":{"state":"known","value":"relaxed"}}}\n'
    command = codec.decode_command(codec.encode_command(Command(original)))
    assert command.raw == original
    fields = first.fields
    fields.update(command.data['changes'])
    content = wire(fields)
    revision = Revision(first.needs_id, 2, 'correction', original, content)
    assert codec.decode_revision(codec.encode_revision(revision)) == revision
    assert fields['budget_paid'] == {'state': 'missing'}
    assert fields['fixed_items'] == first.fields['fixed_items']


def test_wrong_patch_and_invented_initial_fields_are_rejected():
    first = codec.decode_revision(wire(EXAMPLES['valid']['revision']))
    fields = json.loads(first.content)
    fields['party_size']['value'] = 4
    with pytest.raises(InvalidInput):
        codec.encode_revision(Revision(first.needs_id, 1, first.action_id, first.original_input, wire(fields)))
    fields = json.loads(first.content)
    fields['departure'] = copy.deepcopy(fields['arrival'])
    with pytest.raises(InvalidInput):
        codec.encode_revision(Revision(first.needs_id, 1, first.action_id, first.original_input, wire(fields)))


@pytest.mark.parametrize('encoded', ['not base64', 'Zh==', '中文', ''])
def test_noncanonical_or_empty_original(encoded):
    value = dict(EXAMPLES['valid']['command'], original_input_utf8_base64=encoded)
    with pytest.raises(InvalidInput): codec.decode_command(wire(value))
