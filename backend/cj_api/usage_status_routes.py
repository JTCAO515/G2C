"""Readonly original-attempt status, final encoded bytes within AUTH/USAGE lifetime."""
from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from .generated import UsageAttemptStatusResponse
from .history_routes import _query
from .message_routes import _error,_token
from .usage_status_composition import UsageStatusConfiguration
from .usage_status_projection import encode_response

class UsageReadInterrupted(Exception):pass

def register_usage_status(app,configuration=None,dependencies=None):
    if dependencies is None:
        if configuration is not None:raise ValueError('Complete USAGE read configuration required')
    elif type(configuration) is not UsageStatusConfiguration or type(dependencies) is not tuple or len(dependencies)!=4:
        raise ValueError('Canonical USAGE read dependencies required')
    modules=dependencies[3] if dependencies else None
    def unavailable(request):return _error(request,503,'USAGE_STATUS_UNAVAILABLE','dependency','unknown','retry_safe_read')
    @app.get('/v1/usage-attempt-status',response_model=UsageAttemptStatusResponse)
    async def read(request:Request):
        if dependencies is None:return unavailable(request)
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        try:
            query=_query(request,('attempt_id',));aid=query['attempt_id']
            modules['cj_usage.core'].label(aid)
            if len(aid.encode('utf-8'))>configuration.max_attempt_id_bytes:
                return _error(request,413,'ATTEMPT_ID_TOO_LARGE','input','failed','do_not_retry')
        except (ValueError,UnicodeError,modules['cj_usage.core'].Blocked):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        request_id=request.state.request_id
        def invoke():
            checker,resolver,host,_=dependencies
            # Public AUTH boundary is one-active-context per instance. Use one
            # native instance per HTTP read, with the same canonical host checker.
            boundary=modules['cj_auth.read_context'].ProtectedReadBoundary(checker,max_response_bytes=host.max_response_bytes)
            reader=modules['cj_usage.protected_status'].AttemptStatusReader(boundary,resolver,configuration=host)
            try:return reader.read(token,aid,project=lambda minimal:encode_response(minimal,request_id,aid))
            except BaseException as exc:
                if isinstance(exc,Exception):raise
                raise UsageReadInterrupted() from None
        try:
            encoded=await run_in_threadpool(invoke)
            return Response(content=encoded,media_type='application/json')
        except modules['cj_auth.read_context'].ReadAdmissionFailure as exc:
            auth=modules['cj_auth.interfaces']
            if exc.status is auth.AdmissionStatus.DENIED:
                return _error(request,401 if exc.reason is auth.AdmissionReason.IDENTITY_INVALID else 403,'ACCESS_DENIED','access','failed','do_not_retry')
            return _error(request,503,'ACCESS_UNKNOWN','access','unknown','retry_safe_read')
        except Exception:return unavailable(request)
