"""One original message association GET; no attempt query/login/mint or mutation."""
from fastapi import Request
from fastapi.responses import JSONResponse,Response
from starlette.concurrency import run_in_threadpool
from .generated import OriginalUsageAssociationResponse
from .history_routes import _message_id_query
from .message_routes import _error,_sanitized_read,_token
from .original_usage_composition import OriginalUsageWireConfiguration
from .original_usage_projection import encode_response

def register_original_usage(app,reader=None,configuration=None,modules=None):
    if reader is None:
        if configuration is not None or modules is not None:raise ValueError('Complete association configuration required')
    elif type(configuration) is not OriginalUsageWireConfiguration or not modules or type(reader) is not modules['cj_run.original_usage_read'].OriginalUsageAssociationReader:
        raise ValueError('Fixed public association reader required')
    def unavailable(request):return _error(request,503,'ORIGINAL_USAGE_UNAVAILABLE','dependency','unknown','retry_safe_read')
    @app.get('/v1/message-usage-association',response_model=OriginalUsageAssociationResponse)
    async def read(request:Request):
        if reader is None:return unavailable(request)
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        mid=_message_id_query(request,configuration.max_message_id_bytes)
        if isinstance(mid,JSONResponse):return mid
        request_id=request.state.request_id
        def invoke():
            return reader.read_projected(token,mid,lambda raw:encode_response(raw,request_id,mid))
        try:return Response(content=await run_in_threadpool(_sanitized_read,invoke),media_type='application/json')
        except modules['cj_run.original_usage_read'].UsageAssociationTooLarge:
            return _error(request,413,'ASSOCIATION_TOO_LARGE','input','failed','retry_safe_read')
        except Exception:return unavailable(request)
