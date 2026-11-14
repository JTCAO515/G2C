"""Versioned RUN limits retain the original account, attempts and UNKNOWN holds."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict,replace
import json
import unittest
from cj_usage.core import Blocked,Command,Config,Meter,Receipt,NATIVE4_PROFILE,LedgerV2
from cj_usage.codec import CorruptLedger,decode,decode_v2,encode,encode_v2
from test_core import TransactionFake
from cj_usage.run_capacity import encode_capacity,encode_capacity_v2


class Native4PolicyTests(unittest.TestCase):
    def setUp(self):
        self.cfg=Config('provider_call',800,0,1000,24,12,65536,600)
        self.repo=TransactionFake();self.repo.ledger=LedgerV2();self.native=Meter(self.repo,self.cfg,lambda:100,run_profile=NATIVE4_PROFILE)
        self.legacy=Meter(self.repo,self.cfg,lambda:100)

    def command(self,key,kind='tool',run='four',output=1):
        return Command(key,'op-'+key,run,kind,'a'*64,1,output)

    def reserve(self,command):
        return self.native.reserve(command,provider_kind='amap'if command.kind=='tool'else None)

    def test_six_models_include_memory_and_unknown_attempts_are_not_refunded(self):
        for i in range(5):
            self.reserve(self.command(str(i),'model'));self.native.claim(str(i))
        self.reserve(self.command('memory','memory'));self.native.claim('memory')
        before=deepcopy(self.repo.ledger)
        with self.assertRaisesRegex(Blocked,'limit_exceeded'):
            self.reserve(self.command('seventh','model'))
        self.assertEqual(self.repo.ledger,before)
        self.assertEqual(Meter.exposure(before),6)
        self.native.cancel('four')
        self.assertEqual(Meter.exposure(self.repo.ledger),6)
        self.native.settle(Receipt('memory','memory-receipt','provider_call',1,0))
        self.assertEqual(self.native.query('memory').state,'settled')

    def test_actual_45_tool_attempts_and_six_models_in_same_original_800_account(self):
        for i in range(45):self.reserve(self.command(str(i),output=8192))
        for i in range(6):self.reserve(self.command('m'+str(i),'memory'if i==5 else'model',output=12000))
        self.native.claim('44')  # >65536 characters remains a valid native reservation.
        self.assertEqual(Meter.exposure(self.repo.ledger),51)
        self.assertEqual(self.repo.ledger.config,self.cfg)
        self.assertEqual(self.repo.ledger.runs['four'].tools,45)
        with self.assertRaisesRegex(Blocked,'limit_exceeded'):self.reserve(self.command('46'))
        with self.assertRaisesRegex(CorruptLedger,'version-2'):encode(self.repo.ledger)
        self.assertEqual(decode_v2(json.loads(encode_v2(self.repo.ledger))),self.repo.ledger)

    def test_legacy_limits_and_old_bytes_are_unchanged_in_mixed_account(self):
        self.reserve(self.command('native'))
        for i in range(12):self.legacy.reserve(self.command('old'+str(i),run='old'))
        with self.assertRaisesRegex(Blocked,'limit_exceeded'):
            self.legacy.reserve(self.command('old13',run='old'))
        with self.assertRaisesRegex(Blocked,'original_run_profile_conflict'):
            self.reserve(self.command('upgrade',run='old'))
        with self.assertRaisesRegex(Blocked,'original_run_profile_conflict'):
            self.legacy.reserve(self.command('downgrade'))
        old=TransactionFake();meter=Meter(old,self.cfg,lambda:100)
        meter.reserve(self.command('only-old',run='old'))
        value=json.loads(encode(old.ledger))
        self.assertNotIn('run_profiles',value)
        self.assertEqual(set(value['runs']['old']),{'started','steps','tools','cancelled'})
        self.assertEqual(decode(value),old.ledger)
        self.assertEqual(decode_v2(json.loads(encode_v2(self.repo.ledger))),self.repo.ledger)

    def test_registered_gaode_and_local_tools_have_separate_limits(self):
        for i in range(45):self.reserve(self.command('amap'+str(i)))
        for i in range(12):self.native.reserve(self.command('local'+str(i)),provider_kind='local')
        with self.assertRaisesRegex(Blocked,'limit_exceeded'):
            self.reserve(self.command('amap46'))
        with self.assertRaisesRegex(Blocked,'limit_exceeded'):
            self.native.reserve(self.command('local13'),provider_kind='local')
        with self.assertRaisesRegex(Blocked,'explicit_registered_tool_provider_required'):
            self.native.reserve(self.command('unclassified'))
        with self.assertRaisesRegex(Blocked,'id_conflict'):
            self.native.reserve(self.command('amap0'),provider_kind='local')
        snapshot=json.loads(encode_capacity_v2(self.repo.ledger,'four'))
        self.assertEqual(snapshot['remaining_amap_attempts'],0)
        self.assertEqual(snapshot['remaining_local_tools'],0)
        self.assertEqual(Meter.exposure(self.repo.ledger),57)

    def test_concurrent_model_limit_has_one_serializable_outcome_per_attempt(self):
        def reserve(i):
            try:return self.reserve(self.command(str(i),'model'))
            except Blocked:return None
        with ThreadPoolExecutor(max_workers=16)as pool:results=list(pool.map(reserve,range(40)))
        self.assertEqual(sum(result is not None for result in results),6)
        self.assertEqual(len(self.repo.ledger.attempts),6)

    def test_shared_budget_never_refilled_or_partitioned_by_profile(self):
        cfg=replace(self.cfg,budget=2);repo=TransactionFake();repo.ledger=LedgerV2()
        native=Meter(repo,cfg,lambda:100,run_profile=NATIVE4_PROFILE);legacy=Meter(repo,cfg,lambda:100)
        native.reserve(self.command('native'),provider_kind='amap');legacy.reserve(self.command('old',run='old'))
        with self.assertRaisesRegex(Blocked,'limit_exceeded'):native.reserve(self.command('extra'),provider_kind='amap')
        self.assertEqual(Meter.exposure(repo.ledger),2)
        with self.assertRaisesRegex(Blocked,'configuration_conflict'):
            Meter(repo,replace(cfg,budget=800),lambda:100,run_profile=NATIVE4_PROFILE).reserve(self.command('reset'),provider_kind='amap')

    def test_capacity_v2_shows_original_holds_and_profile_without_granting_calls(self):
        self.reserve(self.command('model','model',output=12000));self.native.claim('model')
        self.reserve(self.command('poi',output=8192));self.native.claim('poi')
        before=deepcopy(self.repo.ledger)
        value=json.loads(encode_capacity_v2(before,'four'))
        self.assertEqual((value['remaining_models'],value['remaining_tools'],value['remaining_steps']),(5,56,61))
        self.assertEqual(value['remaining_calls'],798)
        self.assertEqual(value['remaining_output'],538944-12000-8192)
        self.assertEqual(value['admission'],'NOT_GRANTED')
        self.assertEqual(value['output_unit'],'Python str characters')
        self.assertEqual(self.repo.ledger,before)
        legacy=json.loads(encode_capacity_v2(before,'old'))
        self.assertEqual((legacy['remaining_models'],legacy['remaining_tools'],legacy['remaining_steps']),(None,12,24))
        self.native.cancel('four')
        cancelled=json.loads(encode_capacity_v2(self.repo.ledger,'four'))
        self.assertEqual((cancelled['remaining_models'],cancelled['remaining_tools'],cancelled['remaining_steps']),(0,0,0))
        self.assertEqual(cancelled['remaining_calls'],798)

    def test_v2_corrupt_profile_and_forged_model_counters_fail_closed(self):
        self.reserve(self.command('native','model'))
        original=json.loads(encode_v2(self.repo.ledger))
        for profiles in({'missing':NATIVE4_PROFILE},{'four':'unknown'},[],{'four':True}):
            value=deepcopy(original);value['run_profiles']=profiles
            with self.assertRaises(CorruptLedger):decode_v2(value)
        with self.assertRaises(CorruptLedger):decode(original)
        value=deepcopy(original)
        for i in range(1,7):
            value['attempts'][str(i)]=deepcopy(value['attempts']['native'])
            value['attempts'][str(i)]['command'].update(attempt_id=str(i),operation_id='op-'+str(i))
            value['attempt_providers'][str(i)]='model'
        value['runs']['four']['steps']=7
        with self.assertRaises(CorruptLedger):decode_v2(value)
        with self.assertRaisesRegex(Blocked,'limit_exceeded'):
            self.reserve(self.command('oversize',output=8193))


if __name__=='__main__':unittest.main()
