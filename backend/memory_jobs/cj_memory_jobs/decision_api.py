"""Explicit local signed decision jobs; no provider/dispatch route."""
from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from psycopg import Error as DatabaseError
from cj_api.message_routes import _token,_error,_read_body,_body_error,BodyError,_query_pairs
from cj_message.auth_boundary import AccessBlocked,IdentityChanged
from cj_auth.interfaces import AdmissionStatus
from cj_trip.domain import Denied as TripDenied,Conflict as TripConflict
from cj_message.domain import Unavailable as MessageUnavailable
from cj_memory.domain import Unavailable as MemoryUnavailable,Conflict as MemoryConflict
from .codec import InvalidInput,Conflict,Unavailable
from .service import OperationWithheld


def register(app,service):
    async def invoke(request,*,write=False):
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        try:
            if write:
                if request.scope['query_string']:raise InvalidInput('unexpected decision query')
                raw=await _read_body(request,32768)
                result=await run_in_threadpool(service.enqueue_decision,token,raw,request_id=request.state.request_id)
            else:
                try:pairs=_query_pairs(request)
                except (ValueError,UnicodeError) as error:raise InvalidInput('invalid query encoding') from error
                values=dict(pairs)
                if set(values)!={'job_id','attempt_id'} or len(pairs)!=len(values):raise InvalidInput('exact original decision query required')
                result=await run_in_threadpool(service.query_decision_publication,token,values['job_id'],values['attempt_id'],
                                               request_id=request.state.request_id)
            return Response(result,media_type='application/json')
        except BodyError as error:return _body_error(request,error)
        except InvalidInput:return _error(request,400,'INVALID_DECISION_INPUT','input','failed','do_not_retry')
        except (Conflict,TripConflict,MemoryConflict):return _error(request,409,'MEMORY_DECISION_CONFLICT','conflict','failed','do_not_retry')
        except AccessBlocked as error:
            return _error(request,503 if error.status is AdmissionStatus.UNKNOWN else 403,'ACCESS_UNKNOWN' if error.status is AdmissionStatus.UNKNOWN else 'ACCESS_DENIED',
                          'access','unknown' if error.status is AdmissionStatus.UNKNOWN else 'failed','retry_safe_read')
        except OperationWithheld:return _error(request,503,'MEMORY_DECISION_UNKNOWN','dependency','unknown','reconcile_original')
        except (Unavailable,TripDenied,IdentityChanged,DatabaseError,MessageUnavailable,MemoryUnavailable):
            return _error(request,503,'MEMORY_DECISION_UNAVAILABLE','dependency','unknown' if write else 'failed',
                          'reconcile_original' if write else 'retry_safe_read')

    @app.post('/internal/v1/memory-decision/jobs')
    async def enqueue(request:Request):return await invoke(request,write=True)
    @app.get('/internal/v3/memory-decision/publications')
    async def original(request:Request):return await invoke(request)
