"""Validate B-protected original evidence; never infer it from a model response."""
from .contract import VERSION, decode, digest, encode, hash256, label, raw_digest, require


def reference(value):
    require(type(value) is dict and set(value) == {'ref', 'sha256'}, 'ORIGINAL_REFERENCE')
    label(value['ref'])
    hash256(value['sha256'])
    return value


def check_snapshot(raw, *, request, binding, pins, original):
    """One external read boundary. Each inventory entry has original Meter and
    provider/fee references; a missing receipt retains UNKNOWN and its hold.
    `original` is B's owner-protected resolver, not a general file/HTTP loader.
    """
    require(type(raw) is bytes and len(raw) <= 2_097_152, 'EVIDENCE_BYTE_BOUND')
    s = decode(raw)
    fields = {'version', 'attempt_id', 'step_id', 'request_sha256', 'binding_sha256',
              'pins_sha256', 'status', 'message_id', 'run_ids', 'action_id',
              'action', 'inventory', 'operations', 'result', 'state_evidence'}
    require(type(s) is dict and set(s) == fields and s['version'] == VERSION, 'EVIDENCE_FIELDS')
    require(s['attempt_id'] == request['attempt_id'] and s['step_id'] == request['step_id'] and
            s['request_sha256'] == digest(request) and s['binding_sha256'] == binding.key and
            s['pins_sha256'] == pins.key, 'ORIGINAL_BINDING_MISMATCH')
    require(s['status'] in ('PASS', 'FAIL', 'UNKNOWN', 'UNRUN', 'CANCELLED', 'RUNNING'), 'EVIDENCE_STATUS')
    require(type(s['run_ids']) is list and len(s['run_ids']) <= 128, 'RUN_INVENTORY')
    for rid in s['run_ids']:
        label(rid)
    require(len(s['run_ids']) == len(set(s['run_ids'])), 'RUN_INVENTORY')
    for key in ('message_id', 'action_id'):
        require(s[key] is None or type(s[key]) is str and s[key], 'ORIGINAL_OPERATION_ID')
    if request['kind'] == 'lio_undo_current_trip':
        require(s['message_id'] is None and not s['run_ids'] and s['action_id'] is not None,
                'UNDO_MUST_NOT_FABRICATE_MESSAGE_RUN')
    elif request['kind'] in ('message', 'new_conversation_message', 'start_controlled_generation') and s['status'] not in ('UNRUN', 'UNKNOWN'):
        require(s['message_id'] is not None and s['run_ids'], 'MESSAGE_RUN_REQUIRED')

    def read(ref):
        reference(ref)
        body = original(ref['ref'])
        require(type(body) is bytes and len(body) <= 1_048_576 and raw_digest(body) == ref['sha256'],
                'ORIGINAL_HASH_MISMATCH')
        return body

    action = decode(read(s['action']))
    require(type(action) is dict and action.get('binding_sha256') == binding.key and
            action.get('client_step_id') == request['step_id'] and
            action.get('request_sha256') == digest(request) and
            action.get('message_id') == s['message_id'] and action.get('action_id') == s['action_id'],
            'ACTION_ORIGINAL_MISMATCH')
    inventory = decode(read(s['inventory']))
    require(type(inventory) is dict and inventory.get('binding_sha256') == binding.key and
            inventory.get('run_ids') == s['run_ids'] and type(inventory.get('operation_ids')) is list,
            'PROTECTED_INVENTORY_REQUIRED')
    require(type(s['operations']) is list and len(s['operations']) <= 2048, 'OPERATION_BOUND')
    identities = []
    provider_ids = []
    unsettled = False
    for op in s['operations']:
        require(type(op) is dict and set(op) == {'operation_id', 'attempt_id', 'run_id',
                'registration_id', 'kind', 'input', 'output', 'meter', 'provider', 'fee',
                'provider_state', 'meter_state', 'fee_state', 'model'}, 'OPERATION_FIELDS')
        for name in ('operation_id', 'attempt_id', 'registration_id'):
            label(op[name])
        identities.append(op['operation_id'])
        provider_ids.append(op['attempt_id'])
        require(op['run_id'] in s['run_ids'] and op['kind'] in ('model', 'tool', 'memory'), 'OPERATION_RUN')
        read(op['input'])
        meter = decode(read(op['meter']))
        require(type(meter) is dict and meter.get('attempt_id') == op['attempt_id'] and
                meter.get('operation_id') == op['operation_id'] and
                meter.get('binding_sha256') == binding.key and
                meter.get('status') == op['meter_state'], 'METER_ORIGINAL_MISMATCH')
        if op['provider_state'] == 'NOT_SENT':
            require(op['provider'] is None and op['fee'] is None and op['fee_state'] == 'NOT_SENT',
                    'UNSENT_PROVIDER_MUST_NOT_INVENT_RECEIPT')
        else:
            require(op['provider_state'] in ('RECEIVED', 'INTENT') and
                    op['fee_state'] in ('RECEIVED', 'INTENT'), 'PROVIDER_STATE')
            fee = decode(read(op['fee']))
            require(type(fee) is dict and fee.get('attempt_id') == op['attempt_id'] and fee.get('ledger_id') == binding.ledger_id
                    and fee.get('state') == op['fee_state'], 'SHARED_FEE_ORIGINAL_MISMATCH')
            if op['provider_state'] == 'RECEIVED':
                provider = decode(read(op['provider']))
                require(type(provider) is dict and provider.get('attempt_id') == op['attempt_id'] and
                        provider.get('input_sha256') == op['input']['sha256'] and
                        op['output'] is not None and provider.get('response_sha256') == op['output']['sha256'],
                        'PROVIDER_ORIGINAL_MISMATCH')
                read(op['output'])
            else:
                require(op['provider'] is None, 'INTENT_MUST_NOT_INVENT_RECEIPT')
        if op['kind'] in ('model', 'memory'):
            require(encode(op['model']) == encode(pins.value['model']), 'ACTUAL_MODEL_PIN_MISMATCH')
        unsettled |= op['provider_state'] == 'INTENT' or op['fee_state'] == 'INTENT' or op['meter_state'] != 'SETTLED'
    require(len(identities) == len(set(identities)) and identities == inventory['operation_ids'] and
            len(provider_ids) == len(set(provider_ids)), 'INCOMPLETE_OPERATION_INVENTORY')
    if request['kind'] == 'reflection':
        require(len(s['operations']) == 1 and s['operations'][0]['kind'] == 'model' and
                s['operations'][0]['registration_id'] == 'model.runtime_reflection.1',
                'REFLECTION_REGISTERED_MODEL_ONLY')
    require(type(s['state_evidence']) is list and len(s['state_evidence']) <= 256, 'STATE_PROOF_BOUND')
    for proof in s['state_evidence']:
        read(proof)
    result = None if s['result'] is None else decode(read(s['result']))
    status = 'UNKNOWN' if unsettled or s['status'] in ('UNKNOWN', 'RUNNING') else s['status']
    return dict(status=status, source_status=s['status'], snapshot=s, result=result)
