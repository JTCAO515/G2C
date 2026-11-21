"""Actual native4 v1/v2 -> rich API undo v3 and original receipt, private PG only."""
import asyncio
from copy import copy
import json
import os
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
import sys
import time
from threading import Event
from types import MappingProxyType
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'backend/cj_api/tests')]
import httpx,psycopg
from fastapi.testclient import TestClient
from lio_exploration_flow_pg import (SUBJECT,OUTSIDE,KEY,ISSUER,dev_auth,load_run_context,LocalDatabase,
    Runtime,scope_for,checkpoint,demo_accounts,TypedRuntimeConfiguration,AuthorizationBudget,DEMO_DEADLINE,
    MeteredDashScopeProvider,DashScopeConfig,M4_BASE,M4_MODEL,RealServices,RealTools,
    CurrentScopeEpochReader,load_confirmation_signer,create_local_app,run_worker)
import lio_exploration_flow_pg as native
from cj_api.local_lio_exploration import ExplorationPlanning, Scene, defaults
from cj_api.local_lio_calendar import LioCalendar
from cj_api.local_worker_context import checker_for
from cj_api.local_needs import protected_reader
from cj_agent.draft import DraftRejected
from cj_agent.worker import _PublicationUncertain
from cj_api.local_lio_rich_source import RichProfileSource
from cj_api.local_lio_rich_calendar_source import RichCalendarSource
from cj_api.local_lio_provider_sources import RegisteredProviderSources,POI2_REGISTRATION
from cj_api.local_lio_rich_checks import RichUndatedChecks
from cj_api.local_lio_pipeline_calls import Call,PipelineCalls
from cj_api.local_lio_planning import PlanningDetails,register
from cj_api.lio_poi2_tool import POI2Input,registration
from cj_api.lio_pipeline_document import compile_document, unconfirmed_legs, unconfirmed_place
from cj_api.lio_pipeline_skeleton import recipes,parse_skeleton
from cj_draft.rich_provider_source import RichProviderContextSource
from cj_draft.lio_rich import LioRichPublisher
from cj_draft.rich_adjustment import RichAdjustment
from cj_feasibility.rich_assembly import Assembly, assemble_unconfirmed
from cj_feasibility.rich_edges import activity_windows
from cj_feasibility.rich_solver import Limits
from cj_memory.runtime import RuntimeDenied
from cj_memory.api_scope_hold import ApiMemoryScopeHolder
from cj_message.lio_wire import ExplorationOrigin,exploration_original_protocol
from cj_message.lio_plan_needs import original_needs
from cj_needs.revision_lease import LeaseUnavailable
from cj_place.gaode_v2 import TextSearch
from cj_place import https_transport
from cj_trip.domain import Conflict, Denied, packed
from cj_trip.lio_history import TripHead, plan_action_id
from cj_trip.planning_context import read_current
from cj_message.needs_binding import needs_scope_for
from cj_message.lio_plan_needs import lio_needs_id
from cj_trip.needs_edit_store import NeedsEdits
from cj_trip.rich_undo import RichUndo
from cj_trip.confirmation import ConfirmationSigner
from cj_trip.postgres import Repository
from cj_trip.rich_reasons import ProfileFact
from cj_trip.current_needs_source import CurrentNeedsSource
from cj_trip.needs_lineage import current_origin
from cj_trip.rich_history import history_sources
from cj_trip.rich_undo_sources import ApiRichUndoSources
from lio_provider_sources_pg import FixtureWriter
from test_lio_pipeline_skeleton import proposal
from test_lio_exploration_profile import packet
from cj_message.lio_exploration_schema import UNDERSTANDING,RESPONSE
from rich_pg_support import prepare

def exercise(root,conninfo,*,scoped=False):
    fixture=prepare(root,conninfo)
    auth,database,context,memory,subjects,scope,journal=(fixture.auth,fixture.database,fixture.context,
        fixture.memory,fixture.subjects,fixture.scope,fixture.journal)
    locale='zh';current_text='';wire=[];saved=[];writers=[];rejected=[];rollback=False;undone=[]
    def response(request):
        body=json.loads(request.content);wire.append(body)
        schema=body['response_format']['json_schema']['schema'];version=schema['properties']['version']['const']
        extra=json.loads(body['messages'][-1]['content'])
        if version==UNDERSTANDING:
            quote='轻松'if locale=='zh'else'relaxed'
            value=dict(version=version,intent='explore',current_source_index=extra['current_source_index'],
                updates=[packet('pace','relaxed',quote,index=extra['current_source_index'])])
        elif version==RESPONSE:
            groups=[dict(factor_key=g['factor_key'],question=g['question'],
                options=[dict(id=o['id'],display_text=o['display_text'])for o in g['options']])for g in extra['candidates']]
            value=dict(version=version,body='可以按轻松节奏细化。'if locale=='zh'else'We can refine a relaxed itinerary.',groups=groups)
        else:raise AssertionError(version)
        identity=dict(id='rich-writer-'+str(len(wire)),model=M4_MODEL)
        chunks=[dict(**identity,choices=[dict(index=0,delta=dict(content=json.dumps(value,ensure_ascii=False)),finish_reason=None)]),
                dict(**identity,choices=[dict(index=0,delta={},finish_reason='stop')]),
                dict(**identity,choices=[],usage=dict(prompt_tokens=50,completion_tokens=20,total_tokens=70))]
        raw=''.join('data: '+json.dumps(chunk)+'\n\n'for chunk in chunks)+'data: [DONE]\n\n'
        return httpx.Response(200,stream=httpx.ByteStream(raw.encode()))
    model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,KEY),journal,transport=httpx.MockTransport(response))
    services=RealServices(model,KEY,subjects,demo_subjects=subjects,national_subjects=subjects)
    original_registry=RealTools._registrations
    def registry(t):return MappingProxyType(dict(original_registry(t),**{POI2_REGISTRATION:registration(t.services)}))
    with patch.object(RealTools,'_registrations',registry):
        tools=RealTools(services,buffered_streaming_subjects=subjects)
    signer=load_confirmation_signer(auth)
    app=create_local_app(conninfo_path=None,auth_dir=auth,database=database,run_context=context,account_admission=True,
        confirmation_signer=signer,demo_dialogue_subjects=subjects,lio_dialogue_subjects=subjects,
        lio_calendar_subjects=subjects,lio_exploration_subjects=subjects,
        lio_profile_epoch_reader=CurrentScopeEpochReader.for_api(database,memory.collection))
    headers={'Authorization':'Bearer '+dev_auth.token(auth,SUBJECT,3600),'Content-Type':'application/octet-stream'}
    original_model=ExplorationPlanning._model
    def plan(host,worker,binding,view,profile,system,extra):
        if profile!=RESPONSE or extra.get('scene')!='plan_now_preview':
            return original_model(host,worker,binding,view,profile,system,extra)
        profiles=RichProfileSource(database)
        state=profiles.record_plan_now(worker,binding,worker.runs.snapshot(binding))
        register(worker,binding,state,PlanningDetails(None,{'fixed_items':[]},None,view.references))
        original=host.legacy.calendar.context_publisher
        repo=Repository(original.repository.connect,original.repository.scope,signer,structured=True,calendar=True,rich=True)
        providers=RegisteredProviderSources(worker,binding)
        calendar=RichCalendarSource(database,worker.message_context,day_count=extra['duration_days'],start_date=None,references=view.references)
        source=RichProviderContextSource(original.source,original_needs,calendar,repo,profile_reader=profiles,
            worker=worker,expected_profile=view.profile,provider_reader=providers)
        _,captured=worker._step(binding,lambda:source.capture(binding))
        edge=activity_windows(captured.basis.day_count)
        day_recipes=recipes(captured.basis.day_count,view.profile['pace'].value,
            light_first=edge.first_unknown_recipe,light_last=edge.last_unknown_morning)
        context=source.contexts[binding]
        original_run=binding.run_id if context is None else json.loads(context.needs_source)['planning_profile']['original']['run_id']
        skeleton=parse_skeleton(packed(proposal(day_recipes)),day_recipes,id_prefix='code-'+original_run[:12])
        origin=ExplorationOrigin(database,binding,worker.messages.query(binding.message_id))
        lookups=[(s.item_id,s.name_zh)for s in skeleton.stops]+[('hotel-'+str(i),n[0])for i,n in enumerate(skeleton.hotels)]
        packets=tuple(POI2Input(TextSearch(name,'北京',2),'lookup-'+binding.run_id[:12]+'-'+str(i),origin,providers,(target,))
            for i,(target,name)in enumerate(lookups))
        def send_check():
            worker.memory_run.check()
            assert worker.message_context.active_original(binding).receipt.message_id==binding.message_id
        async def dial():
            reader=asyncio.StreamReader();writer=FixtureWriter(reader,send_check,available=False);writers.append(writer)
            return reader,writer
        with patch.object(https_transport,'_connect',dial):
            calls=PipelineCalls(worker,binding)
            # Keep the original native output reservation bound: this fixture
            # has only one 48k tool slot plus a reserved model slot at a time.
            replies=tuple(calls.parallel((Call('gaode',POI2_REGISTRATION,p),))[0]for p in packets)
        assert all(json.loads(raw)['status']=='unavailable'for raw in replies)
        sealed=source.seal_providers(binding,captured)
        reader=RichUndatedChecks(source)
        def original_check(candidate,stored,expected):
            with database.connect(binding.scope)as db:exploration_original_protocol(db.cursor(),candidate,stored)
            return candidate==binding and stored==worker.message_context.active_original(binding)and expected == (None if context is None else TripHead.from_trip(context.trip))
        adjustment=None
        if scoped and context is not None:
            prior=json.loads(context.trip.content)
            selected=next(item for item in prior['items'] if item['schedule']['start']['day_index']==2
                          and item['fixed']=={'state':'known','value':False} and item['kind']=='sight')
            adjustment=RichAdjustment(TripHead.from_trip(context.trip),selected['id'],
                                      'replace' if locale=='zh' else 'remove')

        def fixture_authority(candidate,stored,scope):
            # Exercise the C boundary with a simulated L admission. This fixture
            # uses the actual signed generation transport and original source.
            return scope==adjustment and original_check(candidate,stored,scope.head)

        publisher=LioRichPublisher(original,signer,source,original_check,reader,
            **({'adjustment_authority':fixture_authority} if scoped else {}))
        def assemble():
            with source.hold_for_publication(binding):
                skeleton_calendar=dict(calendar={'state':'undated'},days=[dict(day_index=i)for i in range(1,captured.basis.day_count+1)])
                checks=reader.capture(binding,sealed,skeleton_calendar)
                document,activities,proposed=compile_document(skeleton,captured.basis,locale=locale,subjects=('party',),
                    timezone='Asia/Shanghai',code_checks=checks.checks,places={s.item_id:None for s in skeleton.stops},
                    hotel_places=(None,None),protected_items=(),protected_activities=(),legacy_sources=())
                if adjustment is not None:
                    document=json.loads(context.trip.content)
                    if adjustment.operation=='replace':
                        item=next(item for item in document['items'] if item['id']==adjustment.item_id)
                        item.update(text='另一个待确认建议',place=unconfirmed_place(('另一个待确认建议','Different suggestion')))
                    else:
                        document['items']=[item for item in document['items'] if item['id']!=adjustment.item_id]
                    document['legs']=unconfirmed_legs(document)
                    document['date_checks']=checks.checks
                    actual=worker.message_context.active_original(binding)
                    producer=publisher.conditional_adjustment_source(binding,actual,sealed,checks,document,adjustment)
                    assert not any(record['kind']=='retained_item' and record['payload']['item']['id']==adjustment.item_id
                                   for record in producer.document['records'])
                    return Assembly('CONDITIONAL_SCHEDULE','scoped fixture',packed(document)),checks,{}
                if context is not None:
                    document=json.loads(context.trip.content)
                    target=next(item for item in document['items']if item['fixed']=={'state':'known','value':False})
                    target['note']='This suggested activity remains unconfirmed.'
                    document['date_checks']=checks.checks
                    proposed={}
                rich=publisher.conditional_source(binding,sealed,checks,document)
                facts=tuple(ProfileFact(f.key,f.state,json.dumps(f.value,ensure_ascii=False))for f in view.profile.values())
                result=assemble_unconfirmed(document,source=rich,facts=facts,activities=activities,
                    edges=edge,phase='order',locale=locale,limits=Limits(max_seconds=2),stop=Event(),
                    unconfirmed_items=frozenset(s.item_id for s in skeleton.stops))
                assert result.status=='UNCONFIRMED_SKELETON',result
                assert all(a.nearby is None for a in activities)
                return result,checks,proposed
        _,(assembly,checks,proposed)=worker._step(binding,assemble)
        actual=worker.messages.query(binding.message_id)
        def save():
            current=worker.message_context.active_original(binding)
            try:
                if adjustment is not None:
                    def publish(candidate, *, scope=adjustment, stored=actual):
                        return publisher.publish_adjustment_for_message(binding,stored,current,candidate,sealed,
                            adjustment=scope,checks=checks,before_publish=worker._publication_check)
                    wrong=json.loads(assembly.content)
                    other=next(item for item in wrong['items'] if item['id']!=adjustment.item_id)
                    other['text']='outside authorized selection'
                    for rejected_candidate in (
                            lambda:publish(replace(assembly,content=packed(wrong))),
                            lambda:publish(assembly,scope=replace(adjustment,head=replace(adjustment.head,version=99))),
                            lambda:publish(assembly,stored=None)):
                        try:rejected_candidate()
                        except (DraftRejected,LeaseUnavailable):pass
                        else:raise AssertionError('invalid scoped action reached writer')
                    with patch.object(publisher,'adjustment_authority',None):
                        try:publish(assembly)
                        except DraftRejected:pass
                        else:raise AssertionError('unissued adjustment reached writer')
                    act=repo._act_in_tx
                    def withdraw_authority(cursor,action):
                        receipt=act(cursor,action)
                        publisher.adjustment_authority=None
                        return receipt
                    try:
                        with patch.object(repo,'_act_in_tx',withdraw_authority):
                            try:publish(assembly)
                            except DraftRejected:pass
                            else:raise AssertionError('withdrawn adjustment authority committed')
                    finally:publisher.adjustment_authority=fixture_authority
                    assert repo.query_action(plan_action_id(binding.run_id)) is None
                    assert repo.detail(context.trip.trip_id)==context.trip
                    return publish(assembly)
                for wrong_capture,wrong_checks,wrong_assembly in (
                        (copy(sealed),checks,assembly),
                        (sealed,copy(checks),assembly),
                        (sealed,checks,replace(assembly,unconfirmed_items=('not-source-covered',)))):
                    try:
                        publisher.publish_assembly_for_message(binding,actual,current,wrong_assembly,wrong_capture,
                            checks=wrong_checks,proposed_subjects=proposed,before_publish=worker._publication_check)
                    except (DraftRejected,LeaseUnavailable):pass
                    else:raise AssertionError('unissued source/checks or uncovered fallback reached the writer')
                return publisher.publish_assembly_for_message(binding,actual,current,assembly,sealed,
                    checks=checks,proposed_subjects=proposed,before_publish=worker._publication_check)
            except psycopg.Error:
                import traceback
                traceback.print_exc()
                raise
        original_act=repo._act_in_tx
        def withdrawn_after_act(cursor,action):
            value=original_act(cursor,action)
            if rollback:reader._issued=None
            return value
        try:
            with patch.object(worker,'drafts',publisher),patch.object(repo,'_act_in_tx',withdrawn_after_act):
                _,receipt=worker._step(binding,save,lambda value:'trip_proposal:'+value.proposal_id,draft=True)
        except _PublicationUncertain:
            if not rollback:raise
            assert repo.detail('trip-'+binding.run_id)is None
            with repo.transaction()as cur:
                cur.execute('SELECT count(*) FROM cj_trip_proposal WHERE scope=%s AND trip_id=%s',
                    (repo.scope,'trip-'+binding.run_id));assert cur.fetchone()[0]==0
                cur.execute('SELECT count(*) FROM cj_trip_needs_basis WHERE scope=%s AND run_id=%s',
                    (repo.scope,binding.run_id));assert cur.fetchone()[0]==0
            rejected.append(binding.message_id)
            print('PASS withdrawn original code-check token at final commit rolls back Trip/proposal/source basis '+binding.message_id,flush=True)
            raise
        trip=repo.detail(receipt.trip_id)
        assert trip.version==(1 if context is None else 2) and json.loads(trip.content)['content_version']=='structured.4'
        assert json.loads(trip.content)['date_checks']==checks.checks
        assert all(item['place']['state']=='unconfirmed'for item in json.loads(trip.content)['items'])
        assert repo.query_action(receipt.action_id)==receipt
        assert repo.rich_plan_receipt(binding)==receipt
        snapshot,_=sealed.records()
        head=repo.lio_current_trip(json.loads(sealed.raw)['needs_scope'],snapshot.needs_id)
        assert (head.trip_id,head.version,head.content_sha256)==(trip.trip_id,trip.version,sha256(trip.content).hexdigest())
        assert repo.lio_revisions(trip.trip_id,None,10)[0]==trip
        checker=checker_for(auth)
        historical=CurrentNeedsSource(database,checker,dev_auth.token(auth,SUBJECT,3600),protected_reader(database,checker))
        with repo.transaction()as cursor:origin=current_origin(cursor,repo,trip)
        if adjustment is not None:
            assert json.loads(origin['source'])['scoped_adjustment']==adjustment.basis()
        with history_sources(historical,origin)as historical_message:
            historical_message.check()
            assert historical_message.scope==binding.scope
            assert historical_message.principal==historical.admit()
            api_sources=ApiRichUndoSources(database,ApiMemoryScopeHolder(database,memory.collection))
            with api_sources.hold(None,current=trip,previous=trip,active_origin=origin,
                    previous_origin=origin,message_context=historical_message)as api_check:
                api_check()
            expired_history=copy(historical_message)
        try:expired_history.check()
        except Denied:pass
        else:raise AssertionError('copied actual historical M/T frame outlived its source locks')
        try:repo.calendar_plan_receipt(binding)
        except Denied:pass
        else:raise AssertionError('rich basis was accepted as an old calendar plan receipt')
        try:repo.rich_plan_receipt(replace(binding,message_id='foreign-original'))
        except Denied:pass
        else:raise AssertionError('rich receipt retargeted to another original message')
        if context is not None:
            assert trip.content!=context.trip.content
            repo.needs_edits=NeedsEdits(historical)
            request=RichUndo.parse(packed(dict(version='TRIP-lio-undo.3',action_id='api-undo-'+binding.run_id,
                trip_id=trip.trip_id,expected_version=2,original_hash=sha256(trip.content).hexdigest(),content_version='structured.4')))
            try:repo.undo_rich(request)
            except Denied:pass
            else:raise AssertionError('unconfigured API Memory/profile holder permitted undo')
            repo.rich_undo_sources=ApiRichUndoSources(database,ApiMemoryScopeHolder(database,memory.collection))
            attempts_before=len(journal.inspect())
            actual_undo=repo.undo_rich(request)
            restored=repo.detail(trip.trip_id)
            assert restored.version==3 and restored.content==context.trip.content
            assert [row.version for row in repo.lio_revisions(trip.trip_id,None,10)]==[3,2,1]
            assert repo.rich_undo_receipt(request)==actual_undo
            with patch.object(ConfirmationSigner,'issue',side_effect=AssertionError('original receipt must not resign')):
                assert repo.undo_rich(request)==actual_undo
            assert len(journal.inspect())==attempts_before
            conflict=RichUndo.parse(packed(dict(json.loads(request.raw),original_hash='b'*64)))
            try:repo.rich_undo_receipt(conflict)
            except Conflict:pass
            else:raise AssertionError('same action ID accepted different original bytes')
            blocked=RichUndo.parse(packed(dict(version='TRIP-lio-undo.3',action_id='blocked-'+binding.run_id,
                trip_id=trip.trip_id,expected_version=3,original_hash=sha256(restored.content).hexdigest(),content_version='structured.4')))
            before_act=repo._act_in_tx
            extra=repo.rich_undo_sources
            def withdraw_after_sql(cursor,action):
                result=before_act(cursor,action)
                repo.rich_undo_sources=None
                return result
            with patch.object(repo,'_act_in_tx',withdraw_after_sql):
                try:repo.undo_rich(blocked)
                except Denied:pass
                else:raise AssertionError('withdrawn extra holder committed the undo')
            repo.rich_undo_sources=extra
            assert repo.detail(trip.trip_id)==restored and repo.rich_undo_receipt(blocked)is None
            undone.append(actual_undo)
            print('PASS actual rich v1 -> v2 -> API undo v3 byte restoration, original no-resign receipt and post-SQL withdrawal rollback '+binding.message_id,flush=True)
        saved.append((trip,receipt))
        print('PASS actual native4 rich undated skeleton saved via original signer/sole writer '+binding.message_id,flush=True)
        body='\n'.join(('第'+str(day)+'天：待确认建议。'if locale=='zh'else'Day '+str(day)+': unconfirmed suggestions.')
            for day in range(1,captured.basis.day_count+1))
        return packed(dict(version=RESPONSE,body=body,groups=[])).decode()
    def diagnosed(*args, **kwargs):
        try: return plan(*args, **kwargs)
        except _PublicationUncertain:
            if not rollback:
                import traceback
                traceback.print_exc()
            raise
        except Exception:
            import traceback
            traceback.print_exc()
            raise
    def current_rich(calendar_host,binding):
        with calendar_host.database.message_repository(binding.scope).transaction()as tx:stored=tx.find(binding.message_id)
        with calendar_host.database.connect(binding.scope)as db:exploration_original_protocol(db.cursor(),binding,stored)
        old=calendar_host.repository
        repository=Repository(old.connect,old.scope,old.confirm,structured=True,calendar=True,rich=True)
        return read_current(repository,needs_scope_for(binding.scope),lio_needs_id(binding.scope,binding.conversation_id))
    def component_plan(host,worker,binding,state,view,locale,*,prior_model_calls=0):
        # Use signed MESSAGE intake and the real C writer while isolating the
        # producer from the L production orchestration for this component test.
        facts=defaults(view.profile)
        facts.update({key:fact.value for key,fact in view.profile.items() if fact.state!='not_needed'})
        extra=dict(scene='plan_now_preview',locale=locale,duration_days=facts['duration_days'])
        result=json.loads(diagnosed(host,worker,binding,view,RESPONSE,'',extra))
        return host._finish(worker,binding,worker.runs.snapshot(binding),result['body'],Scene.ADJUSTMENT,locale)
    scoped_hook=patch.object(ExplorationPlanning,'_plan',component_plan) if scoped else nullcontext()
    with TestClient(app)as api,patch.object(RealTools,'_registrations',registry),patch.object(ExplorationPlanning,'_model',diagnosed),patch.object(LioCalendar,'current',current_rich),scoped_hook:
        for language in ('zh','en'):
            locale=language
            for i in range(1):
                rollback=False
                cid=None
                for step,text in (('pace','节奏改为：轻松'if locale=='zh'else'Change my travel pace to relaxed'),('plan','直接出方案'if locale=='zh'else'Plan now'),('plan2','直接出方案'if locale=='zh'else'Plan now')):
                    current_text=text;mid='rich-save-'+locale+'-'+str(i)+'-'+step
                    command=dict(version='LIO-message.4',message_id=mid,text=text,locale=locale,
                        **({'conversation_id':cid}if cid else{'new_conversation':True}))
                    received=api.post('/v4/lio/messages',headers=headers,content=packed(command));assert received.status_code==200,received.text
                    cid=received.json()['conversation_id']
                    result=run_worker.run_once(database,model,auth,tools_configuration=tools,real_services=services,
                        memory_configuration_for_scope=lambda owner:memory if owner==scope else None,
                        account_admission=True,hk_demo_scopes=frozenset({scope}),lio_confirmation=signer)
                    expected='unknown'if rollback and step=='plan'else'completed'
                    assert [r.status for r in result]==[expected],result
    assert len(saved)==4 and len(undone)==2 and len(writers)==36,(len(saved),len(undone),len(writers))
    assert all(w.closed and len(w.writes)==1 for w in writers)
    assert all(record['state']=='RECEIVED'for record in journal.inspect())
    print('PASS ZH1/EN1 actual two signed rich versions and API-scope undo/receipt/late rollback; 36 unavailable tool fixture operations, 0 real suppliers; full HTTP4 host/release remains UNRUN',flush=True)


def main():
    with patch.object(native,'exercise',exercise):native.main()


if __name__=='__main__':main()
