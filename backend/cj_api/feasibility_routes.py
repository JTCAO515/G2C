"""Current NEEDS-only protected evaluation; no caller projector, write or solver."""
from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from .generated import FeasibilityCurrentResponse
from .history_routes import _query
from .message_routes import _error,_token
from .feasibility_composition import CandidateDependencies
from .feasibility_projection import encode_response

class EvaluationInterrupted(Exception):pass

def register_feasibility(app,dependencies=None):
    if dependencies is not None and type(dependencies) is not CandidateDependencies:
        raise ValueError('Explicit canonical candidate dependencies required')
    modules=dependencies.modules if dependencies else None
    def unavailable(request,code='FEASIBILITY_UNAVAILABLE'):
        return _error(request,503,code,'dependency','unknown','retry_safe_read')
    @app.get('/v1/needs-feasibility',response_model=FeasibilityCurrentResponse)
    async def read(request:Request):
        if dependencies is None:return unavailable(request)
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        try:
            needs_id=_query(request,('needs_id',))['needs_id'];modules['cj_needs.domain'].identifier(needs_id)
        except (ValueError,UnicodeError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        request_id=request.state.request_id
        def invoke():
            d=dependencies
            auth=modules['cj_auth.read_context'].ProtectedReadBoundary(d.checker,max_response_bytes=d.configuration.max_response_bytes)
            reader=modules['cj_needs.protected_read'].ProtectedReader(auth,d.resolve,configuration=d.host)
            def project(operation,context):
                raw=modules['cj_feasibility.current_read'].project_current(operation,context,needs_id,limits=d.limits)
                return encode_response(raw,request_id,needs_id,d.configuration.max_response_bytes)
            try:return reader.read(token,project)
            except BaseException as exc:
                if isinstance(exc,Exception):raise
                raise EvaluationInterrupted() from None
        try:return Response(content=await run_in_threadpool(invoke),media_type='application/json')
        except modules['cj_auth.read_context'].ReadAdmissionFailure as exc:
            auth=modules['cj_auth.interfaces']
            if exc.status is auth.AdmissionStatus.DENIED:
                return _error(request,401 if exc.reason is auth.AdmissionReason.IDENTITY_INVALID else 403,'ACCESS_DENIED','access','failed','do_not_retry')
            return _error(request,503,'ACCESS_UNKNOWN','access','unknown','retry_safe_read')
        except modules['cj_feasibility.current_read'].ReadWithheld as exc:
            return unavailable(request,'FEASIBILITY_INPUT_INVALID' if exc.code=='EVALUATION_INPUT_INVALID' else 'FEASIBILITY_UNAVAILABLE')
        except Exception:return unavailable(request)
