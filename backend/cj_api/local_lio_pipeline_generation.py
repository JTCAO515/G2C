"""Explicit actual4 full generation; old protocols retain their own planner."""
from threading import Event
import hashlib
import json
import logging
import re

from cj_agent.draft import DraftRejected
from cj_message.lio_plan_needs import lio_needs_id
from cj_message.lio_context import UNSAVED_PLAN_ANSWER
from cj_message.needs_binding import needs_scope_for
from cj_needs.domain import InvalidInput
from cj_trip.postgres import Repository
from cj_trip.planning_context import read_current
from cj_trip.structured import SourceRejected

from .lio_exploration_policy import Scene
from .lio_pipeline_skeleton import CapacityExceeded,SkeletonUnavailable
from .lio_pipeline_model import WordingUnavailable
from .local_lio_pipeline_calls import PipelineCapacity
from .local_lio_pipeline_places import PlaceSelectionBlocked
from .local_lio_pipeline import (DestinationUnresolved,prepare_generation,retrieve_skeleton,
    compile_retrieved_plan,order_retrieved_plan,route_ordered_plan,schedule_retrieved_plan,
    word_retrieved_plan,publish_retrieved_plan)


_SAFE=re.compile(r'[A-Za-z0-9_.:\-]{1,80}')


def _safe(value):
    text=str(value)
    return text if _SAFE.fullmatch(text) else 'redacted'


def _log_refusal(binding,stage,error=None,*,reason=None,capacity=False):
    """Content-free diagnosis (HK run -42): stage, class, code fields and cause locations only."""
    details=['run_id='+_safe(getattr(binding,'run_id','unknown')),'stage='+stage]
    if error is not None:
        details+=['error='+type(error).__name__,'message_sha256='+hashlib.sha256(str(error).encode()).hexdigest()[:12]]
        for name in ('field','rule'):
            if isinstance(getattr(error,name,None),str):details.append(name+'='+_safe(getattr(error,name)))
        cause=error.__cause__
        if cause is not None:
            details.append('cause='+type(cause).__name__)
            errors=getattr(cause,'errors',None)
            if callable(errors):
                try:items=errors()
                except Exception:items=[]
                details.append('cause_errors='+','.join(
                    _safe('.'.join(str(part)for part in item.get('loc',()))or'root')+':'+_safe(item.get('type','unknown'))
                    for item in items[:8]))
                details.append('cause_error_count='+str(len(items)))
    if reason:details.append('reason='+_safe(reason))
    if capacity:details.append('capacity=1')
    logging.getLogger('cj_usage.audit').info('LIO_PIPELINE_REFUSED '+' '.join(details))


class PipelineGeneration:
    def current(self,host,binding):
        """Independent rich read capability; never mutate the legacy reader."""
        calendar=host.legacy.calendar
        original=calendar.context_publisher.repository
        repository=Repository(original.connect,original.scope,calendar.confirmation,
            structured=True,calendar=True,rich=True)
        return read_current(repository,needs_scope_for(binding.scope),lio_needs_id(binding.scope,binding.conversation_id))

    def plan(self,host,worker,binding,view,*,locale,effective,prior_model_calls):
        """Complete data acquisition, code scheduling, final prose and sole commit.

        Provider UNKNOWN, budget denial and withdrawn source/Memory exceptions
        propagate unchanged: they are never retried or turned into successful
        receipts. A known validation/capacity refusal gives an honest next step.
        """
        stage='prepare'
        try:
            prepared=prepare_generation(host,worker,binding,view,locale=locale,effective=effective,
                prior_model_calls=prior_model_calls)
            stage='retrieve'
            places,hotels,capture=retrieve_skeleton(prepared)
            count=capture.basis.day_count;dated=capture.basis.start_date is not None
            provisional=[dict(kind=kind,state='unknown'if dated else'not_checked',
                day_indices=list(range(1,count+1)),item_ids=[],
                reason='date_evidence_not_collected'if dated else'date_not_set',evidence_refs=[])
                for kind in ('weather','day_opening')]
            party=prepared.projection.fields.get('party_size',{})
            subjects=('self',)if party.get('state')=='known'and party['value']==1 else('party',)
            stage='compile'
            compiled=compile_retrieved_plan(prepared,places,hotels,capture,checks=provisional,
                subjects=subjects,locale=locale)
            stage='order'
            ordered=order_retrieved_plan(prepared,compiled,capture,locale=locale,stop=Event())
            if ordered.content is None:
                _log_refusal(binding,stage,reason=ordered.reason)
                return self._refused(host,worker,binding,locale,reason=ordered.reason)
            stage='route'
            routed,capture=route_ordered_plan(prepared,json.loads(ordered.content))
            stage='schedule'
            scheduled=schedule_retrieved_plan(prepared,compiled,capture,routed,locale=locale,stop=Event())
            if scheduled.content is None:
                _log_refusal(binding,stage,reason=scheduled.reason)
                return self._refused(host,worker,binding,locale,reason=scheduled.reason)
            stage='word'
            worded=word_retrieved_plan(host,prepared,compiled,capture,scheduled,view,locale=locale)
            stage='publish'
            _,receipt=publish_retrieved_plan(prepared,compiled,capture,worded)
        except(CapacityExceeded,PipelineCapacity)as error:
            _log_refusal(binding,stage,error,capacity=True)
            return self._refused(host,worker,binding,locale,capacity=True)
        except(DraftRejected,InvalidInput,SourceRejected,SkeletonUnavailable,WordingUnavailable,
                DestinationUnresolved,PlaceSelectionBlocked)as error:
            _log_refusal(binding,stage,error)
            return self._refused(host,worker,binding,locale)
        state=worker.runs.snapshot(binding)
        unverified=('天气、当天开放情况和部分交通尚未确认'if worded.unknown_transfers else'天气和当天开放情况尚未确认')if locale=='zh'else(
            'Weather, opening information and some routes remain unverified'if worded.unknown_transfers else
            'Weather and opening information remain unverified')
        if worded.edge_proximity_unconfirmed:
            # JT 2026-11-25: saved without an observed lodging point; say so.
            unverified+=('；首末日的抵达或离开时间未定，已建议把活动安排在住处附近；补充酒店位置后可以再调整'if locale=='zh'else
                '. Arrival or departure times are not set, so first- and last-day activities are kept near where you stay; '
                'you can adjust after adding your hotel')
        body=(worded.summary+'\n\n'+('行程已保存；'+unverified+'。想先看哪一天？'if locale=='zh'else
            'The itinerary is saved. '+unverified+'. Which day would you like to see first?'))
        return host._finish(worker,binding,state,body,Scene.ADJUSTMENT,locale)

    @staticmethod
    def _refused(host,worker,binding,locale,*,capacity=False,reason=None):
        state=worker.runs.snapshot(binding)
        state=worker._event(binding,state,'effect_committed',UNSAVED_PLAN_ANSWER)
        retained=host.current(binding)is not None
        kept=('，原行程保留'if locale=='zh'else'; the original itinerary is kept')if retained else''
        if reason=='EDGE_DAY_PROXIMITY_UNCONFIRMED':
            body=('暂时无法核对首末日活动是否在酒店附近，这次未保存'+kept+'。能补充酒店的具体位置吗？'if locale=='zh'else
                'I could not verify whether the first or last day’s activities are near the hotel, so I have not saved this plan'+kept+'. Can you provide the exact hotel location?')
        elif capacity:
            body=('这次没能完整生成并保存行程'+kept+'。想换成天数更少的方案吗？'if locale=='zh'else
                'I could not generate and save the complete itinerary'+kept+'. Would you like a plan with fewer days?')
        else:
            body=('这次没能把完整方案保存'+kept+'。想先讨论一个不保存的方案，还是核对固定安排？'if locale=='zh'else
                'I could not save a complete plan'+kept+'. Would you like to discuss an unsaved outline or review the fixed arrangements?')
        return host._finish(worker,binding,state,body,Scene.ADJUSTMENT,locale)
