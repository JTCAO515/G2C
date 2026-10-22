"""Readonly preview POST: current own Trip + pure edit/diff, no persistence/permission."""
import base64,json
from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from .generated import ManualPreviewRequest,ManualPreviewResponse
from .message_routes import _error,_token
from .manual_preview_composition import ManualPreviewConfiguration
from .manual_preview_projection import encode_response

class PreviewConflict(Exception):pass
class PreviewUnavailable(Exception):pass
class PreviewInvalid(Exception):pass
class PreviewTooLarge(Exception):pass

def register_manual_preview(app,boundary=None,configuration=None,modules=None):
    if boundary is None:
        if configuration is not None or modules is not None:raise ValueError('Complete preview configuration required')
    elif type(configuration) is not ManualPreviewConfiguration or not modules or type(boundary) is not modules['cj_trip.auth_boundary'].Boundary:
        raise ValueError('Existing public TRIP preview boundary required')
    manual=modules['cj_manual_edit.core'] if modules else None
    trip=modules['cj_trip.domain'] if modules else None
    def unavailable(request):return _error(request,503,'MANUAL_PREVIEW_UNAVAILABLE','dependency','unknown','retry_safe_read')
    @app.post('/v1/trip-manual-previews',response_model=ManualPreviewResponse)
    async def preview(request:Request):
        if boundary is None:return unavailable(request)
        token=_token(request)
        if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
        media=request.headers.getlist('content-type')
        if (len(media)!=1 or media[0].split(';',1)[0].strip().lower()!='application/json'
                or request.headers.get('content-encoding','identity').lower()!='identity'):
            return _error(request,415,'UNSUPPORTED_MEDIA_TYPE','input','failed','do_not_retry')
        def unique(pairs):
            value={}
            for key,item in pairs:
                if key in value:raise ValueError('Duplicate preview input')
                value[key]=item
            return value
        chunks=[];size=0
        try:
            if request.scope['query_string']:raise ValueError('No preview query parameters')
            async for chunk in request.stream():
                size+=len(chunk)
                if size>configuration.max_body_bytes:return _error(request,413,'BODY_TOO_LARGE','input','failed','do_not_retry')
                chunks.append(chunk)
            raw=b''.join(chunks)
            json.loads(raw.decode('utf-8'),object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite input')))
            command=ManualPreviewRequest.model_validate_json(raw,strict=True)
            values=command.model_dump(mode='json')  # Official scalar RootModels serialize to plain IDs.
            original=base64.b64decode(command.original_content_utf8_base64,validate=True)
            if base64.b64encode(original).decode()!=command.original_content_utf8_base64 or not original:raise ValueError('Canonical original base64 required')
            original.decode('utf-8')
            if len(original)>configuration.max_original_bytes:raise PreviewTooLarge()
            title=values['title']
            order=tuple(values['order']) if isinstance(values['order'],list) else None
            for text in ([title] if title is not None else [])+[u.text for u in command.text_updates]:
                if not text.strip():raise ValueError('Nonblank edit text required')
                if len(text.encode('utf-8'))>configuration.max_field_bytes:raise PreviewTooLarge()
        except PreviewTooLarge:return _error(request,413,'PREVIEW_INPUT_TOO_LARGE','input','failed','do_not_retry')
        except (ValueError,UnicodeError,RecursionError):return _error(request,400,'INVALID_INPUT','input','failed','do_not_retry')
        except Exception:return unavailable(request)
        request_id=request.state.request_id
        def operation(ctx):
            actual=ctx.detail(command.trip_id)
            if type(actual) is not trip.Trip or actual.trip_id!=command.trip_id:raise PreviewUnavailable()
            if actual.version!=command.expected_version or actual.content!=original:raise PreviewConflict()
            try:
                draft=manual.edit(actual,expected_version=command.expected_version,original_content=original,
                    selected_ids=tuple(values['selected_ids']),title_selected=command.title_selected,title=title,
                    text_updates=tuple((u.item_id,u.text) for u in command.text_updates),order=order,protected_ids=None)
            except (ValueError,TypeError,UnicodeError):raise PreviewInvalid() from None
            def observe(session):
                current=ctx.detail(command.trip_id)
                if current is not None and (type(current) is not trip.Trip or current.trip_id!=command.trip_id):raise PreviewUnavailable()
                session=session.observe(current)
                if session.status=='UNKNOWN':raise PreviewUnavailable()
                if session.status=='CONFLICT':raise PreviewConflict()
                return session
            session=observe(manual.EditSession(draft))
            body=encode_response(session,request_id,trip)
            if len(body)>configuration.max_response_bytes:raise PreviewTooLarge()
            observe(session)  # Recheck current own source after all private JSON encoding.
            return body
        try:
            body=await run_in_threadpool(boundary.with_operation,token,operation)
            return Response(content=body,media_type='application/json')
        except PreviewConflict:return _error(request,409,'MANUAL_PREVIEW_CONFLICT','conflict','failed','do_not_retry')
        except PreviewInvalid:return _error(request,400,'MANUAL_PREVIEW_UNSUPPORTED','input','failed','do_not_retry')
        except PreviewTooLarge:return _error(request,413,'PREVIEW_RESPONSE_TOO_LARGE','input','failed','retry_safe_read')
        except Exception:return unavailable(request)
