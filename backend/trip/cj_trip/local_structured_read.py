"""Explicit local structured discovery; original AUTH/operation/repository only."""
import json
import os
import re
from hashlib import sha256
from pathlib import Path
from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from cj_api.app import create_app
from cj_api.local_app import LocalDatabase,scope_for
from cj_api.local_worker_context import checker_for
from cj_api.composition import CompositionUnavailable
from cj_api.message_routes import _error,_token
from cj_agent.draft import trip_scope_for
from .auth_boundary import Boundary
from .domain import identifier,Denied

VERSION='TRIP-structured-read.1'


def create_local_structured_read_app(*,conninfo_path,auth_dir,run_context,max_response_bytes=1_000_000):
    if os.environ.get('CJ_ENV')!='local' or run_context is None or type(max_response_bytes) is not int or max_response_bytes<1:
        raise CompositionUnavailable('explicit local structured read host required')
    database=LocalDatabase(conninfo_path,run_context=run_context,travel_context=True,needs_context=True)
    def resolve(principal):
        owner=scope_for(principal.issuer,principal.subject);scope=trip_scope_for(owner)
        # Existing Trip host provisioning; no formal record/Proposal is created.
        with database.connect(owner) as conn:
            conn.execute('INSERT INTO cj_trip_scope(scope) VALUES(%s) ON CONFLICT DO NOTHING',(scope,))
        return lambda:database.connect(owner),scope
    boundary=Boundary(checker_for(Path(auth_dir)),resolve,structured=True)
    app=create_app()

    def structured(trip):
        content=json.loads(trip.content);version=content.get('content_version')
        if version in ('structured.1','structured.2'):return content
        if version in (None,'provenance.1'):return None
        raise Denied('unsupported stored content version')

    def summary(trip,content):
        return dict(trip_id=trip.trip_id,version=trip.version,content_version=content['content_version'],
                    title=content['title'],content_sha256=sha256(trip.content).hexdigest())

    async def invoke(request,kind):
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        pairs=list(request.query_params.multi_items());query=dict(pairs)
        try:
            if len(query)!=len(pairs):raise ValueError('duplicate query')
            if kind=='detail':
                if set(query)!={'trip_id'}:raise ValueError('exact trip query required')
                identifier(query['trip_id'])
            else:
                if not set(query)<={'after','limit'}:raise ValueError('unknown query')
                after=query.get('after','')
                if after:identifier(after)
                raw=query.get('limit','20')
                if re.fullmatch(r'(?:[1-9][0-9]?|100)',raw) is None:raise ValueError('bounded page required')
                limit=int(raw)
        except ValueError:return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        def operation():
            def encode(ctx):
                result=dict(version=VERSION,request_id=request.state.request_id)
                if kind=='detail':
                    trip=ctx.detail(query['trip_id']);content=None if trip is None else structured(trip)
                    result['trip']=None if content is None else dict(trip_id=trip.trip_id,version=trip.version,
                        content_sha256=sha256(trip.content).hexdigest(),content=content)
                else:
                    scanned=ctx.list_trips(after,limit)
                    result['trips']=[summary(trip,content) for trip in scanned if (content:=structured(trip)) is not None]
                    # Cursor counts scanned formal records, including legacy ones.
                    result['next_after']=scanned[-1].trip_id if len(scanned)==limit else None
                raw=json.dumps(result,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
                if len(raw)>max_response_bytes:raise Denied('private response too large')
                return raw
            return boundary.with_operation(token,encode)
        try:return Response(content=await run_in_threadpool(operation),media_type='application/json')
        except Exception:return _error(request,503,'TRIP_UNAVAILABLE','dependency','unknown','retry_safe_read')

    @app.get('/v1/trip-structured-list')
    async def listing(request:Request):return await invoke(request,'list')
    @app.get('/v5/trip-structured')
    async def detail(request:Request):return await invoke(request,'detail')
    return app
