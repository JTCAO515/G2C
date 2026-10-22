"""Known missing cross-instance durable binding: originally FAIL; now must reject a replacement.

Run with the same --usage-repo argument as usage_composition_checks.py.
The old FAIL log is retained. This regression does not enable a real executor.
"""
from dataclasses import replace
from usage_composition_checks import CompositionTests, SyntheticFirstStep, ReconcileOriginal, Conflict
case=CompositionTests()
case.setUp()
claim=case.meter.claim

def lost(identity):
    claim(identity)
    raise OSError('synthetic claim ACK lost')
case.meter.claim=lost
try:
    case.go()
except ReconcileOriginal:
    pass
case.meter.claim=claim
# Deliberately violate original-action provenance by creating a new fixture bound
# to a replacement attempt. There is no canonical durable fence to reject it.
replacement=replace(case.command,attempt_id='replacement')
new=SyntheticFirstStep(case.run,case.meter,original_binding=case.b,
                       original_command=replacement,original_input_bytes=case.input_bytes,synthetic_executor=case.execute)
try:
    new.execute_fixture(case.b,replacement,case.start)
except (ReconcileOriginal, Conflict):
    pass
print('regression: replacement executor calls=',len(case.calls),flush=True)
assert len(case.calls)==0, 'original attempt must survive reconstruction'
print('PASS: replaced attempt rejected by original stored association; real cross-domain fence still HOLD')
