"""Selection source L0 controls; fixture readers confer no actual eligibility."""
from copy import copy, deepcopy
from dataclasses import replace
from hashlib import sha256
import json

import pytest

from cj_draft.lio_rich import LioRichPublisher
from cj_draft.rich_place_selection import RichPlaceSelectionContextSource, LioSelectedRichPublisher
from cj_draft.rich_provider_source import RichProviderContextSource
from cj_memory.runtime import RuntimeUnknown
from cj_needs.revision_lease import LeaseUnavailable
from cj_trip.domain import packed
from cj_trip.place_selection import VERSION, SOURCE, PLAN_SOURCE, selections, validate_basis
from cj_trip.structured import FieldRejected, SourceRejected
from test_rich_calendar_source import source_harness
from test_rich_provider_source import FixtureProviders, RECORD


def outcome(*, operation='op-one', target='stop-one', keyword='目标地点', status='ok', count=1):
    return dict(version='LIO-provider-outcome.1', operation_id=operation, attempt_id='attempt-'+operation,
        registration='tool.lio_poi2.1', input_sha256='a'*64, reply_sha256='b'*64,
        request_ref='request-'+operation, status=status, item_count=count, targets=[target],
        query_type='TextSearch', query=dict(keyword=keyword, region='北京', page_size=3))


def place(name='另一个地点', *, operation='op-one', amap_id='B000A00001'):
    payload=deepcopy(RECORD['payload']);payload.update(name_zh=name,amap_id=amap_id)
    return dict(provider='amap',kind='place',reference=operation+':poi:'+amap_id,
                sha256=sha256(packed(payload)).hexdigest(),payload=payload)


class SelectionProviders(FixtureProviders):
    def __init__(self):
        super().__init__();self.outcomes=[outcome()];self.records=[place()]

    def capture(self,binding):
        captured=super().capture(binding)
        self.issued=replace(captured,records=deepcopy(self.records))
        return self.issued


@pytest.fixture
def harness(monkeypatch):
    providers=SelectionProviders()
    h=source_harness(monkeypatch,RichPlaceSelectionContextSource,provider_reader=providers)
    providers.events=h.events;h.providers=providers
    return h


def test_nonempty_no_exact_is_separate_selection_proof_not_changed_provider(harness):
    h=harness;before=deepcopy(h.providers.outcomes)
    capture=h.source.seal_providers(h.binding,h.capture)
    value=json.loads(capture.raw)
    assert value['version']==SOURCE and value['place_selection_version']==VERSION
    with pytest.raises(LeaseUnavailable):h.source.place_selection(h.binding,capture,'stop-one',keyword='目标地点')
    with h.source.hold_for_publication(h.binding):
        selected=h.source.place_selection(h.binding,capture,'stop-one',keyword='目标地点')
        assert selected['status']=='unavailable' and selected['reason']=='no_exact_eligible_place'
        assert selected['selected_record'] is None
        assert selected['provider_outcome_sha256']==sha256(packed(before[0])).hexdigest()
        assert h.source.unavailable_targets(h.binding,capture)==frozenset({'stop-one'})
        assert h.source.provider_outcomes(h.binding,capture)==before
    assert h.providers.outcomes==before and before[0]['status']=='ok' and before[0]['item_count']==1
    with pytest.raises(LeaseUnavailable):h.source.selection_results(h.binding,capture)


def test_unique_exact_result_is_shared_with_host_and_cannot_be_unavailable(harness):
    h=harness;h.providers.records=[place('目标地点')]
    capture=h.source.seal_providers(h.binding,h.capture)
    with h.source.hold_for_publication(h.binding):
        selected=h.source.place_selection(h.binding,capture,'stop-one',keyword='目标地点')
        assert selected['status']=='matched' and selected['reason']=='unique_exact_place'
        assert selected['selected_record']==h.providers.records[0]
        assert h.source.unavailable_targets(h.binding,capture)==frozenset()
        selected['status']='unavailable';selected['selected_record']['payload']['name_zh']='model fake'
        assert h.source.place_selection(h.binding,capture,'stop-one',keyword='目标地点')['status']=='matched'
        assert h.source.unavailable_targets(h.binding,capture)==frozenset()


def test_multiple_exact_identities_are_ambiguous_not_first_result_or_fallback(harness):
    h=harness;h.providers.outcomes=[outcome(count=2)]
    h.providers.records=[place('目标地点'),place('目标地点',amap_id='B000A00002')]
    capture=h.source.seal_providers(h.binding,h.capture)
    with h.source.hold_for_publication(h.binding):
        result=h.source.place_selection(h.binding,capture,'stop-one',keyword='目标地点')
        assert result['status']=='ambiguous' and result['selected_record'] is None
        assert h.source.unavailable_targets(h.binding,capture)==frozenset()


@pytest.mark.parametrize('status,count,records,reason',[
    ('ok',1,[],'no_exact_eligible_place'),
    ('ok',0,[],'empty_page'),
    ('unavailable',0,[],'provider_unavailable'),
])
def test_complete_terminal_page_outcomes_remain_distinct(harness,status,count,records,reason):
    h=harness;h.providers.outcomes=[outcome(status=status,count=count)];h.providers.records=records
    captured=h.source.seal_providers(h.binding,h.capture)
    with h.source.hold_for_publication(h.binding):
        assert h.source.place_selection(h.binding,captured,'stop-one',keyword='目标地点')['reason']==reason


@pytest.mark.parametrize('mutate',[
    lambda p:p.outcomes[0].pop('operation_id'),
    lambda p:p.outcomes[0].update(query={}),
    lambda p:p.outcomes[0].update(query_type='POIDetail',query={'provider_id':'B000A00001'}),
    lambda p:p.outcomes[0].update(targets=[]),
    lambda p:p.outcomes[0].update(status='unknown'),
    lambda p:p.outcomes[0].update(status='unavailable'),
    lambda p:p.records[0].update(reference='foreign-op:poi:B000A00001'),
    lambda p:p.records[0].update(sha256='c'*64),
    lambda p:p.records[0].update(provider='visitor',kind='tip'),
    lambda p:p.outcomes.append(outcome(operation='op-two')),
    lambda p:p.records.append(deepcopy(p.records[0])),
])
def test_missing_unknown_wrong_operation_or_query_cannot_issue_selection(harness,mutate):
    h=harness;mutate(h.providers)
    with pytest.raises(FieldRejected):h.source.seal_providers(h.binding,h.capture)
    assert h.source.provider_captures=={}


def test_same_name_in_foreign_operation_does_not_cover_target(harness):
    h=harness;h.providers.outcomes.append(outcome(operation='op-two',target='stop-two'))
    h.providers.records.append(place('目标地点',operation='op-two'))
    captured=h.source.seal_providers(h.binding,h.capture)
    with h.source.hold_for_publication(h.binding):
        assert h.source.place_selection(h.binding,captured,'stop-one',keyword='目标地点')['status']=='unavailable'
        assert h.source.place_selection(h.binding,captured,'stop-two',keyword='目标地点')['status']=='matched'
        with pytest.raises(LeaseUnavailable):h.source.place_selection(h.binding,captured,'foreign-target',keyword='目标地点')
        with pytest.raises(LeaseUnavailable):h.source.place_selection(h.binding,captured,'stop-one',keyword='wrong query')


def test_nearby_uses_its_actual_keyword_and_route_failure_does_not_cover_a_place(harness):
    h=harness;h.providers.records=[place('目标地点')]
    poi=h.providers.outcomes[0];poi['query_type']='Nearby'
    poi['query'].update(center={'raw':'116.4,39.9'},radius_m=1500)
    route=outcome(operation='route-op',target='stop-one',status='unavailable',count=0)
    route.update(registration='tool.lio_route.1',query_type='CityRoute',query={})
    h.providers.outcomes.append(route)
    captured=h.source.seal_providers(h.binding,h.capture)
    with h.source.hold_for_publication(h.binding):
        assert h.source.place_selection(h.binding,captured,'stop-one',keyword='目标地点')['status']=='matched'
        assert h.source.unavailable_targets(h.binding,captured)==frozenset()


def test_no_operation_and_unsettled_original_do_not_create_fallback(harness):
    h=harness;h.providers.outcomes=[];h.providers.records=[]
    captured=h.source.seal_providers(h.binding,h.capture)
    with h.source.hold_for_publication(h.binding):
        assert h.source.unavailable_targets(h.binding,captured)==frozenset()
        with pytest.raises(LeaseUnavailable):h.source.place_selection(h.binding,captured,'stop-one',keyword='目标地点')
    h.providers.pending=True
    with pytest.raises(RuntimeUnknown):h.source.seal_providers(h.binding,h.capture)
    assert h.providers.capture_calls==2


@pytest.mark.parametrize('withdraw',['provider','profile','calendar','reader'])
def test_selection_rechecks_the_original_final_holder(harness,withdraw):
    h=harness;capture=h.source.seal_providers(h.binding,h.capture)
    with pytest.raises(LeaseUnavailable),h.source.hold_for_publication(h.binding):
        assert h.source.place_selection(h.binding,capture,'stop-one',keyword='目标地点')['status']=='unavailable'
        if withdraw=='provider':h.providers.available=False
        elif withdraw=='reader':h.source.provider_reader=object()
        else:h.flags[withdraw]=False


def test_copied_old_foreign_and_revised_captures_are_not_selection_authority(harness):
    h=harness;old=h.source.seal_providers(h.binding,h.capture)
    current=h.source.seal_providers(h.binding,h.capture)
    with h.source.hold_for_publication(h.binding):
        for capture in (old,copy(current)):
            with pytest.raises(LeaseUnavailable):h.source.selection_results(h.binding,capture)
        with pytest.raises(LeaseUnavailable):h.source.selection_results(replace(h.binding,run_id='foreign-run'),current)
    h.providers.revision+=1
    with pytest.raises(LeaseUnavailable),h.source.hold_for_publication(h.binding):pass


def test_new_basis_is_exactly_reconstructible_from_complete_retained_originals(harness):
    h=harness;captured=h.source.seal_providers(h.binding,h.capture)
    value=json.loads(captured.raw);value.update(version=PLAN_SOURCE,provider_outcomes=deepcopy(h.providers.outcomes))
    validate_basis(value)
    for change in ('selection','outcome','record'):
        wrong=deepcopy(value)
        if change=='selection':wrong['place_selections'][0]['status']='matched'
        elif change=='outcome':wrong['provider_outcomes'][0]['query']['keyword']='另一个地点'
        else:wrong['provider_records'][0]['payload']['name_zh']='目标地点'
        with pytest.raises(SourceRejected):validate_basis(wrong)


def test_old_source_and_publisher_remain_the_default(monkeypatch):
    providers=SelectionProviders()
    h=source_harness(monkeypatch,RichProviderContextSource,provider_reader=providers)
    captured=h.source.seal_providers(h.binding,h.capture)
    assert json.loads(captured.raw)['version']=='TRIP-RICH-PROVIDER-SOURCE.1'
    assert 'place_selections' not in json.loads(captured.raw)
    with h.source.hold_for_publication(h.binding):assert h.source.unavailable_targets(h.binding,captured)==frozenset()
    assert LioRichPublisher.plan_source_version=='TRIP-RICH-PLAN-SOURCE.1'
    assert LioSelectedRichPublisher.plan_source_version==PLAN_SOURCE
    with pytest.raises(ValueError,match='explicit issued selection source'):
        LioSelectedRichPublisher(None,None,h.source,None,None)


def test_new_source_cannot_be_installed_on_the_old_publisher(harness):
    with pytest.raises(ValueError,match='matching source/publisher version'):
        LioRichPublisher(None,None,harness.source,None,None)
