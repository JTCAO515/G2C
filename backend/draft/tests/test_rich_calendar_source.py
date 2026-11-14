"""L0 grammar/lifetime controls; these doubles are not native PG acceptance."""
from contextlib import contextmanager
from copy import copy, deepcopy
from dataclasses import replace
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cj_message.domain import Receipt, Stored
from cj_needs.domain import Snapshot
from cj_needs.revision_lease import LeaseUnavailable
from cj_run.core import Binding
from cj_trip.domain import packed
from cj_draft.calendar_source import CalendarBasis
from cj_draft.lio_plan import LioContextSource
from cj_draft.rich_calendar_source import (
    FIXED_BINDINGS, RichCalendarBasis, RichCalendarCapture, RichCalendarContextSource,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = json.loads((ROOT/'contracts/message/trip-send-examples.2.json').read_bytes())
OLD = next(row['value'] for row in FIXTURE['positive'] if row['definition'] == 'FixedDays')


def sidecar():
    value = deepcopy(OLD)
    value['version'] = FIXED_BINDINGS
    value['reference']['lio_protocol'] = 'LIO-message.4'
    return value


def test_new_root_keeps_historical_protocol_and_old_codec_refuses_it():
    value = sidecar()
    basis = RichCalendarBasis(3, None, packed(value))
    assert basis.metadata()['version'] == 'TRIP-calendar-basis.2'
    assert basis.day_indices() == {'hotel-meetup': (1, 1)}
    assert json.loads(basis.fixed_bindings)['bindings'][0]['source_reference']['lio_protocol'] == 'LIO-message.3'
    with pytest.raises(ValueError):
        CalendarBasis(3, None, basis.fixed_bindings)
    value['version'] = 'LIO-fixed-day-bindings.1'
    with pytest.raises(ValueError):
        CalendarBasis(3, None, packed(value))
    assert CalendarBasis(3, None, packed(OLD)).day_indices() == basis.day_indices()
    with pytest.raises(TypeError):
        RichCalendarCapture(None, None, basis, None, None, None, b'{}')


@pytest.mark.parametrize('change', [
    lambda v: v.update(version='LIO-fixed-day-bindings.1'),
    lambda v: v['reference'].update(lio_protocol='LIO-message.3'),
    lambda v: v['reference'].update(lio_protocol='MESSAGE-send.4'),
    lambda v: v['reference'].update(sequence=True),
    lambda v: v['reference'].update(input_sha256='outer-wire-sha'),
    lambda v: v['reference'].update(message_version='LIO-message.4'),
    lambda v: v.update(needs_content_sha256='not-a-digest'),
    lambda v: v.update(needs_version=True),
    lambda v: v['bindings'][0].update(day_index=0),
    lambda v: v['bindings'][0].update(end_day_index=4),
    lambda v: v['bindings'][0].update(day_index=2, end_day_index=1),
    lambda v: v['bindings'][0].update(quote=''),
    lambda v: v['bindings'].append(deepcopy(v['bindings'][0])),
    lambda v: v['bindings'][0]['source_reference'].update(lio_protocol='LIO-message.5'),
])
def test_new_grammar_refuses_wrong_version_originals_and_fixed_bindings(change):
    value = sidecar()
    change(value)
    with pytest.raises(ValueError):
        RichCalendarBasis(3, None, packed(value))


@pytest.fixture
def harness(monkeypatch):
    events = []
    value = sidecar()
    original = deepcopy(FIXTURE['source_messages']['fixed-message'])
    original.update(message_id='plan-now', text='Plan now', expected_sequence=1)
    root = value['reference']
    root.update(message_id='plan-now', run_id='plan-run', sequence=2, input_sha256=sha256(packed(original)).hexdigest())
    binding = Binding('scope', root['conversation_id'], root['generation'], root['message_id'], root['run_id'], root['sequence'])
    before = Snapshot(value['needs_id'], 1, packed(FIXTURE['needs_basis']['fields']))
    value['needs_content_sha256'] = sha256(before.content).hexdigest()
    basis = RichCalendarBasis(3, None, packed(value))
    references = {root['message_id']: root, 'fixed-message': value['bindings'][0]['source_reference']}
    originals = {root['message_id']: original, 'fixed-message': FIXTURE['source_messages']['fixed-message']}
    stored = {mid: Stored(packed(originals[mid]), Receipt(**{key: ref[key] for key in
              ('message_id', 'conversation_id', 'generation', 'sequence', 'run_id', 'input_sha256')}))
              for mid, ref in references.items()}
    needs = SimpleNamespace(raw=packed(dict(version='TRIP-NEEDS-SOURCE@1', reference=root,
        needs_scope='needs-scope', needs_id=before.needs_id, revision=1)), records=lambda: (before, ()))
    flags = dict(calendar=True, profile=True, question_day=date(2026, 11, 14))

    class Message:
        reference = SimpleNamespace(public_value=lambda: {k: v for k, v in root.items() if k != 'lio_protocol'})
        def check(self, b):
            assert b == binding
            events.append('message-check')
        def original_message(self): return stored[root['message_id']]

    message = Message()
    class Messages:
        @contextmanager
        def hold_for_effect(self, b):
            assert b == binding
            events.append('message-enter')
            try: yield message
            finally: events.append('message-exit')

    class NeedsLease:
        @contextmanager
        def hold(self, _token, b):
            assert b == binding
            events.append('needs-enter')
            try: yield lambda: events.append('needs-check')
            finally: events.append('needs-exit')

    class Calendar:
        def capture(self, b, m, n):
            assert b == binding and m is message and n is needs
            return basis
        @contextmanager
        def hold(self, b, issued, m):
            assert b == binding and issued is basis and m is message
            def check():
                if not flags['calendar']: raise LeaseUnavailable('fixture calendar withdrawn')
                events.append('calendar-check')
            held = SimpleNamespace(day_count=3, start_date=None, check=check,
                original=lambda ref: (stored[ref['message_id']], references[ref['message_id']]['lio_protocol']),
                question_day=lambda _: flags['question_day'],
                fixed_day_indices=lambda *_: (1, 1))
            events.append('calendar-enter')
            try: yield held
            finally: events.append('calendar-exit')

    profile = SimpleNamespace(original=dict(protocol='LIO-message.4', message_id=binding.message_id,
        run_id=binding.run_id, input_sha256=root['input_sha256'], question_day='2026-11-14'),
        plan_now={'kind': 'fixture'}, policy={'id': 'fixture'}, profile_states={'pace': 'known'}, profile={})
    worker, expected = object(), object()
    class Profiles:
        def capture_for_plan(self, w, b, m, *, expected_profile):
            assert w is worker and b == binding and m is message and expected_profile is expected
            return profile
        @contextmanager
        def hold_for_plan(self, w, b, captured, m):
            assert w is worker and b == binding and captured is profile and m is message
            def check():
                if not flags['profile']: raise LeaseUnavailable('fixture Memory/profile withdrawn')
                events.append('profile-check')
            events.append('profile-enter')
            try: yield SimpleNamespace(check=check)
            finally: events.append('profile-exit')

    base = SimpleNamespace(reader=None, message_context=Messages(), revision_lease=NeedsLease(),
        token_supplier=lambda: 'synthetic-only', max_revisions=128, max_bytes=4_000_000, trip_repository=None)
    source = RichCalendarContextSource(base, None, Calendar(), None, profile_reader=Profiles(),
                                       worker=worker, expected_profile=expected)
    def capture(_self, b):
        assert b == binding
        source._captures[b] = needs
        source.contexts[b] = None
        return needs
    monkeypatch.setattr(LioContextSource, 'capture', capture)
    result = source.capture(binding)
    return SimpleNamespace(source=source, capture=result, binding=binding, events=events, flags=flags)


def test_same_message_profile_and_calendar_remain_held_before_needs(harness):
    h = harness
    with pytest.raises(LeaseUnavailable): h.source.check(h.binding, h.capture)
    raw = json.loads(h.capture.raw)
    assert raw['version'] == 'TRIP-RICH-CALENDAR-SOURCE.1'
    assert raw['planning_profile']['original']['protocol'] == 'LIO-message.4'
    with h.source.hold_for_publication(h.binding) as check:
        assert check() is True
        h.events.append('body')
    assert h.events.index('calendar-enter') < h.events.index('profile-enter') < h.events.index('needs-enter') < h.events.index('body')
    assert h.events.index('needs-exit') < h.events.index('profile-exit') < h.events.index('calendar-exit')
    with pytest.raises(LeaseUnavailable): h.source.check(h.binding, h.capture)


@pytest.mark.parametrize('kind', ['profile', 'calendar'])
def test_final_source_withdrawal_and_copied_capture_withhold(harness, kind):
    h = harness
    with pytest.raises(LeaseUnavailable), h.source.hold_for_publication(h.binding):
        with pytest.raises(LeaseUnavailable): h.source.check(h.binding, copy(h.capture))
        with pytest.raises(LeaseUnavailable): h.source.check(replace(h.binding, run_id='foreign-run'), h.capture)
        h.flags[kind] = False


def test_changed_reader_cannot_reuse_previous_capture(harness):
    h = harness
    h.source.profile_reader = object()
    with pytest.raises(LeaseUnavailable), h.source.hold_for_publication(h.binding): pass


def test_calendar_clock_cannot_differ_from_native_profile_original(harness):
    h = harness
    h.flags['question_day'] = date(2026, 11, 15)
    with pytest.raises(LeaseUnavailable, match='question clock differs'), h.source.hold_for_publication(h.binding): pass


@pytest.mark.parametrize('change', [
    lambda v: v.update(needs_id='foreign-needs'),
    lambda v: v.update(needs_version=2),
    lambda v: v.update(needs_content_sha256='0'*64),
    lambda v: v['reference'].update(run_id='foreign-run'),
    lambda v: v['reference'].update(input_sha256='0'*64),
    lambda v: v['bindings'][0].update(item_id='invented-fixed-item'),
])
def test_data_valid_sidecar_cannot_replace_actual_message_or_needs(harness, monkeypatch, change):
    h = harness
    value = json.loads(h.capture.basis.fixed_bindings)
    change(value)
    valid_data = RichCalendarBasis(3, None, packed(value))
    monkeypatch.setattr(h.source.calendar_reader, 'capture', lambda *_: valid_data)
    with pytest.raises(LeaseUnavailable): h.source.capture(h.binding)


def test_copied_context_in_another_thread_cannot_use_the_lease(harness):
    from contextvars import copy_context
    from threading import Thread
    h = harness
    failures = []
    def use():
        try: h.source.check(h.binding, h.capture)
        except LeaseUnavailable: failures.append('denied')
    with h.source.hold_for_publication(h.binding):
        context = copy_context()
        other = Thread(target=lambda: context.run(use))
        other.start()
        other.join(timeout=2)
        assert not other.is_alive() and failures == ['denied']
