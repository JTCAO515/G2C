"""Six planned synthetic tool-continuation cases; fail stops all new dispatch.

This is prerequisite evidence, not the33-scenario product quality corpus. No
holdout/prompt tuning; all original request IDs and failures remain read-only.
"""
import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from importlib.metadata import version
import io
import json
import os
from pathlib import Path
import re
import subprocess
import time
from zoneinfo import ZoneInfo

from real import (ROOT, STATE, save, keychain, private_database, tcp_app, run_case,
                  original_operations, body_available, LocalDatabase, create_local_app,
                  load_run_context, ConfirmationSigner, RealServices, MeteredDashScopeProvider,
                  DashScopeConfig, M4_BASE, M4_MODEL, AuthorizationBudget, ABI,
                  dev_auth, local_run_context)
from real_budget import estimate


def cases(today):
    forecast_day=(datetime.fromisoformat(today)+timedelta(days=1)).date().isoformat()
    return [dict(id='place-route', required=['place','route'], native=['place_search','place_route'], inputs=dict(
        zh='合成旅行冒烟：先用place_search查询北京故宫、景山公园各1个地点，city北京/page1/page_size1。仅复制实际结果的POI ID、原始GCJ-02坐标和点角色，用place_route查询两点walking路线。根据实际来源说明查询时估计及未知项，不创建或保存行程。',
        en='Synthetic travel smoke: use place_search for Forbidden City and Jingshan Park, Beijing, each page1/page_size1. Copy actual POI IDs, raw GCJ-02 coordinates and point roles into place_route for walking between them. Report query-time estimates, sources and unknowns; no trip write.')),
        dict(id='weather', required=['weather'], native=['weather'], inputs=dict(
            zh=f'合成天气冒烟：调用weather查询北京{forecast_day}，start_date/end_date均为该日期，Asia/Shanghai。按返回来源、报告时点和未知项回答，不重复相同查询，不保存行程。',
            en=f'Synthetic weather smoke: call weather for Beijing with start_date/end_date {forecast_day}, Asia/Shanghai. Answer using actual report time, source and unknowns; do not repeat the same query or write a trip.')),
        dict(id='fact', required=['fact'], native=['fact'], inputs=dict(
            zh=f'合成事实冒烟：调用fact，start_date/end_date为{today}。只根据官方国家移民管理局页面的实际摘录说明来源；旅客资格与日期适用性保持UNKNOWN。不编造、订票或保存行程。',
            en=f'Synthetic fact smoke: call fact with start_date/end_date {today}. Answer only from actual official NIA page excerpts and cite source; traveler eligibility/date applicability stay UNKNOWN. No invented execution, booking or trip write.'))]


def check(case, evidence):
    """Independent actual-state/receipt proof; model self-assessment is irrelevant."""
    observed = evidence.get('observed') or {}
    receipt = observed.get('message_receipt') or {}
    run = receipt.get('run_id')
    mid = receipt.get('message_id')
    reasons = []
    outcomes = evidence.get('outcomes') or []
    if (not run or len(outcomes)!=1 or outcomes[0].get('run_id')!=run
            or outcomes[0].get('message_id')!=mid or outcomes[0].get('status')!='completed'):
        reasons.append('original_RUN_not_completed')
    events = evidence.get('events') or []
    display = events[-1].get('data',{}) if events else {}
    if (display.get('run_id')!=run or display.get('message_id')!=mid
            or display.get('status')!='completed' or display.get('text_state')!='complete'
            or display.get('text')!=evidence.get('answer') or not body_available(evidence.get('answer',''))):
        reasons.append('same_RUN_complete_body_not_delivered')
    for field,expected in dict(runtime_role='cj_m1_runtime',foreign_message_rows=0,
                               foreign_mutations=0,formal_trip_count=0,memory_item_count=0).items():
        if observed.get(field)!=expected:reasons.append(field+'_not_proven')
    records = {v['attempt_id']:v for v in evidence.get('authorization_attempts',[])}
    covered=set();tool_rounds=[];model_rounds=[]
    for op in evidence.get('operations',[]):
        record=records.get(op['attempt_id'],{})
        detail=record.get('receipt') or {}
        if op['run_id']!=run or record.get('state')!='RECEIVED':
            reasons.append('original_operation_receipt_incomplete');continue
        if op['registration_id']=='model.tool_turn':
            match=re.fullmatch(r'model\.tool_turn\.([0-7])',op['operation_key'])
            if (match is None or (detail.get('model_id'),detail.get('endpoint'),detail.get('region'))!=(M4_MODEL,M4_BASE,'cn-beijing')
                    or not isinstance(detail.get('usage'),dict)
                    or re.fullmatch('[0-9a-f]{64}',detail.get('receipt_sha256','')) is None):
                reasons.append('Beijing_model_receipt_not_proven')
            else:model_rounds.append(int(match[1]))
        elif op['registration_id'].startswith('tool.'):
            kind=record.get('kind');match=re.fullmatch(r'tool\.([0-7])\.([0-9]+)',op['operation_key'])
            # FACT applicability remains UNKNOWN by design even after a valid
            # page fetch. That is distinct from an unreceipted fetch/RUN failure.
            expected='ok' if kind in ('place','route') else 'unknown' if kind=='fact' else 'observed'
            endpoints=dict(place='https://restapi.amap.com/v3/place/text',
                route='https://restapi.amap.com/v3/direction/walking',
                weather='https://restapi.amap.com/v3/weather/weatherInfo',fact='https://en.nia.gov.cn/')
            registration='tool.'+('place' if kind in ('place','route') else str(kind))
            if (kind not in case['required'] or op['registration_id']!=registration or detail.get('result_status')!=expected or match is None
                    or detail.get('endpoint')!=endpoints.get(kind)):
                reasons.append('required_tool_success_not_proven')
            else:covered.add(kind);tool_rounds.append(int(match[1]))
        else:reasons.append('unexpected_original_registration')
    if not set(case['required'])<=covered:reasons.append('required_tool_kind_missing')
    if not model_rounds or not tool_rounds or max(model_rounds)<=max(tool_rounds):
        reasons.append('complete_model_continuation_after_tool_missing')
    if 'fact' in case['required']:
        excerpts=[]
        for op in evidence.get('operations',[]):
            if op['registration_id']=='model.tool_turn':
                for message in op['input']['messages']:
                    if message['role']=='tool':
                        value=json.loads(message['content'])
                        if value.get('tool')=='fact':excerpts.append(value['result'])
        if not any(v.get('source_url')=='https://en.nia.gov.cn/' and v.get('excerpts')
                   and v.get('original_bytes',0)>0 and re.fullmatch('[0-9a-f]{64}',v.get('original_sha256',''))
                   for v in excerpts):reasons.append('official_page_excerpt_not_proven')
    return dict(status='FAIL' if reasons else 'PASS',reasons=sorted(set(reasons)),
                covered=sorted(covered),required=case['required'],run_id=run,message_id=mid,
                kind='program',independent=True,ref='eval/smoke.py:check')


def summarize(plan, rows, directory):
    expected={(c['id'],l) for c in cases(plan['source_date']) for l in ('zh','en')}
    identities=[(r['case_id'],r['language']) for r in rows]
    if (plan['cases']!=cases(plan['source_date']) or plan['planned_n']!=6
            or len(set(identities))!=len(identities) or not set(identities)<=expected):
        raise ValueError('fixed_three_paired_four_tool_smoke_cases_required')
    outcomes=[]
    seen_runs=set();seen_attempts=set()
    for case in plan['cases']:
        for language in ('zh','en'):
            row=next((v for v in rows if v['case_id']==case['id'] and v['language']==language),None)
            if row is None:
                outcomes.append(dict(case_id=case['id'],language=language,status='UNRUN'))
            else:
                raw=(directory/row['raw_evidence_ref']).read_bytes()
                evidence=json.loads(raw)
                proof=check(case,evidence)
                prompt=case['inputs'][language]
                first_inputs=[op['input']['messages'] for op in evidence.get('operations',[])
                              if op['operation_key']=='model.tool_turn.0']
                if (evidence['input_sha256']!=sha256(prompt.encode()).hexdigest()
                        or not any(m['role']=='user' and m['content']==prompt for values in first_inputs for m in values)):
                    proof['reasons'].append('frozen_language_input_not_proven')
                actual_ids=[a['attempt_id'] for a in evidence.get('authorization_attempts',[])]
                if proof['run_id'] in seen_runs or len(actual_ids)!=len(set(actual_ids)) or seen_attempts.intersection(actual_ids):
                    proof['reasons'].append('original_RUN_or_attempt_reused_across_smoke_cases')
                seen_runs.add(proof['run_id']);seen_attempts.update(actual_ids)
                if proof['reasons']:proof['status']='FAIL'
                outcomes.append(dict(case_id=case['id'],language=language,raw_evidence_ref=row['raw_evidence_ref'],
                    raw_evidence_sha256=sha256(raw).hexdigest(),**proof))
    status='FAIL' if any(v['status']=='FAIL' for v in outcomes) else 'PASS' if all(v['status']=='PASS' for v in outcomes) else 'UNRUN'
    return dict(candidate_id=plan['candidate_id'],batch_id=plan['batch_id'],status=status,
                planned_n=6,executed_n=len(rows),outcomes=outcomes,
                full66_authorized_to_start=status=='PASS',product_quality_verdict='UNRUN: prerequisite tool smoke only')


def require_full_ready(path, candidate):
    if path is None:raise ValueError('six_case_smoke_evidence_required_before_full_dispatch')
    plan=json.loads((path/'plan.json').read_bytes());rows=json.loads((path/'observations.json').read_bytes())
    if (plan['cases']!=cases(plan['source_date']) or plan['planned_n']!=6
            or {(v['case_id'],v['language']) for v in rows}!={(c['id'],l) for c in plan['cases'] for l in ('zh','en')}):
        raise ValueError('fixed_three_paired_four_tool_smoke_cases_required')
    summary=summarize(plan,rows,path)
    if summary['candidate_id']!=candidate or summary['status']!='PASS' or len(rows)!=6:
        raise ValueError('same_candidate_all_six_tool_smokes_must_PASS_before_full_dispatch')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        print('READ_ONLY: original smoke retained; no request/retry');return 0
    if os.environ.get('CJ_M4_SYNTHETIC_ONLY')!='1':parser.error('explicit M4 synthetic-only activation required')
    candidate=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    budget=AuthorizationBudget(STATE);budget.check_date();before=budget.inspect()
    forecast=estimate(before,include_smoke=True)
    if not forecast['within_stop_lines']:raise ValueError('smoke_plus_full_estimate_exceeds_stop_line_report_495')
    today=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    plan=dict(candidate_id=candidate,batch_id='round2-smoke',cases=cases(today),source_date=today,created_at=datetime.now(timezone.utc).isoformat(),
              model_id=M4_MODEL,endpoint=M4_BASE,collector_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
              authorization='PR540 M4 items3/4; synthetic only; no old action replay',planned_n=6)
    args.output.mkdir(parents=True,mode=0o700);(args.output/'raw').mkdir(mode=0o700)
    save(args.output/'plan.json',plan);save(args.output/'budget-before.json',before)
    save(args.output/'estimate.json',forecast)
    save(args.output/'packages.json',{k:version(k) for k in ('httpx','psycopg','uvicorn','fastapi')})
    model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,keychain('g2c-dashscope'),max_output_tokens=1024),budget)
    subjects=frozenset('m4-synthetic-r2-smoke-'+c['id']+'-'+l for c in plan['cases'] for l in ('zh','en'))
    services=RealServices(model,keychain('g2c-amap-web-key'),subjects);rows=[]
    with redirect_stdout(io.StringIO()),private_database('real-r2-smoke') as conninfo:
        auth=conninfo.parent/'auth';dev_auth.init(auth,sorted(subjects));now=int(time.time())
        profile=conninfo.parent/'run.json'
        save(profile,dict(version='CJ-LOCAL-RUN@2',history=[],current=dict(meter=dict(unit='provider_call',budget=100,
            period_start=now-60,period_end=now+7200,max_steps=24,max_tools=12,max_output=65536,max_seconds=600),
            output_limits=dict(model=12000,tool=48000,memory=2000))))
        context=load_run_context(profile)
        for subject in subjects:
            local_run_context.provision_budget(conninfo,context,subject);dev_auth.activate_travel(conninfo,subject,context,ABI)
        database=LocalDatabase(conninfo,run_context=context,travel_context=True,needs_context=True)
        app=create_local_app(conninfo_path=conninfo,auth_dir=auth,run_context=context,travel_context=True,
            needs_profile='manual-v1',confirmation_signer=ConfirmationSigner((auth/'trip-confirmation.key').read_bytes()))
        with tcp_app(app) as client:
            for case in plan['cases']:
                for language in ('zh','en'):
                    subject='m4-synthetic-r2-smoke-'+case['id']+'-'+language
                    scenario=dict(case,id='smoke-'+case['id'],recipe='answer')
                    evidence=dict(input_sha256=sha256(case['inputs'][language].encode()).hexdigest())
                    row=dict(case_id=case['id'],language=language,raw_evidence_ref='raw/'+case['id']+'-'+language+'.json',
                             first_body_seconds=None,full_answer_seconds=None)
                    try:
                        observed,expected,first,full=run_case(client,database,conninfo,auth,context,services,scenario,language,
                            subject,evidence,allowed_native=frozenset(case['native']))
                        evidence.update(observed=observed,expected=expected)
                        row.update(first_body_seconds=first,full_answer_seconds=full)
                    except Exception as error:evidence['error_kind']=type(error).__name__
                    evidence['operations']=original_operations(database,subject)
                    identities={v['attempt_id'] for v in evidence['operations']}
                    evidence['authorization_attempts']=[v for v in budget.inspect() if v['attempt_id'] in identities]
                    save(args.output/row['raw_evidence_ref'],evidence);rows.append(row)
                    save(args.output/'observations.json',rows);save(args.output/'budget-after.json',budget.inspect())
                    summary=summarize(plan,rows,args.output);save(args.output/'summary.json',summary)
                    verdict=summary['outcomes'][len(rows)-1]['status']
                    os.write(1,(case['id']+' '+language+' '+verdict+'\n').encode())
                    if verdict!='PASS':return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
