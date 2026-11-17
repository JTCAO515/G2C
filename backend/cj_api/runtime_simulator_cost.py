"""Native original charge evidence for the simulator's qualified lifecycle.

This reader neither dispatches nor settles anything. Its operation evidence is
not by itself a whole-episode certificate; the concrete host must close its real
producers and reconcile the original journal before publishing complete totals.
"""
from hashlib import sha256

from cj_usage.authorization_budget import CNY_SCALE, LIMITS, _price_receipt
from runtime_adapter.contract import Unavailable, decode, require


def original_charges(originals, token, message_id, role):
    """Verify every native operation, including a registered local zero-cost tool."""
    inventory_raw = originals.inventory(token, message_id)
    inventory = decode(inventory_raw)
    rows = []
    seen = set()
    for operation in inventory['operations']:
        op, attempt = operation['operation_id'], operation['attempt_id']
        require(attempt not in seen, 'SIMULATOR_DUPLICATE_NATIVE_ATTEMPT')
        seen.add(attempt)
        meter_raw = originals.meter(token, message_id, op)
        meter = decode(meter_raw)
        command = meter['command']
        require((command['attempt_id'], command['operation_id'], command['run_id']) ==
                (attempt, op, inventory['run_id']), 'SIMULATOR_NATIVE_METER_BINDING_CHANGED')
        logical = originals.input(token, message_id, op)
        require(command['kind'] == operation['kind'] and
                command['input_digest'] == sha256(logical).hexdigest(),
                'SIMULATOR_NATIVE_METER_INPUT_CHANGED')
        require(meter['state'] == 'settled' and meter['receipt'] is not None,
                'SIMULATOR_NATIVE_OPERATION_NOT_SETTLED')
        try:
            fee_raw = originals.fee(token, message_id, op)
            fee = decode(fee_raw)
        except Unavailable as error:
            if (str(error) != 'ORIGINAL_FINANCIAL_ATTEMPT_UNAVAILABLE'
                    or operation['registration_id'] != 'tool.visitor_fact'):
                raise
            # The original artifact reader verifies the code-owned local
            # catalogue receipt, exact Meter association and absent paid fee.
            raw = originals.artifact(token, message_id, op)
            artifact = decode(raw)
            require(artifact['receipt'].get('actual_cost_cny') == '0',
                    'SIMULATOR_LOCAL_ZERO_RECEIPT_REQUIRED')
            rows.append(dict(role=role, message_id=message_id, run_id=inventory['run_id'],
                operation_id=op, attempt_id=attempt, registration_id=operation['registration_id'],
                native_kind=operation['kind'], financial_kind=None, financial_attempt=False,
                financial_state='REGISTERED_LOCAL_ZERO', conservative_units=0,
                estimated_units=0, artifact_sha256=sha256(raw).hexdigest(), wire_sha256=None,
                meter_sha256=sha256(meter_raw).hexdigest(), fee_sha256=None))
            continue
        require(fee['attempt_id'] == attempt and fee['ledger_id'] == originals.budget.ledger_id
                and fee['kind'] in LIMITS and fee['state'] == 'RECEIVED'
                and fee['receipt_utf8'] is not None, 'SIMULATOR_ORIGINAL_FINANCIAL_RECEIPT_REQUIRED')
        require((command['kind'] in ('model', 'memory')) == (fee['kind'] == 'model'),
                'SIMULATOR_ORIGINAL_FINANCIAL_KIND_CHANGED')
        raw = originals.artifact(token, message_id, op)
        wire_sha = None
        if command['kind'] in ('model', 'memory'):
            wire = originals.artifact(token, message_id, op, wire_input=True)
            wire_sha = sha256(wire).hexdigest()
        estimate = _price_receipt(fee['kind'], fee['receipt_utf8'])
        conservative = LIMITS[fee['kind']][1] * CNY_SCALE if estimate is None else estimate
        rows.append(dict(role=role, message_id=message_id, run_id=inventory['run_id'],
            operation_id=op, attempt_id=attempt, registration_id=operation['registration_id'],
            native_kind=operation['kind'], financial_kind=fee['kind'], financial_attempt=True,
            financial_state=fee['state'], conservative_units=conservative,
            estimated_units=estimate, artifact_sha256=sha256(raw).hexdigest(),
            wire_sha256=wire_sha, meter_sha256=sha256(meter_raw).hexdigest(),
            fee_sha256=sha256(fee_raw).hexdigest()))
    return dict(message_id=message_id, run_id=inventory['run_id'], status=inventory['status'],
                inventory_sha256=sha256(inventory_raw).hexdigest(), operations=rows)


def recheck_charge_metadata(originals, token, report):
    """Recheck already captured evidence without reviving historical raw access.

    Actor raw input must be captured while its original DUT frame is current.
    Its hashes are accounting association data, never a later payload permit.
    """
    mid = report['message_id']
    require(sha256(originals.inventory(token, mid)).hexdigest() == report['inventory_sha256'],
            'SIMULATOR_CAPTURED_INVENTORY_CHANGED')
    for row in report['operations']:
        op = row['operation_id']
        require(sha256(originals.meter(token, mid, op)).hexdigest() == row['meter_sha256'],
                'SIMULATOR_CAPTURED_METER_CHANGED')
        if row['financial_attempt']:
            require(sha256(originals.fee(token, mid, op)).hexdigest() == row['fee_sha256'],
                    'SIMULATOR_CAPTURED_FINANCIAL_RECEIPT_CHANGED')
        else:
            try:
                originals.fee(token, mid, op)
            except Unavailable as error:
                if str(error) != 'ORIGINAL_FINANCIAL_ATTEMPT_UNAVAILABLE':
                    raise
            else:
                raise Unavailable('SIMULATOR_LOCAL_ZERO_GAINED_FINANCIAL_ATTEMPT')
