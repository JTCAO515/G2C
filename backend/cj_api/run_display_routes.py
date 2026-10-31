"""One read-only original-message snapshot; private JSON never encoded after guard."""
from fastapi import Request
from fastapi.responses import JSONResponse,Response
from starlette.concurrency import run_in_threadpool
from .generated import RunDisplayResponse,RunDisplayV2Response
from .history_routes import _message_id_query
from .message_routes import _error,_sanitized_read,_token
from .run_display_composition import RunDisplayWireConfiguration
from .run_display_projection import encode_response

def register_run_display_route(app,reader=None,configuration=None,modules=None):
    if reader is None:
        if configuration is not None or modules is not None:raise ValueError('Complete display configuration required')
    elif (type(configuration) is not RunDisplayWireConfiguration or not modules
            or type(reader) is not modules['cj_run.display_snapshot'].DisplaySnapshotReader):
        raise ValueError('Pinned protected display reader required')
    def unavailable(request):return _error(request,503,'RUN_DISPLAY_UNAVAILABLE','dependency','unknown','retry_safe_read')
    async def read_version(request:Request, *, version):
        if reader is None:return unavailable(request)
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        mid=_message_id_query(request,configuration.max_message_id_bytes)
        if isinstance(mid,JSONResponse):return mid
        request_id=request.state.request_id
        def invoke():
            if version==4:return reader.read_edit_display(token,mid,request_id)
            if version==3:return reader.read_trip_display(token,mid,request_id)
            if version==2:return reader.read_travel_display(token,mid,request_id)
            return reader.read_projected(token,mid,lambda nine:encode_response(nine,request_id))
        try:
            body=await run_in_threadpool(_sanitized_read,invoke)
            return Response(content=body,media_type='application/json')
        except modules['cj_run.display_snapshot'].SnapshotTooLarge:
            return _error(request,413,'RUN_DISPLAY_TOO_LARGE','input','failed','retry_safe_read')
        except Exception:return unavailable(request)

    @app.get('/v1/run-display',response_model=RunDisplayResponse)
    async def read(request:Request):return await read_version(request,version=1)

    @app.get('/v2/run-display',response_model=RunDisplayV2Response)
    async def read_v2(request:Request):return await read_version(request,version=2)

    @app.get('/v3/run-display')
    async def read_v3(request:Request):return await read_version(request,version=3)

    @app.get('/v4/run-display')
    async def read_v4(request:Request):return await read_version(request,version=4)
