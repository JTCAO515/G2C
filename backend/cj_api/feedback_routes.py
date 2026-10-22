"""Submit/original-query only; minimal source observations and exact receipt bytes."""
from dataclasses import asdict
import json
from fastapi import Request
from fastapi.responses import JSONResponse,Response
from starlette.concurrency import run_in_threadpool
from .generated import FeedbackAction,FeedbackReceipt,FeedbackSubmitResponse,FeedbackQueryResponse
from .message_routes import _error,_token
from .history_routes import _query,PrivateOutputTooLarge
from .feedback_composition import FeedbackWireConfiguration

def register_feedback_routes(app,boundary=None,configuration=None,modules=None):
    if boundary is None:
        if configuration is not None or modules is not None:raise ValueError('Complete FEEDBACK configuration required')
    elif (type(configuration) is not FeedbackWireConfiguration or not modules
            or type(boundary) is not modules['cj_feedback.boundary'].Boundary):raise ValueError('Pinned FEEDBACK boundary required')
    domain=modules['cj_feedback.domain'] if modules else None
    def failure(request,write,exc=None):
        if domain and not getattr(exc,'commit_possible',False):
            if isinstance(exc,domain.InvalidInput):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
            if isinstance(exc,domain.Conflict):return _error(request,409,'FEEDBACK_CONFLICT','conflict','failed','do_not_retry')
        return _error(request,503,'FEEDBACK_OUTCOME_UNKNOWN' if write else 'FEEDBACK_UNAVAILABLE',
            'dependency','unknown','reconcile_original' if write else 'retry_safe_read')
    def prepare(request,required=()):
        if boundary is None:return failure(request,False)
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        try:
            query=_query(request,required)
            for value in query.values():domain.identifier(value)
        except (ValueError,UnicodeError,domain.InvalidInput):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        return token,query
    def project(request,value,expected,write):
        if value is None:
            if write:raise ValueError('Missing submitted receipt')
            receipt=None
        else:
            if type(value) is not domain.Receipt or value.action_id!=expected:raise ValueError('Invalid original receipt')
            if value.source is not None and type(value.source) is not domain.SourceReference:raise ValueError('Invalid source observation')
            receipt=FeedbackReceipt.model_validate_json(json.dumps(asdict(value)),strict=True)
        model=FeedbackSubmitResponse if write else FeedbackQueryResponse
        raw=JSONResponse(model.model_validate({'request_id':request.state.request_id,'receipt':receipt}).model_dump(mode='json')).body
        if len(raw)>configuration.max_private_response_bytes:raise PrivateOutputTooLarge()
        return raw
    async def invoke(request,token,argument,write):
        def operation(ctx):
            value=ctx.submit(argument) if write else ctx.query_action(argument)
            return project(request,value,argument.action_id if write else argument,write)
        try:
            raw=await run_in_threadpool(boundary.with_operation,token,operation)
            return Response(content=raw,media_type='application/json')
        except Exception as exc:return failure(request,write,exc)
    @app.post('/v1/feedback',response_model=FeedbackSubmitResponse)
    async def submit(request:Request):
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
            original=b''.join(chunks);action=domain.Action(original)
            FeedbackAction.model_validate_json(original,strict=True)
        except (ValueError,UnicodeError,domain.InvalidInput):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        except Exception:return failure(request,True)
        return await invoke(request,token,action,True)
    @app.get('/v1/feedback-action-receipts',response_model=FeedbackQueryResponse)
    async def query(request:Request):
        ready=prepare(request,('action_id',))
        if isinstance(ready,JSONResponse):return ready
        token,q=ready;return await invoke(request,token,q['action_id'],False)
