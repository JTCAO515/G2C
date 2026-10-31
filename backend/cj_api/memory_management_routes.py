"""Original UTF8 lifecycle actions and original-ID receipt query; candidate closed."""
import json
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from .generated import (MemoryManagementAction,MemoryManagementReceipt,
    MemoryManagementApplyResponse,MemoryManagementReceiptResponse,MemoryManagementEditAction,
    MemoryStopUseAction,MemoryStopUseReceipt,MemoryStopUseApplyResponse,MemoryStopUseReceiptResponse)
from .history_routes import _query,PrivateOutputTooLarge
from .message_routes import BodyError,_body_error,_error,_read_octets,_token
from .memory_boundary import MemoryAccessBlocked
from .memory_management_boundary import MemoryManagementBoundary,MemoryManagementConfiguration

def register_memory_management(app,boundary=None,configuration=None):
    if (boundary is None)!=(configuration is None):raise ValueError('Complete candidate lifecycle binding/configuration required')
    if boundary is not None and (type(boundary) is not MemoryManagementBoundary or type(configuration) is not MemoryManagementConfiguration):
        raise ValueError('Fixed candidate lifecycle boundary/configuration required')
    domain=boundary.modules['cj_memory.domain'] if boundary else None
    def failure(request,write,exc=None):
        if isinstance(exc,MemoryAccessBlocked) and not exc.commit_possible:
            from cj_auth.interfaces import AdmissionStatus,AdmissionReason
            d=exc.decision
            if d and d.status is AdmissionStatus.UNKNOWN:return _error(request,503,'ACCESS_UNKNOWN','access','unknown','retry_safe_read')
            return _error(request,401 if d and d.reason is AdmissionReason.IDENTITY_INVALID else 403,'ACCESS_DENIED','access','failed','do_not_retry')
        if domain and isinstance(exc,domain.Conflict):return _error(request,409,'MEMORY_MANAGEMENT_CONFLICT','conflict','failed','do_not_retry')
        if domain and isinstance(exc,domain.InvalidInput):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        return _error(request,503,'MEMORY_MANAGEMENT_OUTCOME_UNKNOWN' if write else 'MEMORY_MANAGEMENT_UNAVAILABLE','dependency','unknown','reconcile_original' if write else 'retry_safe_read')
    def prepare(request,keys):
        if boundary is None:return failure(request,False)
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        try:
            q=_query(request,keys)
            for value in q.values():
                if not value.strip() or len(value)>4096:raise ValueError('Bounded original action ID required')
                value.encode('utf-8')
        except (ValueError,UnicodeError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        return token,q
    def project(request,kind,argument,value,*,stop_use=False):
        if value is None:
            if kind=='save':raise ValueError('Missing action receipt')
            receipt=None
        else:
            if type(value) is not domain.Receipt:raise ValueError('Canonical stored receipt required')
            from cj_memory_management.edit import parse_action
            expected=parse_action(argument).action_id if kind=='save' else argument
            if value.operation_id!=expected:raise ValueError('Wrong original receipt')
            receipt_type=MemoryStopUseReceipt if stop_use else MemoryManagementReceipt
            receipt=receipt_type.model_validate_json(json.dumps(dict(action_id=value.operation_id,item_id=value.item_id,version=value.version,status=value.status,input_sha256=value.input_sha256)),strict=True)
        if stop_use:
            model=MemoryStopUseApplyResponse if kind=='save' else MemoryStopUseReceiptResponse
        else:
            model=MemoryManagementApplyResponse if kind=='save' else MemoryManagementReceiptResponse
        raw=JSONResponse(model.model_validate({'request_id':request.state.request_id,'receipt':receipt}).model_dump(mode='json')).body
        if len(raw)>configuration.max_private_response_bytes:raise PrivateOutputTooLarge()
        return raw
    async def invoke(request,token,kind,argument,*,stop_use=False):
        try:
            raw=await run_in_threadpool(boundary.invoke,token,kind,argument,lambda value:project(request,kind,argument,value,stop_use=stop_use))
            return Response(content=raw,media_type='application/json')
        except Exception as exc:return failure(request,kind=='save',exc)
    async def apply_action(request, *, edit=False,stop_use=False):
        prepared=prepare(request,())
        if isinstance(prepared,JSONResponse):return prepared
        token,_=prepared
        try:
            raw=await _read_octets(request,configuration.max_body_bytes)
            if stop_use:
                from cj_memory_withdrawal.stop_use import StopUse
                action=StopUse.parse(raw)
                MemoryStopUseAction.model_validate_json(raw,strict=True)
                action.source_id.encode('utf-8')
            elif edit:
                from cj_memory_management.edit import Edit
                action=Edit.parse(raw)
                MemoryManagementEditAction.model_validate_json(raw,strict=True)
            else:
                action=boundary.modules['cj_memory_management.domain'].Action.parse(raw)
                MemoryManagementAction.model_validate_json(raw,strict=True)
            action.action_id.encode('utf-8');action.item_id.encode('utf-8')
        except BodyError as exc:return _body_error(request,exc)
        except (ValueError,UnicodeError,domain.InvalidInput):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        except Exception:return failure(request,True)
        return await invoke(request,token,'save',raw,stop_use=stop_use)
    @app.post('/v1/memory-management-actions',response_model=MemoryManagementApplyResponse)
    async def apply(request:Request):
        return await apply_action(request)
    @app.post('/v1/memory-edit-actions',response_model=MemoryManagementApplyResponse)
    async def edit(request:Request):
        return await apply_action(request,edit=True)
    @app.post('/v1/memory-withdrawal-actions',response_model=MemoryStopUseApplyResponse)
    async def withdraw(request:Request):
        return await apply_action(request,stop_use=True)
    @app.get('/v1/memory-withdrawal-receipts',response_model=MemoryStopUseReceiptResponse)
    async def withdrawal_receipt(request:Request):
        prepared=prepare(request,('action_id',))
        if isinstance(prepared,JSONResponse):return prepared
        token,q=prepared
        return await invoke(request,token,'query',q['action_id'],stop_use=True)
    @app.get('/v1/memory-management-receipts',response_model=MemoryManagementReceiptResponse)
    async def query(request:Request):
        prepared=prepare(request,('action_id',))
        if isinstance(prepared,JSONResponse):return prepared
        token,q=prepared
        return await invoke(request,token,'query',q['action_id'])
