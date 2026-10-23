"""Existing operation progress GET for CURRENT valid account only, no recovery."""
from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from .generated import CurrentAccountCleanupProgressResponse
from .history_routes import _query
from .message_routes import _error,_token
from .cleanup_progress_composition import CleanupProgressConfiguration
from .cleanup_progress_projection import encode_response

class CleanupReadInterrupted(Exception):pass

def register_cleanup_progress(app,configuration=None,dependencies=None):
    if dependencies is None:
        if configuration is not None:raise ValueError('Complete progress configuration required')
    elif type(configuration) is not CleanupProgressConfiguration or type(dependencies) is not tuple or len(dependencies)!=4:
        raise ValueError('Canonical progress dependencies required')
    modules=dependencies[3] if dependencies else None
    def unavailable(request):return _error(request,503,'CLEANUP_PROGRESS_UNAVAILABLE','dependency','unknown','retry_safe_read')
    @app.get('/v1/account-cleanup-progress',response_model=CurrentAccountCleanupProgressResponse)
    async def read(request:Request):
        if dependencies is None:return unavailable(request)
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        try:
            oid=_query(request,('operation_id',))['operation_id'];modules['cj_cleanup.core'].identifier(oid)
        except (ValueError,UnicodeError,modules['cj_cleanup.core'].Invalid):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        request_id=request.state.request_id
        def invoke():
            checker,resolve,host,_=dependencies
            boundary=modules['cj_auth.read_context'].ProtectedReadBoundary(checker,max_response_bytes=host.max_response_bytes)
            reader=modules['cj_cleanup.protected_progress'].ProgressReader(boundary,resolve,configuration=host)
            try:return reader.read(token,oid,project=lambda raw:encode_response(raw,request_id,oid))
            except BaseException as exc:
                if isinstance(exc,Exception):raise
                raise CleanupReadInterrupted() from None
        try:return Response(content=await run_in_threadpool(invoke),media_type='application/json')
        except modules['cj_auth.read_context'].ReadAdmissionFailure as exc:
            auth=modules['cj_auth.interfaces']
            if exc.status is auth.AdmissionStatus.DENIED:
                return _error(request,401 if exc.reason is auth.AdmissionReason.IDENTITY_INVALID else 403,'ACCESS_DENIED','access','failed','do_not_retry')
            return _error(request,503,'ACCESS_UNKNOWN','access','unknown','retry_safe_read')
        except Exception:return unavailable(request)
