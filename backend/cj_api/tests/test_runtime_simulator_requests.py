from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace
import sqlite3
import unittest

from cj_run.core import Binding
from cj_strict_json import compact
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.registered_exit import InvocationInput, Registration
from runtime_adapter.contract import Unavailable
from cj_api.runtime_simulator_requests import SimulatorRunRequests


class SimulatorRequestsTest(unittest.TestCase):
    def setUp(self):
        self.mid = 'c936-' + 'a' * 64
        self.binding = Binding('original-scope', 'original-chat', 'original-generation',
                               self.mid, 'original-run', 1)
        self.wire = compact(dict(version='LIO-message.2', message_id=self.mid,
                                 text='Public opening', locale='en', new_conversation=True))
        self.request = dict(step_id=self.mid, native_input_utf8=self.wire.decode())
        self.raw = compact(self.request)
        self.allowed = True
        self.source_digest = sha256(self.wire).hexdigest()
        self.receipt = SimpleNamespace(run_id='original-run', conversation_id='original-chat',
                                       generation='original-generation', sequence=1)
        self.history_reads, self.checks, self.sends = [], [], []
        self.before_claim_return = lambda: None

        def read(mid, *, deadline):
            self.assertEqual((mid, deadline), (self.mid, 100))
            self.before_claim_return()
            return self.raw

        def current(**kwargs):
            self.checks.append(kwargs)
            self.assertEqual(kwargs, dict(binding=self.owner, pins_sha256='original-pins', deadline=100))
            if not self.allowed:
                raise Unavailable('ORIGINAL_AUTH_CHANGED')

        def history(token, callback):
            self.history_reads.append(token)
            return callback(SimpleNamespace(scope='original-scope',
                query_lio_message=lambda mid: SimpleNamespace(receipt=self.receipt),
                query_lio_receipt=lambda mid: SimpleNamespace(input_sha256=self.source_digest)))

        self.owner = SimpleNamespace(scope='original-scope')
        self.dut = SimpleNamespace(stopped=False, owner=self.owner,
            specification=SimpleNamespace(message_ids=(self.mid,), key='original-pins'),
            claims=SimpleNamespace(read=read), originals=[self.request],
            consumed_inputs={self.mid: self.raw}, deadline=100,
            token_supplier=lambda: 'fixture-original-auth',
            authority=SimpleNamespace(require_current_operation=current),
            boundary=SimpleNamespace(with_history_context=history))
        self.marker = object()
        self.native_guard = lambda: True

        def prepare(argument):
            self.assertIs(argument, self.marker)

            def bind(operation, guard):
                def invoke():
                    if guard() is not True:
                        raise BudgetUnknown('native guard refused')
                    self.sends.append(operation)
                    return 'original result'
                return invoke

            return InvocationInput(b'unchanged original bytes', None, bind,
                                   self.marker, tool_output_limit=7, on_settled=self.marker)

        self.registry = {'model.original': Registration('model', prepare)}
        self.routing = SimulatorRunRequests(self.dut, SimpleNamespace(registrations=self.registry))

    def invoke(self, registrations=None, *, binding=None):
        registry = self.routing.registrations(self.binding) if registrations is None else registrations
        prepared = registry['model.original'].prepare_input(self.marker)
        self.assertEqual(prepared.original_bytes, b'unchanged original bytes')
        self.assertIs(prepared.receipt, self.marker)
        self.assertIs(prepared.on_settled, self.marker)
        self.assertEqual(prepared.tool_output_limit, 7)
        operation = SimpleNamespace(binding=self.binding if binding is None else binding)
        return prepared.bind_operation(operation, lambda: self.native_guard())()

    def test_original_input_receipt_limits_and_send_are_preserved(self):
        self.assertEqual(self.invoke(), 'original result')
        self.assertEqual(len(self.sends), 1)
        self.assertEqual(self.history_reads, ['fixture-original-auth'])
        self.assertTrue(self.routing.selects(self.binding))
        # Send checks reuse the native worker's source guard, without acquiring
        # a new MESSAGE frame from inside the registered provider operation.
        self.assertEqual(len(self.history_reads), 1)
        self.assertIsNone(self.routing.reflection(self.binding))

    def test_ordinary_message_keeps_its_exact_original_registry(self):
        ordinary = replace(self.binding, message_id='ordinary-message')
        self.assertIs(self.routing.registrations(ordinary), self.registry)
        self.assertIsNone(self.routing.reflection(ordinary))
        self.assertEqual(self.history_reads, [])
        self.assertFalse(self.routing.selects(ordinary))

    def test_unclaimed_unconsumed_restarted_and_stopped_c936_never_fall_back(self):
        for fault in ('unconsumed', 'restarted', 'stopped', 'changed_claim'):
            with self.subTest(fault=fault):
                self.routing = SimulatorRunRequests(self.dut, SimpleNamespace(registrations=self.registry))
                original = (self.dut.consumed_inputs.copy(), self.dut.originals[:],
                            self.dut.stopped, self.raw)
                if fault == 'unconsumed': self.dut.consumed_inputs.clear()
                elif fault == 'restarted': self.dut.originals.clear()
                elif fault == 'stopped': self.dut.stopped = True
                else: self.raw = compact(dict(self.request, native_input_utf8='changed'))
                self.assertEqual(self.routing.registrations(self.binding), {})
                with self.assertRaises(BudgetUnknown): self.routing.reflection(self.binding)
                self.dut.consumed_inputs, self.dut.originals, self.dut.stopped, self.raw = original
        self.assertEqual(self.sends, [])

    def test_foreign_scope_unknown_namespace_and_wrong_native_binding_are_refused(self):
        for binding in (replace(self.binding, scope='foreign'),
                        replace(self.binding, message_id='c936-not-a-planned-id'),
                        replace(self.binding, run_id='other-run'),
                        replace(self.binding, generation='other-generation')):
            with self.subTest(binding=binding):
                self.assertEqual(self.routing.registrations(binding), {})
                with self.assertRaises(BudgetUnknown): self.routing.reflection(binding)
        self.source_digest = '0' * 64
        self.assertEqual(self.routing.registrations(self.binding), {})
        self.assertEqual(self.sends, [])

    def test_authority_change_during_native_guard_blocks_the_actual_send(self):
        registry = self.routing.registrations(self.binding)
        def revoke():
            self.allowed = False
            return True
        self.native_guard = revoke
        with self.assertRaises(BudgetUnknown): self.invoke(registry)
        self.assertEqual(self.sends, [])
        self.assertEqual(len(self.history_reads), 1)

    def test_claim_change_after_selection_is_sticky_query_only(self):
        registry = self.routing.registrations(self.binding)
        self.dut.consumed_inputs.clear()
        with self.assertRaises(BudgetUnknown): self.invoke(registry)
        self.dut.consumed_inputs[self.mid] = self.raw
        with self.assertRaises(BudgetUnknown): self.invoke(registry)
        self.assertEqual(self.sends, [])

    def test_operation_binding_change_after_selection_stops_send(self):
        registry = self.routing.registrations(self.binding)
        with self.assertRaises(BudgetUnknown):
            self.invoke(registry, binding=replace(self.binding, run_id='changed'))
        self.assertEqual(self.sends, [])

    def test_native_guard_refusal_is_not_replaced_by_simulator_authority(self):
        self.native_guard = lambda: False
        with self.assertRaises(BudgetUnknown): self.invoke()
        self.assertEqual(self.sends, [])

    def test_financial_database_read_failure_selects_no_fallback_registry(self):
        def unavailable(**kwargs):
            raise sqlite3.OperationalError('fixture original journal unavailable')
        self.dut.authority.require_current_operation = unavailable
        self.assertEqual(self.routing.registrations(self.binding), {})
        with self.assertRaises(BudgetUnknown): self.routing.reflection(self.binding)
        self.assertEqual(self.sends, [])

    def test_financial_database_read_failure_after_selection_is_sticky_unknown(self):
        registry = self.routing.registrations(self.binding)
        original = self.dut.authority.require_current_operation
        def unavailable(**kwargs):
            raise sqlite3.OperationalError('fixture original journal unavailable')
        self.dut.authority.require_current_operation = unavailable
        with self.assertRaises(BudgetUnknown): self.invoke(registry)
        self.dut.authority.require_current_operation = original
        with self.assertRaises(BudgetUnknown): self.invoke(registry)
        self.assertEqual(self.sends, [])


if __name__ == '__main__':
    unittest.main()
