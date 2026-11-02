"""Appended source-bound manual.2 HTTP host, original operation/Signer/act only."""
import json,os
from pathlib import Path
from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from cj_api.app import create_app
from cj_api.local_app import LocalDatabase,scope_for
from cj_api.local_account_admission_v2 import account_checker_for
from cj_api.local_needs import protected_reader
from cj_api.message_routes import _token,_error
from .auth_boundary import Boundary
from .confirmation import ConfirmationSigner
from .current_needs_source import CurrentNeedsSource
from .manual_needs_v2 import NeedsEditV2,NeedsSaveV2,NeedsEditsV2
from .domain import Conflict,Denied,identifier
from .scoped_discovery import parse_discovery_query
from cj_agent.draft import trip_scope_for


def create_local_place_manual_app(*,conninfo_path,auth_dir,run_context,confirmation_signer,max_response_bytes=1_000_000):
    from cj_api.composition import CompositionUnavailable
    if (os.environ.get('CJ_ENV')!='local' or run_context is None or type(confirmation_signer) is not ConfirmationSigner
            or type(max_response_bytes) is not int or max_response_bytes<1):raise CompositionUnavailable('explicit local source-bound manual host required')
    database=LocalDatabase(conninfo_path,run_context=run_context,travel_context=True,needs_context=True)
    checker=account_checker_for(Path(auth_dir),database)
    def resolve(principal):
        owner=scope_for(principal.issuer,principal.subject)
        return lambda:database.connect(owner),trip_scope_for(owner)
    class PlaceManualBoundary(Boundary):
        def _bind(self,token):
            repository,principal,guard=super()._bind(token)
            from cj_auth.interfaces import AdmissionStatus
            from cj_message.travel_reference import MessageContextAuthority
            from cj_draft.needs_local import publisher
            from .needs_action_store import NeedsActions
            owner=scope_for(principal.issuer,principal.subject)
            def admit():
                decision=checker.check(token)
                if decision.status is not AdmissionStatus.ALLOWED or decision.principal!=principal:raise Denied('source admission changed')
                return decision.principal
            authority=MessageContextAuthority(database.message_repository(owner),admit)
            actions=NeedsActions(database,owner,publisher(database,checker,authority,lambda:token,owner).source)
            repository.needs_actions=actions
            service=NeedsEditsV2(CurrentNeedsSource(database,checker,token,protected_reader(database,checker)))
            repository.needs_edits=service
            def check(stage):
                guard(stage)
                if repository.needs_edits is not service or repository.needs_actions is not actions:raise Denied('manual source binding changed')
            return repository,principal,check
    boundary=PlaceManualBoundary(checker,resolve,confirmation_signer,structured=True);app=create_app()
    async def invoke(request,kind,value):
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        def operation():
            def project(ctx):
                if kind=='discovery':
                    def project_discovery(value):
                        if value['proposal'] is not None:
                            detail=value['proposal'];p=detail.proposal
                            value=dict(value,proposal=dict(proposal_id=p.proposal_id,trip_id=p.trip_id,expected_version=p.expected_version,candidate_hash=detail.candidate_hash,status=detail.status,expires_at=p.expires_at,content=json.loads(p.content)))
                        raw=json.dumps(dict(version='TRIP-needs-discovery.2',request_id=request.state.request_id,discovery=value),ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
                        if len(raw)>max_response_bytes:raise Denied('bounded private response required')
                        return raw
                    return ctx.discover_place_needs(value,project_discovery)
                result=dict(version='TRIP-needs-result.2',request_id=request.state.request_id)
                if kind=='prepare':prepared=ctx.prepare_needs(NeedsEditV2.parse(value))
                elif kind=='query':prepared=ctx.needs_preparation(value)
                else:
                    receipt=ctx.save_needs(NeedsSaveV2.parse(value))
                    result['receipt']=dict(action_id=receipt.action_id,kind=receipt.kind,proposal_id=receipt.proposal_id,candidate_hash=receipt.candidate_hash,
                        trip_id=receipt.trip_id,committed_version=receipt.committed_version)
                if kind in ('prepare','query'):
                    if prepared is None:result['preparation']=None
                    else:
                        p=prepared.detail.proposal
                        result['preparation']=dict(proposal_id=p.proposal_id,trip_id=p.trip_id,expected_version=p.expected_version,candidate_hash=prepared.detail.candidate_hash,
                            status=prepared.detail.status,content=json.loads(p.content),diff=json.loads(prepared.diff))
                raw=json.dumps(result,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
                if len(raw)>max_response_bytes:raise Denied('bounded private response required')
                return raw
            return boundary.with_operation(token,project)
        try:return Response(content=await run_in_threadpool(operation),media_type='application/json')
        except Conflict:return _error(request,409,'TRIP_CONFLICT','conflict','failed','do_not_retry')
        except (ValueError,UnicodeError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        except Exception:return _error(request,503,'TRIP_OUTCOME_UNKNOWN' if kind=='save' else 'TRIP_UNAVAILABLE','dependency','unknown',
            'reconcile_original' if kind=='save' else 'retry_safe_read')
    @app.get('/v2/trip-needs-edits')
    async def query(request:Request):
        pairs=list(request.query_params.multi_items())
        try:
            if len(pairs)!=1 or pairs[0][0]!='request_id':raise ValueError('exact original request query required')
            identifier(pairs[0][1])
        except ValueError:return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        return await invoke(request,'query',pairs[0][1])
    @app.get('/v2/trip-needs-discovery')
    async def discovery(request:Request):
        try:query=parse_discovery_query(request.scope['query_string'])
        except (ValueError,UnicodeError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        return await invoke(request,'discovery',query)
    async def body(request,kind):
        media=request.headers.getlist('content-type')
        if request.query_params or len(media)!=1 or media[0].split(';')[0].strip().lower()!='application/octet-stream' or request.headers.get('content-encoding','identity').lower()!='identity':
            return _error(request,415,'UNSUPPORTED_MEDIA_TYPE','input','failed','do_not_retry')
        chunks=[];size=0
        async for chunk in request.stream():
            size+=len(chunk)
            if size>1_000_000:return _error(request,413,'BODY_TOO_LARGE','input','failed','do_not_retry')
            chunks.append(chunk)
        return await invoke(request,kind,b''.join(chunks))
    @app.post('/v2/trip-needs-edits')
    async def prepare(request:Request):return await body(request,'prepare')
    @app.post('/v2/trip-needs-saves')
    async def save(request:Request):return await body(request,'save')
    return app
