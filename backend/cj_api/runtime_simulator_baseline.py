"""Explicit legacy2 simulator input; candidate labels never select a protocol.

The original native4 private claim stays version1 and retains its exact bytes.
This additive version fixes actual .2 in its immutable pins and ordinary input.
It does not attest historical code equivalence or manufacture observations.
"""
import json
from cj_message.demo_dialogue import LIO_VERSION_V2
from cj_strict_json import compact
from .runtime_simulator_dut import DutSpecification


class BaselineDutSpecification(DutSpecification):
    @property
    def claim_version(self):
        return 'LIO-simulator-dut.2'

    @property
    def wire_version(self):
        return LIO_VERSION_V2

    @property
    def raw(self):
        return compact(dict(json.loads(super().raw), wire_version=self.wire_version),sort_keys=True)
