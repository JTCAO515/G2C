"""Original charge association controls; never real provider evidence."""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import unittest

from cj_strict_json import compact
from cj_usage.authorization_budget import CNY_SCALE, LIMITS
from cj_api.runtime_simulator_cost import original_charges, recheck_charge_metadata
from runtime_adapter.contract import Invalid, Unavailable


class Originals:
    def __init__(self):
        self.budget = SimpleNamespace(ledger_id='original-ledger')
        self.logical = compact({'original': 'logical input'})
        self.ops = [dict(operation_id='original-op', attempt_id='original-attempt',
                         registration_id='model.original', kind='model')]
        self.command = dict(attempt_id='original-attempt', operation_id='original-op',
                            run_id='original-run', kind='model', input_digest=sha256(self.logical).hexdigest())
        self.meter_value = dict(command=self.command, state='settled', receipt={'original': True})
        self.fee_value = dict(attempt_id='original-attempt', ledger_id='original-ledger',
                              kind='model', state='RECEIVED', receipt_utf8='{}')
        self.reads = []
        self.no_fee = False

    def inventory(self, token, mid):
        return compact(dict(run_id='original-run', status='completed', operations=self.ops))

    def meter(self, token, mid, op):
        return compact(self.meter_value)

    def fee(self, token, mid, op):
        if self.no_fee:
            raise Unavailable('ORIGINAL_FINANCIAL_ATTEMPT_UNAVAILABLE')
        return compact(self.fee_value)

    def input(self, token, mid, op):
        self.reads.append('input')
        return self.logical

    def artifact(self, token, mid, op, *, wire_input=False):
        self.reads.append('wire' if wire_input else 'artifact')
        return compact({'receipt': {'actual_cost_cny': '0'}})


class OriginalCostTest(unittest.TestCase):
    def test_unpriced_received_keeps_full_hold_and_unknown_estimate(self):
        source = Originals()
        report = original_charges(source, 'fixture', 'mid', 'actor')
        row = report['operations'][0]
        self.assertEqual(row['conservative_units'], LIMITS['model'][1] * CNY_SCALE)
        self.assertIsNone(row['estimated_units'])
        self.assertEqual(source.reads, ['input', 'artifact', 'wire'])
        source.reads.clear()
        recheck_charge_metadata(source, 'fixture', report)
        self.assertEqual(source.reads, [])  # Never revive historical raw permission.

    def test_changed_native_binding_or_unsettled_attempt_is_refused(self):
        for key, value in (('attempt_id', 'other'), ('operation_id', 'other'),
                           ('run_id', 'other'), ('kind', 'tool'), ('input_digest', '0'*64)):
            source = Originals(); source.command[key] = value
            with self.subTest(key=key), self.assertRaises((Invalid, Unavailable)):
                original_charges(source, 'fixture', 'mid', 'dut')
        for key, value in (('state', 'reserved'), ('receipt', None)):
            source = Originals(); source.meter_value[key] = value
            with self.subTest(key=key), self.assertRaises((Invalid, Unavailable)):
                original_charges(source, 'fixture', 'mid', 'dut')

    def test_fee_owner_kind_or_receipt_change_is_refused(self):
        for key, value in (('attempt_id', 'other'), ('ledger_id', 'other'),
                           ('kind', 'amap'), ('state', 'UNKNOWN'), ('receipt_utf8', None)):
            source = Originals(); source.fee_value[key] = value
            with self.subTest(key=key), self.assertRaises((Invalid, Unavailable)):
                original_charges(source, 'fixture', 'mid', 'dut')

    def test_duplicate_attempt_not_hidden_in_operation_group(self):
        source = Originals(); source.ops.append(deepcopy(source.ops[0]))
        with self.assertRaises((Invalid, Unavailable)):
            original_charges(source, 'fixture', 'mid', 'dut')

    def test_only_registered_catalogue_may_have_native_zero_without_financial_attempt(self):
        source = Originals(); source.no_fee = True
        with self.assertRaises((Invalid, Unavailable)):
            original_charges(source, 'fixture', 'mid', 'dut')
        source.ops[0].update(registration_id='tool.visitor_fact', kind='tool')
        source.command['kind'] = 'tool'
        report = original_charges(source, 'fixture', 'mid', 'dut')
        row = report['operations'][0]
        self.assertFalse(row['financial_attempt'])
        self.assertEqual(row['conservative_units'], 0)
        recheck_charge_metadata(source, 'fixture', report)
        source.no_fee = False
        with self.assertRaises((Invalid, Unavailable)):
            recheck_charge_metadata(source, 'fixture', report)

    def test_metadata_tamper_cannot_reuse_captured_proof(self):
        for field in ('inventory', 'meter', 'fee'):
            source = Originals(); report = original_charges(source, 'fixture', 'mid', 'actor')
            if field == 'inventory': source.ops[0]['registration_id'] = 'changed'
            elif field == 'meter': source.command['run_id'] = 'changed'
            else: source.fee_value['state'] = 'UNKNOWN'
            with self.subTest(field=field), self.assertRaises((Invalid, Unavailable)):
                recheck_charge_metadata(source, 'fixture', report)
