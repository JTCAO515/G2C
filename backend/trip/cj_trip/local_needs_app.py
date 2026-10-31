"""Explicit source-bound Trip action/read host; canonical original AUTH and act."""
import json
import os
from pathlib import Path
from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from cj_api.app import create_app
from cj_api.local_app import LocalDatabase,scope_for
from cj_api.local_worker_context import checker_for
from cj_api.composition import CompositionUnavailable
from cj_api.message_routes import _error,_token
from cj_auth.interfaces import AdmissionStatus
from cj_message.travel_reference import MessageContextAuthority
from cj_agent.draft import trip_scope_for
from cj_draft.needs_local import publisher
from .auth_boundary import Boundary
from .confirmation import ConfirmationSigner
from .needs_action import NeedsAction
from .needs_action_store import NeedsActions
from .manual_needs import NeedsEdit,NeedsSave
from .current_needs_source import CurrentNeedsSource
from .needs_edit_store import NeedsEdits
from .source_initialization import SourceInitializations,SourceInitialization,SourceInitializationSave
from cj_api.local_needs import protected_reader
from .domain import Conflict,Denied,identifier


def create_local_needs_app(*,conninfo_path,auth_dir,run_context,confirmation_signer,max_response_bytes=1_000_000):
    if os.environ.get('CJ_ENV')!='local' or type(confirmation_signer) is not ConfirmationSigner or run_context is None or type(max_response_bytes) is not int or max_response_bytes<1:
        raise CompositionUnavailable('explicit local source-bound Trip host required')
    database=LocalDatabase(conninfo_path,run_context=run_context,travel_context=True,needs_context=True)
    checker=checker_for(Path(auth_dir))
    def resolve(principal):
        owner=scope_for(principal.issuer,principal.subject)
        return lambda:database.connect(owner),trip_scope_for(owner)
    class NeedsBoundary(Boundary):
        def _bind(self,token):
            repository,principal,check=super()._bind(token)
            owner=scope_for(principal.issuer,principal.subject)
            def admit():
                value=checker.check(token)
                if value.status is not AdmissionStatus.ALLOWED or value.principal!=principal:raise Denied('source admission unavailable')
                return value.principal
            authority=MessageContextAuthority(database.message_repository(owner),admit)
            source=publisher(database,checker,authority,lambda:token,owner).source
            service=NeedsActions(database,owner,source)
            repository.needs_actions=service
            edits=NeedsEdits(CurrentNeedsSource(database,checker,token,protected_reader(database,checker)))
            repository.needs_edits=edits
            initializations=SourceInitializations(database,owner,source)
            repository.source_initializations=initializations
            def guard(stage):
                check(stage)
                if repository.needs_actions is not service or repository.needs_edits is not edits or repository.source_initializations is not initializations:raise Denied('source action binding changed')
            return repository,principal,guard
    boundary=NeedsBoundary(checker,resolve,confirmation_signer,structured=True)
    app=create_app()
    def query(request,key):
        values=list(request.query_params.multi_items())
        if len(values)!=1 or values[0][0]!=key:raise ValueError('exact query required')
        identifier(values[0][1]);return values[0][1]
    def receipt(value):
        if value is None:return None
        return dict(action_id=value.action_id,kind=value.kind,proposal_id=value.proposal_id,
            candidate_hash=value.candidate_hash,trip_id=value.trip_id,committed_version=value.committed_version)
    def project(request,kind,value):
        result=dict(version='TRIP-needs-result.1',request_id=request.state.request_id)
        if kind.startswith('source_'):result['version']='TRIP-source-initialize-result.1'
        if kind in ('action','receipt','save','source_save','source_receipt'):result['receipt']=receipt(value)
        elif kind in ('prepare','preparation','source_prepare','source_preparation'):
            if value is None:result['preparation']=None
            else:
                p=value.detail.proposal
                result['preparation']=dict(proposal_id=p.proposal_id,trip_id=p.trip_id,expected_version=p.expected_version,
                    candidate_hash=value.detail.candidate_hash,status=value.detail.status,content=json.loads(p.content),diff=json.loads(value.diff))
                if kind in ('source_prepare','source_preparation'):
                    result['preparation']['item_source_association']=dict(status='UNKNOWN',
                        zh='原legacy条目没有NEEDS条目映射；保留原文与未知，不推断整体可行。',
                        en='Legacy items have no NEEDS item mapping; retain original text and unknowns, without inferring overall feasibility.')
        elif kind=='trip':result['trip']=None if value is None else dict(trip_id=value.trip_id,version=value.version,content=json.loads(value.content))
        else:
            original=value.proposal
            result['proposal']=dict(proposal_id=original.proposal_id,trip_id=original.trip_id,
                expected_version=original.expected_version,candidate_hash=value.candidate_hash,status=value.status,
                expires_at=original.expires_at,content=json.loads(original.content))
        raw=json.dumps(result,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
        if len(raw)>max_response_bytes:raise ValueError('private response too large')
        return raw
    async def invoke(request,kind,arg):
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        def operation():
            def callback(ctx):
                if kind=='prepare':value=ctx.prepare_needs(NeedsEdit.parse(arg))
                elif kind=='source_prepare':value=ctx.prepare_source_initialization(SourceInitialization.parse(arg))
                elif kind=='source_save':value=ctx.save_source_initialization(SourceInitializationSave.parse(arg))
                elif kind=='source_preparation':value=ctx.source_initialization(arg)
                elif kind=='source_receipt':value=ctx.source_initialization_receipt(arg)
                elif kind=='save':value=ctx.save_needs(NeedsSave.parse(arg))
                elif kind=='preparation':value=ctx.needs_preparation(arg)
                elif kind=='action':value=ctx.act_needs(NeedsAction.parse(arg))
                elif kind=='receipt':value=ctx.query_action(arg)
                elif kind=='trip':value=ctx.detail(arg)
                else:value=ctx.proposal_detail(arg)
                return project(request,kind,value)
            return boundary.with_operation(token,callback)
        try:return Response(content=await run_in_threadpool(operation),media_type='application/json')
        except Conflict:return _error(request,409,'TRIP_CONFLICT','conflict','failed','do_not_retry')
        except (ValueError,UnicodeError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        except Exception:return _error(request,503,'TRIP_OUTCOME_UNKNOWN' if kind in ('action','prepare','save','source_prepare','source_save') else 'TRIP_UNAVAILABLE',
            'dependency','unknown','reconcile_original' if kind in ('action','prepare','save','source_prepare','source_save') else 'retry_safe_read')
    @app.post('/v1/trip-needs-actions')
    async def action(request:Request):
        media=request.headers.getlist('content-type')
        if (request.query_params or len(media)!=1 or media[0].split(';')[0].strip().lower()!='application/octet-stream'
                or request.headers.get('content-encoding','identity').lower()!='identity'):
            return _error(request,415,'UNSUPPORTED_MEDIA_TYPE','input','failed','do_not_retry')
        parts=[];size=0
        async for chunk in request.stream():
            size+=len(chunk)
            if size>32768:return _error(request,413,'BODY_TOO_LARGE','input','failed','do_not_retry')
            parts.append(chunk)
        return await invoke(request,'action',b''.join(parts))
    async def read(request,kind,key):
        try:arg=query(request,key)
        except ValueError:return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        return await invoke(request,kind,arg)
    @app.get('/v1/trip-needs-action-receipts')
    async def original(request:Request):return await read(request,'receipt','action_id')
    @app.get('/v4/trip-structured')
    async def trip(request:Request):return await read(request,'trip','trip_id')
    @app.get('/v2/trip-needs-proposals')
    async def proposal(request:Request):return await read(request,'proposal','proposal_id')
    async def edit_write(request,kind):
        media=request.headers.getlist('content-type')
        if request.query_params or len(media)!=1 or media[0].split(';')[0].strip().lower()!='application/octet-stream' or request.headers.get('content-encoding','identity').lower()!='identity':
            return _error(request,415,'UNSUPPORTED_MEDIA_TYPE','input','failed','do_not_retry')
        parts=[];size=0
        async for chunk in request.stream():
            size+=len(chunk)
            if size>(1000000 if kind in ('prepare','source_prepare') else 32768):return _error(request,413,'BODY_TOO_LARGE','input','failed','do_not_retry')
            parts.append(chunk)
        return await invoke(request,kind,b''.join(parts))
    @app.post('/v1/trip-needs-edits')
    async def edit(request:Request):return await edit_write(request,'prepare')
    @app.get('/v1/trip-needs-edits')
    async def edit_query(request:Request):return await read(request,'preparation','request_id')
    @app.post('/v1/trip-needs-saves')
    async def edit_save(request:Request):return await edit_write(request,'save')
    @app.post('/v1/trip-source-initializations')
    async def source_prepare(request:Request):return await edit_write(request,'source_prepare')
    @app.get('/v1/trip-source-initializations')
    async def source_query(request:Request):return await read(request,'source_preparation','request_id')
    @app.post('/v1/trip-source-initialization-saves')
    async def source_save(request:Request):return await edit_write(request,'source_save')
    @app.get('/v1/trip-source-initialization-receipts')
    async def source_receipt(request:Request):return await read(request,'source_receipt','action_id')
    return app
