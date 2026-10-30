"""Explicit local structured/manual host; original AUTH, Proposal and act only."""
import json
import os
from pathlib import Path

from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from cj_api.app import create_app
from cj_api.composition import CompositionUnavailable
from cj_api.local_app import LocalDatabase, scope_for
from cj_api.local_worker_context import checker_for
from cj_api.message_routes import _token, _error
from cj_agent.draft import trip_scope_for

from .auth_boundary import Boundary
from .confirmation import ConfirmationSigner
from .domain import Conflict, Denied, identifier
from .manual import ManualEdit, ManualSave
from .initialization import Initialization, InitializationSave
from .structured import validate_document


def create_local_manual_app(*, conninfo_path, auth_dir, confirmation_signer,
                            max_response_bytes=1_000_000, run_context=None):
    if (os.environ.get('CJ_ENV') != 'local' or type(confirmation_signer) is not ConfirmationSigner
            or type(max_response_bytes) is not int or max_response_bytes < 1):
        raise CompositionUnavailable('explicit bounded local structured manual host required')
    from cj_api.local_run_context import LocalRunContext
    if run_context is not None and type(run_context) is not LocalRunContext:
        raise CompositionUnavailable('canonical explicit local run context required')
    database = LocalDatabase(conninfo_path,run_context=run_context)
    def resolve(principal):
        message_scope=scope_for(principal.issuer,principal.subject)
        scope=trip_scope_for(message_scope)
        with database.connect(message_scope) as conn:
            conn.execute('INSERT INTO cj_trip_scope(scope) VALUES(%s) ON CONFLICT DO NOTHING',(scope,))
        return lambda:database.connect(message_scope),scope
    class ManualBoundary(Boundary):
        def _bind(self,token):
            repository,principal,check=super()._bind(token)
            from .manual_origin import ManualOrigin
            from cj_message.needs_binding import needs_scope_for
            scope=scope_for(principal.issuer,principal.subject)
            origin=ManualOrigin(scope,trip_scope_for(scope),needs_scope_for(scope) if run_context is not None else None)
            repository.manual_origin=origin
            def guard(stage):
                check(stage)
                if repository.manual_origin is not origin:raise Denied('original source reader changed')
            return repository,principal,guard
    boundary=ManualBoundary(checker_for(Path(auth_dir)),resolve,confirmation_signer,structured=True)
    app=create_app()

    def query(request, fields):
        pairs=list(request.query_params.multi_items()); values=dict(pairs)
        if set(values)!=set(fields) or len(values)!=len(pairs): raise ValueError('exact query required')
        for value in values.values():identifier(value)
        return values

    def receipt(value):
        if value is None:return None
        return dict(action_id=value.action_id,kind=value.kind,proposal_id=value.proposal_id,
            candidate_hash=value.candidate_hash,trip_id=value.trip_id,committed_version=value.committed_version)

    def proposal(value):
        if value is None:return None
        detail=value.detail; original=detail.proposal
        from cj_feasibility.trip_time import evaluate
        report=evaluate(original.content)
        return dict(proposal_id=original.proposal_id,trip_id=original.trip_id,
            expected_version=original.expected_version,basis=original.basis_version,
            expires_at=original.expires_at,candidate_hash=detail.candidate_hash,status=detail.status,
            content=json.loads(original.content),diff=json.loads(value.diff),
            feasibility=dict(version=report.version,status=report.status,
                checks=[dict(code=c.code,status=c.status,missing=c.missing,zh=c.zh,en=c.en,
                    evidence=[dict(path=e.path,declaration=json.loads(e.declaration)) for e in c.evidence])
                        for c in report.checks]))

    def project(request, kind, value):
        initialization=kind in ('initialize','initialization','initialize_save','initialize_receipt')
        body=dict(version='TRIP-initialize-result.1' if initialization else 'TRIP-manual-result.1',request_id=request.state.request_id)
        if kind in ('initialize','initialization'):body['initialization']=proposal(value)
        elif kind in ('prepare','preparation'):body['preparation']=proposal(value)
        elif kind in ('save','receipt','initialize_save','initialize_receipt'):body['receipt']=receipt(value)
        else:
            if value is None:body['trip']=None
            else:
                document=json.loads(value.content);validate_document(document)
                body['trip']=dict(trip_id=value.trip_id,version=value.version,content=document)
        encoded=json.dumps(body,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
        if len(encoded)>max_response_bytes:raise ValueError('private response bound exceeded')
        return encoded

    async def invoke(request,kind,value):
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        def operation():
            def callback(context):
                if kind=='initialize':result=context.prepare_initialization(Initialization.parse(value))
                elif kind=='initialize_save':result=context.save_initialization(InitializationSave.parse(value))
                elif kind=='initialization':result=context.initialization(value)
                elif kind=='initialize_receipt':result=context.query_action(value)
                elif kind=='prepare':result=context.prepare_manual(ManualEdit.parse(value))
                elif kind=='save':result=context.save_manual(ManualSave.parse(value))
                elif kind=='preparation':result=context.manual_preparation(value)
                elif kind=='receipt':result=context.query_action(value)
                else:result=context.detail(value)
                return project(request,kind,result)
            return boundary.with_operation(token,callback)
        try:return Response(content=await run_in_threadpool(operation),media_type='application/json')
        except Conflict:return _error(request,409,'TRIP_CONFLICT','conflict','failed','do_not_retry')
        except (ValueError,UnicodeError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        except Exception as error:
            write=kind in ('prepare','save','initialize','initialize_save')
            return _error(request,503,'TRIP_ACCESS_UNAVAILABLE' if isinstance(error,Denied) else 'TRIP_OUTCOME_UNKNOWN' if write else 'TRIP_UNAVAILABLE',
                'dependency','unknown','reconcile_original' if write else 'retry_safe_read')

    async def write(request,kind):
        media=request.headers.getlist('content-type')
        if (len(media)!=1 or media[0].split(';',1)[0].strip().lower()!='application/octet-stream'
                or request.headers.get('content-encoding','identity').lower()!='identity'):
            return _error(request,415,'UNSUPPORTED_MEDIA_TYPE','input','failed','do_not_retry')
        try:
            query(request,());parts=[];size=0
            async for part in request.stream():
                size+=len(part)
                if size>(1_000_000 if kind in ('prepare','initialize') else 32768):
                    return _error(request,413,'BODY_TOO_LARGE','input','failed','do_not_retry')
                parts.append(part)
        except (ValueError,UnicodeError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        return await invoke(request,kind,b''.join(parts))

    @app.post('/v1/trip-manual-preparations')
    async def prepare(request:Request):return await write(request,'prepare')

    @app.post('/v1/trip-manual-saves')
    async def save(request:Request):return await write(request,'save')

    async def read(request,kind,field):
        try:value=query(request,(field,))[field]
        except (ValueError,UnicodeError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        return await invoke(request,kind,value)

    @app.get('/v1/trip-manual-preparations')
    async def preparation(request:Request):return await read(request,'preparation','request_id')

    @app.get('/v1/trip-manual-receipts')
    async def original_receipt(request:Request):return await read(request,'receipt','action_id')

    @app.get('/v3/trip-structured')
    async def detail(request:Request):return await read(request,'detail','trip_id')

    @app.post('/v1/trip-structured-initializations')
    async def initialize(request:Request):return await write(request,'initialize')

    @app.get('/v1/trip-structured-initializations')
    async def initialization_query(request:Request):return await read(request,'initialization','request_id')

    @app.post('/v1/trip-structured-initialization-saves')
    async def initialize_save(request:Request):return await write(request,'initialize_save')

    @app.get('/v1/trip-structured-initialization-receipts')
    async def initialize_receipt(request:Request):return await read(request,'initialize_receipt','action_id')

    return app
