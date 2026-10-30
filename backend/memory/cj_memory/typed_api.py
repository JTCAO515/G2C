"""Local typed MEMORY API; canonical AUTH/operation and B-owned current leases."""
import json
from datetime import datetime,timezone
from pathlib import Path
from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from cj_api.app import create_app
from cj_api.generated import (MemorySaveV2Response,MemoryReceiptV2Response,MemoryDetailV2Response,
    MemoryListV2Response,MemoryManagementApplyV2Response,MemoryManagementReceiptV2Response)
from cj_api.composition import CompositionUnavailable
from cj_api.local_app import (LocalDatabase,scope_for,ISSUER,AUDIENCE,KEY_ID,InvitedSubjects)
from cj_api.memory_boundary import (MemoryBoundary,MemoryBinding,MemoryAccessBlocked,
                                    MemorySourceRejected,build_memory_boundary)
from cj_api.message_routes import _error,_token
from cj_auth.interfaces import AdmissionStatus,AdmissionReason
from cj_auth.jwt_adapter import JWTConfiguration,StaticPublicKeys,VerificationKey
from cj_message.travel_reference import MessageContextAuthority
from .domain import Service,InvalidInput,Conflict
from .postgres import Repository
from .typed import parse_manual
from .typed_local import TypedConfiguration


class _RequestBoundary(MemoryBoundary):
    def __init__(self, original, authority):
        super().__init__(original.checker,original.resolve_binding,original.source_policy,original.modules)
        self.authority=authority

    def _command(self, kind, argument):
        return parse_manual(argument) if kind=='save' else None

    def _context_value(self, context, kind, argument):
        if kind=='save':return context.save_manual_typed(argument,self.authority)
        return super()._context_value(context,kind,argument)


def create_local_typed_app(*,conninfo_path,auth_dir,configuration,max_body_bytes=32768,max_response_bytes=1_000_000):
    import os
    if (os.environ.get('CJ_ENV')!='local' or type(configuration) is not TypedConfiguration
            or type(max_body_bytes) is not int or not 1<=max_body_bytes<=32768
            or type(max_response_bytes) is not int or max_response_bytes<1):
        raise CompositionUnavailable('explicit bounded local typed MEMORY host required')
    database=LocalDatabase(conninfo_path,travel_context=True)
    auth_dir=Path(auth_dir)
    keys=StaticPublicKeys({KEY_ID:VerificationKey('RS256',(auth_dir/'public.pem').read_bytes())})

    def resolve(principal):
        if principal.subject not in configuration.collection.profiles:
            raise MemorySourceRejected()
        scope=scope_for(principal.issuer,principal.subject)
        with database.connect(scope) as conn:
            if conn.execute('SELECT 1 FROM cj_memory_scope WHERE scope=%s',(scope,)).fetchone() is None:
                conn.execute('INSERT INTO cj_memory_scope(scope) VALUES(%s) ON CONFLICT DO NOTHING',(scope,))
        repository=Repository(lambda:database.connect(scope),scope,
            transaction_binder=lambda conn,cur:conn.bind_scope(cur),typed_context=True)
        return MemoryBinding(scope,Service(repository,manual_policy=configuration.policy(principal.subject)))

    def policy(principal,scope,kind,command,raw,stage):
        if command is None:return True
        with database.connect(scope) as conn:
            stored=conn.execute('SELECT original_input FROM cj_memory_operation WHERE scope=%s AND operation_id=%s',
                                (scope,command.operation_id)).fetchone()
        if stored is not None and bytes(stored[0])==raw:return True
        return configuration.collection.profiles[principal.subject].expires_at>datetime.now(timezone.utc)

    boundary=build_memory_boundary(environment='local',jwt_configuration=JWTConfiguration(ISSUER,AUDIENCE,'RS256',0),
        verification_keys=keys,access_provider=InvitedSubjects(auth_dir/'invited.json'),resolve_binding=resolve,source_policy=policy)
    app=create_app()

    def query(request,fields):
        pairs=list(request.query_params.multi_items());value=dict(pairs)
        if (set(value)!=set(fields) or len(pairs)!=len(value)
                or any(not v.strip() or len(v)>4096 for v in value.values())):
            raise InvalidInput('exact bounded query fields required')
        for v in value.values():v.encode('utf-8')
        return value

    def private_item(item):
        command=item.command
        value=json.loads(command.raw)
        value.pop('version',None);value.pop('context_id',None)
        value.pop('context_kind',None);value.pop('context_version',None)
        value['context']=(None if command.extent=='long_term' else
            dict(kind=command.context_kind,id=command.context_id,
                 expected_version=command.context_version if command.schema_version==2 else None))
        return dict(command=value,version=item.version,status=item.status,recorded_at=item.recorded_at.isoformat())

    def project(request,kind,value):
        if kind in ('save','query'):
            result={'receipt':None if value is None else value.__dict__}
        elif kind in ('manage','withdraw','management_query'):
            result={'receipt':None if value is None else dict(action_id=value.operation_id,item_id=value.item_id,
                version=value.version,status=value.status,input_sha256=value.input_sha256)}
        elif kind=='detail':result={'item':None if value is None else private_item(value)}
        elif kind=='list':result={'items':[private_item(item) for item in value]}
        else:raise ValueError('unsupported typed projection')
        raw=json.dumps(dict(version='MEMORY-result.2',request_id=request.state.request_id,**result),
                       ensure_ascii=False,separators=(',',':')).encode()
        models={'save':MemorySaveV2Response,'query':MemoryReceiptV2Response,'detail':MemoryDetailV2Response,
                'list':MemoryListV2Response,'manage':MemoryManagementApplyV2Response,
                'withdraw':MemoryManagementApplyV2Response,'management_query':MemoryManagementReceiptV2Response}
        models[kind].model_validate_json(raw,strict=True)
        if len(raw)>max_response_bytes:raise ValueError('private output exceeds explicit limit')
        return raw

    def failure(request,write,error):
        if isinstance(error,MemoryAccessBlocked):
            decision=error.decision
            if decision is not None and decision.status is AdmissionStatus.UNKNOWN:
                return _error(request,503,'ACCESS_UNKNOWN','access','unknown','retry_safe_read')
            status=401 if decision is not None and decision.reason is AdmissionReason.IDENTITY_INVALID else 403
            return _error(request,status,'ACCESS_DENIED','access','failed','do_not_retry')
        if isinstance(error,Conflict):return _error(request,409,'MEMORY_CONFLICT','conflict','failed','do_not_retry')
        if isinstance(error,InvalidInput) and write:return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        return _error(request,503,'MEMORY_OUTCOME_UNKNOWN' if write else 'MEMORY_UNAVAILABLE','dependency','unknown',
                      'reconcile_original' if write else 'retry_safe_read')

    async def invoke(request,kind,argument):
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        def operation():
            first=boundary.checker.check(token)
            if first.status is not AdmissionStatus.ALLOWED:raise MemoryAccessBlocked(first)
            principal=first.principal;scope=scope_for(principal.issuer,principal.subject)
            def admit():
                current=boundary.checker.check(token)
                if current.status is not AdmissionStatus.ALLOWED or current.principal!=principal:
                    raise MemoryAccessBlocked(current)
                return current.principal
            authority=MessageContextAuthority(database.message_repository(scope),admit)
            if kind in ('manage','withdraw','management_query'):
                from cj_memory_management.typed_guarded import execute,query as query_management
                def guard(stage):return admit(),scope
                service=resolve(principal).service
                if kind=='management_query':
                    return query_management(service.repository,service.manual_policy,guard,argument,
                                            lambda value:project(request,kind,value))
                from cj_memory.typed import decode
                version=decode(argument).get('version')
                expected='MEMORY-STOP-USE@2' if kind=='withdraw' else 'MEMORY-management.2'
                if version!=expected:raise InvalidInput('typed operation endpoint/version mismatch')
                return execute(service.repository,service.manual_policy,guard,authority,argument,
                               lambda value:project(request,kind,value))
            return _RequestBoundary(boundary,authority).invoke(token,kind,argument,lambda value:project(request,kind,value))
        try:return Response(content=await run_in_threadpool(operation),media_type='application/json')
        except Exception as error:return failure(request,kind in ('save','manage','withdraw'),error)

    async def write(request,kind):
        media=request.headers.getlist('content-type')
        if (len(media)!=1 or media[0].split(';',1)[0].strip().lower()!='application/octet-stream'
                or request.headers.get('content-encoding','identity').lower()!='identity'):
            return _error(request,415,'UNSUPPORTED_MEDIA_TYPE','input','failed','do_not_retry')
        try:
            query(request,());chunks=[];size=0
            async for chunk in request.stream():
                size+=len(chunk)
                if size>max_body_bytes:return _error(request,413,'BODY_TOO_LARGE','input','failed','do_not_retry')
                chunks.append(chunk)
        except (InvalidInput,UnicodeError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        return await invoke(request,kind,b''.join(chunks))

    @app.post('/v2/memories')
    async def save(request:Request):return await write(request,'save')

    @app.post('/v2/memory-management-actions')
    async def manage(request:Request):return await write(request,'manage')

    @app.post('/v2/memory-withdrawal-actions')
    async def withdraw(request:Request):return await write(request,'withdraw')

    @app.get('/v2/memory-management-receipts')
    async def management_receipt(request:Request):
        try:value=query(request,('action_id',))
        except (InvalidInput,UnicodeError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        return await invoke(request,'management_query',value['action_id'])

    @app.get('/v2/memory-receipts')
    async def receipt(request:Request):
        try:value=query(request,('operation_id',))
        except (InvalidInput,UnicodeError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        return await invoke(request,'query',value['operation_id'])

    @app.get('/v2/memory-items')
    async def detail(request:Request):
        try:value=query(request,('item_id',))
        except (InvalidInput,UnicodeError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        return await invoke(request,'detail',value['item_id'])

    @app.get('/v2/memories')
    async def listing(request:Request):
        try:
            value=query(request,('after','limit') if 'after' in request.query_params else ('limit',));limit=int(value['limit'])
            if str(limit)!=value['limit'] or not 1<=limit<=100:raise InvalidInput('page bound')
        except (InvalidInput,ValueError,UnicodeError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        return await invoke(request,'list',(value.get('after'),limit))
    return app
