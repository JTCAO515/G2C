"""Same protected storage boundary, original exhaustive ledger, no grant/write."""
from copy import deepcopy
from dataclasses import asdict
import json
import unittest
from cj_usage.read_status import ReadUnavailable
import test_read_status as storage


class CapacityTests(unittest.TestCase):
    Conn=storage.ReadTests.Conn
    setUp=storage.ReadTests.setUp
    event=storage.ReadTests.event
    guard=storage.ReadTests.guard

    def read(self,**kwargs):
        options=dict(guard=self.guard,max_response_bytes=4096,expected_period=(0,1000));options.update(kwargs)
        return self.repo.read_run_capacity('run',**options)

    def test_capacity_counts_unknown_hold_without_revision_change(self):
        before=deepcopy(self.row);value=json.loads(self.read())
        self.assertEqual(value['remaining_calls'],4)
        self.assertEqual(value['remaining_output'],18)
        self.assertEqual(value['admission'],'NOT_GRANTED')
        self.assertEqual(self.row,before)
        self.assertNotIn('FOR UPDATE',' '.join(x[0]for x in self.log if isinstance(x,tuple)))

    def test_new_original_run_is_explicit_not_started(self):
        value=json.loads(self.repo.read_run_capacity('new-run',guard=self.guard,max_response_bytes=4096,expected_period=(0,1000)))
        self.assertEqual(value['run_state'],'not_started')
        self.assertEqual(value['remaining_calls'],4)
        self.assertEqual(value['remaining_steps'],20)
        self.assertEqual(value['remaining_output'],20)

    def test_period_is_required_and_mismatch_is_not_current_fallback(self):
        for period in (None,(1,1000)):
            with self.subTest(period=period),self.assertRaises(ReadUnavailable):self.read(expected_period=period)

    def test_cancelled_run_keeps_hold_but_has_no_run_capacity(self):
        ledger=deepcopy(self.ledger);ledger.runs['run'].cancelled=True
        self.row=(7,1,asdict(ledger));value=json.loads(self.read())
        self.assertEqual(value['run_state'],'cancelled')
        self.assertEqual(value['remaining_calls'],4)
        for key in ('remaining_steps','remaining_tools','remaining_output'):self.assertEqual(value[key],0)

    def test_revoke_during_projection_fetch_or_cleanup_withholds(self):
        for stage in ('fetch','cursor_close','connection_close'):
            with self.subTest(stage=stage):
                self.setUp();self.hooks[stage]=lambda:setattr(self,'allowed',False)
                with self.assertRaises(ReadUnavailable):self.read()

    def test_absent_account_is_not_full_capacity(self):
        self.row=None
        with self.assertRaises(storage.RepositoryUnavailable):self.read()
