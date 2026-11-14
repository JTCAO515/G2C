"""Native signed registered skeleton/parallel wording; fixture HTTP, zero Trip."""
from pathlib import Path
import json
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'backend/cj_api/tests')]
import httpx
from cj_api.local_lio_exploration import ExplorationPlanning
from cj_api.local_lio_pipeline_calls import PipelineCalls,model_call
from cj_api.lio_pipeline_model import SKELETON_SYSTEM,WORDING_SYSTEM,skeleton_data,parse_wording
from cj_api.lio_pipeline_skeleton import recipes,parse_skeleton
from cj_message.lio_exploration_schema import RESPONSE,response_format
from cj_message.lio_pipeline_schema import SKELETON,WORDING
from cj_trip.domain import packed
from test_lio_pipeline_skeleton import proposal
import lio_exploration_flow_pg as native


def main():
    original_model=ExplorationPlanning._model
    original_http=httpx.MockTransport.handle_request
    wires=[];completed=[]
    def response(transport,request):
        body=json.loads(request.content)
        version=body.get('response_format',{}).get('json_schema',{}).get('schema',{}).get('properties',{}).get('version',{}).get('const')
        if version not in (SKELETON,WORDING):return original_http(transport,request)
        extra=json.loads(body['messages'][-1]['content'])
        assert body['response_format']==response_format(version)
        assert 1<=body['max_tokens']<=1536
        if version==SKELETON:value=proposal(recipes(extra['effective']['duration_days'],'moderate',light_first=True,light_last=True))
        else:value=dict(version=WORDING,items=[dict(item_id=item['item_id'],reason=None,reason_refs=[],tip=None)for item in extra['items']])
        wires.append((version,body['max_tokens']))
        identity=dict(id='pipeline-model-fixture-'+str(len(wires)),model=body['model'])
        chunks=[dict(**identity,choices=[dict(index=0,delta=dict(content=packed(value).decode()),finish_reason=None)]),
                dict(**identity,choices=[dict(index=0,delta={},finish_reason='stop')]),
                dict(**identity,choices=[],usage=dict(prompt_tokens=50,completion_tokens=100,total_tokens=150))]
        raw=''.join('data: '+json.dumps(chunk)+'\n\n'for chunk in chunks)+'data: [DONE]\n\n'
        return httpx.Response(200,stream=httpx.ByteStream(raw.encode()))
    def model(host,worker,binding,view,profile,system,extra):
        if profile==RESPONSE and extra.get('scene')=='plan_now_preview':
            calls=PipelineCalls(worker,binding)
            expected=recipes(extra['duration_days'],'moderate',light_first=True,light_last=True)
            packet=model_call(host,worker,binding,view,SKELETON,SKELETON_SYSTEM,
                              skeleton_data(extra['effective'],expected,locale=extra['locale']))
            raw,=calls.parallel((packet,))
            skeleton=parse_skeleton(raw.encode(),expected,id_prefix='registered-p4')
            items=tuple(dict(item_id=stop.item_id,tip=None)for stop in skeleton.stops)
            # Two explicit wording requests share one original RUN. Every one
            # traverses the registered exit, financial journal and true4 origin.
            batches=(items[::2],items[1::2])
            results=calls.parallel(tuple(model_call(host,worker,binding,view,WORDING,WORDING_SYSTEM,
                dict(locale=extra['locale'],items=batch))for batch in batches))
            for result,batch in zip(results,batches,strict=True):
                parse_wording(result.encode(),batch,allowed_reason_keys=set())
            assert calls.model==4 # one reserved understanding slot, three actual dispatches
            completed.append(binding.run_id)
            print('PASS native4 skeleton + two separately registered wording calls '+binding.message_id+' RUN '+binding.run_id+'; no Trip publication',flush=True)
        return original_model(host,worker,binding,view,profile,system,extra)
    with patch.object(httpx.MockTransport,'handle_request',response),patch.object(ExplorationPlanning,'_model',model):native.main()
    assert len(completed)==6 and len(wires)==18
    print('PASS ZH3/EN3 signed native4/three pipeline model registrations each; actual caps/schema/Meter, fixture HTTP only; full publisher/G6/G9 UNRUN',flush=True)


if __name__=='__main__':main()
