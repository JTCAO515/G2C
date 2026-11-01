"""Offline source-preserving model for the explicit NEEDS draft CLI profile.

This produces synthetic unverified model data only. C's canonical builder,
protection and publication still validate it; it is never a source or permission.
"""
from copy import deepcopy
import json
from cj_agent.provider import FakeProvider,ProviderFailed
from cj_draft.needs_publisher import SYSTEM


class NeedsPlanFakeProvider(FakeProvider):
    def stream(self,messages,system=None):
        if system!=SYSTEM:
            yield from super().stream(messages,system=system)
            return
        self.calls+=1
        source=json.loads(messages[-1]['content'])
        if source.get('version')!='TRIP-source-input.1':
            raise ProviderFailed('explicit C source prompt required')
        originals=source['fields'].get('fixed_items',[])
        if not originals:raise ProviderFailed('synthetic profile requires explicit source items')
        items=[]
        for original in originals:
            schedule={edge:{key:deepcopy(original[edge][key]) for key in ('date','time','timezone')}
                      for edge in ('start','end')}
            for value in schedule.values():value['utc_offset']=dict(state='unknown')
            items.append(dict(id=original['item_id'],text=original['description'],verification='pending',
                evidence=[],schedule=schedule,fixed=original['locked'],source_category='user_provided',source_refs=[]))
        yield json.dumps(dict(version='TRIP-model-plan.1',title='本地合成来源行程 / synthetic sourced plan',
            items=items,proposed_subjects={}),ensure_ascii=False,separators=(',',':'))
