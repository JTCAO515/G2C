"""New calendar edit path; old structured versions retain their original publisher."""
from datetime import date,datetime,time
import json
from zoneinfo import ZoneInfo

from cj_agent.draft import DraftRejected
from cj_feasibility.solver import Limits
from cj_message.lio_wire import original_protocol
from cj_message.demo_dialogue import LIO_VERSION_V3
from cj_trip.domain import Denied
from cj_usage.local_provider_exit import BudgetExceeded

from .lio_calendar_edit import select_calendar_edit
from .lio_planning_grounding import planning_withdrawn
from .local_lio_calendar_source import LioCalendarSource
from .local_lio_edit import LioEdit,_bind_current


class LioCalendarEdit:
    matches=staticmethod(LioEdit.matches)

    def __init__(self,calendar,legacy):
        self.calendar,self.legacy=calendar,legacy

    def execute(self,worker,binding,state,original,text,locale,deadline):
        context=self.calendar.current(binding)
        if context is None or json.loads(context.trip.content)['content_version']!='structured.3':
            return self.legacy.execute(worker,binding,state,original,text,locale,deadline)
        with self.calendar.database.connect(binding.scope) as connection:
            protocol=original_protocol(connection.cursor(),binding,original)
        if protocol!=LIO_VERSION_V3:raise Denied('calendar edit requires original LIO3 capability')
        answer=self.calendar._answer
        if planning_withdrawn(text):
            return answer(worker,binding,state,locale,'好，先不改行程。想继续看看哪一天？',
                          'I will keep the itinerary. Which day would you like to look at?')
        selected=select_calendar_edit(context.trip,text,locale,'lio-edit-'+binding.run_id)
        if selected.status=='protected':
            return answer(worker,binding,state,locale,'这项安排已锁定或尚未确认能否修改。想看看其他哪项安排？',
                          'That arrangement is locked or its edit permission is unconfirmed. Which other stop would you like to look at?')
        if selected.status!='preview':
            return answer(worker,binding,state,locale,'请说清第几天、哪个时段或原地点名，并用引号注明一个替换地点。想改哪一项？',
                          'Use the day number and period or original stop name, with one replacement place in quotes. Which stop would you like to change?')
        state=_bind_current(worker,binding,state)
        document=json.loads(context.trip.content)
        starts=document['calendar']['start_date'] if document['calendar']['state']=='dated' else None
        source=LioCalendarSource(self.calendar.database,worker.message_context,day_count=len(document['days']),
            start_date=starts,references=(),selection=selected)
        publisher=self.calendar._publisher(worker,binding,original,context,source)
        previous=worker.drafts
        worker.drafts=publisher
        try:
            _,capture=worker._step(binding,lambda:publisher.sources_for(binding),draft=True)
            worker._model_history(binding,publisher.model_messages(binding,text,capture,[]),None)
            # For undated content this is the original message's measurement
            # epoch, not a travel start date. Calendar instants remain unknown.
            day=(date.fromisoformat(starts) if starts is not None else
                 next(item.question_day for item in source.originals if item.binding==binding))
            limits=Limits(datetime.combine(day,time.min,tzinfo=ZoneInfo('Asia/Shanghai')),
                          7*86400,1,10_000_000,60,120,128,.05,.05,100)

            def publish():
                return publisher.publish_edit_for_message(binding,original,
                    worker.message_context.active_original(binding),selected.request.raw,selected.edit,capture,
                    limits=limits,before_publish=worker._publication_check)

            state,_=worker._step(binding,publish,lambda receipt:'trip_proposal:'+receipt.proposal_id,
                                 draft=True,publication_deadline=deadline)
        except DraftRejected:
            state=worker._event(binding,worker.runs.snapshot(binding),'draft_outcome','validation_failed')
            return answer(worker,binding,state,locale,'这次没能更新行程，原安排保留。想调整哪一项？',
                          'I could not update the itinerary; the original is kept. Which stop would you like to adjust?')
        except BudgetExceeded:
            return worker._event(binding,worker._budget_rejection(binding,'draft'),'completed')
        finally:worker.drafts=previous
        return answer(worker,binding,state,locale,'这一项已更新，其他安排保留。还想调整哪一天？',
                      'That stop is updated and the other arrangements are kept. Which day would you like to adjust next?')
