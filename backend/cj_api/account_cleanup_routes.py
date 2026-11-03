"""CLEANUP-API@1 / CLEANUP-DEVICE@1; no ordinary business credential from a cap."""
import json
from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from cj_cleanup.core import Denied,Conflict,Invalid,digest,identifier,hash_value
from cj_cleanup.capabilities import CapabilityUnavailable
from cj_strict_json import reject_duplicates
from .message_routes import _token,_read_body,_body_error,_error,BodyError
from .history_routes import _query


def _credential(request,scheme):
    headers=request.headers.getlist('authorization')
    if len(headers)!=1:return None
    kind,sep,value=headers[0].partition(' ')
    if not sep or kind.lower()!=scheme.lower() or not value or any(c.isspace() for c in value):return None
    return value


def _parse(raw,version,fields):
    try:
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=reject_duplicates(Invalid,'duplicate cleanup field'))
        if type(value) is not dict or set(value)!=set(fields)|{'version'} or value['version']!=version:raise Invalid('invalid cleanup request')
        return {k:v for k,v in value.items() if k!='version'}
    except (ValueError,UnicodeError,RecursionError):raise Invalid('invalid cleanup request') from None


def register_account_cleanup_routes(app,gateway):
    def project(request):
        def encode(value):
            raw=json.dumps(dict(request_id=request.state.request_id,**value),ensure_ascii=True,separators=(',',':')).encode('ascii')
            if len(raw)>65536:raise Invalid('cleanup response too large')
            return raw
        return encode
    async def invoke(request,callback,*,write,scheme,fields=(),version='CLEANUP-API@1',query_fields=()):
        if gateway is None:return _error(request,503,'CLEANUP_UNAVAILABLE','dependency','unknown','do_not_retry')
        credential=_token(request) if scheme=='Bearer' else _credential(request,scheme)
        if credential is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        try:
            if request.scope['query_string'] and not query_fields:raise Invalid('unexpected cleanup query')
            raw=await _read_body(request,16384) if write else b''
            value=_parse(raw,version,fields) if write else _query(request,query_fields) if query_fields else {}
            for key in ('action_id','binding_id','device_id','operation_id','invocation_id'):
                if key in value:identifier(value[key])
            for key in ('state_ref','registry_digest','request_digest','input_sha256'):
                if key in value:hash_value(value[key])
            encoded=await run_in_threadpool(callback,credential,value,raw,project(request))
            return Response(encoded,media_type='application/json')
        except BodyError as exc:return _body_error(request,exc)
        except (Invalid,ValueError,TypeError):return _error(request,400,'INVALID_CLEANUP_INPUT','input','failed','do_not_retry')
        except Conflict:return _error(request,409,'CLEANUP_ORIGINAL_CONFLICT','conflict','failed','reconcile_original')
        except (Denied,CapabilityUnavailable):return _error(request,403,'CLEANUP_ACCESS_UNAVAILABLE','access','failed','do_not_retry')
        except Exception:return _error(request,503,'CLEANUP_OUTCOME_UNKNOWN','dependency','unknown','reconcile_original' if write else 'retry_safe_read')

    @app.post('/v1/account-cleanup-operations')
    async def prepare(request:Request):
        return await invoke(request,lambda token,v,raw,p:gateway.prepare(token,v['action_id'],digest(raw),v['binding_id'],p),
            write=True,scheme='Bearer',fields=('action_id','binding_id'))

    @app.post('/v1/account-cleanup-operations/{operation_id}/confirmation')
    async def confirm(operation_id:str,request:Request):
        return await invoke(request,lambda token,v,raw,p:gateway.confirm(token,identifier(operation_id),v['registry_digest'],v['confirmation'],digest(raw),p),
            write=True,scheme='Bearer',fields=('registry_digest','confirmation'))

    @app.get('/v1/account-cleanup-preparations')
    async def preparation(request:Request):
        token=_token(request)
        if gateway is None:return _error(request,503,'CLEANUP_UNAVAILABLE','dependency','unknown','do_not_retry')
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        try:
            values=_query(request,('action_id',));identifier(values['action_id'])
            encoded=await run_in_threadpool(gateway.preparation,token,values['action_id'],project(request))
            return Response(encoded,media_type='application/json')
        except (ValueError,Invalid):return _error(request,400,'INVALID_CLEANUP_INPUT','input','failed','do_not_retry')
        except Denied:return _error(request,403,'CLEANUP_ACCESS_UNAVAILABLE','access','failed','do_not_retry')
        except Exception:return _error(request,503,'CLEANUP_OUTCOME_UNKNOWN','dependency','unknown','retry_safe_read')

    @app.get('/v1/account-cleanup-operations/{operation_id}')
    async def progress(operation_id:str,request:Request):
        return await invoke(request,lambda cap,v,raw,p:gateway.progress(cap,identifier(operation_id),p),write=False,scheme='Cleanup')

    def device_routes(prefix,version):
        @app.post(prefix+'/cleanup-devices')
        async def register_device(request:Request):
            return await invoke(request,lambda token,v,raw,p:gateway.register_device(token,v['action_id'],digest(raw),v['device_id'],v['state_ref'],p,device_version=version),
                write=True,scheme='Bearer',version=version,fields=('action_id','device_id','state_ref'))

        @app.post(prefix+'/cleanup-device-calls')
        async def device_call(request:Request):
            v3=version in ('CLEANUP-DEVICE@3','CLEANUP-DEVICE@4')
            return await invoke(request,lambda cap,v,raw,p:gateway.device_call(cap,v['binding_id'],v['reason'],p,device_version=version,
                action_id=v['action_id'] if v3 else None,input_digest=digest(raw) if v3 else None),write=True,
                scheme='Device',version=version,fields=('action_id','binding_id','reason') if v3 else ('binding_id','reason'))

        @app.post(prefix+'/cleanup-device-receipts')
        async def device_receipt(request:Request):
            return await invoke(request,lambda cap,v,raw,p:gateway.device_receipt(cap,v['action_id'],v['operation_id'],v['invocation_id'],
                v['binding_id'],v['request_digest'],v['outcome'],raw,p,device_version=version),write=True,scheme='Cleanup',version=version,
                fields=('action_id','operation_id','invocation_id','binding_id','request_digest','outcome'))

        @app.get(prefix+'/cleanup-device-calls/{invocation_id}')
        async def device_query(invocation_id:str,request:Request):
            return await invoke(request,lambda cap,v,raw,p:gateway.device_query(cap,identifier(invocation_id),p,device_version=version),write=False,scheme='Device')

    device_routes('/v1','CLEANUP-DEVICE@1')
    device_routes('/v2','CLEANUP-DEVICE@2')
    device_routes('/v3','CLEANUP-DEVICE@3')
    device_routes('/v4','CLEANUP-DEVICE@4')

    def original_device_routes(prefix,version):
        @app.get(prefix+'/cleanup-device-registrations')
        async def original_registration(request:Request):
            return await invoke(request,lambda token,v,raw,p:gateway.device_registration_query(token,v['action_id'],v['input_sha256'],p,device_version=version),
                write=False,scheme='Bearer',query_fields=('action_id','input_sha256'))

        @app.get(prefix+'/cleanup-device-call-actions')
        async def original_device_action(request:Request):
            return await invoke(request,lambda token,v,raw,p:gateway.device_action_query(token,v['action_id'],v['input_sha256'],p,device_version=version),
                write=False,scheme='Device',query_fields=('action_id','input_sha256'))

    original_device_routes('/v3','CLEANUP-DEVICE@3')
    original_device_routes('/v4','CLEANUP-DEVICE@4')

    def completion_route(prefix,device_version,version):
        @app.get(prefix+'/cleanup-device-completions/{invocation_id}')
        async def original_device_completion(invocation_id:str,request:Request):
            return await invoke(request,lambda token,v,raw,p:gateway.device_completion(token,identifier(invocation_id),v['request_digest'],p,
                device_version=device_version,completion_version=version),write=False,scheme='Device',query_fields=('request_digest',))

    completion_route('/v1','CLEANUP-DEVICE@3','CLEANUP-DEVICE-COMPLETION@1')
    completion_route('/v2','CLEANUP-DEVICE@4','CLEANUP-DEVICE-COMPLETION@2')
