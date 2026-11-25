"""Actual host factory over signed private PG and TCP-denied HTTP fixtures.

Two original bilingual slots, not the real sixty-slot experiment or a live
qualification. No C profile, runner or renderer is copied or changed.
"""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from threading import Event, Thread
from unittest.mock import patch
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'backend/cj_api/tests')]

import httpx
import dev_auth, local_run_context, run_worker
from cj_agent.provider import DashScopeConfig,MeteredDashScopeProvider,M4_BASE,M4_MODEL,M4_NATIVE_TURN_BUFFERED
from cj_api.local_app import LocalDatabase,ISSUER,scope_for,load_confirmation_signer
from cj_api.local_run_context import load_run_context
from cj_api.real_services import RealServices,RealTools
from cj_api.runtime_model import configured_model
from cj_api.runtime_simulator_host import NativeSimulatorHost,SimulatorEpisode
from cj_api.runtime_simulator_episode import run_native_episode
from cj_message.travel import ABI
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_strict_json import compact
from cj_usage.authorization_budget import AuthorizationBudget,CNY_SCALE
from cj_usage.sublimits import activate,scope_hash
from eval.lio_simulated_user.core import render_choice,InputError
from eval.lio_simulated_user.runner import run_episode,HostUnavailable
from test_lio_planning_flow import flow


def private_file(path,value):
    path.write_bytes(compact(value));path.chmod(0o600);return path


def pin(path):
    path.mkdir(mode=0o700)
    info=path.stat();return dict(path=str(path),device=info.st_dev,inode=info.st_ino)


def exercise(conninfo):
    root=conninfo.parent/'simulator-host';root.mkdir(mode=0o700)
    auth=root/'auth'
    subjects={locale:'m4-synthetic-local-host-'+locale for locale in ('zh','en')}
    dev_auth.init(auth,set(subjects.values()))
    now=int(time.time())
    meter=private_file(root/'meter.json',dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(
        unit='provider_call',budget=800,period_start=now-60,period_end=now+3600,
        max_steps=8,max_tools=4,max_output=65536,max_seconds=600),
        output_limits=dict(model=12000,tool=48000,memory=2000)),history=[]))
    context=load_run_context(meter)
    for subject in subjects.values():
        local_run_context.provision_budget(conninfo,context,subject)
        dev_auth.activate_travel(conninfo,subject,context,ABI)
    database=LocalDatabase(conninfo,run_context=context,travel_context=True,needs_context=True)
    profile=dict(subjects=['self'],slots={'preference':dict(kind='preference',
        collection_allowed=True,semantic_resolved=True)},extents=['long_term'],context_ids=[])
    memory=TypedRuntimeConfiguration.from_bytes(compact(dict(version='local-memory-run.2',
        collection=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
            expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
            profiles={s:profile for s in subjects.values()}),
            travel_contexts={s:[] for s in subjects.values()}),
        selections={s:dict(subject='self',slots=['preference'],max_bytes=1000) for s in subjects.values()})))
    # Explicit fixture clock in C's existing standing window; never a live clock override.
    wall=datetime(2026,11,16,11,10,tzinfo=timezone.utc)
    budget=AuthorizationBudget(root/'financial',clock=lambda:wall)
    budget.begin('fixture-preexisting-original','model',b'fixture-preexisting')
    budget.finish('fixture-preexisting-original',{})
    blank=dict(cap=None,active_cap=None,model_cap=None,tool_cap=None,max_calls=None,model_calls=None,tool_calls=None)
    grants={line:dict(blank) for line in ('A','B','L','C','E','F')}
    for line in ('L','C','E','F'):grants[line].update(cap=100*CNY_SCALE,active_cap=100*CNY_SCALE)
    activate(budget,grants,{scope_hash(scope_for(ISSUER,s)):'C' for s in subjects.values()})
    sent=[]
    def response(request):
        body=json.loads(request.content);sent.append(body)
        system=body['messages'][0]['content']
        from eval.lio_simulated_user.core import SIMULATOR_SYSTEM
        if system.startswith(SIMULATOR_SYSTEM+'\n'):
            payload=json.loads(body['messages'][1]['content']);profile=payload['profile']
            round_number=len(payload['history'])//2
            value=dict(answers=['interests'],action='direct' if round_number>=profile['behavior']['direct_after'] else 'continue')
        elif 'response_format' not in body:
            # JT 2026-11-25 B: after intake, a consult message continues to the detailed answer path.
            value=None
        else:
            schema=body['response_format']['json_schema']['schema']
            index=schema['properties']['current_source_index']['const']
            value=flow('Synthetic public question',city=None,days=None,intent='consult',
                reply='I can help plan your visit. What interests you?',questions=(),index=index)
            value.update(version='LIO-planning-intake.8',planning_request_index=None,needs_tools=False)
        event=dict(id='chatcmpl-host-fixture-'+str(len(sent)),model=M4_MODEL,
            choices=[dict(index=0,delta=dict(content='I can help plan your visit. What interests you?' if value is None else json.dumps(value)),finish_reason='stop')],
            usage=dict(prompt_tokens=100,completion_tokens=100,total_tokens=200))
        return httpx.Response(200,stream=httpx.ByteStream(('data: '+json.dumps(event)+'\n\ndata: [DONE]\n\n').encode()))
    model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,'fixture-only-not-live'),
                                  budget,transport=httpx.MockTransport(response))
    services=RealServices(model,'fixture-only-not-live',frozenset(subjects.values()),
                         demo_subjects=frozenset(subjects.values()),national_subjects=frozenset(subjects.values()))
    tools=RealTools(services,buffered_streaming_subjects=frozenset(subjects.values()))
    class Runtime:
        demo_subjects=frozenset(subjects.values())
        def database(self):return database
    runtime=Runtime();runtime.auth=auth
    results=pin(root/'results');artifacts=root/'artifacts';artifacts.mkdir(mode=0o700)
    end=wall+timedelta(minutes=30)
    evidence=private_file(root/'evidence.json',dict(version='G2C-runtime-evidence-window.4',
        directory=str(artifacts),subjects=list(subjects.values()),kinds=['tool','model'],
        source_commit='a'*40,expires_at=end.isoformat()))
    identities=[]
    for locale,subject in subjects.items():
        token=root/(locale+'.token');token.write_text(dev_auth.token(auth,subject,1800));token.chmod(0o600)
        identities.append(dict(locale=locale,subject=subject,token_file=str(token),
                               canonical_directory=pin(root/(locale+'-canonical'))))
    card=dict(code_sha='a'*40,image_digest='sha256:'+'b'*64,
              model=configured_model(model,M4_NATIVE_TURN_BUFFERED))
    actor_model=dict(endpoint=M4_BASE,id=M4_MODEL,parameters=dict(stream=True,
        stream_options={'include_usage':True},enable_thinking=False,max_tokens=1024,
        response_format={'type':'json_object'}))
    manifest=private_file(root/'manifest.json',dict(version='G2C-native-simulator-host.1',
        window_id='local-signed-host',mode='legacy2',runtime_card=card,actor_model=actor_model,
        evidence_manifest=str(evidence),results_directory=results,starts_at=(wall-timedelta(seconds=1)).isoformat(),
        ends_at=end.isoformat(),episode_seconds=120,identities=identities))
    host=NativeSimulatorHost(manifest,runtime,services,tools,wall_clock=lambda:wall)
    stop=Event();errors=[]
    signer=load_confirmation_signer(auth)
    def worker():
        try:
            while not stop.is_set():
                with host.execution_lock:
                    outcomes=run_worker.run_once(database,model,auth,tools_configuration=tools,
                        real_services=services,account_admission=True,
                        hk_demo_scopes=host.scopes,lio_confirmation=signer,
                        memory_configuration_for_scope=lambda scope:memory,
                        runtime_registrations_for_run=host.registrations,runtime_reflection=host.reflection,
                        runtime_exit_observer_for_run=host.exit_observer)
                    host.completed(outcomes)
                stop.wait(.02)
        except BaseException as error:errors.append(error)
    # Exercise the accepted HK scoped-ID branch against this disposable Mac
    # journal. The already constructed fixture budget keeps its Mac producer;
    # no HK path/anchor is opened and TCP is denied for the entire process.
    from cj_usage.authorization_budget import HK_PRODUCER
    id_environment=patch.dict(os.environ,{'CJ_M4_BUDGET_PRODUCER':HK_PRODUCER})
    id_environment.start()
    thread=Thread(target=worker);thread.start()
    traces=[]
    try:
        if not host.worker_ready.wait(10):
            if errors:raise errors[0]
            raise AssertionError("native worker did not become ready")
        dataset=json.loads(host.actor_spec.dataset)['profiles']
        for locale in ('zh','en'):
            profile=next(p for p in dataset if p['locale']==locale and p['behavior']['direct_after']==1)
            episode=SimulatorEpisode(host,profile['id'],1);host.active=episode
            for mid in episode.specification.message_ids:host.by_message[(episode.session['scope'],mid)]=episode
            trace=run_native_episode(episode.dut,episode.actor,episode.links,episode.original_cost,
                candidate='local-fixture-not-qualified',evidence_layer='L0',run_episode=run_episode,
                renderer=render_choice,input_error=InputError,host_unavailable=HostUnavailable)
            assert trace['failure_owner'] is None,(trace,episode.last_cost_report,[(type(e).__name__,str(e)) for e in errors])
            assert trace['end_reason']=='evaluation_bound_before_observed_exploration_end'
            assert episode.last_cost_report['coverage']=='COMPLETE'
            assert len(episode.last_cost_report['operations'])==5  # JT 2026-11-25 B: DUT consult = intake + answer
            assert {x['role'] for x in episode.last_cost_report['operations']}=={'actor','dut'}
            assert len(episode.returns)==2
            assert trace['cost']['actual_paid_cny'] is None
            traces.append(trace);host.active=None
    finally:
        host.stopped=True;stop.set();thread.join(10);id_environment.stop()
    assert not thread.is_alive() and not errors,errors
    assert len(sent)==10,len(sent)  # JT 2026-11-25 B: DUT consult = intake + answer
    from eval.lio_simulated_user.core import SIMULATOR_SYSTEM
    assert sum(SIMULATOR_SYSTEM in b['messages'][0]['content'] for b in sent)==2
    assert all('hidden_answers'not in compact(b).decode() for b in sent if SIMULATOR_SYSTEM not in b['messages'][0]['content'])
    print('PASS actual NativeSimulatorHost signed PG factory, ZH/EN original DUT→actor→DUT, '
          'producer-return witnesses, separate ten original fees and closed journal; '
          '2 local slots, 10 fixture HTTP, live0, real60 UNRUN, observations incomplete')


if __name__=='__main__':
    if os.environ.get('CJ_ENV')!='local':raise SystemExit('CJ_ENV=local fixture only')
    from eval.runtime import private_database
    from eval.lio_simulated_user.local_controls import no_tcp
    with no_tcp(),private_database('b936host') as conninfo:exercise(conninfo)
