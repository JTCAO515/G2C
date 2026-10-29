"""Prepare an authenticated, content-bound Trip action; never execute it here."""
import base64
import json

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from cj_trip.confirmation import ConfirmationSigner
from cj_trip.domain import Conflict
from .generated import TripConfirmationRequest, TripConfirmationResponse, SourceTripConfirmationResponse
from .message_routes import _error, _token
from .trip_projection import proposal_projection, source_representation


def register_trip_confirmations(app, boundary=None, configuration=None, modules=None, signer=None):
    if signer is not None:
        if (type(signer) is not ConfirmationSigner or boundary is None or configuration is None
                or not modules or boundary.confirm is not signer):
            raise ValueError('same confirmation issuer and transaction validator required')

    @app.post('/v1/trip-confirmations', response_model=TripConfirmationResponse | SourceTripConfirmationResponse)
    async def prepare(request: Request):
        def unavailable():
            return _error(request, 503, 'TRIP_CONFIRMATION_UNAVAILABLE', 'dependency', 'unknown', 'retry_safe_read')

        if signer is None or boundary.confirm is not signer:
            return unavailable()
        token = _token(request)
        if token is None:
            return _error(request, 401, 'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
        media = request.headers.getlist('content-type')
        if (len(media) != 1 or media[0].split(';', 1)[0].strip().lower() != 'application/json'
                or request.headers.get('content-encoding', 'identity').lower() != 'identity'):
            return _error(request, 415, 'UNSUPPORTED_MEDIA_TYPE', 'input', 'failed', 'do_not_retry')

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate field')
                result[key] = value
            return result

        try:
            source_view = source_representation(request)
            if request.scope['query_string']:
                raise ValueError('no query parameters')
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > configuration.max_action_bytes:
                    return _error(request, 413, 'BODY_TOO_LARGE', 'input', 'failed', 'do_not_retry')
                chunks.append(chunk)
            raw = b''.join(chunks)
            obj = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
            if type(obj) is not dict or set(obj) != {'action_id', 'kind', 'proposal_id', 'candidate_hash'}:
                raise ValueError('exact confirmation input required')
            command = TripConfirmationRequest.model_validate_json(raw, strict=True)
        except (ValueError, UnicodeError):
            return _error(request, 400, 'INVALID_INPUT', 'input', 'failed', 'do_not_retry')
        except Exception:
            return unavailable()

        def operation(ctx):
            if boundary.confirm is not signer:
                raise ValueError('confirmation configuration changed')
            # Do not mint replacement bytes for an already committed original action.
            if ctx.query_action(command.action_id) is not None:
                raise Conflict('query the original action')
            detail = ctx.proposal_detail(command.proposal_id)
            prepared = signer.issue(ctx.metadata.scope, detail, action_id=command.action_id,
                                    kind=command.kind, candidate_hash=command.candidate_hash)
            model = SourceTripConfirmationResponse if source_view else TripConfirmationResponse
            fields = {
                'request_id': request.state.request_id,
                'action_utf8_base64': base64.b64encode(prepared.action.raw()).decode('ascii'),
                'expires_at': prepared.expires_at,
                'proposal': proposal_projection(detail, modules['cj_trip.domain'], source_view).model_dump(mode='json'),
            }
            if source_view:
                fields['representation'] = 'provenance.1'
            payload = model.model_validate(fields)
            body = JSONResponse(payload.model_dump(mode='json')).body
            if len(body) > configuration.max_private_response_bytes:
                raise ValueError('private response limit')
            return body

        try:
            body = await run_in_threadpool(boundary.with_operation, token, operation)
            return Response(body, media_type='application/json')
        except Conflict:
            return _error(request, 409, 'TRIP_CONFIRMATION_CONFLICT', 'conflict', 'failed', 'do_not_retry')
        except Exception:
            return unavailable()
