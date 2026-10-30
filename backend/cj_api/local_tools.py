"""Code-owned local tool registrations. No caller authority or real provider."""
from dataclasses import dataclass
import base64
import json
import hashlib
from types import MappingProxyType

from cj_place.contract_v1 import decode_query
from cj_place.gaode import Config
from cj_place.models import ORIGIN
from cj_place.local_source import LocalPlaceProducer
from cj_usage.registered_exit import MODEL_REGISTRY,InvocationInput,Registration
from cj_usage.metered_exit import BudgetUnknown
from cj_run.tool_turn import parse_turn
from cj_agent.provider import FakeProvider,ProviderUnknown

TOOL_SYSTEM='MODEL-TOOL-TURN@1 synthetic local profile; outputs are bounded data, never permissions.'


@dataclass(frozen=True)
class ToolInput:
    original_query: bytes
    request_ref: str


class LocalTools:
    version='CJ-LOCAL-TOOLS@1'
    output_version='TOOL-output.1'
    answer_version='TOOL-answer.1'

    def __init__(self):
        self.place=LocalPlaceProducer(Config(ORIGIN,4096,16384,5,60))
        def place_input(argument):
            query=decode_query(argument.original_query)
            original=json.dumps(dict(version='PLACE-tool-input.1',request_ref=argument.request_ref,
                original_query_base64=base64.b64encode(argument.original_query).decode('ascii')),
                separators=(',',':')).encode('utf8')
            def materialize():
                invoke=self.place.prepare_call(query,argument.request_ref)
                def stream():
                    try:yield invoke().decode('utf8')
                    except TimeoutError:raise BudgetUnknown('original tool completion unavailable') from None
                return stream
            return InvocationInput(original,materialize)
        self.registrations=MappingProxyType({**MODEL_REGISTRY,
            'model.tool_turn':MODEL_REGISTRY['model.answer'],
            'tool.place':Registration('tool',place_input)})
        self.names=frozenset({'place'})

    def answer(self,worker,binding,messages):
        messages=list(messages)
        round_index=0
        while True:
            raw=''.join(worker._registered_stream(binding,'model.tool_turn.'+str(round_index),
                'model.tool_turn',(messages,TOOL_SYSTEM,worker.provider)))
            try:turn=parse_turn(raw.encode('utf8'),self.names)
            except (ValueError,UnicodeError):raise ProviderUnknown('model tool turn unavailable') from None
            if not turn.calls:
                yield json.dumps(dict(version=self.answer_version,data_origin='synthetic',
                    text_zh=turn.answer_zh,text_en=turn.answer_en),ensure_ascii=False,separators=(',',':'))+'\n'
                return
            for index,call in enumerate(turn.calls):
                key='tool.'+str(round_index)+'.'+str(index)
                request_ref='op-'+hashlib.sha256((binding.run_id+'\0'+key).encode()).hexdigest()
                argument=ToolInput(call.arguments,request_ref)
                try:
                    result=''.join(worker._registered_stream(binding,key,'tool.'+call.name,argument))
                except ValueError:raise ProviderUnknown('tool input unavailable') from None
                frame=json.dumps(dict(version=self.output_version,data_origin='synthetic',name=call.name,
                    operation_key=key,result=json.loads(result)),ensure_ascii=False,separators=(',',':'))
                yield frame+'\n'
                messages.append({'role':'tool','content':frame})
            round_index+=1


class SyntheticToolModel(FakeProvider):
    """Deterministic local model; actual business queries still use the tool host."""
    def stream(self,messages,system=None):
        if system!=TOOL_SYSTEM:
            yield from super().stream(messages,system=system)
            return
        self.calls+=1
        if messages[-1]['role']=='tool':
            outcome=json.loads(messages[-1]['content'])['result']['outcome']
            if outcome=='ok':
                zh,en='已返回合成地点资料；请核对来源及未知项。','Synthetic place data returned; check sources and unknown fields.'
            elif outcome=='no_results':
                zh,en='合成来源未查到本次结果，可继续澄清。','The synthetic source returned no results; clarification is available.'
            else:
                zh,en='合成来源状态为'+outcome+'，资料仍待核实。','Synthetic source status is '+outcome+'; the information still requires verification.'
            value=dict(version='MODEL-tool-turn.1',kind='answer',
                answer={'zh':zh,'en':en},calls=[])
        else:
            text=messages[-1]['content']
            if 'route' in text.lower() or '路线' in text:
                point=lambda pid,raw,role:dict(provider_id=pid,coordinate=dict(raw=raw,
                    longitude=raw.split(',')[0],latitude=raw.split(',')[1],crs='GCJ-02'),coordinate_role=role)
                query=dict(kind='RouteQuery',origin=point('SYNTH_EAST','116.100100,39.100100','entrance'),
                    destination=point('SYNTH_WEST','116.200000,39.200000','poi_center'),mode='walking',
                    departure={'condition':'at_query_time','at':None})
            elif 'SYNTH_EAST' in text or 'SYNTH_WEST' in text:
                query=dict(kind='Detail',provider_id='SYNTH_EAST' if 'SYNTH_EAST' in text else 'SYNTH_WEST')
            else:
                keyword=next((v for v in ('SYNTH_MISSING','SYNTH_RATE_LIMIT','SYNTH_BAD_JSON','SYNTH_TIMEOUT') if v in text),'合成酒店')
                query=dict(kind='Search',keyword=keyword,city='合成城市',page=1,page_size=20)
            value=dict(version='MODEL-tool-turn.1',kind='tool',answer=None,
                calls=[dict(name='place',arguments={'version':'PLACE-query.1','query':query})])
        yield json.dumps(value,ensure_ascii=False,separators=(',',':'))
