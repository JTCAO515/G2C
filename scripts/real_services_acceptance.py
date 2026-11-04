"""One bounded synthetic L2 batch through signed API/RUN/USAGE, never a spike exit.

Existing batch is read-only, even if interrupted. No --root, arbitrary prompts,
endpoint, model, transport or identity override. Secrets stay in process memory.
"""
import argparse
from contextlib import redirect_stdout,contextmanager,nullcontext
from datetime import datetime,timezone
import fcntl
import hashlib
from importlib.metadata import version
import io
import json
import logging
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
from cj_agent.provider import DashScopeConfig,MeteredDashScopeProvider,M4_BASE,M4_MODEL,ProviderFailed
from cj_api.real_services import RealServices,RealTools
from cj_api.local_app import LocalDatabase,app_from_environment,scope_for,ISSUER
from cj_api.local_run_context import load_run_context
from cj_usage.authorization_budget import AuthorizationBudget,canonical
import dev_auth,local_run_context,migrate,pg_suites,run_worker

STATE=Path.home()/'.local/share/g2c/m4-real-services'
ROUTE_KEYWORDS=('北海公园','恭王府')


def verification_passed(batch,attempts):
    """Transport receipts + original operations + readable product result.

    A model-only answer, a different tool, an incomplete follow-up or a failed
    anti-redispatch check is not evidence that native continuation worked.
    """
    required={'place-zh':('tool.place',{'https://restapi.amap.com/v3/place/text':1})}
    if batch.get('verification_profile','native-1')=='native-1':
        required['weather-en']=('tool.weather',{'https://restapi.amap.com/v3/weather/weatherInfo':1})
    elif batch.get('verification_profile')=='route-diagnostics-1':
        required={'route-zh':('tool.place',{'https://restapi.amap.com/v3/place/text':2,'https://restapi.amap.com/v3/direction/walking':1})}
    elif batch.get('verification_profile') not in ('base-search-1','native-diagnostics-1'):return False
    route_profile=batch.get('verification_profile')=='route-diagnostics-1'
    if route_profile and (batch.get('response_capture_failed') or not route_audit_passed(batch.get('route_audit',[]))):return False
    if batch.get('state')!='COMPLETE' or set(batch.get('cases',{}))!=set(required):return False
    receipts={item['attempt_id']:item for item in attempts}
    for name,(registration,endpoints) in required.items():
        case=batch['cases'][name];display=case.get('display',{})
        if (case.get('state')!='completed' or display.get('run_id')!=case.get('run_id')
                or display.get('message_id')!=case.get('message_id') or display.get('status')!='completed'
                or display.get('text_state')!='complete' or type(display.get('answer_chars')) is not int or display['answer_chars']<1):return False
        tools=[];models=[];found={}
        for operation in case.get('operations',[]):
            if operation.get('run_id')!=case['run_id']:return False
            record=receipts.get(operation['attempt_id'],{})
            if record.get('state')!='RECEIVED' or type(record.get('receipt')) is not dict:return False
            if operation['registration_id'].startswith('tool.'):
                if operation['registration_id']!=registration or record['receipt'].get('endpoint') not in endpoints:return False
                endpoint=record['receipt']['endpoint'];found[endpoint]=found.get(endpoint,0)+1
                expected='ok' if name in ('place-zh','route-zh') else 'observed'
                if record['receipt'].get('result_status')!=expected:return False
                key=re.fullmatch(r'tool\.([0-7])\.([0-9]+)',operation['operation_key'])
                if key is None:return False
                tools.append(int(key[1]))
            elif operation['registration_id']=='model.tool_turn':
                r=record['receipt'];key=re.fullmatch(r'model\.tool_turn\.([0-7])',operation['operation_key'])
                if key is None or (r.get('model_id'),r.get('endpoint'),r.get('region'))!=(M4_MODEL,M4_BASE,'cn-beijing') or type(r.get('usage')) is not dict:return False
                models.append(int(key[1]))
            else:return False
        if not tools or not models or max(models)<=max(tools) or route_profile and found!=endpoints:return False
    if route_profile and not route_operations_passed(batch,receipts):return False
    return True


def route_operations_passed(batch,receipts):
    from cj_place.contract_v1 import decode_query
    from cj_place.models import Search,RouteQuery
    case=batch['cases']['route-zh'];events=batch['route_audit'];ordered=[]
    for operation in case['operations']:
        if not operation['registration_id'].startswith('tool.'):continue
        value=operation.get('input')
        if type(value) is not dict or hashlib.sha256(canonical(value)).hexdigest()!=receipts[operation['attempt_id']].get('input_sha'):return False
        event=next((e for e in events if e.get('request_ref')==value.get('request_ref')),None)
        if event is None:return False
        try:query=decode_query(canonical(value['query']))
        except (ValueError,KeyError):return False
        if event['kind']=='search':
            if type(query) is not Search or query.keyword!=event['keyword'] or query.page!=1 or query.page_size!=1:return False
        else:
            if type(query) is not RouteQuery or query.mode!='walking':return False
            for prefix,endpoint in (('origin',query.origin),('destination',query.destination)):
                expected=event[prefix]
                if endpoint.provider_id!=expected['provider_id'] or endpoint.coordinate.raw!=expected['coordinate_raw'] or endpoint.coordinate_role!='poi_center':return False
        match=re.fullmatch(r'tool\.([0-7])\.([0-9]+)',operation['operation_key'])
        ordered.append(((int(match[1]),int(match[2])),value['request_ref']))
    return [ref for _,ref in sorted(ordered)]==[event['request_ref'] for event in events]


def route_audit_passed(events):
    if len(events)!=3 or any(e.get('kind')!='search' for e in events[:2]) or events[-1].get('kind')!='route':return False
    searches={e.get('keyword'):e for e in events[:2]}
    if set(searches)!=set(ROUTE_KEYWORDS):return False
    if searches[ROUTE_KEYWORDS[0]].get('provider_id')==searches[ROUTE_KEYWORDS[1]].get('provider_id'):return False
    route=events[-1]
    if route.get('mode')!='walking':return False
    for prefix,keyword in zip(('origin','destination'),ROUTE_KEYWORDS):
        source=searches[keyword]
        if (not source.get('provider_id') or not source.get('coordinate_raw')
                or route.get(prefix)!=dict(provider_id=source['provider_id'],coordinate_raw=source['coordinate_raw'],coordinate_role='poi_center',search_ref=source['request_ref'])):return False
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


@contextmanager
def record_place_responses(root,batch,batch_path):
    """Fixed R1 guard plus observer of the original secret-checked transport.

    Out-of-plan model calls stop before HTTP. Retention IO failure is separately
    visible and cannot replace an already received original provider response.
    """
    from cj_api import real_services
    from cj_place.models import Search,RouteQuery,FieldState
    from cj_place.gaode import parse_response
    original=real_services.fetch_candidate;searches={};attempted=set();route_sent=False
    folder=root/'provider';folder.mkdir(mode=0o700);batch['route_audit']=[]
    async def record(config,request,credentials,**kwargs):
        nonlocal route_sent
        query=request.query
        if type(query) is Search:
            if (query.keyword not in ROUTE_KEYWORDS or query.keyword in attempted or query.city not in ('北京','Beijing','beijing','110000')
                    or query.page!=1 or query.page_size!=1):raise ProviderFailed('R1 fixed original search required')
            attempted.add(query.keyword)
        elif type(query) is RouteQuery:
            if route_sent or query.mode!='walking' or set(searches)!=set(ROUTE_KEYWORDS):
                raise ProviderFailed('R1 search receipts before one walking route required')
            if searches[ROUTE_KEYWORDS[0]].provider_id==searches[ROUTE_KEYWORDS[1]].provider_id:
                raise ProviderFailed('R1 distinct actual POIs required')
            for endpoint,keyword in zip((query.origin,query.destination),ROUTE_KEYWORDS):
                place=searches[keyword]
                if (place.coordinate.state is not FieldState.PRESENT or endpoint.coordinate_role!='poi_center'
                        or endpoint.provider_id!=place.provider_id or endpoint.coordinate.raw!=place.coordinate.value.raw):
                    raise ProviderFailed('R1 original POI and raw coordinate binding required')
            route_sent=True
        else:raise ProviderFailed('R1 fixed search and walking registrations required')
        result=await original(config,request,credentials,**kwargs)
        if result.state=='received' and result.response.http_status==200:
            response=result.response
            parsed=parse_response(config,request,response,now=response.received_at,basic=True)
            if type(query) is Search and parsed.outcome.value=='ok':
                place=parsed.places[0];searches[query.keyword]=place
                batch['route_audit'].append(dict(kind='search',keyword=query.keyword,provider_id=place.provider_id,
                    coordinate_raw=place.coordinate.value.raw if place.coordinate.state is FieldState.PRESENT else None,request_ref=request.request_ref))
            elif type(query) is RouteQuery:
                search_refs={event['keyword']:event['request_ref'] for event in batch['route_audit']}
                def point(value,keyword):return dict(provider_id=value.provider_id,coordinate_raw=value.coordinate.raw,
                    coordinate_role=value.coordinate_role,search_ref=search_refs[keyword])
                batch['route_audit'].append(dict(kind='route',request_ref=request.request_ref,mode=query.mode,origin=point(query.origin,ROUTE_KEYWORDS[0]),
                    destination=point(query.destination,ROUTE_KEYWORDS[1])))
            try:
                name=request.binding_digest+'.json'
                with (folder/name).open('xb') as output:
                    os.fchmod(output.fileno(),0o600);output.write(response.body);output.flush();os.fsync(output.fileno())
                batch['provider_responses'].append(dict(path=request.path,binding_digest=request.binding_digest,
                    response_sha256=hashlib.sha256(response.body).hexdigest(),response_bytes=len(response.body),
                    http_status=response.http_status,request_ref=request.request_ref,started_at=request.started_at.isoformat(),
                    received_at=response.received_at.isoformat(),file='provider/'+name))
                save(batch_path,batch)
            except OSError:
                batch['response_capture_failed']=True
                logging.getLogger('cj_provider.audit').error('R1_CAPTURE_IO_FAILED original_response_continues')
        return result
    with patch.object(real_services,'fetch_candidate',record):yield


@contextmanager
def provider_diagnostics():
    messages=[]
    class Sink(logging.Handler):
        def emit(self,record):messages.append(record.getMessage())
    logger=logging.getLogger('cj_provider.audit');sink=Sink();logger.addHandler(sink)
    try:yield messages
    finally:logger.removeHandler(sink)


def run_batch(*,resume_setup=False,verification=False,basic_verification=False,diagnostic_verification=False,route_diagnostic=False):
    STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (STATE/'acceptance.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        tag='verification-route-diagnostics-1' if route_diagnostic else 'verification-native-diagnostics-1' if diagnostic_verification else 'verification-base-search-1' if basic_verification else 'verification-native-1' if verification else 'acceptance'
        path=STATE/(tag+'.json')
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
        if basic_verification:cases={'place-zh':'合成基础地点验证：使用place_search查询北京故宫，city北京，page1/page_size1，只请求基础资料。根据结果说明地点名称、坐标与来源，未知详情明确待核实，不写行程。'}
        if diagnostic_verification:cases={'place-zh':'合成接口诊断D1：使用place_search查询北京天安门，city北京，page1/page_size1；仅需一次基础地点查询，再根据返回的地点、来源与未知项答复，不调用路线，不写行程。'}
        if route_diagnostic:cases={'route-zh':'合成路线诊断R1：用place_search分别查询北京北海公园与恭王府，city北京，各page1/page_size1；再只用实际返回POI ID、GCJ-02原坐标和poi_center调用一次walking place_route。根据工具结果说明查询时估计、来源和未知项，不重试相同查询，不写行程。'}
        value=dict(state='INTENT',model_id=M4_MODEL,endpoint=M4_BASE,region='cn-beijing',
            packages={k:version(k) for k in ('httpx','psycopg','fastapi','pydantic')},cases={k:dict(state='PLANNED') for k in cases})
        if route_diagnostic:value.update(verification_profile='route-diagnostics-1',provider_responses=[])
        elif diagnostic_verification:value['verification_profile']='native-diagnostics-1'
        elif basic_verification:value['verification_profile']='base-search-1'
        elif verification:value['verification_profile']='native-1'
        if previous is not None:value['setup_recovery']='explicit_login_keychain_after_proven_zero_dispatch'
        save(path,value)  # Lost setup is conservative: inspect this original batch.
        root=STATE/(tag+'-pg')
        if root.exists():raise ValueError('original_private_acceptance_cluster_exists')
        model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,keychain('g2c-dashscope')),budget)
        subject='m4-synthetic-real-services-route1' if route_diagnostic else 'm4-synthetic-real-services-diagnostic1' if diagnostic_verification else 'm4-synthetic-real-services-base1' if basic_verification else 'm4-synthetic-real-services-verify1' if verification else 'm4-synthetic-real-services'
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
                        unit='provider_call',budget=10 if route_diagnostic else 4 if diagnostic_verification else 80,period_start=now-60,period_end=now+3600,
                        max_steps=10 if route_diagnostic else 4 if diagnostic_verification else 24,max_tools=3 if route_diagnostic else 1 if diagnostic_verification else 12,
                        max_output=65536,max_seconds=600),output_limits=dict(model=12000,tool=48000,memory=1000)),history=[])))
                    context=load_run_context(context_path);local_run_context.provision_budget(conninfo,context,subject)
                    db=LocalDatabase(conninfo,run_context=context)
                    with patch.dict(os.environ,dict(CJ_LOCAL_AUTH_DIR=str(auth),CJ_LOCAL_CONNINFO=str(conninfo),CJ_LOCAL_RUN_CONTEXT=str(context_path))):
                        app=app_from_environment()
                    headers=dict(Authorization='Bearer '+dev_auth.token(auth,subject,30))
                    with TestClient(app) as client:
                        for case,prompt in cases.items():
                            case_tools=(RealTools(services,allowed_native=frozenset({'place_search','place_route'})) if diagnostic_verification or route_diagnostic else
                                        RealTools(services,allowed_native=frozenset({'place_search' if case=='place-zh' else 'weather'}))
                                        if verification or basic_verification else tools)
                            cid='m4-'+case
                            opened=client.put('/v1/conversations',params=dict(conversation_id=cid),headers=headers)
                            if opened.status_code!=200:raise ValueError('synthetic_API_conversation_unavailable')
                            sent=client.post('/v1/messages',headers={**headers,'Content-Type':'application/octet-stream'},content=json.dumps(dict(
                                version='MESSAGE-send.1',conversation_id=cid,message_id=cid,text=prompt,trip_id=None,creation_intent='none',
                                expected_generation=opened.json()['generation'],expected_sequence=0)).encode())
                            if sent.status_code!=200:raise ValueError('synthetic_API_message_unavailable')
                            receipt=sent.json()['receipt'];value['cases'][case]=dict(state='ACCEPTED',run_id=receipt['run_id'],message_id=cid);save(path,value)
                            capture=record_place_responses(STATE/(tag+'-responses'),value,path) if route_diagnostic else nullcontext()
                            if route_diagnostic:(STATE/(tag+'-responses')).mkdir(mode=0o700)
                            with provider_diagnostics() as diagnostics,capture:
                                outcomes=run_worker.run_once(db,model,auth,tools_configuration=case_tools,real_services=services)
                            value['cases'][case]['provider_diagnostics']=diagnostics
                            if len(outcomes)!=1:raise ValueError('original_RUN_outcome_unavailable')
                            value['cases'][case]['state']=outcomes[0].status
                            with db.connect(scope_for(ISSUER,subject)) as conn:
                                operations=conn.execute('SELECT run_id,operation_key,registration_id,attempt_id,input_bytes FROM cj_run_metered_operation WHERE run_id=%s ORDER BY operation_key',(receipt['run_id'],)).fetchall()
                            value['cases'][case]['operations']=[dict(run_id=r,operation_key=k,registration_id=i,attempt_id=a,
                                **({'input':json.loads(bytes(raw))} if route_diagnostic and i.startswith('tool.') else {})) for r,k,i,a,raw in operations]
                            displayed=client.get('/v1/run-display',params=dict(message_id=cid),headers=headers)
                            if displayed.status_code==200:
                                snapshot=displayed.json()['snapshot'];text=snapshot['text']
                                answer='\n'.join(line for line in text.splitlines() if not line.startswith(('Source:','来源：'))).strip()
                                value['cases'][case]['display']=dict(run_id=snapshot['run_id'],message_id=snapshot['message_id'],
                                    status=snapshot['status'],text_state=snapshot['text_state'],answer_chars=len(answer),
                                    text_sha256=hashlib.sha256(text.encode()).hexdigest())
                            before=model.calls
                            if run_worker.run_once(db,model,auth,tools_configuration=case_tools,real_services=services) or model.calls!=before:
                                raise ValueError('original_RUN_redispatched')
                            save(path,value)
            value['state']='COMPLETE'
        except BaseException:
            value['state']='UNKNOWN_INTERRUPTED';save(path,value)
            raise
        save(path,value)
        return dict(mode='EXECUTED',batch=value,attempts=budget.inspect(),actual_total_cost_cny='UNKNOWN')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('run','inspect','resume-setup','verify-native','verify-base-search','verify-diagnostics','verify-route'));args=parser.parse_args()
    if args.command=='inspect':
        path=STATE/'acceptance.json'
        result=dict(batch=None if not path.exists() else json.loads(path.read_text()),attempts=AuthorizationBudget(STATE).inspect())
    else:result=run_batch(resume_setup=args.command=='resume-setup',verification=args.command=='verify-native',basic_verification=args.command=='verify-base-search',diagnostic_verification=args.command=='verify-diagnostics',route_diagnostic=args.command=='verify-route')
    print(json.dumps(result,ensure_ascii=False,separators=(',',':')))
    if args.command in ('verify-native','verify-base-search','verify-diagnostics','verify-route') and not verification_passed(result['batch'],AuthorizationBudget(STATE).inspect()):
        return 1
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        print(json.dumps(dict(state='UNKNOWN',error_type=type(error).__name__)),file=sys.stderr)
        raise SystemExit(1) from None
