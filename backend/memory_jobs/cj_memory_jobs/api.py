"""Explicit local host routes; the host injects the sole canonical Service."""
from fastapi import Request
from fastapi.responses import Response
from psycopg import Error as DatabaseError
from starlette.concurrency import run_in_threadpool

from cj_auth.interfaces import AdmissionReason, AdmissionStatus
from cj_message.auth_boundary import AccessBlocked, IdentityChanged
from cj_message.domain import (Unavailable as MessageUnavailable, InvalidInput as MessageInvalidInput,
                               CommitUnknown as MessageCommitUnknown)
from cj_message.travel_reference import Denied as ContextDenied,LeaseUnavailable as ContextUnavailable
from cj_memory.domain import (Unavailable as MemoryUnavailable, CommitUnknown as MemoryCommitUnknown,
                              Conflict as MemoryConflict)
from cj_api.message_routes import BodyError, _body_error, _error, _read_body, _token, _query_pairs
from .codec import Conflict, InvalidInput, Unavailable
from .service import OperationWithheld
from .extraction import CollectionUnavailable


def register_routes(app, service, *, collection=False):
    """No model/worker dispatch route, policy resolver or client owner field."""
    async def invoke(request, operation, fields=()):
        token = _token(request)
        if token is None:
            return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        write = operation in ('consent','enqueue','enqueue_ending','candidate_action')
        try:
            if write:
                if request.scope['query_string']:
                    raise InvalidInput('unexpected history query')
                raw = await _read_body(request,32768)
                if operation=='consent':call=service.apply_consent
                elif operation=='enqueue':call=service.enqueue
                elif operation=='enqueue_ending':call=service.enqueue_ending
                else:call=service.apply_candidate
                encoded = await run_in_threadpool(call,token,raw,request_id=request.state.request_id)
            else:
                try:
                    pairs = _query_pairs(request)
                except (ValueError,UnicodeError):
                    raise InvalidInput('invalid history query encoding') from None
                values = dict(pairs)
                if (set(values) != set(fields) or len(pairs) != len(values)
                        or any((not v.strip() and not (operation=='candidate_jobs' and k=='after_job_id' and v==''))
                               or len(v)>4096 for k,v in values.items())):
                    raise InvalidInput('exact history query required')
                calls = {'consent_query':service.query_consent_action,
                         'settings':service.settings,'job_query':service.query_original}
                if collection:
                    calls.update(candidates=service.candidates,candidate_receipt=service.query_candidate_action,
                                 publication_receipt=service.query_publication,
                                 publication_receipt_v2=service.query_publication_v2,
                                 publication_items_v2=service.publication_items_v2,
                                 candidate_jobs=service.discover_candidate_jobs)
                call = calls[operation]
                encoded = await run_in_threadpool(call,token,**values,request_id=request.state.request_id)
            return Response(encoded,media_type='application/json')
        except BodyError as error:
            return _body_error(request,error)
        except (InvalidInput,MessageInvalidInput):
            return _error(request,400,'INVALID_HISTORY_INPUT','input','failed','do_not_retry')
        except (Conflict,MemoryConflict):
            return _error(request,409,'MEMORY_HISTORY_CONFLICT','conflict','failed','do_not_retry')
        except AccessBlocked as error:
            if error.status is AdmissionStatus.UNKNOWN:
                return _error(request,503,'ACCESS_UNKNOWN','access','unknown','retry_safe_read')
            status = 401 if error.reason is AdmissionReason.IDENTITY_INVALID else 403
            return _error(request,status,'ACCESS_DENIED','access','failed','do_not_retry')
        except OperationWithheld:
            return _error(request,503,'MEMORY_HISTORY_UNKNOWN','dependency','unknown','reconcile_original')
        except (MemoryCommitUnknown,MessageCommitUnknown):
            return _error(request,503,'MEMORY_HISTORY_UNKNOWN','dependency','unknown',
                          'reconcile_original' if write else 'retry_safe_read')
        except (IdentityChanged,Unavailable,MessageUnavailable,MemoryUnavailable,CollectionUnavailable,
                ContextDenied,ContextUnavailable,DatabaseError):
            return _error(request,503,'MEMORY_HISTORY_UNAVAILABLE','dependency',
                          'unknown' if write else 'failed',
                          'reconcile_original' if write else 'retry_safe_read')

    @app.post('/v3/memory-history-actions')
    async def consent(request: Request):
        return await invoke(request,'consent')

    @app.get('/v3/memory-history-receipts')
    async def consent_query(request: Request):
        return await invoke(request,'consent_query',('action_id',))

    @app.get('/v3/memory-history-settings')
    async def settings(request: Request):
        return await invoke(request,'settings',('conversation_id',))

    @app.post('/internal/v1/memory-history/jobs')
    async def enqueue(request: Request):
        return await invoke(request,'enqueue')

    @app.get('/internal/v1/memory-history/jobs')
    async def original(request: Request):
        return await invoke(request,'job_query',('job_id','attempt_id'))

    @app.post('/internal/v1/memory-ending/jobs')
    async def enqueue_ending(request: Request):
        return await invoke(request,'enqueue_ending')

    if collection:
        @app.get('/v5/memory-candidate-jobs')
        async def candidate_jobs(request: Request):
            return await invoke(request,'candidate_jobs',('conversation_id','after_job_id'))

        @app.get('/v3/memory-candidates')
        async def candidates(request: Request):
            return await invoke(request,'candidates',('job_id','attempt_id'))

        @app.post('/v3/memory-candidate-actions')
        async def decide(request: Request):
            return await invoke(request,'candidate_action')

        @app.get('/v3/memory-candidate-receipts')
        async def decision_receipt(request: Request):
            return await invoke(request,'candidate_receipt',('action_id',))

        @app.get('/v3/memory-publication-receipts')
        async def publication_receipt(request: Request):
            return await invoke(request,'publication_receipt',('job_id','attempt_id'))

        @app.get('/v4/memory-publication-receipts')
        async def publication_receipt_v2(request: Request):
            return await invoke(request,'publication_receipt_v2',('job_id','attempt_id'))

        @app.get('/v4/memory-publication-items')
        async def publication_items_v2(request: Request):
            return await invoke(request,'publication_items_v2',('job_id','attempt_id'))
