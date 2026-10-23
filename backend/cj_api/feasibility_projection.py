"""Validate official model without regenerating the original report bytes."""
import json
from .generated import FeasibilityCurrentReport,FeasibilityCurrentResponse

def encode_response(raw,request_id,needs_id,max_bytes):
    if type(raw) is not bytes:raise ValueError('Materialized source report required')
    value=FeasibilityCurrentReport.model_validate_json(raw,strict=True)
    if value.needs_id!=needs_id:raise ValueError('Wrong original NEEDS record')
    # Validation only; preserve every original projected JSON byte inside the envelope.
    encoded=b'{"request_id":'+json.dumps(request_id).encode('ascii')+b',"evaluation":'+raw+b'}'
    if len(encoded)>max_bytes:raise ValueError('Complete BASE bound exceeded')
    FeasibilityCurrentResponse.model_validate_json(encoded,strict=True)
    return encoded
