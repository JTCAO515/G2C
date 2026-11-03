"""Candidate explicit signed item delete API; final bytes remain in identity callback."""
from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from psycopg import Error as DatabaseError
from cj_api.message_routes import _token,_error,_read_body,_query_pairs,_body_error,BodyError
from cj_message.auth_boundary import AccessBlocked,IdentityChanged
from cj_auth.interfaces import AdmissionStatus
from cj_memory.domain import InvalidInput,Conflict,Unavailable
from cj_memory_jobs.codec import Unavailable as HistoryUnavailable
from cj_memory_jobs.service import OperationWithheld
from cj_cleanup.core import Denied,Conflict as CleanupConflict
from cj_cleanup.postgres import Unavailable as CleanupUnavailable


def register(app,service):
    async def invoke(request,write):
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        try:
            if write:
                if request.scope['query_string']:raise InvalidInput('unexpected delete query')
                raw=await _read_body(request,32768)
                result=await run_in_threadpool(service.delete,token,raw,request_id=request.state.request_id)
            else:
                try:pairs=_query_pairs(request)
                except (ValueError,UnicodeError) as error:raise InvalidInput('invalid delete query encoding') from error
                if len(pairs)!=1 or pairs[0][0]!='action_id':raise InvalidInput('exact original action ID required')
                result=await run_in_threadpool(service.progress,token,pairs[0][1],request_id=request.state.request_id)
            return Response(result,media_type='application/json')
        except BodyError as error:return _body_error(request,error)
        except InvalidInput:return _error(request,400,'INVALID_ERASURE_INPUT','input','failed','do_not_retry')
        except (Conflict,CleanupConflict):return _error(request,409,'ERASURE_CONFLICT','conflict','failed','reconcile_original')
        except AccessBlocked as error:
            unknown=error.status is AdmissionStatus.UNKNOWN
            return _error(request,503 if unknown else 403,'ACCESS_UNKNOWN' if unknown else 'ACCESS_DENIED','access',
                          'unknown' if unknown else 'failed','retry_safe_read')
        except OperationWithheld:return _error(request,503,'ERASURE_OUTCOME_UNKNOWN','dependency','unknown','reconcile_original')
        except (Unavailable,HistoryUnavailable,IdentityChanged,Denied,CleanupUnavailable,DatabaseError):
            return _error(request,503,'ERASURE_UNAVAILABLE','dependency','unknown','reconcile_original' if write else 'retry_safe_read')
    @app.post('/v1/memory-erasures')
    async def delete(request:Request):return await invoke(request,True)
    @app.get('/v1/memory-erasure-progress')
    async def progress(request:Request):return await invoke(request,False)
