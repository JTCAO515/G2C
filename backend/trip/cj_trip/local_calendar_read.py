"""Explicit TRIP-structured-read.2; old read endpoints are not widened."""
from hashlib import sha256
import json
import os
from pathlib import Path
import re

from cj_strict_json import compact
from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from cj_api.app import create_app
from cj_api.local_app import LocalDatabase, trip_resolver
from cj_api.local_account_admission_v2 import account_checker_for
from cj_api.composition import CompositionUnavailable
from cj_api.message_routes import _error, _token
from .auth_boundary import Boundary
from .domain import identifier, Denied

VERSION = 'TRIP-structured-read.2'


def create_local_calendar_read_app(*, conninfo_path, auth_dir, run_context, max_response_bytes=1_000_000):
    app = create_app()
    database = LocalDatabase(conninfo_path, run_context=run_context, travel_context=True, needs_context=True)
    register_local_calendar_read_routes(app, database=database, auth_dir=auth_dir,
                                        max_response_bytes=max_response_bytes)
    return app


def register_local_calendar_read_routes(app, *, database, auth_dir,
                                         max_response_bytes=1_000_000, selected_subjects=None):
    if (os.environ.get('CJ_ENV') != 'local' or database.run_context is None
            or type(max_response_bytes) is not int or max_response_bytes < 1):
        raise CompositionUnavailable('explicit local calendar read host required')

    resolve = trip_resolver(database, provision=True)
    checker = account_checker_for(Path(auth_dir), database, selected_subjects=selected_subjects)
    boundary = Boundary(checker, resolve, structured=True, calendar=True)

    def structured(trip):
        document = json.loads(trip.content)
        version = document.get('content_version')
        if version in ('structured.1', 'structured.2', 'structured.3'):
            return document
        if version in (None, 'provenance.1'):
            return None
        raise Denied('unsupported stored content version')

    async def invoke(request, detail):
        token = _token(request)
        if token is None:
            return _error(request, 401, 'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
        pairs = list(request.query_params.multi_items())
        query = dict(pairs)
        try:
            if len(query) != len(pairs):
                raise ValueError('duplicate query')
            if detail:
                if set(query) != {'trip_id'}:
                    raise ValueError('exact trip query required')
                identifier(query['trip_id'])
            else:
                if not set(query) <= {'after', 'limit'}:
                    raise ValueError('unknown query')
                after = query.get('after', '')
                if after:
                    identifier(after)
                if re.fullmatch(r'(?:[1-9][0-9]?|100)', query.get('limit', '20')) is None:
                    raise ValueError('bounded page required')
                limit = int(query.get('limit', '20'))
        except ValueError:
            return _error(request, 400, 'INVALID_INPUT', 'input', 'failed', 'do_not_retry')

        def operation():
            def encode(context):
                result = dict(version=VERSION, request_id=request.state.request_id)
                if detail:
                    trip = context.detail(query['trip_id'])
                    content = None if trip is None else structured(trip)
                    result['trip'] = None if content is None else dict(trip_id=trip.trip_id,
                        version=trip.version, content_sha256=sha256(trip.content).hexdigest(), content=content)
                else:
                    scanned = context.list_trips(after, limit)
                    result['trips'] = []
                    for trip in scanned:
                        content = structured(trip)
                        if content is not None:
                            calendar = content.get('calendar') if content['content_version'] == 'structured.3' else None
                            result['trips'].append(dict(trip_id=trip.trip_id, version=trip.version,
                                content_version=content['content_version'], title=content['title'],
                                content_sha256=sha256(trip.content).hexdigest(), calendar=calendar,
                                day_count=len(content['days']) if calendar is not None else None))
                    result['next_after'] = scanned[-1].trip_id if len(scanned) == limit else None
                raw = compact(result)
                if len(raw) > max_response_bytes:
                    raise Denied('calendar private response exceeds bound')
                return raw
            return boundary.with_operation(token, encode)

        try:
            return Response(content=await run_in_threadpool(operation), media_type='application/json')
        except Exception:
            return _error(request, 503, 'TRIP_UNAVAILABLE', 'dependency', 'unknown', 'retry_safe_read')

    @app.get('/v2/trip-structured-list')
    async def listing(request: Request):
        return await invoke(request, False)

    @app.get('/v6/trip-structured')
    async def read_detail(request: Request):
        return await invoke(request, True)

    return app
