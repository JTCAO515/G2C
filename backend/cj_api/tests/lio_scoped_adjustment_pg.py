"""The same native4 button and typed request reach the actual Source4 writer."""
from hashlib import sha256
import json
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx
from cj_api.local_app import ISSUER,scope_for
from cj_trip.lio_history import plan_action_id
from cj_trip.postgres import Repository
from cj_message.lio_exploration_schema import RESPONSE
from cj_memory.api_scope_hold import ApiMemoryScopeHolder
from cj_trip.rich_undo_sources import ApiRichUndoSources
from cj_api.lio_exploration_policy import ADJUSTMENT_EFFECT
import lio_pipeline_models_pg as pipeline
import lio_exploration_flow_pg as native


def main(*,matched=True):
    run_original=native.run_worker.run_once
    read_original=TestClient.get
    transport_original=httpx.MockTransport.handle_request
    receipt_original=Repository.rich_plan_receipt
    app_original=native.create_local_app
    current={};seen=set();model_calls=[]
    owner=scope_for(ISSUER,native.SUBJECT)

    def create(**kwargs):
        database=kwargs['database']
        config=kwargs['lio_profile_epoch_reader'].collection
        return app_original(**kwargs,lio_rich_undo_sources=ApiRichUndoSources(database,ApiMemoryScopeHolder(database,config)))

    def run(*args,**kwargs):
        current.update(args=args,kwargs=kwargs)
        return run_original(*args,**kwargs)

    def transport(self,request):
        wire=json.loads(request.content)
        context=wire['messages'][-1]
        if context['role']!='system' or 'scoped_food_adjustment' not in context['content']:
            return transport_original(self,request)
        plan=json.loads(context['content']);locale=plan['locale']
        model_calls.append(locale)
        name='当地小吃体验'if locale=='zh'else'Local snack tasting'
        value=dict(version=RESPONSE,body=name,groups=[])
        frame=dict(id='scoped-food-'+locale,model=wire['model'],choices=[dict(index=0,
            delta=dict(content=json.dumps(value,ensure_ascii=False)),finish_reason='stop')],
            usage=dict(prompt_tokens=60,completion_tokens=25,total_tokens=85))
        return httpx.Response(200,stream=httpx.ByteStream(('data: '+json.dumps(frame)+'\n\ndata: [DONE]\n\n').encode()))

    def original_revision(database,trip_id):
        with database.connect(owner)as db:
            version,raw=db.execute('SELECT version,content FROM cj_trip_record WHERE trip_id=%s',(trip_id,)).fetchone()
        return version,json.loads(bytes(raw)),sha256(bytes(raw)).hexdigest()

    def send(api,headers,cid,locale,text,mid):
        raw=json.dumps(dict(version='LIO-message.4',message_id=mid,conversation_id=cid,
                            locale=locale,text=text),ensure_ascii=False).encode()
        accepted=api.post('/v4/lio/messages',headers=headers,content=raw)
        assert accepted.status_code==200,accepted.status_code
        result,=run_original(*current['args'],**current['kwargs'])
        assert result.status=='completed',(locale,mid,result.status)
        timeline=read_original(api,'/v4/lio/timeline',headers=headers,params=dict(conversation_id=cid))
        assert timeline.status_code==200,timeline.text
        return result,timeline.json()['messages'][-1]

    def check_case(api,headers,locale,cid,row):
        database=current['args'][0]
        trip_id=row['trip']['trip_id']
        version,before,context=original_revision(database,trip_id)
        control=next(button['send_text']for button in row['exits']if button['id']=='less_walking')
        freeform='能多安排点美食吗？'if locale=='zh'else'Could you add more local food?'
        with patch.object(Repository,'rich_plan_receipt',receipt_original):
            for operation,text in (('remove',control),('replace',freeform)):
                outcome,adjusted=send(api,headers,cid,locale,text,'wp5-'+locale+'-'+operation)
                assert adjusted['answer'] and adjusted['trip'] is not None,adjusted['answer']
                assert (adjusted['trip']['trip_id'],adjusted['trip']['trip_version'])==(trip_id,version+1)
                after_version,after,after_digest=original_revision(database,trip_id)
                with database.connect(owner)as db:
                    basis,=db.execute('SELECT source_input FROM cj_trip_needs_basis WHERE run_id=%s',(outcome.run_id,)).fetchone()
                    marker,=db.execute("SELECT value FROM cj_run_event WHERE run_id=%s AND value LIKE %s",
                                      (outcome.run_id,ADJUSTMENT_EFFECT+'%')).fetchone()
                    action,=db.execute('SELECT action_id FROM cj_trip_receipt WHERE action_id=%s',
                                       (plan_action_id(outcome.run_id),)).fetchone()
                verified=json.loads(bytes(basis));scope=verified['scoped_adjustment']
                assert verified['planning_profile']['plan_now'] is None
                assert (scope['operation'],scope['version'],scope['content_sha256'])==(operation,version,context)
                assert json.loads(marker.removeprefix(ADJUSTMENT_EFFECT))['adjustment']==scope
                assert action==plan_action_id(outcome.run_id)
                by_id={item['id']:item for item in after['items']}
                target=scope['item_id']
                for item in before['items']:
                    if item['id']!=target:assert by_id[item['id']]==item
                if operation=='remove':assert target not in by_id
                else:assert by_id[target]['kind']=='meal' and by_id[target]['place']['state']=='unconfirmed'
                history=read_original(api,'/v4/lio/trip',headers=headers,params=dict(conversation_id=cid))
                assert history.status_code==200,history.text
                target=history.json()['undo_target']
                assert (target['expected_version'],target['original_hash'],target['restore_hash'])==(after_version,after_digest,context)
                action_id='wp5-undo-'+locale+'-'+operation
                undo=dict(version='LIO-trip-undo.4',action_id=action_id,conversation_id=cid,target=target)
                restored=api.post('/v4/lio/trip-undos',headers=headers,content=json.dumps(undo).encode())
                assert restored.status_code==200 and restored.json()['committed'] is True,restored.text
                observed=read_original(api,'/v4/lio/trip-undo-receipts',headers=headers,params=dict(
                    action_id=action_id,conversation_id=cid,target=json.dumps(target)))
                assert observed.status_code==200 and observed.json()==restored.json()
                restored_version,restored_document,restored_digest=original_revision(database,trip_id)
                assert (restored_version,restored_document,restored_digest)==(after_version+1,before,context)
                version=restored_version
        print('PASS '+locale+' original button/remove + typed food/replace through Source4, history, and exact undo readback',flush=True)

    def read(self,url,**kwargs):
        if url!='/v4/lio/timeline':return read_original(self,url,**kwargs)
        observe_generation=Repository.rich_plan_receipt
        def receipt(repository,binding):
            observe=receipt_original if binding.message_id.startswith('wp5-') else observe_generation
            return observe(repository,binding)
        # The base fixture counts initial generation receipts. Adjustment and
        # undo readback use the same real reader without that fixture observer.
        with patch.object(Repository,'rich_plan_receipt',receipt):
            response=read_original(self,url,**kwargs)
        if response.status_code!=200:return response
        page=response.json();rows=page['messages'];cid=page['conversation_id']
        if not rows:return response
        row=rows[-1];mid=row['message_id']
        if mid in seen or mid not in ('flow4-zh-0-plan','flow4-en-0-plan'):return response
        seen.add(mid)
        check_case(self,kwargs['headers'],mid.split('-')[1],cid,row)
        return response

    with patch.object(native.run_worker,'run_once',run),patch.object(TestClient,'get',read), \
            patch.object(httpx.MockTransport,'handle_request',transport),patch.object(native,'create_local_app',create):
        pipeline.main(production=True,cases=(0,),followups=False,provider_available=matched)
    assert model_calls==['zh','en'],model_calls


if __name__=='__main__':main()
