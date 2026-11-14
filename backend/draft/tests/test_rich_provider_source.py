"""L0 composition controls; fake readers do not prove actual provider admission."""
from contextlib import contextmanager
from copy import copy, deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cj_memory.runtime import RuntimeUnknown
from cj_needs.revision_lease import LeaseUnavailable
from cj_draft.rich_provider_source import RichProviderCapture, RichProviderContextSource
from test_rich_calendar_source import source_harness

ROOT = Path(__file__).resolve().parents[3]
RECORD = json.loads((ROOT/'contracts/trip/structured-examples.4.json').read_bytes())['cases']['matched']['source']['records'][0]


@dataclass(frozen=True)
class FixtureProviderCapture:
    records: list
    revision: int


class FixtureProviders:
    def __init__(self):
        self.revision = 0
        self.capture_calls = 0
        self.issued = None
        self.available = True
        self.pending = False
        self.events = []

    def capture(self, binding):
        self.capture_calls += 1
        if self.pending:
            raise RuntimeUnknown('fixture unresolved original attempt')
        self.issued = FixtureProviderCapture([deepcopy(RECORD)], self.revision)
        self.events.append('provider-seal')
        return self.issued

    @contextmanager
    def hold(self, binding, capture, message):
        if capture is not self.issued:
            raise LeaseUnavailable('fixture unissued provider capture')
        def check():
            message.check(binding)
            if not self.available or self.revision != capture.revision:
                raise LeaseUnavailable('fixture provider changed')
            self.events.append('provider-check')
        self.events.append('provider-enter')
        try:
            yield SimpleNamespace(check=check)
        finally:
            self.events.append('provider-exit')


@pytest.fixture
def harness(monkeypatch):
    providers = FixtureProviders()
    h = source_harness(monkeypatch, RichProviderContextSource, provider_reader=providers)
    providers.events = h.events
    h.providers = providers
    return h


def test_no_record_list_or_copied_calendar_can_issue_a_capture(harness):
    h = harness
    with pytest.raises(TypeError): RichProviderCapture(h.capture, [], h.providers, b'{}')
    for fake in ([], copy(h.capture)):
        with pytest.raises(LeaseUnavailable): h.source.seal_providers(h.binding, fake)
    assert h.providers.capture_calls == 0
    with pytest.raises(LeaseUnavailable), h.source.hold_for_publication(h.binding): pass


def test_actual_reader_seals_before_publication_and_joins_before_needs(harness):
    h = harness
    capture = h.source.seal_providers(h.binding, h.capture)
    assert capture.binding == h.binding and capture.basis is h.capture.basis
    assert capture.profile is h.capture.profile and capture.records() == h.capture.records()
    assert json.loads(capture.raw)['version'] == 'TRIP-RICH-PROVIDER-SOURCE.1'
    assert capture.provider_records == [RECORD]
    local_copy = capture.provider_records
    local_copy[0]['payload'] = {'model': 'changed display copy'}
    assert capture.provider_records == [RECORD]
    with pytest.raises(LeaseUnavailable): h.source.check(h.binding, capture)
    with h.source.hold_for_publication(h.binding) as check:
        assert check() is True
        h.events.append('body')
    assert h.events.index('provider-seal') < h.events.index('calendar-enter') < h.events.index('profile-enter')
    assert h.events.index('profile-enter') < h.events.index('provider-enter') < h.events.index('needs-enter') < h.events.index('body')
    assert h.events.index('needs-exit') < h.events.index('provider-exit') < h.events.index('profile-exit')
    with pytest.raises(LeaseUnavailable): h.source.check(h.binding, capture)


def test_materialization_inside_publication_is_denied_before_reader_runs(harness):
    h = harness
    h.source.seal_providers(h.binding, h.capture)
    with h.source.hold_for_publication(h.binding):
        before = h.providers.capture_calls
        with pytest.raises(LeaseUnavailable, match='publication locks'):
            h.source.seal_providers(h.binding, h.capture)
        assert h.providers.capture_calls == before


@pytest.mark.parametrize('withdraw', ['provider', 'profile', 'calendar'])
def test_final_provider_and_base_source_changes_withhold(harness, withdraw):
    h = harness
    capture = h.source.seal_providers(h.binding, h.capture)
    with pytest.raises(LeaseUnavailable), h.source.hold_for_publication(h.binding):
        assert h.source.check(h.binding, capture) is True
        if withdraw == 'provider': h.providers.available = False
        else: h.flags[withdraw] = False


def test_new_provider_operation_invalidates_the_old_seal(harness):
    h = harness
    h.source.seal_providers(h.binding, h.capture)
    h.providers.revision += 1
    with pytest.raises(LeaseUnavailable), h.source.hold_for_publication(h.binding): pass


def test_reissued_or_copied_capture_never_becomes_current_authority(harness):
    h = harness
    old = h.source.seal_providers(h.binding, h.capture)
    current = h.source.seal_providers(h.binding, h.capture)
    with h.source.hold_for_publication(h.binding):
        assert h.source.check(h.binding, current) is True
        for fake in (old, copy(current)):
            with pytest.raises(LeaseUnavailable): h.source.check(h.binding, fake)


def test_unsettled_original_never_yields_a_seal_or_triggers_a_retry(harness):
    h = harness
    h.providers.pending = True
    with pytest.raises(RuntimeUnknown): h.source.seal_providers(h.binding, h.capture)
    assert h.providers.capture_calls == 1 and h.source.provider_captures == {}
    with pytest.raises(LeaseUnavailable), h.source.hold_for_publication(h.binding): pass


def test_source_size_and_changed_reader_do_not_release_a_capture(harness):
    h = harness
    h.source.max_bytes = 1
    with pytest.raises(LeaseUnavailable, match='byte bound'): h.source.seal_providers(h.binding, h.capture)
    assert h.source.provider_captures == {}
    h.source.max_bytes = 4_000_000
    h.source.seal_providers(h.binding, h.capture)
    h.source.provider_reader = object()
    with pytest.raises(LeaseUnavailable), h.source.hold_for_publication(h.binding): pass


def test_reader_change_inside_final_frame_withholds_publication(harness):
    h = harness
    h.source.seal_providers(h.binding, h.capture)
    with pytest.raises(LeaseUnavailable), h.source.hold_for_publication(h.binding):
        h.source.provider_reader = object()
