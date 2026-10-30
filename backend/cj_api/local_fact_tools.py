"""FACT's local profile reuses the registered tool loop and its one Meter."""
import base64
import json
import re
from types import MappingProxyType

from cj_agent.provider import FakeProvider
from cj_fact.contract_v1 import decode_query, stamp
from cj_fact.local_source import LocalFactProducer, FactCompletionUnknown
from cj_fact.policy import FactFailure
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.registered_exit import MODEL_REGISTRY, InvocationInput, Registration
from .local_tools import LocalTools, TOOL_SYSTEM


class LocalFactTools(LocalTools):
    version='CJ-LOCAL-FACT-TOOLS@1'
    output_version='FACT-output.1'
    answer_version='FACT-answer.1'

    def __init__(self):
        self.fact=LocalFactProducer()
        def fact_input(argument):
            try: query=decode_query(argument.original_query,evaluated_at=self.fact.clock())
            except FactFailure: raise ValueError('FACT query unavailable') from None
            original=json.dumps(dict(version='FACT-tool-input.1',request_ref=argument.request_ref,
                prepared_at=stamp(query.evaluated_at),
                original_query_base64=base64.b64encode(argument.original_query).decode('ascii')),
                separators=(',',':')).encode('utf8')
            def materialize():
                invoke=self.fact.prepare_call(query,argument.request_ref)
                def stream():
                    try: yield invoke().decode('utf8')
                    except FactCompletionUnknown: raise BudgetUnknown('original FACT completion unavailable') from None
                return stream
            return InvocationInput(original,materialize)
        self.registrations=MappingProxyType({**MODEL_REGISTRY,
            'model.tool_turn':MODEL_REGISTRY['model.answer'],
            'tool.fact':Registration('tool',fact_input)})
        self.names=frozenset({'fact'})


class SyntheticFactModel(FakeProvider):
    """Explicit synthetic city/ISO-date prompts only; no guessed current facts."""
    def stream(self,messages,system=None):
        if system!=TOOL_SYSTEM:
            yield from super().stream(messages,system=system)
            return
        self.calls+=1
        if messages[-1]['role']=='tool':
            result=json.loads(messages[-1]['content'])['result']
            value=dict(version='MODEL-tool-turn.1',kind='answer',calls=[],answer=dict(
                zh='合成资料：'+result['summary_zh'],en='Synthetic evidence: '+result['summary_en']))
        else:
            text=messages[-1]['content']
            dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',text)
            region='synthetic-city' if ('合成城市' in text or 'synthetic-city' in text.lower()) else None
            kind='weather' if ('天气' in text or 'weather' in text.lower()) else 'entry_notice' if ('合成规则' in text or 'synthetic rule' in text.lower()) else None
            if region is None or not dates or kind is None:
                value=dict(version='MODEL-tool-turn.1',kind='answer',calls=[],answer=dict(
                    zh='请明确合成城市、天气或合成规则及ISO日期；没有适用事实来源。',
                    en='Specify synthetic-city, weather or synthetic rule, and ISO dates; no applicable factual source is available.'))
            else:
                scenario=next((key.lower() for key in ('EXPIRED','CONFLICT','UNKNOWN','MISSING','INJECTION','RATE','MALFORMED','OVERSIZE','TIMEOUT','REDIRECT') if 'SYNTH_'+key in text),'')
                conditions={}
                if 'Asia/Shanghai' in text: conditions['calendar_timezone']='Asia/Shanghai'
                if 'category=synthetic' in text: conditions['category']='synthetic'
                query=dict(version='FACT-query.1',fact_key=kind+('.'+scenario if scenario else ''),region=region,
                    dates=dict(start=dates[0],end=dates[-1]),conditions=conditions)
                value=dict(version='MODEL-tool-turn.1',kind='tool',answer=None,
                    calls=[dict(name='fact',arguments=query)])
        yield json.dumps(value,ensure_ascii=False,separators=(',',':'))
