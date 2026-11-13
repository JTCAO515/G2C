"""Consumer controls for D/R's frozen contract; no live fixture or authority."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from runtime_adapter.contract import Invalid, encode
from runtime_adapter.fixture_records import (
    FixtureDefinition, FixtureUse, SCHEMA_SHA256, decode_record, link_records,
)
from runtime_adapter import Binding
from runtime_adapter.contract import digest
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / 'eval/optimization/fixtures'
EXAMPLES = json.loads((FROZEN / 'cross-binding-fixture.examples.v1.json').read_bytes())
SCHEMA_BYTES = (FROZEN / 'cross-binding-fixture.v1.schema.json').read_bytes()
ORACLE = Draft202012Validator(json.loads(SCHEMA_BYTES), format_checker=FormatChecker())


def accepted(record):
    assert ORACLE.is_valid(record)
    return decode_record(encode(record))


def rejected(record):
    assert not ORACLE.is_valid(record)
    with pytest.raises(Invalid):
        decode_record(encode(record))


def test_frozen_release_and_both_published_wire_controls():
    assert sha256(SCHEMA_BYTES).hexdigest() == SCHEMA_SHA256
    definition = accepted(EXAMPLES['definition'])
    use = accepted(EXAMPLES['use'])
    assert isinstance(definition, FixtureDefinition) and isinstance(use, FixtureUse)
    assert sha256(encode(EXAMPLES['definition'])).hexdigest() == EXAMPLES['definition_wire_sha256']
    assert sha256(encode(EXAMPLES['use'])).hexdigest() == EXAMPLES['use_wire_sha256']
    assert use.coverage.foreign_write_interface == 'UNRUN'
    assert use.coverage.semantic_disclosure_review == 'UNKNOWN'


@pytest.mark.parametrize('group', ['checks', 'coverage'])
def test_every_known_failure_requires_root_failure(group):
    for name in EXAMPLES['use'][group]:
        record = deepcopy(EXAMPLES['use'])
        if group == 'checks':
            record[group][name]['status'] = 'FAIL'
        else:
            record[group][name] = 'FAIL'
        for root in ('PASS', 'UNKNOWN', 'UNRUN'):
            record['evidence_status'] = root
            rejected(record)
        record['evidence_status'] = 'FAIL'
        assert accepted(record).evidence_status == 'FAIL'


@pytest.mark.parametrize('location', ['root', 'producer', 'baseline', 'cost'])
def test_definition_never_accepts_extra_private_fields(location):
    record = deepcopy(EXAMPLES['definition'])
    target = {'root': record, 'producer': record['producer'], 'baseline': record['baseline'],
              'cost': record['preparation_cost']}[location]
    target['raw_private_body'] = 'private-test-marker-not-for-errors'
    assert not ORACLE.is_valid(record)
    with pytest.raises(Invalid) as error:
        decode_record(encode(record))
    assert 'private-test-marker' not in str(error.value)


@pytest.mark.parametrize('path', [
    ('observer',), ('isolation_ref',), ('reservation_ref',),
    ('consumer', 'inventory_ref'), ('consumer', 'request_association_ref'),
    ('observer', 'dispatch_authority_ref'), ('observer', 'before'),
    ('cost_attribution', 'batch_cost_report_ref'),
])
def test_pass_requires_every_declared_source(path):
    record = deepcopy(EXAMPLES['use'])
    target = record
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = None
    rejected(record)


def test_unknown_and_unstarted_are_not_filled_with_observed_zero():
    record = deepcopy(EXAMPLES['use'])
    record['evidence_status'] = 'UNKNOWN'
    record['observer'] = None
    assert accepted(record).observer is None
    record['evidence_status'] = 'UNRUN'
    record['stage'] = 'NOT_STARTED'
    record['consumer']['probes'] = []
    record['consumer']['task_terminal_at'] = None
    assert accepted(record).stage == 'NOT_STARTED'


@pytest.mark.parametrize('value', [
    '2026-11-13T13:02:03', 'yesterday', '2026-11-31T00:00:00Z',
    '2026-11-13T12:00:00+00:60', '2026-11-13T12:00:00+01:99',
    '2026-11-13T12:00:00-00:99', '2026-11-13T12:00:00+24:00',
])
def test_date_time_requires_an_actual_aware_instant(value):
    record = deepcopy(EXAMPLES['use'])
    record['published_at'] = value
    rejected(record)


@pytest.mark.parametrize('field,value', [
    ('fixture_revision', True), ('fixture_id', 'contains space'),
    ('kind', 'other'), ('version', 'G2C-cross-binding-fixture.2'),
])
def test_strict_record_boundaries(field, value):
    record = deepcopy(EXAMPLES['use'])
    record[field] = value
    rejected(record)


def test_no_urls_duplicate_probes_or_unknown_check_names():
    for mutation in ('url', 'duplicate', 'check'):
        record = deepcopy(EXAMPLES['use'])
        if mutation == 'url':
            record['definition_ref']['ref'] = 'https://untrusted.invalid/fixture'
        elif mutation == 'duplicate':
            record['consumer']['probes'] *= 2
        else:
            record['checks']['invented_success'] = record['checks']['producer_chain']
        rejected(record)


def test_one_shared_strict_json_codec_and_canonical_wire():
    raw = encode(EXAMPLES['use'])
    with pytest.raises(Invalid, match='FIXTURE_RECORD_JSON'):
        decode_record(raw[:-1] + b',"kind":"use"}')
    with pytest.raises(Invalid, match='FIXTURE_RECORD_CANONICAL'):
        decode_record(json.dumps(EXAMPLES['use'], indent=2).encode())
    with pytest.raises(Invalid, match='FIXTURE_RECORD_BOUND'):
        decode_record(b' ' * 1_048_577)
    record = deepcopy(EXAMPLES['use'])
    record['use_id'] = '\ud800'
    raw = json.dumps(record).encode()
    with pytest.raises(Invalid):
        decode_record(raw)


@pytest.mark.parametrize('kind', ['definition', 'use'])
def test_all_published_scalar_paths_against_independent_frozen_schema(kind):
    def leaves(value, path=()):
        if isinstance(value, dict):
            for key, child in value.items():
                yield from leaves(child, (*path, key))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from leaves(child, (*path, index))
        else:
            yield path
    comparisons = 0
    for path in leaves(EXAMPLES[kind]):
        for replacement in (None, True, False, 0, 1, 0.0, 1.0, -1, '', 'invalid value', [], {}):
            record = deepcopy(EXAMPLES[kind])
            target = record
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = replacement
            valid = ORACLE.is_valid(record)
            try:
                decode_record(encode(record))
            except Invalid:
                assert not valid, (kind, path, replacement)
            else:
                assert valid, (kind, path, replacement)
            comparisons += 1
    assert comparisons >= 500


@pytest.fixture
def linked():
    definition, use = deepcopy(EXAMPLES['definition']), deepcopy(EXAMPLES['use'])
    binding = Binding('original-E', 'session-E', 'original-global-ledger', 'original-producer')
    pins = SimpleNamespace(key='c' * 64)
    request = dict(attempt_id='original-attempt', step_id='original-step', payload={'text': 'Original E probe'})
    use['consumer']['binding'].update(binding_sha256=binding.key,
        owner_scope_sha256=sha256(binding.scope.encode()).hexdigest())
    use['consumer'].update(attempt_id=request['attempt_id'], step_id=request['step_id'],
                           request_sha256=digest(request))
    use['definition_ref']['sha256'] = sha256(encode(definition)).hexdigest()
    return definition, use, dict(binding=binding, pins=pins, request=request)


def test_linking_existing_G_context_and_legal_binding_ref_aliases(linked):
    definition, use, context = linked
    records = link_records(encode(definition), encode(use), **context)
    assert records.use.consumer.binding.binding_sha256 == context['binding'].key
    # Legal aliases do not change the original observer's Binding.key.
    use['observer']['binding']['binding_ref']['ref'] = 'original-' + '0' * 64
    link_records(encode(definition), encode(use), **context)


@pytest.mark.parametrize('change,reason', [
    ('hash', 'DEFINITION_HASH'), ('identity', 'IDENTITY_MISMATCH'),
    ('binding', 'CONSUMER_BINDING'), ('pins', 'CONSUMER_PINS'),
    ('request', 'CONSUMER_REQUEST'), ('owner', 'DIFFERENT_OWNER'),
    ('session', 'OBSERVER_BINDING'), ('charge', 'ORIGINAL_CHARGE'),
])
def test_context_or_original_charge_cannot_be_relabelled(linked, change, reason):
    definition, use, context = linked
    if change == 'hash':
        use['definition_ref']['sha256'] = '0' * 64
    elif change == 'identity':
        use['fixture_revision'] += 1
    elif change == 'binding':
        use['consumer']['binding']['binding_sha256'] = '0' * 64
    elif change == 'pins':
        use['consumer']['pins_sha256'] = '0' * 64
    elif change == 'request':
        use['consumer']['request_sha256'] = '0' * 64
    elif change == 'owner':
        definition['producer']['binding']['owner_scope_sha256'] = use['consumer']['binding']['owner_scope_sha256']
        use['observer']['binding']['owner_scope_sha256'] = use['consumer']['binding']['owner_scope_sha256']
        use['definition_ref']['sha256'] = sha256(encode(definition)).hexdigest()
    elif change == 'session':
        use['observer']['binding']['binding_sha256'] = '0' * 64
    else:
        use['cost_attribution']['charge_id'] = 'a-new-charge'
    with pytest.raises(Invalid, match=reason):
        link_records(encode(definition), encode(use), **context)


def test_linking_hashes_original_wire_not_reserialized_normalized_values(linked):
    definition, use, context = linked
    definition['fixture_revision'] = 1.0
    raw = encode(definition)
    use['definition_ref']['sha256'] = sha256(raw).hexdigest()
    records = link_records(raw, encode(use), **context)
    assert records.definition.fixture_revision == 1
    assert records.definition_wire == raw
