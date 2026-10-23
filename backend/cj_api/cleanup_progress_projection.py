"""Only the fixed five-field progress whitelist, encoded inside original context."""
from fastapi.responses import JSONResponse
from .generated import CurrentAccountCleanupProgress,CurrentAccountCleanupProgressResponse

def encode_response(raw,request_id,operation_id):
    if type(raw) is not bytes:raise ValueError('Materialized original progress required')
    progress=CurrentAccountCleanupProgress.model_validate_json(raw,strict=True)
    if progress.operation_id!=operation_id:raise ValueError('Wrong original operation')
    return JSONResponse(CurrentAccountCleanupProgressResponse.model_validate({'request_id':request_id,'progress':progress}).model_dump(mode='json')).body
