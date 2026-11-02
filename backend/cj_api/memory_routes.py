"""MEMORY wire over the producer's public Service; OpenAPI generated projections."""
import json
from dataclasses import asdict
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from .generated import (MemorySaveCommand, MemoryManualSaveCommand, MemoryReceipt, MemoryItem, MemoryGroup,
    MemorySaveResponse, MemoryReceiptQueryResponse, MemoryDetailResponse,
    MemoryGroupsResponse, MemoryListResponse)
from .history_routes import _query, _number, PrivateOutputTooLarge
from .message_routes import BodyError, _body_error, _error, _read_octets, _token
from .memory_boundary import MemoryBoundary, MemoryWireConfiguration, MemoryAccessBlocked, MemorySourceRejected


def register_memory_routes(app, boundary=None, configuration=None):
    if (boundary is None) != (configuration is None):
        raise ValueError('Memory boundary and configuration must be supplied together')
    if boundary is not None and (type(boundary) is not MemoryBoundary or type(configuration) is not MemoryWireConfiguration):
        raise ValueError('Explicit trusted memory composition required')
    domain = boundary.modules['cj_memory.domain'] if boundary else None

    def failure(request, write, exc=None):
        # After entering a write call, projection/admission failures cannot prove rollback.
        if isinstance(exc, MemoryAccessBlocked) and not exc.commit_possible:
            from cj_auth.interfaces import AdmissionStatus, AdmissionReason
            decision = exc.decision
            if decision and decision.status is AdmissionStatus.UNKNOWN:
                return _error(request,503,'ACCESS_UNKNOWN','access','unknown','retry_safe_read')
            return _error(request,401 if decision and decision.reason is AdmissionReason.IDENTITY_INVALID else 403,
                          'ACCESS_DENIED','access','failed','do_not_retry')
        if isinstance(exc, MemorySourceRejected):
            return _error(request,403,'MEMORY_SOURCE_DENIED','access','failed','do_not_retry')
        if domain and isinstance(exc,domain.Conflict):
            return _error(request,409,'MEMORY_INPUT_CONFLICT','conflict','failed','do_not_retry')
        if domain and isinstance(exc,domain.InvalidInput):
            return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        if isinstance(exc,PrivateOutputTooLarge) and not write:
            return _error(request,413,'PRIVATE_RESPONSE_TOO_LARGE','input','failed','retry_safe_read')
        return _error(request,503,'MEMORY_OUTCOME_UNKNOWN' if write else 'MEMORY_UNAVAILABLE',
                      'dependency','unknown','reconcile_original' if write else 'retry_safe_read')

    def prepare(request, required=(), optional=()):
        if boundary is None:
            return failure(request,False)
        token = _token(request)
        if token is None:
            return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        try:
            query = _query(request,required,optional)
            if any(len(v)>4096 or not v.strip() for v in query.values()):
                raise ValueError('Input bound')
            for value in query.values(): value.encode('utf-8')
            if 'limit' in query:
                query['limit'] = _number(query['limit'],1,configuration.max_page_limit)
        except (ValueError,UnicodeError):
            return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        return token,query

    def receipt(value):
        if type(value) is not domain.Receipt:
            raise ValueError('Invalid memory receipt')
        return MemoryReceipt.model_validate_json(json.dumps(asdict(value)),strict=True)

    def item(value):
        if type(value) is not domain.Item or type(value.command) is not domain.Command:
            raise ValueError('Invalid memory item')
        projected = MemorySaveCommand.model_validate_json(value.command.raw,strict=True)
        return MemoryItem.model_validate_json(json.dumps(dict(command=projected.model_dump(mode='json'),
            version=value.version,status=value.status,recorded_at=value.recorded_at.isoformat())),strict=True)

    def project(request,kind,value):
        if kind in ('save','query'):
            if value is None and kind=='save': raise ValueError('Missing save receipt')
            payload={'receipt':None if value is None else receipt(value)}
            model=MemorySaveResponse if kind=='save' else MemoryReceiptQueryResponse
        elif kind=='detail':
            payload={'item':None if value is None else item(value)};model=MemoryDetailResponse
        elif kind=='groups':
            groups=[MemoryGroup.model_validate_json(json.dumps(dict(subject=s,status=t,count=n)),strict=True) for s,t,n in value]
            payload={'groups':groups};model=MemoryGroupsResponse
        else:
            items=[item(v) for v in value]
            payload={'items':items,'next_after':items[-1].command.item_id if items else None}
            model=MemoryListResponse
        response=JSONResponse(model.model_validate({'request_id':request.state.request_id,**payload}).model_dump(mode='json'))
        if len(response.body)>configuration.max_private_response_bytes:
            raise PrivateOutputTooLarge()
        return response.body

    async def invoke(request,token,kind,argument):
        try:
            raw = await run_in_threadpool(boundary.invoke,token,kind,argument,
                lambda value:project(request,kind,value))
            return Response(content=raw,media_type='application/json')
        except Exception as exc:
            return failure(request,kind=='save',exc)

    @app.post('/v1/memories',response_model=MemorySaveResponse)
    async def save(request:Request):
        if boundary is None:return failure(request,True)
        prepared=prepare(request)
        if isinstance(prepared,JSONResponse):return prepared
        token,_=prepared
        try:
            raw=await _read_octets(request,configuration.max_body_bytes)
            command=boundary.modules['cj_memory.manual'].parse_manual(raw)
            # Validate codepoint bounds, integer range and UTF8 scalar values without
            # regenerating or normalizing original bytes used for approval/replay.
            MemoryManualSaveCommand.model_validate_json(raw,strict=True)
            for value in asdict(command).values():
                if type(value) is str:value.encode('utf-8')
        except BodyError as exc:return _body_error(request,exc)
        except (ValueError,UnicodeError,domain.InvalidInput):
            return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        except Exception:return failure(request,True)
        return await invoke(request,token,'save',raw)

    @app.get('/v1/memory-receipts',response_model=MemoryReceiptQueryResponse)
    async def query(request:Request):
        prepared=prepare(request,('operation_id',))
        if isinstance(prepared,JSONResponse):return prepared
        token,q=prepared
        return await invoke(request,token,'query',q['operation_id'])

    @app.get('/v1/memory-items',response_model=MemoryDetailResponse)
    async def detail(request:Request):
        prepared=prepare(request,('item_id',))
        if isinstance(prepared,JSONResponse):return prepared
        token,q=prepared
        return await invoke(request,token,'detail',q['item_id'])

    @app.get('/v1/memory-groups',response_model=MemoryGroupsResponse)
    async def groups(request:Request):
        prepared=prepare(request)
        if isinstance(prepared,JSONResponse):return prepared
        token,_=prepared
        return await invoke(request,token,'groups',None)

    @app.get('/v1/memories',response_model=MemoryListResponse)
    async def listing(request:Request):
        prepared=prepare(request,('limit',),('after',))
        if isinstance(prepared,JSONResponse):return prepared
        token,q=prepared
        return await invoke(request,token,'list',(q.get('after'),q['limit']))
