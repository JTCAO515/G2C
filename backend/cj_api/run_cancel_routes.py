"""Bounded RUN-CANCEL@1; no caller principal, run ID, scope or dispatch permission."""
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from cj_auth.interfaces import AdmissionReason, AdmissionStatus
from cj_message.auth_boundary import AccessBlocked, IdentityChanged
from cj_run.cancellation import (CancelCommand,TravelCancelCommand,TripCancelCommand,EditCancelCommand,CancellationHandler,CancellationInputTooLarge,
                                 CancellationUnknown,MAX_CANCEL_BYTES,MAX_TRAVEL_CANCEL_BYTES)
from .generated import RunCancellationResponse,RunTravelCancellationResponse
from .message_routes import _error, _token


def register_run_cancel_route(app, reader=None, display_configuration=None, configuration=None):
    # Display-only composition remains read-only. The explicit local streaming
    # composition already owns the scoped RUN repository used by its worker.
    handler = (CancellationHandler(reader.message_boundary, reader.resolve_run_repository)
               if reader is not None and configuration is not None else None)

    def unavailable(request, code='RUN_CANCEL_UNAVAILABLE'):
        return _error(request, 503, code, 'dependency', 'unknown', 'reconcile_original')

    async def cancel_version(request:Request, *, travel, formal=False,edit=False):
        if handler is None: return unavailable(request)
        token = _token(request)
        if token is None: return _error(request, 401, 'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
        media = request.headers.getlist('content-type')
        if len(media) != 1 or media[0].split(';', 1)[0].strip().lower() != 'application/json':
            return _error(request, 415, 'UNSUPPORTED_MEDIA_TYPE', 'input', 'failed', 'do_not_retry')
        try:
            if request.scope['query_string']: raise ValueError('query parameters unavailable')
            raw = bytearray()
            limit=MAX_TRAVEL_CANCEL_BYTES if travel else MAX_CANCEL_BYTES
            async for chunk in request.stream():
                if len(raw) + len(chunk) > limit: raise CancellationInputTooLarge()
                raw.extend(chunk)
            command = EditCancelCommand.parse(bytes(raw)) if edit else TripCancelCommand.parse(bytes(raw)) if formal else TravelCancelCommand.parse(bytes(raw)) if travel else CancelCommand.parse(bytes(raw))
        except CancellationInputTooLarge:
            return _error(request, 413, 'REQUEST_TOO_LARGE', 'input', 'failed', 'do_not_retry')
        except (ValueError, UnicodeError, RecursionError):
            return _error(request, 400, 'INVALID_INPUT', 'input', 'failed', 'do_not_retry')

        def project(state,reference=None):
            value=dict(request_id=request.state.request_id,
                message_id=state.binding.message_id, run_id=state.binding.run_id,
                status=state.status,event_highwater=state.sequence)
            if travel:
                value.update(version='RUN-cancel.4' if edit else 'RUN-cancel.3' if formal else 'RUN-cancel.2',reference=reference.public_value())
            if formal:
                body=JSONResponse(value).body
            else:
                response=(RunTravelCancellationResponse if travel else RunCancellationResponse).model_validate(value)
                body=JSONResponse(response.model_dump(mode='json')).body
            if len(body) > display_configuration.max_response_bytes:
                raise ValueError('cancellation response exceeds configured bound')
            return body

        try:
            operation=handler.cancel_edit_projected if edit else handler.cancel_trip_projected if formal else handler.cancel_travel_projected if travel else handler.cancel_projected
            body = await run_in_threadpool(operation, token, command, project)
            return Response(content=body, media_type='application/json', headers={'Cache-Control': 'no-store'})
        except CancellationUnknown:
            return unavailable(request, 'RUN_CANCEL_UNKNOWN')
        except AccessBlocked as exc:
            if exc.status is AdmissionStatus.UNKNOWN:
                return _error(request, 503, 'ACCESS_UNKNOWN', 'access', 'unknown', 'retry_safe_read')
            return _error(request, 401 if exc.reason is AdmissionReason.IDENTITY_INVALID else 403,
                          'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
        except IdentityChanged:
            return _error(request, 403, 'ACCESS_DENIED', 'access', 'failed', 'do_not_retry')
        except Exception:
            return unavailable(request)

    @app.post('/v1/run-cancellations',response_model=RunCancellationResponse)
    async def cancel(request:Request):return await cancel_version(request,travel=False)

    @app.post('/v2/run-cancellations',response_model=RunTravelCancellationResponse)
    async def cancel_v2(request:Request):return await cancel_version(request,travel=True)

    @app.post('/v3/run-cancellations')
    async def cancel_v3(request:Request):return await cancel_version(request,travel=True,formal=True)

    @app.post('/v4/run-cancellations')
    async def cancel_v4(request:Request):return await cancel_version(request,travel=True,formal=True,edit=True)
