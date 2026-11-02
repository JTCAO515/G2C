"""Code-owned FakeProvider job registration over the existing single Meter core."""
from dataclasses import dataclass
import json
from cj_agent.provider import FakeProvider
from cj_strict_json import reject_duplicates
from .metered_exit import MeteredExitCore,_PreparedCall,BudgetUnknown


@dataclass(frozen=True,repr=False)
class ModelInput:
    system:str
    messages:tuple[tuple[str,str],...]

    @classmethod
    def parse(cls,raw):
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=reject_duplicates(ValueError,'duplicate job model field'))
        if (type(value) is not dict or set(value)!={'system','messages'} or type(value['system']) is not str
                or not value['system'].strip() or len(value['system'].encode('utf-8'))>32768
                or type(value['messages']) is not list or not 1<=len(value['messages'])<=100):
            raise ValueError('registered history model input required')
        messages=[]
        for item in value['messages']:
            if (type(item) is not dict or set(item)!={'role','content'} or item['role']!='user'
                    or type(item['content']) is not str or not item['content']):
                raise ValueError('history remains user data, never a model role')
            item['content'].encode('utf-8')
            messages.append(('user',item['content']))
        return cls(value['system'],tuple(messages))


class BackgroundExit(MeteredExitCore):
    def __init__(self,config,resolve_meter,*,clock,environment):
        if environment!='local' or config.unit!='provider_call':raise ValueError('explicit local provider-call profile required')
        super().__init__(config,resolve_meter,clock=clock)

    def prepare(self,record,provider,guard):
        if not isinstance(provider,FakeProvider):raise BudgetUnknown('background model adapter permits only FakeProvider')
        if record.request is None:raise BudgetUnknown('original model input erased')
        payload=ModelInput.parse(record.request.prepared_input)
        def materialize():
            send=provider.stream
            return lambda:send([dict(role=role,content=text) for role,text in payload.messages],system=payload.system)
        return _PreparedCall(record,materialize,'history',guard)
