"""Native4 combined source holders: real private PG, fixture HTTP, no Trip write."""
import asyncio
from copy import copy
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import MappingProxyType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts'), str(ROOT/'backend/cj_api/tests')]

from cj_api.local_lio_exploration import ExplorationPlanning
from cj_api.local_lio_planning import PlanningDetails, register
from cj_api.local_lio_rich_source import RichProfileSource
from cj_api.local_lio_rich_calendar_source import RichCalendarSource
from cj_api.local_lio_provider_sources import RegisteredProviderSources, POI2_REGISTRATION
from cj_api.lio_poi2_tool import POI2Input, registration
from cj_api.real_services import RealTools
from cj_draft.rich_provider_source import RichProviderContextSource
from cj_memory.runtime import RuntimeDenied
from cj_message.lio_exploration_schema import RESPONSE
from cj_message.lio_plan_needs import original_needs
from cj_message.lio_wire import ExplorationOrigin
from cj_message.postgres import Transaction as MessageTransaction
from cj_needs.revision_lease import LeaseUnavailable
from cj_place.gaode_v2 import TextSearch
from cj_place import https_transport
from cj_run.operation_usage import OperationStore
from cj_trip.postgres import Repository
from lio_provider_sources_pg import FixtureWriter
import lio_exploration_flow_pg as native


def main():
    model_before = ExplorationPlanning._model
    registry_before = RealTools._registrations
    original_read = OperationStore.read_original
    original_lock = MessageTransaction.lock_scope
    completed, writers = [], []

    def registry(tools):
        return MappingProxyType(dict(registry_before(tools), **{POI2_REGISTRATION: registration(tools.services)}))

    def model(host, worker, binding, view, profile, system, extra):
        if profile == RESPONSE and extra.get('scene') == 'plan_now_preview':
            profiles = RichProfileSource(host.database)
            state = profiles.record_plan_now(worker, binding, worker.runs.snapshot(binding))
            register(worker, binding, state, PlanningDetails(None, {'fixed_items': []}, None, view.references))
            original = host.legacy.calendar.context_publisher
            repository = Repository(original.repository.connect, original.repository.scope,
                host.legacy.calendar.confirmation, structured=True, calendar=True, rich=True)
            providers = RegisteredProviderSources(worker, binding)
            calendar = RichCalendarSource(host.database, worker.message_context,
                day_count=extra['duration_days'], start_date=None, references=view.references)
            source = RichProviderContextSource(original.source, original_needs, calendar, repository,
                profile_reader=profiles, worker=worker, expected_profile=view.profile, provider_reader=providers)
            _, captured = worker._step(binding, lambda: source.capture(binding))

            def collect(index):
                origin = ExplorationOrigin(host.database, binding, worker.messages.query(binding.message_id))
                packet = POI2Input(TextSearch('合成博物馆', '北京', 2),
                    'combined-'+str(index)+'-'+binding.run_id[:16], origin, providers)
                phases = []
                def sent():
                    worker.memory_run.check()
                    assert worker.message_context.active_original(binding).receipt.message_id == binding.message_id
                    phases.append('send-under-original-frame')
                async def dial():
                    reader = asyncio.StreamReader()
                    writer = FixtureWriter(reader, sent)
                    writers.append(writer)
                    return reader, writer
                receive_before = https_transport._read_response
                async def receive(*args):
                    try: worker.memory_run.check()
                    except RuntimeDenied: pass
                    else: raise AssertionError('Memory lock retained over response')
                    try: worker.message_context.active_original(binding)
                    except LeaseUnavailable: pass
                    else: raise AssertionError('MESSAGE lock retained over response')
                    phases.append('receive-without-original-frame')
                    return await receive_before(*args)
                with patch.object(https_transport, '_connect', dial), patch.object(https_transport, '_read_response', receive):
                    reply = ''.join(worker._registered_stream(binding, 'combined.poi2.'+str(index), POI2_REGISTRATION, packet))
                assert json.loads(reply)['status'] == 'ok'
                assert phases == ['send-under-original-frame', 'receive-without-original-frame']

            collect(0)
            # Actual registered-input materialization occurs outside _step/RUN.
            sealed = source.seal_providers(binding, captured)
            assert len(sealed.provider_records) == 1
            assert sealed.provider_records[0]['payload']['coordinate']['raw'] == '116.4,39.9'
            assert json.loads(sealed.raw)['planning_profile']['profile']['memory_epoch'] == worker.memory_run.snapshot.epoch
            reads, locks, expired = [], [], []
            def tracked_read(store, *args):
                reads.append(args)
                return original_read(store, *args)
            def tracked_lock(tx):
                locks.append(tx.scope)
                return original_lock(tx)
            def prove():
                before = len(locks)
                with source.hold_for_publication(binding) as check:
                    assert check() is True
                    expired.append(check)
                    for wrong_binding, wrong_capture in ((binding, copy(sealed)),
                            (replace(binding, run_id='foreign-run'), sealed)):
                        try: source.check(wrong_binding, wrong_capture)
                        except LeaseUnavailable: pass
                        else: raise AssertionError('unissued combined source admitted')
                    try: source.seal_providers(binding, captured)
                    except LeaseUnavailable: pass
                    else: raise AssertionError('RUN materialization allowed while publication holds N')
                assert len(locks) == before, 'combined holder acquired another exclusive M lock'
            with patch.object(OperationStore, 'read_original', tracked_read), patch.object(MessageTransaction, 'lock_scope', tracked_lock):
                worker._step(binding, prove)
            assert reads == [], 'final holder reacquired RUN to materialize original inputs'
            try: expired[0]()
            except LeaseUnavailable: pass
            else: raise AssertionError('combined source outlived its frame')

            # A distinct new registered observation invalidates the old seal;
            # this is an additional fixture operation, never a supplier retry.
            collect(1)
            def changed():
                try:
                    with source.hold_for_publication(binding): pass
                except RuntimeDenied: return
                raise AssertionError('old seal survived a new producer revision')
            worker._step(binding, changed)
            current = source.seal_providers(binding, captured)
            assert current is not sealed and len(current.provider_records) == 2
            def held_current():
                with source.hold_for_publication(binding) as check: assert check() is True
            worker._step(binding, held_current)
            completed.append(binding.message_id)
            print('PASS native combined calendar/profile/NEEDS/provider original '+binding.message_id+
                  '; same-frame final checks, expired/copied/foreign/revised seals refused; zero Trip write', flush=True)
        return model_before(host, worker, binding, view, profile, system, extra)

    with patch.object(RealTools, '_registrations', registry), patch.object(ExplorationPlanning, '_model', model):
        native.main()
    assert len(completed) == 6 and len(writers) == 12
    assert all(writer.closed and len(writer.writes) == 1 for writer in writers)
    print('PASS ZH3/EN3 native combined holders; 12 distinct fixture tool operations, 0 real supplier calls; '
          'no Source4 compiler/publisher or release acceptance claimed', flush=True)


if __name__ == '__main__': main()
