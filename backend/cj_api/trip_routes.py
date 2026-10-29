"""TRIP routes through the producer's public synchronous output lifetime only."""
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from .generated import (TripActionResponse,TripActionQueryResponse,TripDetailResponse,TripListResponse,TripProposalResponse,
                        SourceTripDetailResponse,SourceTripListResponse,SourceTripProposalResponse)
from .history_routes import _query,_number,PrivateOutputTooLarge
from .message_routes import _error,_token
from .trip_composition import TripWireConfiguration
from .trip_projection import parse_action,receipt_projection,trip_projection,proposal_projection,source_representation


def register_trip_routes(app,boundary=None,configuration=None,modules=None):
    if boundary is None:
        if configuration is not None or modules is not None:raise ValueError('Complete TRIP configuration required')
    elif (type(configuration) is not TripWireConfiguration or not modules
            or type(boundary) is not modules['cj_trip.auth_boundary'].Boundary):
        raise ValueError('Pinned public guarded TRIP boundary required')
    domain=modules['cj_trip.domain'] if modules else None

    def failure(request,write,exc=None):
        if domain and isinstance(exc,domain.Conflict) and not getattr(exc,'commit_possible',False):
            return _error(request,409,'TRIP_CONFLICT','conflict','failed','do_not_retry')
        if isinstance(exc,PrivateOutputTooLarge) and not write:
            return _error(request,413,'PRIVATE_RESPONSE_TOO_LARGE','input','failed','retry_safe_read')
        # Denied deliberately conflates unknown AUTH, missing/wrong-scope candidate,
        # absent confirmation and other admission failures. Never invent its cause.
        denied=domain and isinstance(exc,domain.Denied)
        return _error(request,503,'TRIP_ACCESS_UNAVAILABLE' if denied else 'TRIP_OUTCOME_UNKNOWN' if write else 'TRIP_UNAVAILABLE',
            'access' if denied else 'dependency','unknown','reconcile_original' if write else 'retry_safe_read')

    def prepare(request,required=(),optional=()):
        if boundary is None:return failure(request,False)
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        try:
            source_view=source_representation(request)
            query=_query(request,required,optional)
            for key,value in query.items():
                if key=='limit':query[key]=_number(value,1,configuration.max_page_limit)
                else:domain.identifier(value)
        except (ValueError,UnicodeError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        return token,query,source_view

    def project(request,kind,value,argument,source_view):
        if kind in ('act','query'):
            expected=argument.action_id if kind=='act' else argument
            if kind=='act' and value is None:raise ValueError('Missing committed action receipt')
            if value is not None and value.action_id!=expected:raise ValueError('Wrong original action receipt')
            if kind=='act' and (value.kind,value.proposal_id,value.candidate_hash)!=(argument.kind,argument.proposal_id,argument.candidate_hash):
                raise ValueError('Wrong original action binding')
            model=TripActionResponse if kind=='act' else TripActionQueryResponse
            payload={'receipt':None if value is None else receipt_projection(value,domain)}
        elif kind=='detail':
            if value is not None and value.trip_id!=argument:raise ValueError('Wrong Trip detail')
            model=SourceTripDetailResponse if source_view else TripDetailResponse;payload={'trip':None if value is None else trip_projection(value,domain,source_view)}
        elif kind=='proposal':
            if value.proposal.proposal_id!=argument:raise ValueError('Wrong candidate snapshot')
            model=SourceTripProposalResponse if source_view else TripProposalResponse;payload={'proposal':proposal_projection(value,domain,source_view)}
        else:
            if type(value) is not list or len(value)>argument[1]:raise ValueError('Invalid page')
            if sum(len(row.content) for row in value)>configuration.max_private_response_bytes:raise PrivateOutputTooLarge()
            rows=[trip_projection(row,domain,source_view) for row in value]
            ids=[row.trip_id for row in rows]
            if ids!=sorted(set(ids)) or any(i<=argument[0] for i in ids):raise ValueError('Invalid C keyset page')
            model=SourceTripListResponse if source_view else TripListResponse;payload={'trips':rows,'next_after':ids[-1] if ids else None}
        if source_view and kind in ('detail','proposal','list'):
            payload['representation'] = 'provenance.1'
        body=JSONResponse(model.model_validate({'request_id':request.state.request_id,**payload}).model_dump(mode='json')).body
        if len(body)>configuration.max_private_response_bytes:raise PrivateOutputTooLarge()
        return body

    async def invoke(request,token,kind,argument,source_view):
        def operation(ctx):
            if kind=='act':value=ctx.act(argument)
            elif kind=='query':value=ctx.query_action(argument)
            elif kind=='detail':value=ctx.detail(argument)
            elif kind=='proposal':value=ctx.proposal_detail(argument)
            else:value=ctx.list_trips(*argument)
            return project(request,kind,value,argument,source_view)
        try:
            body=await run_in_threadpool(boundary.with_operation,token,operation)
            return Response(content=body,media_type='application/json')
        except Exception as exc:return failure(request,kind=='act',exc)

    @app.post('/v1/trip-actions',response_model=TripActionResponse)
    async def act(request:Request):
        if boundary is None:return failure(request,True)
        prepared=prepare(request)
        if isinstance(prepared,JSONResponse):return prepared
        token,_,source_view=prepared
        media=request.headers.getlist('content-type')
        if (len(media)!=1 or media[0].split(';',1)[0].strip().lower()!='application/octet-stream'
                or request.headers.get('content-encoding','identity').lower()!='identity'):
            return _error(request,415,'UNSUPPORTED_MEDIA_TYPE','input','failed','do_not_retry')
        chunks=[];size=0
        try:
            async for chunk in request.stream():
                size+=len(chunk)
                if size>configuration.max_action_bytes:return _error(request,413,'BODY_TOO_LARGE','input','failed','do_not_retry')
                chunks.append(chunk)
            action=parse_action(b''.join(chunks),domain)
        except (ValueError,UnicodeError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        except Exception:return failure(request,True)
        return await invoke(request,token,'act',action,source_view)

    @app.get('/v1/trip-action-receipts',response_model=TripActionQueryResponse)
    async def query(request:Request):
        prepared=prepare(request,('action_id',))
        if isinstance(prepared,JSONResponse):return prepared
        token,q,source_view=prepared;return await invoke(request,token,'query',q['action_id'],source_view)

    @app.get('/v1/trip-details',response_model=TripDetailResponse | SourceTripDetailResponse)
    async def detail(request:Request):
        prepared=prepare(request,('trip_id',))
        if isinstance(prepared,JSONResponse):return prepared
        token,q,source_view=prepared;return await invoke(request,token,'detail',q['trip_id'],source_view)

    @app.get('/v1/trip-proposals',response_model=TripProposalResponse | SourceTripProposalResponse)
    async def proposal(request:Request):
        prepared=prepare(request,('proposal_id',))
        if isinstance(prepared,JSONResponse):return prepared
        token,q,source_view=prepared;return await invoke(request,token,'proposal',q['proposal_id'],source_view)

    @app.get('/v1/trips',response_model=TripListResponse | SourceTripListResponse)
    async def listing(request:Request):
        prepared=prepare(request,('limit',),('after',))
        if isinstance(prepared,JSONResponse):return prepared
        token,q,source_view=prepared;return await invoke(request,token,'list',(q.get('after',''),q['limit']),source_view)
