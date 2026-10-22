"""Four NEEDS methods; all private projection and encoding inside producer lifetime."""
from fastapi import Request
from fastapi.responses import JSONResponse,Response
from starlette.concurrency import run_in_threadpool
from .generated import NeedsActionResponse,NeedsActionQueryResponse,NeedsDetailResponse,NeedsRevisionResponse,NeedsCommand
from .history_routes import _query,_number,PrivateOutputTooLarge
from .message_routes import _error,_token
from .needs_composition import NeedsWireConfiguration
from . import needs_projection

def register_needs_routes(app,boundary=None,configuration=None,modules=None):
    if boundary is None:
        if configuration is not None or modules is not None:raise ValueError('Complete NEEDS configuration required')
    elif (type(configuration) is not NeedsWireConfiguration or not modules
            or type(boundary) is not modules['cj_needs.boundary'].Boundary):
        raise ValueError('Pinned NEEDS public boundary required')
    domain=modules['cj_needs.domain'] if modules else None
    def failure(request,write,exc=None):
        if domain and not getattr(exc,'commit_possible',False):
            if isinstance(exc,domain.Conflict):return _error(request,409,'NEEDS_CONFLICT','conflict','failed','do_not_retry')
            if isinstance(exc,domain.InvalidInput):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        if isinstance(exc,PrivateOutputTooLarge) and not write:
            return _error(request,413,'PRIVATE_RESPONSE_TOO_LARGE','input','failed','retry_safe_read')
        denied=domain and isinstance(exc,domain.Denied)
        return _error(request,503,'NEEDS_ACCESS_UNAVAILABLE' if denied else 'NEEDS_OUTCOME_UNKNOWN' if write else 'NEEDS_UNAVAILABLE',
            'access' if denied else 'dependency','unknown','reconcile_original' if write else 'retry_safe_read')
    def prepare(request,required=()):
        if boundary is None:return failure(request,False)
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        try:
            query=_query(request,required)
            for key,value in query.items():
                if key=='version':query[key]=_number(value,1,(1<<63)-1)
                else:domain.identifier(value)
        except (ValueError,UnicodeError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        return token,query
    def project(request,kind,value,argument):
        if kind in ('act','query'):
            if kind=='act' and value is None:raise ValueError('Missing committed receipt')
            expected=argument.action_id if kind=='act' else argument
            if value is not None and value.action_id!=expected:raise ValueError('Wrong original receipt')
            if kind=='act' and (value.needs_id,value.version)!=(argument.data['needs_id'],argument.data['expected_version']+1):
                raise ValueError('Wrong original NEEDS binding')
            model=NeedsActionResponse if kind=='act' else NeedsActionQueryResponse
            payload={'receipt':None if value is None else needs_projection.receipt(value,domain)}
        elif kind=='detail':
            if value is not None and value.needs_id!=argument:raise ValueError('Wrong NEEDS record')
            model=NeedsDetailResponse;payload={'needs':None if value is None else needs_projection.snapshot(value,domain)}
        else:
            if value is not None and (value.needs_id,value.version)!=argument:raise ValueError('Wrong historical revision')
            model=NeedsRevisionResponse;payload={'revision':None if value is None else needs_projection.revision(value,domain)}
        # Optional absent fields stay absent. Required null response keys were
        # explicitly supplied above and therefore survive exclude_unset.
        body=JSONResponse(model.model_validate({'request_id':request.state.request_id,**payload}).model_dump(mode='json',exclude_unset=True)).body
        if len(body)>configuration.max_private_response_bytes:raise PrivateOutputTooLarge()
        return body
    async def invoke(request,token,kind,argument):
        def operation(ctx):
            if kind=='act':value=ctx.act(argument)
            elif kind=='query':value=ctx.query_action(argument)
            elif kind=='detail':value=ctx.detail(argument)
            else:value=ctx.revision(*argument)
            return project(request,kind,value,argument)
        try:
            body=await run_in_threadpool(boundary.with_operation,token,operation)
            return Response(content=body,media_type='application/json')
        except Exception as exc:return failure(request,kind=='act',exc)
    @app.post('/v1/needs-actions',response_model=NeedsActionResponse)
    async def act(request:Request):
        if boundary is None:return failure(request,True)
        ready=prepare(request)
        if isinstance(ready,JSONResponse):return ready
        token,_=ready
        media=request.headers.getlist('content-type')
        if (len(media)!=1 or media[0].split(';',1)[0].strip().lower()!='application/octet-stream'
                or request.headers.get('content-encoding','identity').lower()!='identity'):
            return _error(request,415,'UNSUPPORTED_MEDIA_TYPE','input','failed','do_not_retry')
        chunks=[];size=0
        try:
            async for chunk in request.stream():
                size+=len(chunk)
                if size>configuration.max_body_bytes:return _error(request,413,'BODY_TOO_LARGE','input','failed','do_not_retry')
                chunks.append(chunk)
            raw=b''.join(chunks);command=domain.Command(raw)
            NeedsCommand.model_validate_json(raw,strict=True)
        except (ValueError,UnicodeError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        except Exception:return failure(request,True)
        return await invoke(request,token,'act',command)
    @app.get('/v1/needs-action-receipts',response_model=NeedsActionQueryResponse)
    async def query(request:Request):
        ready=prepare(request,('action_id',))
        if isinstance(ready,JSONResponse):return ready
        token,q=ready;return await invoke(request,token,'query',q['action_id'])
    @app.get('/v1/needs',response_model=NeedsDetailResponse)
    async def detail(request:Request):
        ready=prepare(request,('needs_id',))
        if isinstance(ready,JSONResponse):return ready
        token,q=ready;return await invoke(request,token,'detail',q['needs_id'])
    @app.get('/v1/needs-revisions',response_model=NeedsRevisionResponse)
    async def revision(request:Request):
        ready=prepare(request,('needs_id','version'))
        if isinstance(ready,JSONResponse):return ready
        token,q=ready;return await invoke(request,token,'revision',(q['needs_id'],q['version']))
