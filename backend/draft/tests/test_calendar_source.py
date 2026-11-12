from copy import deepcopy
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from cj_message.domain import Receipt, Stored
from cj_needs.revision_lease import LeaseUnavailable
from cj_trip.domain import packed
from cj_trip.needs_source import NeedsSourceAuthority
from cj_draft.calendar_source import CalendarBasis, CalendarCapture, CalendarContextSource

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = json.loads((ROOT/'contracts/message/trip-send-examples.2.json').read_bytes())
SIDECAR = next(r['value'] for r in FIXTURES['positive'] if r['definition'] == 'FixedDays')


def test_basis_is_data_and_cannot_issue_a_publication_capture():
    basis = CalendarBasis(3, None, packed(SIDECAR))
    assert basis.day_indices() == {'hotel-meetup': (1, 1)}
    assert basis.metadata()['start_date'] is None
    with pytest.raises(TypeError):
        CalendarCapture(None, None, basis, b'{}')


@pytest.mark.parametrize('change', [
    lambda v: v['bindings'][0].update(day_index=0),
    lambda v: v['bindings'][0].update(day_index=4),
    lambda v: v['bindings'][0].update(end_day_index=True),
    lambda v: v['bindings'][0].update(quote=''),
    lambda v: v['bindings'].append(deepcopy(v['bindings'][0])),
    lambda v: v.update(version='MEMORY-CANDIDATE@1'),
])
def test_malformed_binding_sidecars_never_become_a_basis(change):
    value = deepcopy(SIDECAR)
    change(value)
    with pytest.raises(ValueError):
        CalendarBasis(3, None, packed(value))


def test_canonical_original_is_not_an_outer_hash_or_forged_receipt():
    reference = FIXTURES['source_receipts']['fixed-message']
    original_message = FIXTURES['source_messages']['fixed-message']
    receipt = Receipt(**{k: reference[k] for k in ('message_id', 'conversation_id', 'generation',
                                                   'sequence', 'run_id', 'input_sha256')})

    class Held:
        stored = Stored(packed(original_message), receipt)
        protocol = reference['lio_protocol']

        def original(self, _):
            return self.stored, self.protocol

    held = Held()
    command = CalendarContextSource._original(held, reference)
    assert command.message_id == reference['message_id']
    held.protocol = 'LIO-message.2'
    with pytest.raises(LeaseUnavailable):
        CalendarContextSource._original(held, reference)

    held.protocol = reference['lio_protocol']
    held.stored = Stored(packed(original_message), replace(receipt, generation='foreign-generation'))
    with pytest.raises(LeaseUnavailable):
        CalendarContextSource._original(held, reference)
    # MESSAGE stores exact accepted UTF8; do not sort/re-encode the original
    # merely because the internal sidecar itself has canonical encoding.
    raw = json.dumps(original_message, ensure_ascii=False).encode()
    exact = dict(reference, input_sha256=sha256(raw).hexdigest())
    held.stored = Stored(raw, replace(receipt, input_sha256=exact['input_sha256']))
    assert CalendarContextSource._original(held, exact).raw == raw


def test_additional_source_extension_enters_before_needs_and_unwinds_after_it():
    # L0 lock-order harness only; these doubles never stand in for real PG/AUTH proof.
    events = []
    binding, capture = object(), object()

    class Message:
        def check(self, _):
            events.append('message-check')

    class Messages:
        @contextmanager
        def hold_for_effect(self, _):
            events.append('message-enter')
            try:
                yield Message()
            finally:
                events.append('message-exit')

    class Needs:
        @contextmanager
        def hold(self, token, _):
            events.append('needs-enter')
            try:
                yield lambda: events.append('needs-check')
            finally:
                events.append('needs-exit')

    class Source(NeedsSourceAuthority):
        @contextmanager
        def hold_additional_sources(self, b, c, message):
            assert b is binding and c is capture
            events.append('extra-enter')
            try:
                yield
            finally:
                events.append('extra-exit')

    source = Source(None, Messages(), Needs(), lambda: 'synthetic', max_revisions=1, max_bytes=100)
    source._captures[binding] = capture
    with source.hold_for_publication(binding):
        events.append('body')
    assert events.index('message-enter') < events.index('extra-enter') < events.index('needs-enter') < events.index('body')
    assert events.index('needs-exit') < events.index('extra-exit') < events.index('message-exit')
    with pytest.raises(LeaseUnavailable):
        source.check(binding, capture)


@pytest.mark.parametrize('change', [
    lambda v: v['date_source']['reference'].update(conversation_id='other-dialogue'),
    lambda v: v['date_source']['reference'].update(generation='other-generation'),
    lambda v: v['date_source']['reference'].update(sequence=99),
    lambda v: v.update(start_date='2026-12-02'),
])
def test_conversion_cannot_use_another_readable_original_or_different_compiled_date(change):
    from types import SimpleNamespace
    from unittest.mock import patch
    from cj_trip.domain import Trip
    from cj_draft.calendar_dates import convert
    raw = deepcopy(FIXTURES['conversion_input'])
    original = deepcopy(raw)
    change(raw)
    trip = Trip(original['trip_id'], original['expected_version'], packed(FIXTURES['protected_contents'][0]))
    root = packed(dict(reference=original['date_source']['reference']))
    capture = SimpleNamespace(basis=SimpleNamespace(fixed_bindings=root, start_date=original['start_date']))
    message = object()
    class Source:
        contexts = {'binding': SimpleNamespace(trip=trip)}
        calendar_active = SimpleNamespace(get=lambda: (capture, object()))
        def check(self, *_): pass
        def _original(self, *_): raise AssertionError('foreign source cannot be consulted')
    publisher = SimpleNamespace(source=Source(), repository=object(), require_lio=lambda *_: None)
    with patch('cj_draft.calendar_dates.query', return_value=None), pytest.raises(LeaseUnavailable):
        convert(publisher, 'binding', message, message, packed(raw), capture, lambda **_: None)
