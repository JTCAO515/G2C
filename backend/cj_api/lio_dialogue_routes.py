"""User-facing send and polling routes over the original dialogue service."""
import json
import re

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from cj_message.demo_dialogue import LIO_CHAT_PATTERN, LIO_VERSION, LIO_VERSION_V2, LIO_VERSION_V3, message_id
from cj_message.domain import InvalidInput
from cj_message.lio_context import SOURCE_EFFECT, TOOL_EFFECT, display_answer, self_description
from cj_message.lio_plan_needs import BOUND_EFFECT, EDIT_BOUND_EFFECT
from cj_run.core import Binding
from cj_run.display_snapshot import SnapshotTooLarge

from .lio_weather import CITY_EFFECT,reference as city_weather_reference
from .history_routes import _query
from .message_routes import BodyError, _read_body, _token, message_failure


TIMELINE_VERSION = 'LIO-timeline.1'
RECEIPT_VERSION = 'LIO-message-receipt.1'
BEIJING_PUBLIC_FORECAST = 'https://www.weather.com.cn/weather/101010100.shtml'


def _json(value, status=200):
    return JSONResponse(value, status_code=status, headers={'Cache-Control': 'no-store'})


def _failure(status):
    return _json({'failure': 'quota' if status == 429 else 'unavailable'}, status)


def _message(item, state, *, expired=False, trip=None, memory=None):
    failure = None
    if trip is not None:
        status = 'completed'
    elif expired:
        status, failure = 'failed', 'unavailable'
    elif state is None or state.status == 'queued':
        status = 'sending'
    elif state.status == 'running':
        status = 'answering'
    elif state.status == 'completed' and state.draft_outcome is None:
        status = 'completed'
    else:
        status = 'failed'
        failure = ('quota' if state.budget_exhausted_stage != 'none'
                   else 'unavailable')
    sources = []
    amap_weather = False
    weather_city = None
    activity = None
    if state is not None:
        for effect in state.effects:
            if effect.startswith(SOURCE_EFFECT):
                citation = json.loads(effect.removeprefix(SOURCE_EFFECT))
                sources.append(dict(title=citation['title'], url=citation['url'],
                                    observed_at=citation['observed_at']))
                amap_weather |= citation['title'] in ('高德天气', 'Amap Weather') and citation['url'] is None
            elif effect.startswith(CITY_EFFECT):
                weather_city = json.loads(effect.removeprefix(CITY_EFFECT))
            elif status == 'answering' and effect.startswith(TOOL_EFFECT):
                activity = json.loads(effect.removeprefix(TOOL_EFFECT))['activity']
    if amap_weather:
        # Records predating CITY_EFFECT came from the frozen Beijing-only
        # weather producer. New nationwide calls always carry an exact city.
        url = BEIJING_PUBLIC_FORECAST if weather_city is None else city_weather_reference(weather_city['adcode'])
        if url is not None:
            name = ('北京' if item.locale == 'zh' else 'Beijing') if weather_city is None else weather_city['name']
            title = ('中国天气网 · '+name+'当前预报（参考）' if item.locale == 'zh'
                     else 'Weather China · Current '+name+' forecast (reference)')
            sources.append(dict(title=title,url=url,observed_at=None))
    answer = display_answer(state.text, item.locale) if state is not None else ''
    if status == 'completed' and answer is not None:
        introduction = self_description(item.text, item.locale)
        if introduction is not None:
            answer = introduction
    if answer is None:
        if status == 'completed' and trip is None:
            status, failure = 'failed', 'unavailable'
        answer = ''
    return dict(message_id=item.message_id, text=item.text, answer=answer, status=status,
                failure=failure, activity=activity, sources=sources, trip=trip, memory=memory)


def _timeline(boundary, resolve_runs, trip_cards, memory_cards, token, conversation_id, before, multiple=False,calendar=False):
    def compose(context, page, bindings, snapshots):
        messages = []
        if page.messages:
            for item, binding, (state, expired) in zip(page.messages, bindings, snapshots, strict=True):
                trip = None
                if state is not None:
                    if calendar:
                        from .local_lio_calendar import DATE_ATTEMPT
                        if EDIT_BOUND_EFFECT in state.effects or BOUND_EFFECT in state.effects:
                            trip=trip_cards.read(token,binding,edit=EDIT_BOUND_EFFECT in state.effects,
                                                 protocol=item.protocol,conversion=DATE_ATTEMPT in state.effects)
                    elif EDIT_BOUND_EFFECT in state.effects:
                        trip = trip_cards.read(token, binding, edit=True)
                    elif BOUND_EFFECT in state.effects:
                        trip = trip_cards.read(token, binding)
                memory = (memory_cards.project(context, token, item.message_id, binding.run_id)
                          if memory_cards is not None and state is not None and state.status == 'completed' else None)
                messages.append(_message(item, state, expired=expired, trip=trip, memory=memory))
        version = 'LIO-timeline.3' if calendar else 'LIO-timeline.2' if multiple else TIMELINE_VERSION
        response = _json(dict(version=version, conversation_id=page.conversation_id,
                              messages=messages, next_before=page.next_before))
        if len(response.body) > 4_500_000:
            raise SnapshotTooLarge('Lio timeline exceeds response bound')
        if context.lio_timeline(conversation_id, before, multiple=multiple) != page:
            return _failure(503)
        return response

    def project(context):
        page = context.lio_timeline(conversation_id, before, multiple=multiple)
        if not calendar and any(item.protocol==LIO_VERSION_V3 for item in page.messages):
            raise InvalidInput('calendar conversation requires new Lio timeline')
        # An empty page never needed a MESSAGE owner row. Keep that path and
        # its final page/AUTH checks; existing originals get one protected frame.
        if not page.messages:
            return compose(context, page, (), ())
        bindings = [Binding(context.scope, page.conversation_id, page.generation,
                            item.message_id, item.run_id, item.sequence) for item in page.messages]
        snapshots = resolve_runs(context.scope).lio_timeline(bindings)
        # Classify and compose from the same snapshots: a pending-only page
        # must not gain an M lock, or later slip into an unlocked Memory read.
        requires_original = memory_cards is not None and any(
            state is not None and state.status == 'completed' for state, _ in snapshots)
        if requires_original:
            return context.with_lio_timeline_projection(lambda: compose(context, page, bindings, snapshots))
        return compose(context, page, bindings, snapshots)

    return boundary.with_history_context(token, project)


def register_lio_dialogue_routes(app, boundary, resolve_runs, trip_cards, *, prepare_scope, memory_cards=None,calendar_cards=None):
    async def send(request, version, receipt_version):
        token = _token(request)
        if token is None:
            return _failure(401)
        if request.scope['query_string']:
            return _failure(400)
        try:
            raw = await _read_body(request, 16384)
            receipt = await run_in_threadpool(boundary.receive_lio, token, raw, prepare_scope=prepare_scope,
                                              version=version)
        except BodyError as exc:
            return _failure(exc.status)
        except Exception as exc:
            return _failure(message_failure(request, exc, True).status_code)
        return _json(dict(version=receipt_version, message_id=receipt.message_id,
                          conversation_id=receipt.conversation_id))

    async def timeline(request, multiple,calendar=False):
        token = _token(request)
        if token is None:
            return _failure(401)
        try:
            params = _query(request, (), ('conversation_id', 'before'))
            conversation = params.get('conversation_id')
            if conversation is not None and not LIO_CHAT_PATTERN.fullmatch(conversation):
                raise InvalidInput('invalid Lio conversation identifier')
            before = message_id(params['before']) if 'before' in params else None
        except (ValueError, UnicodeError):
            return _failure(400)
        try:
            return await run_in_threadpool(_timeline, boundary, resolve_runs,
                                           calendar_cards if calendar else trip_cards, memory_cards, token,
                                           conversation, before, multiple,calendar)
        except Exception as exc:
            return _failure(message_failure(request, exc, False).status_code)

    @app.post('/v1/lio/messages')
    async def send_default(request: Request):
        return await send(request, LIO_VERSION, RECEIPT_VERSION)

    @app.post('/v2/lio/messages')
    async def send_conversation(request: Request):
        return await send(request, LIO_VERSION_V2, 'LIO-message-receipt.2')

    if calendar_cards is not None:
        @app.post('/v3/lio/messages')
        async def send_calendar(request: Request):
            return await send(request,LIO_VERSION_V3,'LIO-message-receipt.3')

        @app.get('/v3/lio/timeline')
        async def timeline_calendar(request: Request):
            return await timeline(request,True,True)

        @app.get('/v3/lio/messages')
        async def read_calendar_receipt(request: Request):
            return await lookup(request,True)

    @app.get('/v2/lio/messages')
    async def read_original_receipt(request: Request):
        return await lookup(request,False)

    async def lookup(request,calendar):
        token = _token(request)
        if token is None:
            return _failure(401)
        try:
            params = _query(request, ('message_id', 'input_sha256'))
            original_id = message_id(params['message_id'])
            digest = params['input_sha256']
            if re.fullmatch(r'[0-9a-f]{64}', digest) is None:
                raise InvalidInput('invalid original message digest')
        except (ValueError, UnicodeError):
            return _failure(400)
        try:
            receipt = await run_in_threadpool(boundary.query_lio, token, original_id)
        except Exception as exc:
            return _failure(message_failure(request, exc, False).status_code)
        value = None
        if receipt is not None:
            if not calendar and receipt.protocol==LIO_VERSION_V3:
                return _failure(400)
            if receipt.input_sha256 != digest:
                return _failure(409)
            value = dict(version='LIO-message-receipt.3' if calendar else 'LIO-message-receipt.2', message_id=receipt.message_id,
                         conversation_id=receipt.conversation_id)
        return _json(dict(version='LIO-message-lookup.3' if calendar else 'LIO-message-lookup.2', receipt=value))

    @app.get('/v1/lio/timeline')
    async def timeline_default(request: Request):
        return await timeline(request, False)

    @app.get('/v2/lio/timeline')
    async def timeline_conversation(request: Request):
        return await timeline(request, True)
