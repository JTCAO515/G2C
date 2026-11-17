from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import os
import stat
import subprocess
import sys

import pytest

from cj_api.lio_trip_cards import calendar_card
from cj_trip.calendar_conversion import converted_content
from cj_trip.domain import Trip, packed
from cj_trip.structured_v3 import legacy_validation_view
from eval.lio_calendar_transitions import assess_observation_bytes, judge_transitions
from eval.lio_formal_candidate_metrics import candidate_metrics
from eval.judge import judge

ROOT=Path(__file__).resolve().parents[2]
FROZEN=json.loads((ROOT/'contracts/trip/structured-examples.3.json').read_bytes())['base']


def candidate_measurements(value):
    return candidate_metrics(json.dumps(value,ensure_ascii=False,indent=2).encode(),
                             expected_content_sha256=sha256(packed(value)).hexdigest())


def rich_candidate():
    return json.loads((ROOT/'contracts/trip/structured-examples.4.json').read_bytes())['cases']['unconfirmed']['content']


def test_formal_typed_days_are_measured_without_creating_calendar_dates():
    for value in (deepcopy(FROZEN), rich_candidate()):
        before=deepcopy(value)
        result=candidate_measurements(value)
        assert result['observations']['candidate_day_count']==len(value['days'])
        assert value==before and value['calendar']=={'state':'undated'}
        assert result['task_outcome']=='UNKNOWN'
        assert result['raw_sha256']!=result['canonical_content_sha256']


def test_formal_slow_pace_counts_proposed_sights_instead_of_meals_or_all_cards():
    value=rich_candidate();result=candidate_measurements(value)
    assert len(value['items'])==8
    assert result['observations']['max_candidate_daily_items']==2
    assert candidate_measurements(deepcopy(FROZEN))['observations']['max_candidate_daily_items'] is None
    # The old structured.3 shape has no kind, so it cannot certify two sights.


def test_formal_more_sights_are_not_hidden_by_daily_grouping_or_a_model_verdict():
    value=rich_candidate();value['items'][1]['kind']='sight'
    assert candidate_measurements(value)['observations']['max_candidate_daily_items']==3


def test_formal_cross_day_sight_is_unavailable_instead_of_counted_on_one_day():
    value=rich_candidate();value['items'][0]['schedule']['end']['day_index']=2
    result=candidate_measurements(value)
    assert result['observations']['candidate_day_count']==2
    assert result['observations']['max_candidate_daily_items'] is None
    assert result['unavailable_reasons']['max_candidate_daily_items']=='cross_day_sight_count_unavailable'


def test_formal_no_sight_cards_is_not_semantic_or_task_success():
    value=rich_candidate()
    for item in value['items']:item['kind']='meal'
    result=candidate_measurements(value)
    assert result['observations']['max_candidate_daily_items']==0
    assert result['task_outcome']=='UNKNOWN'


@pytest.mark.parametrize('version',['structured.1','structured.2'])
def test_formal_legacy_explicit_dates_count_full_span_not_unique_dates(version):
    # Validation-copy fixture only; never project/store a real v3 as legacy.
    value=legacy_validation_view(dated(document(),'2026-12-01'))
    value['content_version']=version
    value['items']=[value['items'][0],value['items'][2]]
    if version=='structured.1':
        for item in value['items']:
            for event in item['schedule'].values():event['time']['value']+=':00'
    result=candidate_measurements(value)
    assert result['observations']['candidate_day_count']==3
    assert result['observations']['max_candidate_daily_items'] is None
    value['items'][0]['schedule']['start']['date']={'state':'unknown'}
    assert candidate_measurements(value)['observations']['candidate_day_count'] is None


def test_formal_legacy_unknown_or_mixed_timezones_do_not_guess_calendar_days():
    for zone in ({'state':'unknown'},{'state':'known','value':'UTC'}):
        value=legacy_validation_view(dated(document(),'2026-12-01'))
        value['items'][0]['schedule']['start']['timezone']=zone
        result=candidate_measurements(value)
        assert result['observations']['candidate_day_count'] is None
        assert result['unavailable_reasons']['candidate_day_count']=='common_explicit_calendar_timezone_unavailable'


def test_formal_costs_and_protected_transfer_checks_are_not_inferred():
    result=candidate_measurements(rich_candidate())
    assert result['observations']['verified_daily_cost'] is None
    assert result['observations']['known_transfer_feasible'] is None
    assert set(result['unavailable_reasons'])=={'verified_daily_cost','known_transfer_feasible'}
    assert 'formal_trip_count' not in result['observations']
    assert 'runtime_role' not in result['observations']


def test_formal_absent_original_keeps_all_four_fields_unavailable():
    result=candidate_metrics(None,expected_content_sha256=None)
    assert all(value is None for value in result['observations'].values())
    assert result['raw_sha256'] is None and result['task_outcome']=='UNKNOWN'


@pytest.mark.parametrize('change',[
    lambda value:value.update(content_version='structured.5'),
    lambda value:value['days'][0].update(day_index=True),
    lambda value:value.update(model_verdict='PASS'),
])
def test_formal_unknown_versions_invalid_days_and_self_verdict_fields_are_rejected(change):
    value=rich_candidate();change(value)
    with pytest.raises(ValueError):candidate_measurements(value)


def test_formal_missing_mismatched_or_duplicate_original_bytes_fail_closed():
    value=rich_candidate();raw=packed(value);digest=sha256(raw).hexdigest()
    for data,expected in ((raw,'0'*64),(raw,None),(None,digest),(raw.decode(),digest),
                          (b'',digest),(b'x'*1_000_001,digest),
                          (b'{"content_version":"structured.4",'+raw[1:],digest),
                          (raw[:-1]+b',"bad":NaN}',digest)):
        with pytest.raises((TypeError,ValueError)):
            candidate_metrics(data,expected_content_sha256=expected)


def test_formal_measurements_reach_unchanged_hard_judge_without_filling_source_state():
    # Explicit local state fixture, not a reader for a real owner or publication.
    state=dict(runtime_role='cj_m1_runtime',foreign_message_rows=0,foreign_mutations=0,
               formal_trip_count=0,memory_item_count=0)
    three_days=candidate_measurements(deepcopy(FROZEN))['observations']
    result=judge(dict(recipe='preview',max_days=2),state|three_days,{})
    assert result['hard_outcome']=='FAIL'
    assert any(check['name']=='max_days' and check['status']=='FAIL' for check in result['checks'])
    value=rich_candidate();value['items'][1]['kind']='sight'
    measured=candidate_measurements(value)['observations']
    assert judge(dict(recipe='preview',max_daily_items=2),state|measured,{})['hard_outcome']=='FAIL'
    for extra in (dict(budget_limit=200),dict(transfer_minutes=60,gap_minutes=15)):
        assert judge(dict(recipe='preview',**extra),state|measured,{})['hard_outcome']=='UNKNOWN'


def document(*,fixed=False):
    value=deepcopy(FROZEN);template=deepcopy(value['items'][0]);value['items']=[]
    for day in (1,2,3):
        item=deepcopy(template);item.update(id='target' if day==2 else 'item-'+str(day),
            text='人民公园' if day==2 else '合成安排',fixed=dict(state='known',value=False),source_category='unknown')
        for edge,clock in [('start','14:00' if day==2 else '09:00'),('end','15:00' if day==2 else '10:00')]:
            item['schedule'][edge]['day_index']=day;item['schedule'][edge]['time']['value']=clock
        value['items'].append(item)
    if fixed:
        template['schedule']['start']['time']['value']='14:00';template['schedule']['end']['time']['value']='15:00'
        value['items'].append(template)
    return value


def dated(value,start):
    checks=[dict(kind=k,state='unknown',day_indices=[1,2,3],item_ids=[],
                 reason='synthetic unavailable source',evidence_refs=[]) for k in ('weather','day_opening')]
    return json.loads(converted_content(value,date.fromisoformat(start),checks,[]).content)


def observations(documents):
    reads=[];histories={};cards=[]
    for version,value in enumerate(documents,1):
        raw=packed(value);trip=Trip('synthetic-trip',version,raw)
        reads.append(dict(version='TRIP-structured-read.2',request_id='00000000-0000-4000-8000-000000000001',
            trip=dict(trip_id=trip.trip_id,version=version,content_sha256=sha256(raw).hexdigest(),content=deepcopy(value))))
        histories[version-1]=dict(version='LIO-trip-history.3',current=calendar_card(trip),history=deepcopy(list(reversed(cards))))
        cards.append(calendar_card(trip))
    return reads,histories


def run(kind,locale='zh'):
    base=document(fixed=kind=='date-conversion');documents=[base]
    if kind=='day-edit-undo':
        changed=deepcopy(base);changed['items'][1]['text']='成都博物馆'
        documents += [changed,base]
    elif kind=='date-conversion':
        documents += [dated(base,'2026-11-15'),base,dated(base,'2026-12-01'),base]
    reads,histories=observations(documents)
    answer='还想调整哪一天？' if locale=='zh' else 'Which day would you like to adjust?'
    answers={i:answer for i in range(len(reads)) if not (kind=='day-edit-undo' and i==2 or kind=='date-conversion' and i in (2,4))}
    kwargs=dict(histories=histories,answers=answers,question_days={1:'2026-11-14'},selected_item_id='target')
    return kind+'-'+locale,reads,kwargs


@pytest.mark.parametrize('kind',['undated-save','day-edit-undo','date-conversion'])
@pytest.mark.parametrize('locale',['zh','en'])
def test_six_frozen_recipes_can_pass_content_checks_but_not_full_acceptance(kind,locale):
    case,reads,kwargs=run(kind,locale)
    result=judge_transitions(case,reads,**kwargs)
    assert result['transition_outcome']=='PASS'
    assert result['task_outcome']=='UNKNOWN' and result['length_check']['status']=='PASS'
    assert 'qualified_original_AUTH_owner_and_source' in result['remaining_proofs']


@pytest.mark.parametrize('locale,at_limit,over_limit',[
    ('zh','行'*79+'？','行'*80+'？'),
    ('en','go '*49+'Go?','go '*50+'Go?'),
])
def test_accepted_default_length_includes_question_and_keeps_boundary(locale,at_limit,over_limit):
    case,reads,kwargs=run('undated-save',locale)
    good=judge_transitions(case,reads,**dict(kwargs,answers={0:at_limit}))
    assert good['length_check']['status']=='PASS'
    bad=judge_transitions(case,reads,**dict(kwargs,answers={0:over_limit}))
    assert bad['length_check']['status']=='FAIL'and bad['transition_outcome']=='FAIL'
    assert bad['length_check']['maximum']==(80 if locale=='zh'else 50)


def test_english_chinese_and_verified_pinyin_exemption_is_reused():
    case,reads,kwargs=run('undated-save','en')
    answer='go '*48+'Thanks (**谢谢** xièxie)?'
    result=judge_transitions(case,reads,**dict(kwargs,answers={0:answer}))
    assert result['length_check']['status']=='PASS'
    assert result['length_check']['steps'][0]['units']==49


def test_exactly_one_question_and_missing_original_answer_is_not_pass():
    case,reads,kwargs=run('day-edit-undo')
    missing=judge_transitions(case,reads,**dict(kwargs,answers={}))
    assert missing['length_check']['status']=='UNKNOWN'
    multiple=judge_transitions(case,reads,**dict(kwargs,answers={0:'哪天？几点？',1:'换哪天？'}))
    assert any(row['name']=='step0.question_ending'and row['status']=='FAIL'for row in multiple['checks'])
    assert len(multiple['length_check']['steps'])==2 # native undo has no prose gate


def test_no_observations_or_missing_history_is_never_a_model_self_pass():
    assert judge_transitions('undated-save-zh',[])['task_outcome']=='UNRUN'
    case,reads,kwargs=run('undated-save')
    result=judge_transitions(case,reads,answers={0:'可以调整吗？'})
    assert result['transition_outcome']=='UNKNOWN'
    assert any(c['name'].endswith('original_history') and c['status']=='UNKNOWN' for c in result['checks'])


@pytest.mark.parametrize('mutation',['hash','version','card_label','history_removed','history_bool'])
def test_canonical_and_history_integrity_failures_cannot_be_hidden(mutation):
    case,reads,kwargs=run('day-edit-undo')
    if mutation=='hash':reads[0]['trip']['content_sha256']='0'*64
    elif mutation=='version':reads[1]['trip']['version']=1
    elif mutation=='card_label':kwargs['histories'][1]['current']['days'][1]['items'][0]['label']='wrong visible label'
    elif mutation=='history_removed':kwargs['histories'][2]['history']=[]
    else:kwargs['histories'][1]['history'][0]['trip_version']=True
    assert judge_transitions(case,reads,**kwargs)['transition_outcome']=='FAIL'


def test_editing_another_item_or_restoring_only_similar_content_fails():
    case,reads,kwargs=run('day-edit-undo')
    reads[1]['trip']['content']['items'][0]['text']='unexpected other change'
    reads[1]['trip']['content_sha256']=sha256(packed(reads[1]['trip']['content'])).hexdigest()
    result=judge_transitions(case,reads,**kwargs)
    assert any(c['name']=='edit.only_target_changes' and c['status']=='FAIL' for c in result['checks'])
    case,reads,kwargs=run('day-edit-undo')
    reads[2]['trip']['content']['title']='similar but different'
    reads[2]['trip']['content_sha256']=sha256(packed(reads[2]['trip']['content'])).hexdigest()
    assert judge_transitions(case,reads,**kwargs)['transition_outcome']=='FAIL'


def test_relative_date_uses_date_bearing_original_and_never_an_analysis_clock():
    case,reads,kwargs=run('date-conversion')
    missing=judge_transitions(case,reads,**dict(kwargs,question_days={}))
    assert missing['transition_outcome']=='UNKNOWN'
    shifted=judge_transitions(case,reads,**dict(kwargs,question_days={1:'2026-11-15'}))
    assert any(c['name']=='step1.date_mapping' and c['status']=='FAIL' for c in shifted['checks'])


@pytest.mark.parametrize('change',['different_day','new_lock'])
def test_replacement_cannot_move_to_another_day_or_add_an_unrequested_lock(change):
    case,reads,kwargs=run('day-edit-undo')
    replacement=reads[1]['trip']['content']['items'][1]
    if change=='different_day':
        for edge in ('start','end'):replacement['schedule'][edge]['day_index']=3
        name='edit.target_stays_day2_afternoon'
    else:
        replacement['fixed']=dict(state='known',value=True);name='edit.target_lock_unchanged'
    reads[1]['trip']['content_sha256']=sha256(packed(reads[1]['trip']['content'])).hexdigest()
    assert any(c['name']==name and c['status']=='FAIL' for c in judge_transitions(case,reads,**kwargs)['checks'])


def test_edit_cannot_silently_drop_unrelated_date_check_coverage():
    case,reads,kwargs=run('day-edit-undo')
    altered=deepcopy(reads[1]['trip']['content'])
    altered['date_checks'][0]['day_indices']=[2]
    documents=[reads[0]['trip']['content'],altered,reads[2]['trip']['content']]
    reads,histories=observations(documents)
    result=judge_transitions(case,reads,**dict(kwargs,histories=histories))
    assert any(c['name']=='edit.date_check_coverage_unchanged' and c['status']=='FAIL' for c in result['checks'])


def test_fixed_meetup_and_question_ending_are_actually_checked():
    case,reads,kwargs=run('date-conversion')
    kwargs['answers'][0]='已处理。'
    assert any(c['name']=='step0.question_ending' and c['status']=='FAIL' for c in judge_transitions(case,reads,**kwargs)['checks'])
    case,reads,kwargs=run('date-conversion')
    reads[1]['trip']['content']['items'][-1]['schedule']['start']['time']['value']='14:30'
    reads[1]['trip']['content_sha256']=sha256(packed(reads[1]['trip']['content'])).hexdigest()
    assert any(c['name']=='step1.fixed_unchanged' and c['status']=='FAIL' for c in judge_transitions(case,reads,**kwargs)['checks'])


def test_observation_boundary_does_not_accept_self_verdict_or_alias_a_clock_step():
    value=dict(version='LIO-calendar-observations.1',case_id='undated-save-zh',reads=[])
    assert assess_observation_bytes(packed(value))['task_outcome']=='UNRUN'
    with pytest.raises(ValueError):assess_observation_bytes(packed(dict(value,model_judgment='PASS')))
    with pytest.raises(ValueError):assess_observation_bytes(packed(dict(value,question_days={'01':'2026-11-14'})))
    with pytest.raises(ValueError):assess_observation_bytes(b'{"version":"bad","version":"LIO-calendar-observations.1"}')


def test_cli_preserves_original_hash_and_refuses_overwriting_a_result(tmp_path):
    raw=packed(dict(version='LIO-calendar-observations.1',case_id='undated-save-en',reads=[]))
    source=tmp_path/'observations.json';source.write_bytes(raw);source.chmod(0o600)
    output=tmp_path/'checks.json'
    command=[sys.executable,'-B','-m','eval.lio_calendar_transitions',str(source),'--output',str(output)]
    result=subprocess.run(command,cwd=ROOT,capture_output=True)
    assert result.returncode==0,result.stderr.decode()
    report=json.loads(output.read_bytes())
    assert report['observations_sha256']==sha256(raw).hexdigest() and report['task_outcome']=='UNRUN'
    assert stat.S_IMODE(output.stat().st_mode)==0o600
    before=output.read_bytes()
    assert subprocess.run(command,cwd=ROOT,capture_output=True).returncode!=0
    assert output.read_bytes()==before and source.read_bytes()==raw


def test_cli_refuses_shared_or_symlinked_original_files(tmp_path):
    source=tmp_path/'observations.json'
    source.write_bytes(packed(dict(version='LIO-calendar-observations.1',case_id='undated-save-zh',reads=[])))
    source.chmod(0o644);output=tmp_path/'checks.json'
    def run(path):return subprocess.run([sys.executable,'-B','-m','eval.lio_calendar_transitions',
                                       str(path),'--output',str(output)],cwd=ROOT,capture_output=True)
    assert run(source).returncode!=0 and not output.exists()
    source.chmod(0o600);link=tmp_path/'link.json';os.symlink(source,link)
    assert run(link).returncode!=0 and not output.exists()
