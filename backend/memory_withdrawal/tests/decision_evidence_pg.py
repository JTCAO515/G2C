"""Genuine C Data3/Pub3/end/UNKNOWN source proof under original B intent."""
from hashlib import sha256
import json,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
import psycopg

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'backend/memory_jobs/tests')]
from cj_memory_jobs.decision_service import DecisionCollectionService
from cj_memory_withdrawal.source_graph import capture
from cj_memory_withdrawal.erasure_store import freeze
from cj_memory_withdrawal.erasure_command import ErasureCommand,VERSION
from cj_memory_withdrawal.association_reader import AssociationReader
from cj_memory_withdrawal.erasure_evidence import compare_prepared
from cj_api.local_account_admission_v2 import subject_digest
from cj_cleanup.registry import freeze as freeze_registry
from cj_cleanup.coordinator import Coordinator
from cj_cleanup.store import Store,receipt_for
from cj_cleanup.hooks_v1_1 import Selection
from cj_cleanup.core import encode,digest,Denied


def exercise():
    from decision_jobs_pg import DecisionInputChecks
    actual=DecisionCollectionService.apply_candidate;prepare=DecisionCollectionService.prepare_decision_input
    inputs={};observed=[]
    def prepared(service,token,jid,attempt,**kwargs):
        raw=prepare(service,token,jid,attempt,**kwargs);inputs[(jid,attempt)]=raw;return raw
    def apply(service,token,raw,**kwargs):
        result=actual(service,token,raw,**kwargs);action=json.loads(raw);bindings={}
        def stop(context):
            repo,principal,guard=service._binding(context,token);bindings.update(repo=repo,guard=guard)
            with repo.transaction() as memory:
                graph=json.loads(capture(memory,action['candidate_id'],max_sources=1000,max_bytes=1_000_000))
                original=encode(dict(version=VERSION,action_id='erase-real-decision',item_id=action['candidate_id'],
                    expected_version=graph['item_version'],derived_range='owned_trip_derived_scope'))
                bindings['original']=original
                value=freeze(memory,ErasureCommand.parse(original),subject_digest(principal),max_sources=1000,max_jobs=1000,max_bytes=1_000_000)
                guard('decision_evidence_freeze');return value
        association=json.loads(service.boundary.with_history_context(token,stop));scope=bindings['repo'].scope
        # A later model adds a real formal Trip document to a current capture.
        # Tail's original message was never a canonical origin; its message hash
        # alone is still eligible. The actual decision digest is now erased.
        tail_input=inputs[('tail-job','tail-attempt')]
        def late_context(context):
            from cj_memory.runtime import RuntimeMemory,RuntimeDenied,Selection as RuntimeSelection
            from cj_memory.scoped_capture import TrackedMemory,CaptureRegistry
            from cj_memory.domain import Service
            from cj_run.core import Binding
            from cj_message.source import SourceQuery
            from cj_message.domain import Receipt
            from cj_memory_jobs.source_policy import SourcePolicy
            from cj_memory_jobs.model_v2 import origin_reference
            from dataclasses import asdict
            repo,principal,guard=service._binding(context,token)
            source=json.loads(json.loads(tail_input)['messages'][0]['content'])
            tail=next(j for j in json.loads(proof_raw)['jobs'] if j['job_id']=='tail-job')
            original=tail['source_comparison']['messages'][0]['original']
            query=SourceQuery(**json.loads(tail['original_utf8'])['source'])
            def read_receipt(snapshot):
                assert origin_reference(snapshot.messages[0])==original
                return encode(asdict(snapshot.messages[0].receipt))
            receipt=Receipt(**json.loads(context.with_enabled_source(query,SourcePolicy(repo,principal,guard),read_receipt)))
            binding=Binding(repo.scope,receipt.conversation_id,receipt.generation,receipt.message_id,receipt.run_id,receipt.sequence)
            def admit(stage):guard(stage);return principal,repo.scope
            memory=TrackedMemory(RuntimeMemory(Service(repo),admit,RuntimeSelection('self',frozenset({'planning.choice'}),32768)),CaptureRegistry())
            run=memory.capture_history(binding,[original],decision_source_sha256s=[])
            try:memory.with_history(run,[],decision_source_sha256s=[source['decision_source_sha256']])
            except RuntimeDenied:pass
            else:raise AssertionError('later actual erased Trip context bypassed original capture fence')
            assert memory.registry.captured(binding) is run
            return b'late actual decision refused'
        from decision_jobs_pg import manual
        store=Store(lambda:psycopg.connect(**dict(json.loads(Path(manual.CONNINFO).read_text()),user='cj_local_cleanup')),
                    association['subject_digest'],bindings['guard'])
        reader=AssociationReader(store,scope);target='business/message'
        registry=freeze_registry(encode(dict(version='decision-evidence-component',stores=[dict(id='business',objects=[
            dict(id='message',cleanup_protocol='CLEANUP@1.1')])])),(target,),versions=('CLEANUP@1.1',))
        class Observe:
            def execute(self,request):
                nonlocal proof_raw
                proof_raw=reader.read_evidence(request)
                proof=json.loads(proof_raw);assert len(proof['jobs'])==4
                for job in proof['jobs']:
                    prepared=inputs[(job['job_id'],job['attempt_id'])]
                    assert compare_prepared(job,prepared)==sha256(prepared).hexdigest()
                    if job['publication_utf8'] is not None:
                        pub=json.loads(job['publication_utf8']);assert pub['version']=='MEMORY-PUBLICATION-result@3'
                        assert pub['enqueue_input_sha256']==job['original_input_sha256']
                        assert pub['prepared_input_sha256']==sha256(prepared).hexdigest()
                    envelope=json.loads(prepared);data=json.loads(envelope['messages'][0]['content'])
                    data['trip_decisions'][0]['document']='unrelated accepted document'
                    envelope['messages'][0]['content']=json.dumps(data)
                    try:compare_prepared(job,encode(envelope))
                    except Denied:pass
                    else:raise AssertionError('original decision proof accepted another document')
                observed.append(proof);return receipt_for(request,'unknown')
            def reconcile(self,request):return receipt_for(request,'unknown')
        proof_raw=None
        coordinator=Coordinator(store,lambda:registry,{target:Observe()});operation=association['operation_id']
        selection=Selection.from_dict(association['selection'])
        coordinator.create(operation,digest(bindings['original']),'memory',{target:dict(domain_scope=scope,selection=selection.to_dict())})
        coordinator.advance(coordinator.request(operation,target,scope,selection))
        assert coordinator.query(operation)['status']=='unknown'
        service.boundary.with_history_context(token,late_context)
        return result
    suite=unittest.TestSuite([DecisionInputChecks('test_real_modified_trip_and_committed_discussion_feed_bounded_data')])
    with patch.object(DecisionCollectionService,'prepare_decision_input',prepared),patch.object(DecisionCollectionService,'apply_candidate',apply):
        result=unittest.TextTestRunner(verbosity=2).run(suite)
    assert result.wasSuccessful() and len(observed)==1
    # Parent workflow performed the actual signed account confirmation and C
    # hooks after this original evidence was persisted; new proof is gone too.
    from decision_jobs_pg import manual
    with psycopg.connect(**json.loads(Path(manual.CONNINFO).read_text())) as conn:
        assert conn.execute('SELECT count(*) FROM cj_memory_erasure_manifest').fetchone()==(0,)
    print('PASS genuine Data3/Pub3/cross-chat/end/inflight original proof under require_intent; exact original enqueue/prepared source/pub hashes and document tamper deny; later actual account hook physically removes new proof; B remains UNKNOWN, no substitute envelope SHA')


if __name__=='__main__':exercise()
