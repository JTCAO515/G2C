"""Working-tree synthetic integration; no PG, provider or network."""
import argparse
import copy
from contextlib import contextmanager
from dataclasses import replace
import hashlib
from pathlib import Path
import subprocess
import sys
from threading import RLock
import unittest

parser=argparse.ArgumentParser()
parser.add_argument('--case')
args,rest=parser.parse_known_args()
root=Path(__file__).resolve().parents[1]
# Working-tree USAGE (ADR-0004: the repository commit is the pin).
sys.path[:0]=[str(root),str(root.parent/'usage')]
from cj_usage.core import Meter, Config, Command, Receipt, Ledger
from cj_run.core import Binding, Event, Service, Denied, Conflict
from cj_run.fixture import MemoryRepository
from cj_run.usage_fixture import SyntheticFirstStep, ReconcileOriginal


class UsageFixture:
    """Test transaction adapter of canonical Ledger, not a second budget model."""
    def __init__(self):
        self.ledger=Ledger()
        self.lock=RLock()
    @contextmanager
    def transaction(self):
        with self.lock:
            staged=copy.deepcopy(self.ledger)
            yield staged
            self.ledger=staged


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.repo=MemoryRepository()
        self.run=Service(self.repo,lambda _:True)
        self.b=Binding('fixture-same-trusted-partition','chat','g','m','r',1)
        self.usage=UsageFixture()
        self.meter=Meter(self.usage,Config('synthetic-unit',100,0,1000,10,10,100,100),lambda:10)
        self.input_bytes=b'{"synthetic_prompt": "fixture"}\n'
        self.command=Command('attempt','operation','r','model',hashlib.sha256(self.input_bytes).hexdigest(),20,10)
        self.start=Event(self.b,1,'start','started')
        self.receipt=Receipt('attempt','fixture-receipt','synthetic-unit',3,2)
        self.calls=[]
        self.adapter=SyntheticFirstStep(self.run,self.meter,original_binding=self.b,original_command=self.command,original_input_bytes=self.input_bytes,synthetic_executor=self.execute)
        self.adapter.create_fixture()
    def execute(self,command):
        self.calls.append(command)
        return self.receipt
    def go(self): return self.adapter.execute_fixture(self.b,self.command,self.start)
    def observed(self): return self.adapter.observe(self.b,self.command)

    def test_absent_executor_has_no_reservation(self):
        self.adapter.executor=None
        with self.assertRaises(Denied): self.go()
        self.assertEqual(self.usage.ledger.attempts,{})
    def test_success_settles_usage_not_run_completion(self):
        result=self.go()
        self.assertEqual((result.run.status,result.attempt.state,result.recovery),('running','settled','reconcile_original'))
        self.assertEqual(self.calls,[self.command])
        with self.assertRaises(ReconcileOriginal): self.go()
        self.assertEqual(len(self.calls),1)
    def test_claim_ack_unknown_never_executes(self):
        claim=self.meter.claim
        def lost(identity):
            claim(identity)
            raise OSError('fixture ACK lost')
        self.meter.claim=lost
        with self.assertRaises(ReconcileOriginal) as error: self.go()
        self.assertEqual(error.exception.stage,'claim')
        self.meter.claim=claim
        with self.assertRaises(ReconcileOriginal): self.go()
        self.assertEqual((self.observed().run.status,self.observed().attempt.state),('queued','unknown'))
        self.assertEqual(self.calls,[])
        self.assertEqual(Meter.exposure(self.usage.ledger),20)
    def test_started_write_ack_unknown_never_executes(self):
        apply=self.run.apply
        def lost(event):
            apply(event)
            raise OSError('fixture RUN ACK lost')
        self.run.apply=lost
        with self.assertRaises(ReconcileOriginal) as error: self.go()
        self.assertEqual(error.exception.stage,'run_started')
        self.run.apply=apply
        with self.assertRaises(ReconcileOriginal): self.go()
        self.assertEqual((self.observed().run.status,self.observed().attempt.state),('running','unknown'))
        self.assertEqual(self.calls,[])
    def test_started_write_fails_before_commit_holds_claim(self):
        self.run.apply=lambda _:(_ for _ in ()).throw(OSError('write failed'))
        with self.assertRaises(ReconcileOriginal): self.go()
        self.assertEqual((self.observed().run.status,self.observed().attempt.state),('queued','unknown'))
        self.assertEqual(self.calls,[])
    def test_executor_unknown_rebuild_queries_no_retry(self):
        def lost(command):
            self.calls.append(command)
            raise TimeoutError('fixture execution ACK lost')
        self.adapter.executor=lost
        with self.assertRaises(ReconcileOriginal) as error: self.go()
        self.assertEqual(error.exception.stage,'executor')
        rebuilt=SyntheticFirstStep(Service(self.repo,lambda _:True),self.meter,original_binding=self.b,original_command=self.command,original_input_bytes=self.input_bytes,synthetic_executor=self.execute)
        self.assertEqual(rebuilt.observe(self.b,self.command).attempt.state,'unknown')
        with self.assertRaises(ReconcileOriginal): rebuilt.execute_fixture(self.b,self.command,self.start)
        self.assertEqual(len(self.calls),1)
        result=rebuilt.settle_original_fixture(self.b,self.command,self.receipt)
        self.assertEqual((result.run.status,result.attempt.state),('running','settled'))
    def test_cancel_in_valid_hook_no_revive_or_release_claim(self):
        def valid(b):
            self.adapter.cancel_fixture(b,self.command,Event(b,1,'cancel','cancelled'))
            return True
        self.run.valid=valid
        with self.assertRaises(ReconcileOriginal): self.go()
        result=self.observed()
        self.assertEqual((result.run.status,result.attempt.state,result.attempt.cancelled),('cancelled','unknown',True))
        self.assertEqual(self.calls,[])
        self.assertEqual(Meter.exposure(self.usage.ledger),20)
    def test_cancel_unclaimed_releases_only_reserved(self):
        self.meter.reserve(self.command)
        result=self.adapter.cancel_fixture(self.b,self.command,Event(self.b,1,'cancel','cancelled'))
        self.assertEqual((result.run.status,result.attempt.state),('cancelled','released'))
        self.assertEqual(Meter.exposure(self.usage.ledger),0)
        with self.assertRaises(ReconcileOriginal): self.go()
        self.assertEqual(self.calls,[])
    def test_late_receipt_settles_without_reviving(self):
        def cancel_during_execution(command):
            self.calls.append(command)
            self.adapter.cancel_fixture(self.b,self.command,Event(self.b,2,'cancel','cancelled'))
            return self.receipt
        self.adapter.executor=cancel_during_execution
        result=self.go()
        self.assertEqual((result.run.status,result.attempt.state,result.attempt.cancelled),('cancelled','settled',True))
        self.assertEqual(self.adapter.settle_original_fixture(self.b,self.command,self.receipt),result)
        self.assertEqual(len(self.calls),1)
    def test_settle_ack_unknown_not_run_success(self):
        settle=self.meter.settle
        def lost(receipt):
            settle(receipt)
            raise OSError('settlement ACK lost')
        self.meter.settle=lost
        with self.assertRaises(ReconcileOriginal) as error: self.go()
        self.assertEqual(error.exception.stage,'settle')
        self.assertEqual((self.observed().run.status,self.observed().attempt.state),('running','settled'))
        self.assertEqual(len(self.calls),1)
    def test_wrong_receipt_holds_original_reservation(self):
        self.adapter.executor=lambda _:replace(self.receipt,attempt_id='other')
        with self.assertRaises(ReconcileOriginal): self.go()
        self.assertEqual(self.observed().attempt.state,'unknown')
    def test_stop_partial_failure_is_explicit_no_compensation(self):
        self.meter.reserve(self.command)
        self.run.apply=lambda _:(_ for _ in ()).throw(OSError('RUN write failed'))
        with self.assertRaises(ReconcileOriginal) as error:
            self.adapter.cancel_fixture(self.b,self.command,Event(self.b,1,'cancel','cancelled'))
        self.assertEqual(error.exception.stage,'run_cancel')
        self.assertEqual((self.observed().run.status,self.observed().attempt.state),('queued','released'))
        with self.assertRaises(ReconcileOriginal): self.go()
        self.assertEqual(self.calls,[])
    def test_default_context_does_not_reach_executor(self):
        self.run.valid=lambda _:False
        with self.assertRaises(ReconcileOriginal): self.go()
        self.assertEqual(self.calls,[])
        self.assertEqual(self.observed().attempt.state,'unknown')
    def test_new_attempt_after_claim_unknown_rejected_by_fixed_fixture(self):
        claim=self.meter.claim
        def lost(identity):
            claim(identity)
            raise OSError('ACK lost')
        self.meter.claim=lost
        with self.assertRaises(ReconcileOriginal): self.go()
        self.command=replace(self.command,attempt_id='new-attempt')
        with self.assertRaises(Conflict): self.go()
        self.assertEqual(len(self.usage.ledger.attempts),1)
        self.assertEqual(self.calls,[])

    def test_reserve_ack_unknown_never_claims_on_reconstruction(self):
        reserve=self.meter.reserve
        def lost(command):
            reserve(command)
            raise OSError('reserve ACK lost')
        self.meter.reserve=lost
        with self.assertRaises(ReconcileOriginal): self.go()
        self.meter.reserve=reserve
        self.assertEqual(self.observed().attempt.state,'reserved')
        with self.assertRaises(ReconcileOriginal): self.go()
        rebuilt=SyntheticFirstStep(self.run,self.meter,original_binding=self.b,original_command=self.command,
                                   original_input_bytes=self.input_bytes,synthetic_executor=self.execute)
        with self.assertRaises(Conflict): rebuilt.create_fixture()
        with self.assertRaises(ReconcileOriginal): rebuilt.execute_fixture(self.b,self.command,self.start)
        self.assertEqual(self.observed().attempt.state,'reserved')
        self.assertEqual(self.calls,[])

    def test_changed_attempt_command_rejected(self):
        self.meter.reserve(self.command)
        self.command=replace(self.command,input_digest='2'*64)
        with self.assertRaises(Conflict): self.go()
        self.assertEqual(self.calls,[])


if __name__=='__main__': unittest.main(argv=[sys.argv[0]]+rest)
