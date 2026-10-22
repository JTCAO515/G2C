"""Protected public-status codec: exact integer strings, never historical hash/charge."""
import json
from fastapi.responses import JSONResponse
from .generated import UsageAttemptStatus,UsageAttemptStatusResponse

def encode_response(raw,request_id,attempt_id):
    if type(raw) is not bytes:raise ValueError('Materialized original status required')
    data=json.loads(raw.decode('utf-8'))
    if type(data) is not dict or data['attempt_id']!=attempt_id:raise ValueError('Wrong original attempt')
    for name in ['reserved_units','confirmed_units','confirmed_output']:
        value=data[name]
        if value is None and name!='reserved_units':continue
        if type(value) is not int or value<0 or name=='reserved_units' and value<1:raise ValueError('Invalid unit count')
        data[name]=str(value)  # Exact integer rendering, not currency conversion or default zero.
    confirmed=[data['confirmed_units'],data['confirmed_output'],data['receipt_id']]
    if data['status']=='settled':
        if any(v is None for v in confirmed):raise ValueError('Missing original confirmed receipt')
    elif any(v is not None for v in confirmed):raise ValueError('Unconfirmed status cannot invent actual values')
    status=UsageAttemptStatus.model_validate_json(json.dumps(data),strict=True)
    return JSONResponse(UsageAttemptStatusResponse.model_validate({'request_id':request_id,'attempt':status}).model_dump(mode='json')).body
