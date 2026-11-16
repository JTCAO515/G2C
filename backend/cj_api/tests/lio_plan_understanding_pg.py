"""Signed native4 originals -> registered plan data -> compiler, HTTP fixture only.

The city below is explicit fixture data, not an authoritative city lookup.
This component does not register NEEDS or publish a Trip.
"""
from pathlib import Path
import json
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'backend/cj_api/tests')]
import httpx
from fastapi.testclient import TestClient
from cj_api.local_lio_exploration import ExplorationPlanning
from cj_api.local_lio_pipeline_inputs import understand_constraints,planning_details,planning_edges
from cj_api.lio_city import CityReference
from cj_message.lio_exploration_schema import RESPONSE,response_format
from cj_message.lio_plan_input_schema import PLAN_UNDERSTANDING
from cj_trip.domain import packed
import lio_exploration_flow_pg as native


def main():
    original_model=ExplorationPlanning._model
    original_http=httpx.MockTransport.handle_request
    original_post=TestClient.post
    observed=[];wires=[]
    def post(api,url,**kwargs):
        if url=='/v4/lio/messages':
            body=json.loads(kwargs['content'])
            if body['text']in ('我想去中国玩几天','I want to explore China'):
                body['text']+='；预算 CNY 500 总计'if body['locale']=='zh'else'; Budget USD 500 total'
                kwargs['content']=packed(body)
        return original_post(api,url,**kwargs)
    def response(transport,request):
        body=json.loads(request.content)
        version=body.get('response_format',{}).get('json_schema',{}).get('schema',{}).get('properties',{}).get('version',{}).get('const')
        if version!=PLAN_UNDERSTANDING:return original_http(transport,request)
        assert body['response_format']==response_format(PLAN_UNDERSTANDING)
        extra=json.loads(body['messages'][-1]['content'])
        assert len(extra['original_question_days'])==extra['current_source_index']+1
        currency='CNY'if extra['locale']=='zh'else'USD'
        quote='预算 CNY 500 总计'if extra['locale']=='zh'else'Budget USD 500 total'
        value=dict(version=PLAN_UNDERSTANDING,current_source_index=extra['current_source_index'],
            observations=[dict(field=field,state='known',value=amount,note=None,
                sources=[dict(source_index=0,quote=quote)])for field,amount in (
                ('budget_currency',currency),('budget_total','500'),('budget_basis','total'))],
            companions=[],fixed_items=[],temporary_conditions=[])
        wires.append(extra)
        identity=dict(id='compiler-component-'+str(len(wires)),model=body['model'])
        chunks=[dict(**identity,choices=[dict(index=0,delta=dict(content=packed(value).decode()),finish_reason=None)]),
            dict(**identity,choices=[dict(index=0,delta={},finish_reason='stop')]),
            dict(**identity,choices=[],usage=dict(prompt_tokens=50,completion_tokens=100,total_tokens=150))]
        raw=''.join('data: '+json.dumps(chunk)+'\n\n'for chunk in chunks)+'data: [DONE]\n\n'
        return httpx.Response(200,stream=httpx.ByteStream(raw.encode()))
    def model(host,worker,binding,view,profile,system,extra):
        if profile==RESPONSE and extra.get('scene')=='plan_now_preview':
            constraints=understand_constraints(host,worker,binding,view,locale=extra['locale'])
            assert len(constraints.turns)==3
            assert constraints.turns[-1].text in ('直接出方案','Plan now')
            assert [turn.question_day.isoformat()for turn in constraints.turns]==wires[-1]['original_question_days']
            projected=constraints.project()
            assert projected.start_date==dict(state='missing')
            city=CityReference('110100','北京市','北京市',None,'city','Asia/Shanghai')
            compiled=constraints.compile(day_count=extra['duration_days'],city_reference=city,
                message_id=binding.message_id,run_id=binding.run_id)
            details=planning_details(compiled,city,())
            assert details.fields['fixed_items']==[]
            assert details.fields['party_size']==dict(state='missing')
            assert details.fields['budget_currency']==dict(state='known',value='CNY'if extra['locale']=='zh'else'USD')
            assert details.fields['budget_total']==dict(state='known',value='500')
            assert details.fields['budget_basis']==dict(state='known',value='total')
            edges=planning_edges(compiled,extra['duration_days'])
            assert len(edges.windows)==extra['duration_days']
            assert edges.first_unknown_recipe and edges.last_unknown_morning
            observed.append((binding.message_id,binding.run_id))
        return original_model(host,worker,binding,view,profile,system,extra)
    with patch.object(TestClient,'post',post),patch.object(httpx.MockTransport,'handle_request',response),patch.object(ExplorationPlanning,'_model',model):
        native.main()
    assert len(observed)==len(wires)==6
    print('PASS ZH3/EN3 signed native4 original M frames/question_day + registered typed plan model + source-bound budget amount/currency/basis and missing date/party/legal empty fixed; explicit fixture city data only; 0 NEEDS/Trip/real supplier, full factory UNRUN',flush=True)


if __name__=='__main__':main()
