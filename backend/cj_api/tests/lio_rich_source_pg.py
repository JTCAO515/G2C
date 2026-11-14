"""Issued plan source over the real native4/Memory frame; no Trip publisher."""
from dataclasses import FrozenInstanceError,replace
from pathlib import Path
import sys
import threading
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'backend/cj_api/tests')]
from cj_api.local_lio_exploration import ExplorationPlanning
from cj_api.local_lio_rich_source import RichProfileSource,PlanCapture
from cj_api.local_lio_rich_calendar_source import RichCalendarSource
from cj_api.local_lio_planning import register,PlanningDetails
from cj_draft.rich_calendar_source import RichCalendarContextSource
from cj_message.lio_plan_needs import original_needs
from cj_trip.postgres import Repository as TripRepository
import json
from cj_memory.runtime import RuntimeDenied
from cj_message.postgres import Transaction as MessageTransaction
from cj_message.lio_exploration_schema import RESPONSE
import lio_exploration_flow_pg as native


def main():
    actual_model=ExplorationPlanning._model
    original_lock=MessageTransaction.lock_scope
    captures=[]
    def model(host,worker,binding,view,profile,system,extra):
        if profile==RESPONSE and extra.get('scene')=='plan_now_preview':
            source=RichProfileSource(host.database)
            def without_marker():
                with worker.message_context.hold_for_effect(binding)as message:
                    try:source.capture_for_plan(worker,binding,message,expected_profile=view.profile)
                    except RuntimeDenied:return
                    raise AssertionError('an outline/profile without a code marker became authority')
            worker._step(binding,without_marker)
            state=source.record_plan_now(worker,binding,worker.runs.snapshot(binding))
            state=register(worker,binding,state,PlanningDetails(None,{'fixed_items':[]},None,view.references))
            original=host.legacy.calendar.context_publisher
            repository=TripRepository(original.repository.connect,original.repository.scope,
                host.legacy.calendar.confirmation,structured=True,calendar=True,rich=True)
            calendar=RichCalendarSource(host.database,worker.message_context,day_count=extra['duration_days'],
                start_date=None,references=view.references)
            combined=RichCalendarContextSource(original.source,original_needs,calendar,repository,
                profile_reader=source,worker=worker,expected_profile=view.profile)
            locks=[];late=[]
            def lock(tx):locks.append(tx.scope);return original_lock(tx)
            def operation():
                # _step already has the genuine M and Memory frame. Reenter the
                # same authority only to pass its existing message lease to C.
                with worker.message_context.hold_for_effect(binding)as message:
                    capture=source.capture_for_plan(worker,binding,message,expected_profile=view.profile)
                    assert capture.original['message_id']==binding.message_id
                    assert capture.plan_now['original']==capture.original
                    assert capture.plan_now['policy']==capture.policy
                    assert capture.memory_epoch==worker.memory_run.snapshot.epoch
                    assert any(state=='default'for state in capture.profile_states.values())
                    with source.hold_for_plan(worker,binding,capture,message)as held:
                        held.check();late.append(held)
                        errors=[]
                        def foreign_thread():
                            try:held.check()
                            except RuntimeDenied:errors.append(True)
                        thread=threading.Thread(target=foreign_thread);thread.start();thread.join()
                        assert errors==[True]
                    for invalid_source,invalid_binding in ((RichProfileSource(host.database),binding),
                                                           (source,replace(binding,run_id='foreign-run'))):
                        try:
                            with invalid_source.hold_for_plan(worker,invalid_binding,capture,message):pass
                        except RuntimeDenied:pass
                        else:raise AssertionError('foreign/DTO source admitted')
                    try:source.capture_for_plan(worker,binding,message,expected_profile={})
                    except RuntimeDenied:pass
                    else:raise AssertionError('uncommitted expected profile admitted')
                    try:PlanCapture(capture._raw,_factory=object())
                    except RuntimeDenied:pass
                    else:raise AssertionError('unissued capture admitted')
                    try:capture._raw=b'{}'
                    except FrozenInstanceError:pass
                    else:raise AssertionError('source capture is mutable')
                    return capture
            with patch.object(MessageTransaction,'lock_scope',lock):
                _,capture=worker._step(binding,operation)
            assert locks==[],locks
            # Actual C M/NEEDS/calendar/profile composition, with no provider
            # seal or writer. The empty NEEDS fixed list is an original revision.
            def joint():
                captured=combined.capture(binding)
                raw=json.loads(captured.raw)
                assert raw['version']=='TRIP-RICH-CALENDAR-SOURCE.1'
                assert raw['calendar_basis']['version']=='TRIP-calendar-basis.2'
                assert raw['calendar_basis']['fixed_bindings']['reference']['lio_protocol']=='LIO-message.4'
                assert raw['planning_profile']['profile']['memory_epoch']==worker.memory_run.snapshot.epoch
                with combined.hold_for_publication(binding)as check:check()
                return captured
            _,joint_capture=worker._step(binding,joint)
            assert joint_capture.basis.day_count==extra['duration_days']
            try:late[0].check()
            except RuntimeDenied:pass
            else:raise AssertionError('expired plan hold remained usable')
            captures.append(capture)
            print('PASS actual native4 issued profile/PlanNow source '+binding.message_id+'; existing M frame reused with zero additional locks, foreign/expired/forged source refused',flush=True)
        return actual_model(host,worker,binding,view,profile,system,extra)
    def diagnosed(*args,**kwargs):
        try:return model(*args,**kwargs)
        except RuntimeDenied as error:
            print('RICH_SOURCE_REJECTED '+str(error),flush=True)
            raise
    with patch.object(ExplorationPlanning,'_model',diagnosed):native.main()
    assert len(captures)==6
    print('PASS rich source ZH3/EN3 actual signed origins/current committed profiles/code markers; zero Trip writes; provider fixtures only',flush=True)


if __name__=='__main__':main()
