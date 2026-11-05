"""Incremental read-only audit, never an admission/dispatch or quota authority.

Keep original verdicts and every attempt. Component classification is separate
from root cause and cannot promote UNKNOWN, FAIL, Fake or old-head evidence.
"""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from fees import usage
from report import effective_observation, outcome, latency, number
from failure import classify

STATUSES=('PASS','FAIL','UNKNOWN','UNRUN')


def _key(row):return (row.get('case_id',row.get('scenario_id')),row['language'],row.get('attempt',1))


def snapshot(stage,plan,rows,directory,formal,starts):
    if stage not in ('smoke','full'):raise ValueError('explicit_stage_required')
    specs=plan['cases'] if stage=='smoke' else plan['scenarios']
    attempts=[1] if stage=='smoke' else plan['attempts']
    expected={(s['id'],language,a) for s in specs for language in ('zh','en') for a in attempts}
    if len({_key(r) for r in rows})!=len(rows) or any(_key(r) not in expected for r in rows):
        raise ValueError('frozen_plan_observation_identity_required_no_best_attempt_selection')
    started={_key(r) for r in starts}
    if len(started)!=len(starts) or not started<=expected or not {_key(r) for r in rows}<=started:
        raise ValueError('original_case_start_identity_required')
    if stage=='full' and (len(plan['candidates'])!=1 or len(plan['networks'])!=1):
        raise ValueError('one_frozen_candidate_network_per_execution_batch')
    gate={_key(r):r['status'] for r in formal['outcomes']} if stage=='smoke' else {}
    audits=[];receipts=[];seen=set();by_language={}
    for row in rows:
        relative=Path(row['raw_evidence_ref']);path=directory/relative
        if relative.is_absolute() or not relative.parts or relative.parts[0]!='raw' or path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError('original_batch_raw_path_required')
        data=path.read_bytes();raw=json.loads(data)
        observed=raw.get('observed') or {};message=observed.get('message_receipt') or {}
        if not message:
            receipts=[h.get('body',{}).get('receipt',{}) for h in raw.get('http',[]) if h.get('status')==200]
            message=next((r for r in reversed(receipts) if all(k in r for k in ('message_id','conversation_id','run_id'))),{})
        verdict=gate[_key(row)] if stage=='smoke' else outcome(effective_observation(row,next(s for s in specs if s['id']==row['scenario_id'])))
        records={r['attempt_id']:r for r in raw.get('authorization_attempts',[])}
        if len(records)!=len(raw.get('authorization_attempts',[])) or seen&set(records):
            raise ValueError('original_authorization_attempts_must_not_be_counted_twice')
        seen.update(records);receipts.extend(records.values())
        manifest=[];registered=set()
        for op in raw.get('operations',[]):
            registered.add(op['attempt_id'])
            r=records.get(op['attempt_id'])
            manifest.append(dict(attempt_id=op['attempt_id'],run_id=op['run_id'],
                registration_id=op['registration_id'],operation_key=op['operation_key'],
                authorization_state='NO_RECORDED_INTENT' if r is None else r['state'],
                kind='UNKNOWN' if r is None else r['kind'],input_sha=None if r is None else r['input_sha'],
                receipt=None if r is None else r.get('receipt')))
        for aid,r in records.items():
            if aid not in registered:manifest.append(dict(attempt_id=aid,run_id=message.get('run_id'),
                registration_id=None,operation_key=None,authorization_state=r['state'],kind=r['kind'],
                input_sha=r['input_sha'],receipt=r.get('receipt'),registration_status='NO_RECORDED_REGISTRATION'))
        first=row.get('first_body_seconds');full=row.get('full_answer_seconds')
        if any(v is not None and not number(v) for v in (first,full)):
            raise ValueError('measured_clock_must_be_finite_nonnegative')
        if first is not None and full is not None and full<first:raise ValueError('same_task_clock_order_required')
        if observed.get('run_status')!='completed' or raw.get('requested_candidate_missing'):full=None
        audits.append(dict(case_id=_key(row)[0],language=row['language'],attempt=_key(row)[2],
            verdict=verdict,run_id=message.get('run_id'),message_id=message.get('message_id'),
            run_status=observed.get('run_status','UNKNOWN'),failure=classify(raw,verdict),
            original_attempts=manifest,raw_evidence_ref=row['raw_evidence_ref'],raw_evidence_sha256=sha256(data).hexdigest(),
            input_sha256=raw.get('input_sha256'),
            first_body_seconds=first,full_answer_seconds=full,
            time_to_terminal_seconds=raw.get('time_to_terminal_seconds'),
            source=scopesource(plan),expected=(dict(run_status='completed',same_RUN_nonempty_body=True,
                tools=next(s['required'] for s in specs if s['id']==_key(row)[0])) if stage=='smoke' else
                dict(original_expected=raw.get('expected'),checks=[dict(name=c['name'],expected=c.get('expected'),actual=c.get('actual'))
                    for c in (raw.get('judgment') or {}).get('checks',[]) if c['status']=='FAIL']))))
    for language in ('zh','en'):
        cells={k for k in expected if k[1]==language};observed=[a for a in audits if a['language']==language]
        done={_key(a) for a in observed};inflight=(started&cells)-done
        counts=Counter(a['verdict'] for a in observed)
        counts['UNKNOWN']+=len(inflight);counts['UNRUN']+=len(cells-done-inflight)
        original_profile=[] if stage=='smoke' else [p for p in formal['quality_acceptance']['profiles'] if p['language']==language]
        by_language[language]=dict(planned_n=len(cells),observed_n=len(observed),
            outcomes={s:counts[s] for s in STATUSES},started_without_result=[list(k) for k in sorted(inflight)],
            execution_status=dict(Counter(a['run_status'] for a in observed)),
            failure_categories=dict(Counter(a['failure']['category'] for a in observed if a['failure'])),
            first_body_seconds=latency(observed+[None]*(len(cells)-len(observed)),'first_body_seconds'),
            full_answer_seconds=latency(observed+[None]*(len(cells)-len(observed)),'full_answer_seconds'),
            timing_scope='known-subset diagnostic; original formal gate retains full denominator',
            original_product_profiles=original_profile,
            serious_errors='UNRUN: prerequisite, not product review' if stage=='smoke' else [p['criteria']['serious_errors'] for p in original_profile],
            usage=usage([r for row in rows if row['language']==language for r in json.loads((directory/row['raw_evidence_ref']).read_bytes()).get('authorization_attempts',[])]))
        by_language[language]['usage_complete']=not bool(inflight)
        by_language[language]['unknown_inflight_usage']='UNKNOWN' if inflight else None
        by_language[language]['attempt_manifest_complete']=not inflight and all(
            a['authorization_state']!='NO_RECORDED_INTENT' and a.get('registration_status') is None
            for r in observed for a in r['original_attempts'])
        by_language[language]['usage_complete']=by_language[language]['attempt_manifest_complete'] and not by_language[language]['usage']['unknown_intents'] and by_language[language]['usage']['token_unknown_model_attempt_n']==0
    fingerprints={name:sha256((directory/name).read_bytes()).hexdigest() if (directory/name).is_file() else None
                  for name in ('plan.json','runtime-config.json','packages.json')}
    return dict(schema_version=1,kind='incremental_audit_not_admission',stage=stage,
        verdict_scope='prerequisite_only_not_product_quality' if stage=='smoke' else 'original_independent_product_verdicts',
        source=scopesource(plan),planned_n=len(expected),observed_n=len(rows),by_language=by_language,
        artifact_fingerprints=fingerprints,
        attempts=audits,usage=usage(receipts),usage_complete=all(g['usage_complete'] for g in by_language.values()),
        attempt_manifest_complete=all(g['attempt_manifest_complete'] for g in by_language.values()),
        unknown_inflight_usage='UNKNOWN' if started-{_key(r) for r in rows} else None,
        authority='Original formal report/checker and canonical phase, not this file',
        original_gate_status=formal['status'] if stage=='smoke' else formal['quality_acceptance']['evaluation_release_decision'])


def scopesource(plan):
    return dict(candidate_id=plan.get('candidate_id') or plan['candidates'][0]['id'],
        evidence_layer=plan.get('evidence_layer','UNKNOWN'),
        execution_source=plan.get('execution_source'),collector_sha256=plan.get('collector_sha256'),
        model=plan.get('model_id') or plan['candidates'][0]['model_version'],
        sample_set_version=plan.get('sample_set_version'),source_date=plan.get('source_date'))


def markdown(data):
    lines=['# Incremental evaluation audit','',
        'Original verdicts and attempts; categories never promote evidence or authorize dispatch. Root causes remain UNKNOWN unless separately proved. Smoke PASS is prerequisite-only, not product quality.',
        '', '| Language | Planned | PASS | FAIL | UNKNOWN | UNRUN | Recorded |', '|---|---|---|---|---|---|---|']
    for language,group in data['by_language'].items():
        lines.append('| '+' | '.join(map(str,[language,group['planned_n'],*[group['outcomes'][s] for s in STATUSES],group['observed_n']]))+' |')
    lines+=['','Actual paid remains UNKNOWN; holds, token estimates and original incomplete windows remain separate. No final reconstruction or best-attempt selection.']
    return '\n'.join(lines)+'\n'


def write(stage,plan,rows,directory,formal,starts):
    value=snapshot(stage,plan,rows,directory,formal,starts)
    for name,text in (('progress.json',json.dumps(value,ensure_ascii=False,indent=2)+'\n'),('progress.md',markdown(value))):
        path=directory/name;temporary=path.with_suffix('.tmp');temporary.write_text(text);temporary.chmod(0o600);temporary.replace(path)
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--batch',type=Path,required=True)
    parser.add_argument('--stage',choices=('smoke','full'),required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();read=lambda name:json.loads((args.batch/name).read_bytes())
    plan=read('plan.json');rows=read('observations.json');formal=read('summary.json' if args.stage=='smoke' else 'report.json')
    starts=read('case-starts.json')
    value=snapshot(args.stage,plan,rows,args.batch,formal,starts)
    args.output.mkdir(parents=True,exist_ok=False);(args.output/'report.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    (args.output/'report.md').write_text(markdown(value))


if __name__=='__main__':main()
