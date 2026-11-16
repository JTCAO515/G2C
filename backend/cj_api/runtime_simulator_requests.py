"""Per-operation guards for the original simulator DUT, never a second exit.

The B factory supplies its existing NativeSimulatorDut and RealTools. A c936
MESSAGE must have that host's consumed canonical input before the normal worker
can select registrations. The native worker retains its own M/RUN/Memory guard;
registered sends additionally retain the original C AUTH, pins and clock.
"""
from dataclasses import replace
from hashlib import sha256

from cj_message.auth_boundary import AccessBlocked, IdentityChanged
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.registered_exit import Registration
from runtime_adapter.contract import Invalid, Unavailable, decode


class SimulatorRunRequests:
    def __init__(self, dut, tools):
        self.dut, self.tools = dut, tools
        self.proved = {}
        self.rejected = set()

    def _claim(self, binding):
        if (binding in self.rejected or self.dut.stopped or binding.scope != self.dut.owner.scope
                or binding.message_id not in self.dut.specification.message_ids):
            raise Unavailable('SIMULATOR_DUT_ORIGINAL_NOT_SELECTED')
        raw = self.dut.claims.read(binding.message_id, deadline=self.dut.deadline)
        request = decode(raw)
        # A restarted host has no in-process original to dispatch. Its retained
        # canonical claim remains query-only, even when admission ACK was lost.
        originals = [row for row in self.dut.originals
                     if row['step_id'] == binding.message_id]
        if (originals != [request]
                or self.dut.consumed_inputs.get(binding.message_id) != raw):
            raise Unavailable('SIMULATOR_DUT_ORIGINAL_NOT_OWNED')
        return raw, request

    def _request(self, binding):
        if not binding.message_id.startswith('c936-'):
            return None
        raw, request = self._claim(binding)
        native = request['native_input_utf8'].encode()

        def original(context):
            if context.scope != binding.scope:
                raise Unavailable('SIMULATOR_DUT_ORIGINAL_OWNER_CHANGED')
            stored = context.query_lio_message(binding.message_id)
            if stored is None or (
                    stored.receipt.run_id, stored.receipt.conversation_id,
                    stored.receipt.generation, stored.receipt.sequence) != (
                    binding.run_id, binding.conversation_id,
                    binding.generation, binding.message_sequence):
                raise Unavailable('SIMULATOR_DUT_ORIGINAL_RUN_CHANGED')
            # Legacy .2 stores normalized MESSAGE bytes. Compare the genuine
            # outer Lio receipt, not its different normalized storage digest.
            receipt = context.query_lio_receipt(binding.message_id)
            if receipt is None or receipt.input_sha256 != sha256(native).hexdigest():
                raise Unavailable('SIMULATOR_DUT_ORIGINAL_WIRE_CHANGED')

        self.dut.boundary.with_history_context(self.dut.token_supplier(), original)
        self.proved[binding] = raw
        return request

    def _current(self, binding):
        raw, _ = self._claim(binding)
        if self.proved.get(binding) != raw:
            raise Unavailable('SIMULATOR_DUT_ORIGINAL_CLAIM_CHANGED')
        # Called inside the native provider step: do not acquire another M
        # transaction or add +1 to a financial hold already owned by this call.
        self.dut.authority.require_current_operation(binding=self.dut.owner,
            pins_sha256=self.dut.specification.key, deadline=self.dut.deadline)

    def _guard(self, binding):
        try:
            self._current(binding)
        except BudgetUnknown:
            self.rejected.add(binding)
            raise
        except (Unavailable, Invalid, OSError, AccessBlocked, IdentityChanged) as error:
            self.rejected.add(binding)
            raise BudgetUnknown('original simulator operation unavailable') from error

    def _registration(self, binding, original):
        def prepare(argument):
            self._guard(binding)
            native = original.prepare_input(argument)

            def bind(operation, guard):
                if operation.binding != binding:
                    self.rejected.add(binding)
                    raise BudgetUnknown('original simulator operation binding changed')

                def checked():
                    self._guard(binding)
                    result = guard()
                    self._guard(binding)
                    return result

                self._guard(binding)
                return native.bind_operation(operation, checked)

            return replace(native, bind_operation=bind)

        return Registration(original.kind, prepare)

    def registrations(self, binding):
        try:
            request = self._request(binding)
            if request is None:
                return self.tools.registrations
            self._current(binding)
            return {name: self._registration(binding, registration)
                    for name, registration in self.tools.registrations.items()}
        except (Unavailable, Invalid, OSError, AccessBlocked, IdentityChanged, BudgetUnknown):
            self.rejected.add(binding)
            return {}

    def reflection(self, binding):
        # Reuse the worker's existing post-start seam to refuse an unqualified
        # namespace before planning/Memory/model work. No reflection is created.
        if binding.message_id.startswith('c936-'):
            if binding in self.rejected:
                raise BudgetUnknown('original simulator request unavailable; query only')
            self._guard(binding)
        return None

    def selects(self, binding):
        if binding not in self.proved:
            return False
        self._guard(binding)
        return True
