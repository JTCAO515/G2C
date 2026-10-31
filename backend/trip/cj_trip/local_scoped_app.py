"""Local scoped diff/explicit action API; canonical AUTH and original act only."""
import json,os
from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from cj_api.app import create_app
from cj_api.message_routes import _token,_error
from cj_api.local_app import scope_for
from .auth_boundary import Boundary
from .scoped_actions import ScopedAction,ScopedActions
from .domain import Conflict,Denied,identifier
from cj_agent.draft import trip_scope_for


def create_local_scoped_app(*,database,configuration,max_response_bytes=4_000_000):
    from cj_api.composition import CompositionUnavailable
    if (os.environ.get('CJ_ENV')!='local' or database.edit_configuration is not configuration
            or type(max_response_bytes) is not int or max_response_bytes<1):raise CompositionUnavailable('explicit local C scoped host required')
    publisher=configuration.publisher;checker=publisher.checker
    def resolve(principal):
        owner=scope_for(principal.issuer,principal.subject)
        return lambda:database.connect(owner),trip_scope_for(owner)
    class ScopedBoundary(Boundary):
        def _bind(self,token):
            repository,principal,guard=super()._bind(token)
            actions=ScopedActions(database,configuration,token,checker);repository.scoped_actions=actions
            def check(stage):
                guard(stage)
                if repository.scoped_actions is not actions:raise Denied('scoped action binding changed')
            return repository,principal,check
    boundary=ScopedBoundary(checker,resolve,publisher.confirmation,structured=True);app=create_app()
    def receipt(value):return None if value is None else dict(action_id=value.action_id,kind=value.kind,proposal_id=value.proposal_id,
        candidate_hash=value.candidate_hash,trip_id=value.trip_id,committed_version=value.committed_version)
    async def invoke(request,kind,arg):
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        def operation():
            def project(ctx):
                result=dict(version='TRIP-scoped-result.1',request_id=request.state.request_id)
                if kind=='action':result['receipt']=receipt(ctx.act_scoped(ScopedAction.parse(arg)))
                elif kind=='receipt':result['receipt']=receipt(ctx.scoped_receipt(arg))
                else:
                    detail,rows=ctx.scoped_detail(arg);p=detail.proposal
                    result['proposal']=dict(proposal_id=p.proposal_id,trip_id=p.trip_id,expected_version=p.expected_version,
                        candidate_hash=detail.candidate_hash,status=detail.status,expires_at=p.expires_at,content=json.loads(p.content),
                        scope=json.loads(rows[0]),diff=json.loads(rows[1]),feasibility=json.loads(rows[2]))
                raw=json.dumps(result,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
                if len(raw)>max_response_bytes:raise Denied('bounded private response required')
                return raw
            return boundary.with_operation(token,project)
        try:return Response(content=await run_in_threadpool(operation),media_type='application/json')
        except Conflict:return _error(request,409,'TRIP_CONFLICT','conflict','failed','do_not_retry')
        except (ValueError,UnicodeError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        except Exception:return _error(request,503,'TRIP_OUTCOME_UNKNOWN' if kind=='action' else 'TRIP_UNAVAILABLE',
            'dependency','unknown','reconcile_original' if kind=='action' else 'retry_safe_read')
    async def read(request,kind,key):
        values=list(request.query_params.multi_items())
        try:
            if len(values)!=1 or values[0][0]!=key:raise ValueError('exact original query required')
            identifier(values[0][1])
        except ValueError:return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        return await invoke(request,kind,values[0][1])
    @app.get('/v1/trip-scoped-proposals')
    async def proposal(request:Request):return await read(request,'proposal','proposal_id')
    @app.get('/v1/trip-scoped-action-receipts')
    async def original(request:Request):return await read(request,'receipt','action_id')
    @app.post('/v1/trip-scoped-actions')
    async def action(request:Request):
        media=request.headers.getlist('content-type')
        if request.query_params or len(media)!=1 or media[0].split(';')[0].strip().lower()!='application/octet-stream' or request.headers.get('content-encoding','identity').lower()!='identity':
            return _error(request,415,'UNSUPPORTED_MEDIA_TYPE','input','failed','do_not_retry')
        chunks=[];size=0
        async for value in request.stream():
            size+=len(value)
            if size>32768:return _error(request,413,'BODY_TOO_LARGE','input','failed','do_not_retry')
            chunks.append(value)
        return await invoke(request,'action',b''.join(chunks))
    return app
