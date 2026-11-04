"""One bounded synthetic L2 batch through signed API/RUN/USAGE, never a spike exit.

Existing batch is read-only, even if interrupted. No --root, arbitrary prompts,
endpoint, model, transport or identity override. Secrets stay in process memory.
"""
import argparse
from contextlib import redirect_stdout
from datetime import datetime,timezone
import fcntl
import hashlib
from importlib.metadata import version
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from cj_agent.provider import DashScopeConfig,MeteredDashScopeProvider,M4_BASE,M4_MODEL
from cj_api.real_services import RealServices,RealTools
from cj_api.local_app import LocalDatabase,app_from_environment,scope_for,ISSUER
from cj_api.local_run_context import load_run_context
from cj_usage.authorization_budget import AuthorizationBudget
import dev_auth,local_run_context,migrate,pg_suites,run_worker

STATE=Path.home()/'.local/share/g2c/m4-real-services'


def verification_passed(batch,attempts):
    """Transport receipts + original operations + readable product result.

    A model-only answer, a different tool, an incomplete follow-up or a failed
    anti-redispatch check is not evidence that native continuation worked.
    """
    required={'place-zh':('tool.place','https://restapi.amap.com/v3/place/text'),
              'weather-en':('tool.weather','https://restapi.amap.com/v3/weather/weatherInfo')}
    if batch.get('state')!='COMPLETE' or set(batch.get('cases',{}))!=set(required):return False
    receipts={item['attempt_id']:item for item in attempts}
    for name,(registration,endpoint) in required.items():
        case=batch['cases'][name];display=case.get('display',{})
        if (case.get('state')!='completed' or display.get('run_id')!=case.get('run_id')
                or display.get('message_id')!=case.get('message_id') or display.get('status')!='completed'
                or display.get('text_state')!='complete' or type(display.get('answer_chars')) is not int or display['answer_chars']<1):return False
        tools=[];models=[]
        for operation in case.get('operations',[]):
            if operation.get('run_id')!=case['run_id']:return False
            record=receipts.get(operation['attempt_id'],{})
            if record.get('state')!='RECEIVED' or type(record.get('receipt')) is not dict:return False
            if operation['registration_id'].startswith('tool.'):
                if operation['registration_id']!=registration or record['receipt'].get('endpoint')!=endpoint:return False
                expected='ok' if name=='place-zh' else 'observed'
                if record['receipt'].get('result_status')!=expected:return False
                key=re.fullmatch(r'tool\.([0-7])\.([0-9]+)',operation['operation_key'])
                if key is None:return False
                tools.append(int(key[1]))
            elif operation['registration_id']=='model.tool_turn':
                r=record['receipt'];key=re.fullmatch(r'model\.tool_turn\.([0-7])',operation['operation_key'])
                if key is None or (r.get('model_id'),r.get('endpoint'),r.get('region'))!=(M4_MODEL,M4_BASE,'cn-beijing') or type(r.get('usage')) is not dict:return False
                models.append(int(key[1]))
            else:return False
        if not tools or not models or max(models)<=max(tools):return False
    return True


def keychain(name):
    r=subprocess.run(['security','find-generic-password','-s',name,'-w',str(Path.home()/'Library/Keychains/login.keychain-db')],capture_output=True,text=True,timeout=10)
    if r.returncode or not r.stdout.strip():raise ValueError('required_M4_keychain_item_unavailable')
    return r.stdout.strip()


def save(path,value):
    temp=path.with_suffix('.tmp')
    with temp.open('w') as out:
        os.chmod(temp,0o600);json.dump(value,out);out.flush();os.fsync(out.fileno())
    temp.replace(path)


def run_batch(*,resume_setup=False,verification=False):
    STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (STATE/'acceptance.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        path=STATE/('verification-native-1.json' if verification else 'acceptance.json')
        budget=AuthorizationBudget(STATE);budget.check_date()
        previous=None
        if path.exists():
            previous=json.loads(path.read_text())
            if not resume_setup:return dict(mode='READ_ONLY',batch=previous,new_sends=0)
            # Operator-only setup recovery: prove that no Meter attempt, private
            # cluster or accepted message ever existed. Never resumes a sent or
            # uncertain external request, nor invents replacement RUN identities.
            if (budget.inspect() or (STATE/'acceptance-pg').exists()
                    or any(c!={'state':'PLANNED'} for c in previous['cases'].values())):
                raise ValueError('original_batch_requires_read_only_reconciliation')
        today=datetime.now(timezone.utc).date().isoformat()
        cases={
            'place-zh':'这是合成旅行查询。请实际调用place查询北京故宫一个地点（Search city北京,page1,page_size1），只报来源资料和未知项，不创建行程。',
            'place-en':'Synthetic travel query. Actually call place Search for Forbidden City in Beijing, page 1, page_size 1; report source and unknowns, no itinerary write.',
            'route-zh':'合成旅行查询：先用place查询北京故宫和景山公园，各page1/page_size1。仅用返回的POI ID和GCJ-02坐标调用walking RouteQuery，departure condition at_query_time/at null；返回原查询时估计，不创建行程。',
            'route-en':'Synthetic query: use place Search for Forbidden City and Jingshan Park, Beijing, each page1/page_size1; use returned POI IDs and GCJ-02 coordinates for walking RouteQuery at_query_time, at null. Report query-time estimate; no itinerary write.',
            'weather-zh':f'合成旅行查询：请调用weather，FACT-query.1，fact_key weather，region beijing，dates start/end {today}，conditions calendar_timezone Asia/Shanghai。说明预报时间与未知项，不创建行程。',
            'weather-en':f'Synthetic query: call weather with FACT-query.1, fact_key weather, region beijing, dates start/end {today}, conditions calendar_timezone Asia/Shanghai. Report provider time and unknowns; no itinerary write.',
            'fact-zh':f'合成查询：调用fact，FACT-query.1，fact_key entry_notice，region China，dates start/end {today}，conditions空对象。只引述官方国家移民管理局页面，不推断任何旅客资格或适用日期，不创建行程。',
            'fact-en':f'Synthetic query: call fact using FACT-query.1, fact_key entry_notice, region China, dates start/end {today}, conditions empty object. Quote official NIA page only; eligibility and date applicability UNKNOWN. No itinerary write.',
        }
        if verification:
            cases={
                'place-zh':'合成旅行验证：使用place_search实际查询北京故宫，city北京，page1/page_size1。根据工具结果说明来源和待核实项，不写行程。',
                'weather-en':f'Synthetic verification: use weather for Beijing, start_date and end_date {today}. Then answer using the returned report time, source and unknowns. Do not repeat an identical weather request. No itinerary write.',
            }
        value=dict(state='INTENT',model_id=M4_MODEL,endpoint=M4_BASE,region='cn-beijing',
            packages={k:version(k) for k in ('httpx','psycopg','fastapi','pydantic')},cases={k:dict(state='PLANNED') for k in cases})
        if previous is not None:value['setup_recovery']='explicit_login_keychain_after_proven_zero_dispatch'
        save(path,value)  # Lost setup is conservative: inspect this original batch.
        root=STATE/('verification-native-1-pg' if verification else 'acceptance-pg')
        if root.exists():raise ValueError('original_private_acceptance_cluster_exists')
        model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,keychain('g2c-dashscope')),budget)
        subject='m4-synthetic-real-services-verify1' if verification else 'm4-synthetic-real-services'
        services=RealServices(model,keychain('g2c-amap-web-key'),frozenset({subject}));tools=RealTools(services)
        output=io.StringIO()
        try:
            with patch.dict(os.environ,pg_suites.clean_env(),clear=True),redirect_stdout(output):
                with pg_suites.cluster('m4-real',port=55880,role='cj_m4_real_init',root=root) as config:
                    with psycopg.connect(**config,autocommit=True) as conn:migrate.up(conn,migrate.load(),48)
                    auth=root/'auth';dev_auth.init(auth,[subject])
                    conninfo=root/'conn.json';conninfo.write_text(json.dumps(config));conninfo.chmod(0o600)
                    now=int(time.time());context_path=root/'run.json'
                    context_path.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(
                        unit='provider_call',budget=80,period_start=now-60,period_end=now+3600,max_steps=24,max_tools=12,
                        max_output=65536,max_seconds=600),output_limits=dict(model=12000,tool=48000,memory=1000)),history=[])))
                    context=load_run_context(context_path);local_run_context.provision_budget(conninfo,context,subject)
                    db=LocalDatabase(conninfo,run_context=context)
                    with patch.dict(os.environ,dict(CJ_LOCAL_AUTH_DIR=str(auth),CJ_LOCAL_CONNINFO=str(conninfo),CJ_LOCAL_RUN_CONTEXT=str(context_path))):
                        app=app_from_environment()
                    headers=dict(Authorization='Bearer '+dev_auth.token(auth,subject,30))
                    with TestClient(app) as client:
                        for case,prompt in cases.items():
                            cid='m4-'+case
                            opened=client.put('/v1/conversations',params=dict(conversation_id=cid),headers=headers)
                            if opened.status_code!=200:raise ValueError('synthetic_API_conversation_unavailable')
                            sent=client.post('/v1/messages',headers={**headers,'Content-Type':'application/octet-stream'},content=json.dumps(dict(
                                version='MESSAGE-send.1',conversation_id=cid,message_id=cid,text=prompt,trip_id=None,creation_intent='none',
                                expected_generation=opened.json()['generation'],expected_sequence=0)).encode())
                            if sent.status_code!=200:raise ValueError('synthetic_API_message_unavailable')
                            receipt=sent.json()['receipt'];value['cases'][case]=dict(state='ACCEPTED',run_id=receipt['run_id'],message_id=cid);save(path,value)
                            outcomes=run_worker.run_once(db,model,auth,tools_configuration=tools,real_services=services)
                            if len(outcomes)!=1:raise ValueError('original_RUN_outcome_unavailable')
                            value['cases'][case]['state']=outcomes[0].status
                            with db.connect(scope_for(ISSUER,subject)) as conn:
                                operations=conn.execute('SELECT run_id,operation_key,registration_id,attempt_id FROM cj_run_metered_operation WHERE run_id=%s ORDER BY operation_key',(receipt['run_id'],)).fetchall()
                            value['cases'][case]['operations']=[dict(run_id=r,operation_key=k,registration_id=i,attempt_id=a) for r,k,i,a in operations]
                            displayed=client.get('/v1/run-display',params=dict(message_id=cid),headers=headers)
                            if displayed.status_code==200:
                                snapshot=displayed.json()['snapshot'];text=snapshot['text']
                                answer='\n'.join(line for line in text.splitlines() if not line.startswith(('Source:','来源：'))).strip()
                                value['cases'][case]['display']=dict(run_id=snapshot['run_id'],message_id=snapshot['message_id'],
                                    status=snapshot['status'],text_state=snapshot['text_state'],answer_chars=len(answer),
                                    text_sha256=hashlib.sha256(text.encode()).hexdigest())
                            before=model.calls
                            if run_worker.run_once(db,model,auth,tools_configuration=tools,real_services=services) or model.calls!=before:
                                raise ValueError('original_RUN_redispatched')
                            save(path,value)
            value['state']='COMPLETE'
        except BaseException:
            value['state']='UNKNOWN_INTERRUPTED';save(path,value)
            raise
        save(path,value)
        return dict(mode='EXECUTED',batch=value,attempts=budget.inspect(),actual_total_cost_cny='UNKNOWN')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('run','inspect','resume-setup','verify-native'));args=parser.parse_args()
    if args.command=='inspect':
        path=STATE/'acceptance.json'
        result=dict(batch=None if not path.exists() else json.loads(path.read_text()),attempts=AuthorizationBudget(STATE).inspect())
    else:result=run_batch(resume_setup=args.command=='resume-setup',verification=args.command=='verify-native')
    print(json.dumps(result,ensure_ascii=False,separators=(',',':')))
    if args.command=='verify-native' and not verification_passed(result['batch'],AuthorizationBudget(STATE).inspect()):
        return 1
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        print(json.dumps(dict(state='UNKNOWN',error_type=type(error).__name__)),file=sys.stderr)
        raise SystemExit(1) from None
