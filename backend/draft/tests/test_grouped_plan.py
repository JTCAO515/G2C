from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from cj_agent.provider import DashScopeConfig, MeteredDashScopeProvider, M4_BASE, M4_MODEL, M4_REAL_OUTPUT_TOKENS
from cj_draft.grouped_plan import LioGroupedPlanPublisher, LioGroupedCalendarPublisher, expand
from cj_draft.lio_plan import LioPlanPublisher, COMPACT_INITIAL_PLAN, LIO_REPLAN_DELTA_V3
from cj_trip.domain import Trip, packed
from cj_trip.structured import FieldRejected, SourceRejected
from grouped_draft_fixtures import reply, source


def publisher(days, language, *, ordinal=False, party=1):
    snapshot, revisions = source(days, language, ordinal=ordinal, party=party)
    capture = SimpleNamespace(binding='original', records=lambda:(snapshot,revisions),
        basis=SimpleNamespace(day_count=days,start_date=None,day_indices=lambda:{'hotel':(1,1)}))
    cls = LioGroupedCalendarPublisher if ordinal else LioGroupedPlanPublisher
    host = cls.__new__(cls)
    host.source = SimpleNamespace(contexts={'original':None})
    host.draft_guidance = 'Cover every requested morning and afternoon.'
    return host,capture


@pytest.mark.parametrize('days',[4,5])
@pytest.mark.parametrize('language',['zh','en'])
@pytest.mark.parametrize('ordinal',[False,True])
def test_complete_four_five_day_first_and_delta_retain_every_slot_name_and_fixed_item(days,language,ordinal):
    host,capture = publisher(days,language,ordinal=ordinal)
    value = reply(days,language,ordinal=ordinal)
    raw = packed(value)
    assert len(raw) < 1024  # Conservative UTF8 fixture bound, not a measured vendor token count.
    content,candidate,_ = host.build_plan(raw,capture)
    document = json.loads(content)
    assert len(document['items']) == 1+days*2
    assert [i['text'] for i in document['items'][1:]] == [row[1] for _,rows in value['days'] for row in rows]
    assert document['items'][0]['fixed'] == dict(state='known',value=True)
    assert document['items'][0]['schedule']['start']['time']['value'] == '09:00'
    host.source.contexts['original'] = SimpleNamespace(trip=Trip('trip',1,content),proposed=candidate.content)
    delta = reply(days,language,ordinal=ordinal,delta=True)
    result,_,_ = host.build_plan(packed(delta),capture)
    after = json.loads(result)
    assert after['items'][:len(document['items'])] == document['items']
    assert after['title'] == document['title'] and after['sources'] == document['sources']
    assert len(after['items']) == 1+days*4
    host.model_messages('original','plan',capture,[])
    assert delta['version'] in host.system and value['version'] not in host.system
    if ordinal:
        assert after['calendar']=={'state':'undated'} and len(after['days'])==days
        assert all(c['state']=='not_checked' for c in after['date_checks'])
    else:
        assert COMPACT_INITIAL_PLAN not in host.system and LIO_REPLAN_DELTA_V3 not in host.system


@pytest.mark.parametrize('change',[
    lambda v:v.update(owner='forged'),
    lambda v:v.update(proposed_subjects={}),
    lambda v:v['days'].append(deepcopy(v['days'][0])),
    lambda v:v['days'][0][1][0].append({'fixed':False}),
    lambda v:v['days'][0][1][0].__setitem__(0,'hotel'),
    lambda v:v['days'][0][1][0].__setitem__(3,'10:00'),
    lambda v:v['days'][0][1][0].__setitem__(4,['all']),
])
def test_grouped_input_cannot_supply_extra_authority_fixed_override_bad_time_or_party(change):
    host,capture = publisher(5,'en')
    value=reply(5,'en');change(value)
    with pytest.raises(ValueError):host.build_plan(packed(value),capture)


def test_truncated_duplicate_and_legacy_versions_are_not_repaired_or_silently_accepted():
    host,capture=publisher(4,'en');raw=packed(reply(4,'en'))
    for bad in (raw[:-1], b'{"version":1,"version":2}',packed(dict(version=COMPACT_INITIAL_PLAN,title='x',items=[],proposed_subjects={}))):
        with pytest.raises(ValueError):host.build_plan(bad,capture)
    legacy=LioPlanPublisher.__new__(LioPlanPublisher)
    with pytest.raises(FieldRejected):legacy._model_plan(raw,None,capture)


def test_subjects_are_explicit_and_timezone_must_be_confirmed_source_not_default():
    host,capture=publisher(4,'zh',party=3)
    content,candidate,_=host.build_plan(packed(reply(4,'zh',party=3)),capture)
    assert json.loads(candidate.content)['party_size']=={'state':'known','value':3}
    assert all(i['applies_to']==['party'] for i in json.loads(candidate.content)['fixed_items'])
    snapshot,revisions=capture.records();fields=snapshot.fields;fields['destination_timezone']={'state':'unknown'}
    from dataclasses import replace
    capture.records=lambda:(replace(snapshot,content=packed(fields)),revisions)
    with pytest.raises(SourceRejected,match='confirmed source timezone'):
        host.build_plan(packed(reply(4,'zh',party=3)),capture)


@pytest.mark.parametrize('ordinal',[False,True])
def test_five_days_three_periods_and_empty_fixed_items_are_valid_with_explicit_party(ordinal):
    host,capture=publisher(5,'en',ordinal=ordinal,party=3)
    snapshot,revisions=source(5,'en',ordinal=ordinal,party=3,with_fixed=False)
    capture.records=lambda:(snapshot,revisions)
    capture.basis.day_indices=lambda:{}
    value=reply(5,'en',ordinal=ordinal,party=3,periods=3)
    assert len(packed(value)) < 1024
    content,candidate,_=host.build_plan(packed(value),capture)
    document=json.loads(content)
    assert len(document['items'])==15
    assert [i['text'] for i in document['items']]==[r[1] for _,rows in value['days'] for r in rows]
    assert all(i['applies_to']==['party'] for i in json.loads(candidate.content)['fixed_items'])
    assert snapshot.fields['fixed_items']==[] and snapshot.fields['party_size']['value']==3


@pytest.mark.parametrize('ordinal,day',[(False,'not-a-date'),(False,'2026-12-31'),(True,6),(True,True)])
def test_empty_day_groups_cannot_hide_an_invalid_or_out_of_source_day(ordinal,day):
    host,capture=publisher(5,'zh',ordinal=ordinal)
    value=reply(5,'zh',ordinal=ordinal);value['days'].append([day,[]])
    with pytest.raises(ValueError):host.build_plan(packed(value),capture)


def test_current_provider_wire_cap_is_unchanged_and_grouping_removes_repeated_keys():
    class Captured(Exception):pass
    class Ledger:
        def begin(self,attempt,kind,raw):
            self.wire=json.loads(raw)
            raise Captured()
    host,capture=publisher(5,'en');value=reply(5,'en')
    messages=host.model_messages('original','plan five days',capture,[])
    ledger=Ledger()
    provider=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,'offline-only',max_output_tokens=M4_REAL_OUTPUT_TOKENS),ledger)
    stream=provider.invoke(messages,host.system,'offline-grouped-wire',receipt={},guard=lambda:None)
    try:
        with pytest.raises(Captured):next(stream)
    finally:stream.close()
    assert ledger.wire['max_tokens']==1024
    _,items,subjects=expand(packed(value),capture,retained=False,ordinal=False)
    old=packed(dict(version=COMPACT_INITIAL_PLAN,title=value['title'],items=items,proposed_subjects=subjects))
    assert len(packed(value)) < len(old)*.6
    assert len(packed(value)) < 1024 < len(old)
