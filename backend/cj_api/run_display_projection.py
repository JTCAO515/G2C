"""Pure formal codec; caller MUST execute this inside producer projection lifetime."""
from fastapi.responses import JSONResponse
from .generated import RunDisplaySnapshot,RunDisplayResponse

def encode_response(original_snapshot,request_id):
    if type(original_snapshot) is not bytes:raise ValueError('Materialized snapshot bytes required')
    snapshot=RunDisplaySnapshot.model_validate_json(original_snapshot,strict=True)
    expected='complete' if snapshot.status.value=='completed' else 'partial'
    if snapshot.text_state.value!=expected:raise ValueError('Invalid display completion state')
    return JSONResponse(RunDisplayResponse.model_validate({'request_id':request_id,'snapshot':snapshot}).model_dump(mode='json')).body
