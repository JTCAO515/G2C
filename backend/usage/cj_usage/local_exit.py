"""Sole injectable candidate exit for foreground/background synthetic tests.

Not wired to host/Auth. Real provider execution is intentionally unavailable.
"""
from .core import Blocked


class LocalExit:
    def __init__(self, meter, synthetic_executor=None):
        self.meter = meter
        self.executor = synthetic_executor

    def execute(self, command):
        if self.executor is None:
            raise Blocked('provider_disabled')
        self.meter.reserve(command)
        claimed = self.meter.claim(command.attempt_id)
        # Exception/timeout/crash leaves the durable claim unknown, retaining reserve.
        receipt = self.executor(claimed.command)
        if receipt.attempt_id != command.attempt_id:
            raise Blocked('receipt_invalid')
        return self.meter.settle(receipt)
