"""Seven public reference bytes encoded into BASE only inside owner project lifetime."""
from fastapi.responses import JSONResponse
from .generated import OriginalUsageAssociation,OriginalUsageAssociationResponse

def encode_response(raw,request_id,message_id):
    if type(raw) is not bytes:raise ValueError('Materialized original references required')
    association=OriginalUsageAssociation.model_validate_json(raw,strict=True)
    if association.message_id!=message_id:raise ValueError('Original message changed')
    return JSONResponse(OriginalUsageAssociationResponse.model_validate({'request_id':request_id,'association':association}).model_dump(mode='json')).body
