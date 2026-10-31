"""One read-only original-message snapshot; private JSON never encoded after guard."""
from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from .generated import RunDraftStatusResponse, RunDraftStatusV2Response,RunDraftStatusV3Response
from .history_routes import _query
from .message_routes import _error,_token
from .run_display_composition import RunDisplayWireConfiguration

class DisplayReadInterrupted(Exception):
    pass

def register_run_draft_status_route(app,reader=None,configuration=None,modules=None):
    if reader is None:
        if configuration is not None or modules is not None:raise ValueError('Complete display configuration required')
    elif (type(configuration) is not RunDisplayWireConfiguration or not modules
            or type(reader) is not modules['cj_run.display_snapshot'].DisplaySnapshotReader):
        raise ValueError('Pinned protected display reader required')
    def unavailable(request):return _error(request,503,'RUN_DRAFT_STATUS_UNAVAILABLE','dependency','unknown','retry_safe_read')
    async def read(request:Request, *, version):
        if reader is None:return unavailable(request)
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        try:
            query=_query(request,('message_id',));mid=query['message_id']
            if not mid.strip() or '\x00' in mid:raise ValueError('Invalid original message ID')
            if len(mid.encode('utf-8'))>configuration.max_message_id_bytes:
                return _error(request,413,'MESSAGE_ID_TOO_LARGE','input','failed','do_not_retry')
        except (ValueError,UnicodeError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        request_id=request.state.request_id
        def invoke():
            try:
                if version==4:return reader.read_draft_status_v4(token,mid,request_id)
                if version==3:return reader.read_draft_status_v3(token,mid,request_id)
                return (reader.read_draft_status_v2(token,mid,request_id) if version==2
                        else reader.read_draft_status(token,mid,request_id))
            except BaseException as exc:
                if isinstance(exc,Exception):raise
                # Only interruptions originating inside the synchronous reader are
                # sanitized. Cancellation of the outer HTTP await still propagates.
                raise DisplayReadInterrupted() from None
        try:
            body=await run_in_threadpool(invoke)
            return Response(content=body,media_type='application/json')
        except modules['cj_run.display_snapshot'].SnapshotTooLarge:
            return _error(request,413,'RUN_DRAFT_STATUS_TOO_LARGE','input','failed','retry_safe_read')
        except Exception:return unavailable(request)

    @app.get('/v1/run-draft-status',response_model=RunDraftStatusResponse)
    async def read_v1(request:Request): return await read(request,version=1)

    @app.get('/v2/run-draft-status',response_model=RunDraftStatusV2Response)
    async def read_v2(request:Request): return await read(request,version=2)

    @app.get('/v3/run-draft-status',response_model=RunDraftStatusV3Response)
    async def read_v3(request:Request): return await read(request,version=3)

    @app.get('/v4/run-draft-status')
    async def read_v4(request:Request):return await read(request,version=4)
