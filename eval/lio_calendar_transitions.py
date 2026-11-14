"""Deterministic #864 transitions over original native3 read/history responses.

This is not an evidence issuer. Callers must acquire observations through the
qualified original readers. Passing content checks cannot certify AUTH, source,
Memory, prose semantics, fees or a real-service run.
"""
from dataclasses import dataclass
from datetime import date, time, timedelta
from hashlib import sha256
import json
from pathlib import Path
import argparse
import os
import stat

from cj_strict_json import reject_duplicates

from cj_trip.domain import identifier, packed
from cj_trip.structured_v3 import validate_document

HERE = Path(__file__).resolve().parent
CASES = json.loads((HERE/'lio_calendar_cases.v1.json').read_bytes())


@dataclass(frozen=True)
class Snapshot:
    trip_id: str
    version: int
    document: dict
    raw: bytes
    digest: str


def _snapshot(value):
    if (type(value) is not dict or set(value) != {'version','request_id','trip'}
            or value['version'] != 'TRIP-structured-read.2'):
        raise ValueError('original native3 structured read.2 response required')
    trip=value['trip']
    if type(trip) is not dict or set(trip) != {'trip_id','version','content_sha256','content'}:
        raise ValueError('formal Trip and original content required')
    identifier(trip['trip_id'])
    if type(trip['version']) is not int or trip['version'] < 1:
        raise ValueError('positive native formal version required')
    validate_document(trip['content'])
    raw=packed(trip['content']);digest=sha256(raw).hexdigest()
    if trip['content_sha256'] != digest:
        raise ValueError('original canonical content hash differs')
    return Snapshot(trip['trip_id'],trip['version'],trip['content'],raw,digest)


def _card_matches(card,snapshot):
    days=[dict(day,items=[]) for day in snapshot.document['days']]
    for item in snapshot.document['items']:
        start,end=item['schedule']['start'],item['schedule']['end']
        days[start['day_index']-1]['items'].append(dict(item_id=item['id'],label=item['text'],
            start_time=start['time'].get('value'),end_time=end['time'].get('value'),fixed=item['fixed'].get('value')))
    expected=dict(version='LIO-trip-card.2',trip_id=snapshot.trip_id,trip_version=snapshot.version,
        content_version='structured.3',content_sha256=snapshot.digest,title=snapshot.document['title'],
        calendar=snapshot.document['calendar'],days=days,date_checks=snapshot.document['date_checks'])
    return packed(card)==packed(expected)


def _day2_afternoon(item):
    start,end=(item['schedule'][edge] for edge in ('start','end'))
    return (start['day_index']==end['day_index']==2 and start['time']['state']==end['time']['state']=='known'
            and time(12)<=time.fromisoformat(start['time']['value'])<time.fromisoformat(end['time']['value'])<=time(18))


def judge_transitions(case_id, reads, *, histories=None, answers=None,
                      question_days=None, selected_item_id=None):
    """Assess frozen recipes; missing evidence remains UNKNOWN/UNRUN.

    reads/histories are per-step original HTTP responses. question_days maps a
    date-bearing message step index to its protected native question_day, never
    a local/analysis clock. The function does not authenticate that provenance.
    answers contains actual MESSAGE answers only; native undo has no prose gate.
    """
    case=next(c for c in CASES['cases'] if c['id']==case_id)
    checks=[];snapshots=[]
    histories={} if histories is None else histories
    answers={} if answers is None else answers
    question_days={} if question_days is None else question_days
    def check(name,condition):
        checks.append(dict(name=name,status='UNKNOWN' if condition is None else 'PASS' if condition else 'FAIL'))
    check('trace.no_extra_steps',len(reads)<=len(case['steps']))
    for index,step in enumerate(case['steps']):
        value=reads[index] if index<len(reads) else None
        if value is None:
            snapshots.append(None);check(f'step{index}.canonical_read',None);continue
        try:snapshot=_snapshot(value)
        except (KeyError,TypeError,ValueError):
            snapshots.append(None);check(f'step{index}.canonical_read',False);continue
        snapshots.append(snapshot)
        check(f'step{index}.canonical_read',True)
        check(f'step{index}.append_version',snapshot.version==index+1)
        check(f'step{index}.three_explicit_days',len(snapshot.document['days'])==3)
        if step['kind']!='native-undo':
            answer=answers.get(index)
            check(f'step{index}.question_ending',None if answer is None else
                  type(answer) is str and bool(answer.strip()) and answer.rstrip().endswith(('?','？')))
        history=histories.get(index)
        if history is None:
            check(f'step{index}.original_history',None)
        else:
            try:
                cards=history['history'];current=history['current']
                valid=(history['version']=='LIO-trip-history.3' and _card_matches(current,snapshot)
                    and len(cards)==index and all(type(c['trip_version']) is int for c in cards)
                    and {c['trip_version'] for c in cards}==set(range(1,index+1)))
                if valid:
                    for card in cards:
                        previous=snapshots[card['trip_version']-1]
                        if previous is None:valid=None;break
                        valid=valid and _card_matches(card,previous)
                check(f'step{index}.original_history',valid)
            except (KeyError,TypeError,IndexError):check(f'step{index}.original_history',False)
    base=snapshots[0]
    if base is not None:
        check('initial.undated',base.document['calendar']=={'state':'undated'})
        check('initial.date_checks_not_fabricated',all(c['state']=='not_checked' and
              c['reason']=='date_not_set' and not c['evidence_refs'] for c in base.document['date_checks']))
        for index,current in enumerate(snapshots[1:],1):
            if current is None:continue
            check(f'step{index}.same_trip',current.trip_id==base.trip_id)
            fixed={i['id']:i for i in base.document['items'] if i['fixed']=={'state':'known','value':True}}
            items={i['id']:i for i in current.document['items']}
            check(f'step{index}.fixed_unchanged',all(items.get(key)==item for key,item in fixed.items()))
        if case_id.startswith('day-edit-undo'):
            changed=snapshots[1]
            if changed is not None:
                before=base.document;after=changed.document
                target=next((i for i in before['items'] if i['id']==selected_item_id),None)
                eligible=None if selected_item_id is None else (target is not None and
                    target['fixed']=={'state':'known','value':False} and _day2_afternoon(target))
                check('edit.actual_unlocked_day2_target',eligible)
                if target is not None:
                    order=[i['id'] for i in before['items']]
                    check('edit.same_item_set_order',[i['id'] for i in after['items']]==order)
                    by_id={i['id']:i for i in after['items']}
                    check('edit.only_target_changes',all(by_id.get(i['id'])==i for i in before['items'] if i['id']!=selected_item_id))
                    replacement=by_id.get(selected_item_id)
                    check('edit.target_label_changes',replacement is not None and replacement['text']!=target['text'])
                    check('edit.target_stays_day2_afternoon',replacement is not None and _day2_afternoon(replacement))
                    check('edit.target_lock_unchanged',replacement is not None and replacement['fixed']==target['fixed'])
                    check('edit.same_calendar_days_title',all(before[k]==after[k] for k in ('calendar','days','title')))
                    refs={ref for i in before['items'] if i['id']!=selected_item_id for ref in i['source_refs']}
                    old_sources={s['id']:s for s in before['sources']};new_sources={s['id']:s for s in after['sources']}
                    check('edit.other_sources_unchanged',all(new_sources.get(ref)==old_sources[ref] for ref in refs))
            if snapshots[2] is not None:check('undo.exact_original_bytes',snapshots[2].raw==base.raw)
        elif case_id.startswith('date-conversion'):
            fixed=[i for i in base.document['items'] if i['fixed']=={'state':'known','value':True}]
            correct=len(fixed)==1
            if correct:
                start,end=(fixed[0]['schedule'][edge] for edge in ('start','end'))
                correct=(start['day_index']==end['day_index']==1 and start['time']['state']==end['time']['state']=='known'
                    and time.fromisoformat(start['time']['value'])==time(14) and time.fromisoformat(end['time']['value'])==time(15))
            check('initial.fixed_meetup_present',correct)
            for index in (1,3):
                current=snapshots[index]
                if current is None:continue
                expected=date(2026,12,1)
                if index==1:
                    original_day=question_days.get(index)
                    if original_day is None:
                        check('relative.original_question_day',None);expected=None
                    else:
                        try:
                            parsed=date.fromisoformat(original_day)
                            if parsed.isoformat()!=original_day:raise ValueError('canonical native date required')
                            expected=parsed+timedelta(days=1)
                            check('relative.original_question_day',True)
                        except (TypeError,ValueError,OverflowError):
                            check('relative.original_question_day',False);expected=None
                if expected is not None:
                    wanted=[(expected+timedelta(days=n)).isoformat() for n in range(3)]
                    check(f'step{index}.date_mapping',current.document['calendar']==dict(state='dated',start_date=wanted[0])
                          and [d['date'] for d in current.document['days']]==wanted)
                check(f'step{index}.only_date_fields_change',all(current.document[k]==base.document[k]
                      for k in base.document if k not in ('calendar','days','date_checks')))
                check(f'step{index}.date_checks_recomputed',all(c['state']!='not_checked' for c in current.document['date_checks']))
            for index in (2,4):
                if snapshots[index] is not None:check(f'step{index}.undo_exact_undated_bytes',snapshots[index].raw==base.raw)
    failures=[c for c in checks if c['status']=='FAIL']
    transition='FAIL' if failures else 'UNRUN' if not reads else 'UNKNOWN' if any(c['status']=='UNKNOWN' for c in checks) else 'PASS'
    remaining=['qualified_original_AUTH_owner_and_source','no_silent_memory_write',
               'answer_date_party_booking_source_semantics','undo_zero_model_dispatch',
               'timings_and_original_three_column_fees']
    return dict(version='LIO-calendar-transition-checks.1',case_id=case_id,independent=True,
        transition_outcome=transition,task_outcome='FAIL' if failures else 'UNRUN' if not reads else 'UNKNOWN',
        checks=checks,length_check=dict(status='UNRUN',reference=CASES['length_gate']['reference']),
        remaining_proofs=remaining,
        note='Content assertions only; passing transitions is not real/native acceptance or a complete #864 PASS.')


def assess_observation_bytes(raw):
    """Strict local observation format; model verdict fields are not accepted."""
    if type(raw) is not bytes or not 0<len(raw)<=8_000_000:
        raise ValueError('bounded original observation bytes required')
    value=json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate observation field'))
    allowed={'version','case_id','reads','histories','answers','question_days','selected_item_id'}
    if (type(value) is not dict or not {'version','case_id','reads'}<=value.keys()
            or not value.keys()<=allowed or value['version']!='LIO-calendar-observations.1'
            or type(value['case_id']) is not str or value['case_id'] not in {c['id'] for c in CASES['cases']}
            or type(value['reads']) is not list):
        raise ValueError('declared frozen case and original observation arrays required')
    kwargs={}
    for field in ('histories','answers','question_days'):
        entries=value.get(field,{})
        if type(entries) is not dict or any(key not in ('0','1','2','3','4') for key in entries):
            raise ValueError('canonical message-step index required')
        kwargs[field]={int(key):entry for key,entry in entries.items()}
    if 'selected_item_id' in value:kwargs['selected_item_id']=value['selected_item_id']
    return judge_transitions(value['case_id'],value['reads'],**kwargs)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('observations',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    fd=os.open(args.observations,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid()
                or stat.S_IMODE(info.st_mode)!=0o600):
            raise ValueError('owned 0600 original observations required')
        raw=stream.read(8_000_001)
    result=assess_observation_bytes(raw)
    result['observations_sha256']=sha256(raw).hexdigest()
    fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(packed(result)+b'\n');stream.flush();os.fsync(stream.fileno())
    print(json.dumps({key:result[key] for key in ('case_id','transition_outcome','task_outcome')}))


if __name__=='__main__':main()
