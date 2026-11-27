"""User-facing send and polling routes over the original dialogue service."""
import json
import re

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from cj_message.demo_dialogue import LIO_CHAT_PATTERN, LIO_VERSION, LIO_VERSION_V2, LIO_VERSION_V3, message_id
from cj_message.domain import InvalidInput
from cj_message.lio_context import FOLLOWUPS_EFFECT, LAYOUT_EFFECT, SOURCE_EFFECT, TOOL_EFFECT, UNSETTLED_VISIBLE_ANSWER, UNSAVED_PLAN_ANSWER, answer_locale, display_answer, self_description
from cj_message.lio_plan_needs import BOUND_EFFECT, EDIT_BOUND_EFFECT
from cj_run.core import Binding
from cj_agent.run_timing import accepted
from cj_run.display_snapshot import SnapshotTooLarge

from cj_message.lio_followups import VERSION as FOLLOWUPS_VERSION, wire_followups
from cj_message import lio_cards, lio_entities, lio_rich_receipt
from .lio_memory_prompt import PROMPT_EFFECT
from cj_memory.titles import USED_EFFECT, parse_used
from cj_message.lio_entities import ENTITIES_EFFECT

from .local_lio_planning import ITINERARY_PREVIEW_VERSION,read_itinerary_preview
from .lio_weather import CITY_EFFECT,reference as city_weather_reference
from .history_routes import _query
from .message_routes import BodyError, _read_body, _token, message_failure


TIMELINE_VERSION = 'LIO-timeline.1'
RECEIPT_VERSION = 'LIO-message-receipt.1'
BEIJING_PUBLIC_FORECAST = 'https://www.weather.com.cn/weather/101010100.shtml'
RICH_VERSION = 'LIO-answer-rich.1'   # #1984; `accepts` takes exactly one of FOLLOWUPS_VERSION, RICH_VERSION
MAX_RICH_BYTES = 16384
RECEIPT_EFFECT = 'lio_trip_receipt:'   # written by the trip side (T-1); this module only reads it


def _json(value, status=200):
    return JSONResponse(value, status_code=status, headers={'Cache-Control': 'no-store'})


def _failure(status):
    return _json({'failure': 'quota' if status == 429 else 'unavailable'}, status)


def _message(item, state, *, expired=False, trip=None, memory=None, identity=True, declared=False, receipt=None, prompt_open=None, used_titles=None):
    failure = None
    locale = answer_locale(item.text, item.locale)
    if trip is not None:
        status = 'completed'
    elif expired:
        status, failure = 'failed', 'unavailable'
    elif state is None or state.status == 'queued':
        status = 'sending'
    elif state.status == 'running':
        status = 'answering'
    elif state.status == 'unknown' and UNSETTLED_VISIBLE_ANSWER in state.effects and state.text.strip():
        status = 'completed'
    elif state.status == 'completed' and (state.draft_outcome is None or
            UNSAVED_PLAN_ANSWER in state.effects and state.text.strip()):
        status = 'completed'
    else:
        status = 'failed'
        failure = ('quota' if state.budget_exhausted_stage != 'none'
                   else 'unavailable')
    sources = []
    layout = None
    followups = None
    entities = None
    cards = None
    prompt = False
    used = None
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
            elif effect.startswith(LAYOUT_EFFECT):
                layout = effect.removeprefix(LAYOUT_EFFECT)
            elif effect.startswith(USED_EFFECT):
                used = effect
            elif effect == PROMPT_EFFECT:
                prompt = True
            elif effect.startswith(lio_cards.CARDS_EFFECT):
                cards = effect
            elif effect.startswith(ENTITIES_EFFECT):
                entities = effect   # the last one counts
            elif effect.startswith(FOLLOWUPS_EFFECT):
                try:
                    followups = wire_followups(json.loads(effect.removeprefix(FOLLOWUPS_EFFECT)))
                except ValueError:
                    followups = None
            elif effect.startswith(CITY_EFFECT):
                weather_city = json.loads(effect.removeprefix(CITY_EFFECT))
            elif status == 'answering' and effect.startswith(TOOL_EFFECT):
                activity = json.loads(effect.removeprefix(TOOL_EFFECT))['activity']
    if amap_weather:
        # Records predating CITY_EFFECT came from the frozen Beijing-only
        # weather producer. New nationwide calls always carry an exact city.
        url = BEIJING_PUBLIC_FORECAST if weather_city is None else city_weather_reference(weather_city['adcode'])
        if url is not None:
            name = ('北京' if locale == 'zh' else 'Beijing') if weather_city is None else weather_city['name']
            title = ('中国天气网 · '+name+'当前预报（参考）' if locale == 'zh'
                     else 'Weather China · Current '+name+' forecast (reference)')
            sources.append(dict(title=title,url=url,observed_at=None))
    # Failed streams can leave provisional text in the original RUN. Keep
    # those bytes for diagnosis without returning them as a terminal answer.
    answer = display_answer(state.text, locale) if state is not None and status != 'failed' else ''
    if identity and status == 'completed' and answer is not None:
        introduction = self_description(item.text, locale)
        if introduction is not None:
            answer = introduction
    if answer is None:
        if status == 'completed' and trip is None:
            status, failure = 'failed', 'unavailable'
        answer = ''
    row = dict(message_id=item.message_id, text=item.text, answer=answer, status=status,
               failure=failure, activity=activity, sources=sources, trip=trip, memory=memory)
    if declared == 'plan-memory':
        # #2100: a v3 calendar row of a poll that declared LIO-answer-rich.1 carries `rich` with `memory.used` and nothing else
        # (no layout, no followups, no entities, cards, receipt or prompt). The row is exactly the undeclared row otherwise.
        if status == 'completed' and used is not None and used_titles is not None:
            rich = _rich(answer, None, None, None, used=(used, used_titles))
            if rich is not None:
                row['rich'] = rich
    elif declared:
        # W2-1 (#1727), only for a poll that declared LIO-answer-followups.1. The layout is committed
        # before an answer's first text, so any row with text or a final status carries the same value.
        layout = layout if layout in ('split', 'single') else 'single'
        if answer or status in ('completed', 'failed'):
            row['layout'] = layout
        if status == 'completed' and answer and followups is not None and trip is None and layout == 'split':
            row['followups'] = followups
        if declared == 'rich' and status in ('completed', 'failed'):
            # Entities and cards need a finished answer; the save receipt also rides a failed row, because a save
            # that committed before the answer failed still needs its undo (contract).
            finished = status == 'completed' and bool(answer)
            rich = _rich(answer, entities if finished else None, cards if finished and trip is None else None, receipt,
                         prompt=prompt_open if finished and prompt else None,
                         used=(used, used_titles) if finished and used is not None and used_titles is not None else None)
            if rich is not None:
                row['rich'] = rich
                # The one difference from the followups.1 row: a taxi card replaces the taxi button.
                if any(card['type'] == 'taxi' for card in rich.get('cards', ())) and 'followups' in row:
                    kept = [a for a in row['followups'].get('actions', ()) if a.get('tool') != 'taxi']
                    body = {k: v for k, v in row['followups'].items() if k != 'actions'}
                    if kept:
                        body['actions'] = kept
                    if 'actions' in body or 'chips' in body:
                        row['followups'] = body
                    else:
                        del row['followups']
    return row


def _rich(answer, entities, cards=None, receipt=None, prompt=None, used=None):
    """`rich` for a row of a poll that declared LIO-answer-rich.1, or None. Every part fails alone and quietly:
    a bad or missing part is left out, `rich` never fails the page. Parts are added here as their tickets land
    (entities D-1 #1989; cards D-2 #1990; receipt T-1 #1994; memory M-1/M-3)."""
    try:
        if not lio_entities.rich_enabled():
            return None   # off: a rich declaration reads exactly like followups.1, not a 400
        value = {}
        if entities is not None:
            rows = lio_entities.wire(entities, answer, lio_entities.approved_ids().__contains__)
            if rows:
                value['entities'] = rows
        if cards is not None:
            rows = lio_cards.wire(cards)
            if rows:
                value['cards'] = rows
        memory = {}
        if prompt is not None and prompt():   # only after the rich switch said yes: no extra read while it is off
            memory['prompt'] = 'consent'
        if used is not None:
            parsed = parse_used(used[0])
            titles = used[1](parsed[0]) if parsed is not None else {}
            rows = [dict(item_id=i, title=titles[i]) for i in (parsed[0] if parsed else [])
                    if type(titles.get(i)) is str and 0 < len(titles[i]) <= 40 and '\n' not in titles[i]]
            if rows:
                # the traveler may have taken some back since: the count never claims more than is still shown
                memory['used'] = rows
                memory['used_total'] = len(rows) if len(rows) < len(parsed[0]) else max(parsed[1], len(rows))
        if memory:
            value['memory'] = memory
        if receipt is not None:
            checked = lio_rich_receipt.wire(receipt)
            if checked is not None:
                value['trip_receipt'] = checked
        if not value:
            return None
        value = dict(version=RICH_VERSION, **value)
        for part in ('entities', 'cards'):   # the drop order of the contract: entities, then cards; never the receipt
            if len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) <= MAX_RICH_BYTES:
                break
            value.pop(part, None)
        return value if len(value) > 1 else None
    except Exception:
        return None


def _used_titles(memory_cards, context):
    """A lookup of the titles of the memories a row used, run only for a row that carries the used effect; any failure
    is no titles. One read per row at most (three ids)."""
    allowed = []

    def lookup(item_ids):
        try:
            titles = getattr(memory_cards, 'used_titles', None)
            if titles is None:
                return {}
            if not allowed:   # the consent state is read once for the whole page
                allowed.append(bool(memory_cards.used_allowed(context.scope)))
            return titles(context.scope, item_ids, checked=True) if allowed[0] else {}
        except Exception:
            return {}
    return lookup


def _prompt_open(memory_cards, context):
    """A check, run only for a row that carries the prompt marker, that the account still has no consent record and
    the consent switch is on: the prompt is a hint to ask once, never consent, and it is not sent to an account that chose."""
    memo = []

    def check():
        if not memo:   # one read for the whole page
            from .lio_memory_consent import consent_required
            from .lio_memory_prompt import never_chosen
            memo.append(consent_required() and never_chosen(getattr(memory_cards, 'consent', None), context.scope))
        return memo[0]
    return check


def _receipt(reader, context, binding, state):
    """The trip side's receipt for one RUN (T-1, `cj_api.lio_trip_receipt.read`), only when the RUN wrote a receipt effect
    and the poll declared rich; any failure of the reader leaves the receipt out and never fails the page."""
    if reader is None or state is None or state.status not in ('completed', 'failed', 'unknown') \
            or not any(e.startswith(RECEIPT_EFFECT) for e in state.effects):
        return None
    try:
        if not lio_entities.rich_enabled():
            return None   # off: no extra database read (contract R-1)
        return reader(context.scope, binding.run_id, state.effects)
    except Exception:
        return None


def _timeline(boundary, resolve_runs, trip_cards, memory_cards, token, conversation_id, before, multiple=False,calendar=False,declared=False,receipt_reader=None):
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
                messages.append(_message(item, state, expired=expired, trip=trip, memory=memory, declared=declared,
                                         receipt=_receipt(receipt_reader, context, binding, state) if declared == 'rich' else None,
                                         prompt_open=_prompt_open(memory_cards, context) if declared == 'rich' else None,
                                         used_titles=_used_titles(memory_cards, context) if declared in ('rich', 'plan-memory') else None))
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
        if not calendar and page.requires_new_lio:
            raise InvalidInput('calendar conversation requires its selected reader')
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


def _itinerary_preview(boundary, resolve_runs, token, conversation_id, mid):
    def read(context):
        original = context.query_lio_message(mid)
        if original is None or original.receipt.conversation_id != conversation_id:
            return _failure(404)
        receipt = original.receipt
        binding = Binding(context.scope, conversation_id, receipt.generation, mid, receipt.run_id, receipt.sequence)
        (state, expired), = resolve_runs(context.scope).lio_timeline([binding])
        text = json.loads(original.raw)['text']
        locale = answer_locale(text, 'en')
        preview = (read_itinerary_preview(state, locale)
                   if not expired and self_description(text, locale) is None else None)
        current = context.query_lio_receipt(mid)
        if current is None or (current.conversation_id, current.run_id) != (conversation_id, receipt.run_id):
            return _failure(503)
        if current.requires_exploration or current.requires_new_lio:
            return _failure(400)
        return _json(dict(version=ITINERARY_PREVIEW_VERSION, conversation_id=conversation_id,
                          message_id=mid, preview=preview))

    return boundary.with_history_context(token, read)


def register_lio_dialogue_routes(app, boundary, resolve_runs, trip_cards, *, prepare_scope, memory_cards=None,calendar_cards=None,calendar_boundary=None,
                                 trip_receipt_reader=None):
    async def send(request, version, receipt_version):
        token = _token(request)
        if token is None:
            return _failure(401)
        if request.scope['query_string']:
            return _failure(400)
        try:
            raw = await _read_body(request, 16384)
            selected = calendar_boundary if version == LIO_VERSION_V3 else boundary
            receipt = await run_in_threadpool(selected.receive_lio, token, raw, prepare_scope=prepare_scope,
                                              version=version)
        except BodyError as exc:
            return _failure(exc.status)
        except Exception as exc:
            return _failure(message_failure(request, exc, True).status_code)
        accepted(receipt.message_id)
        return _json(dict(version=receipt_version, message_id=receipt.message_id,
                          conversation_id=receipt.conversation_id))

    async def timeline(request, multiple,calendar=False):
        token = _token(request)
        if token is None:
            return _failure(401)
        try:
            params = _query(request, (), ('conversation_id', 'before', 'accepts'))
            # W2-1 (#1727): the v2 conversation timeline takes followups.1 or rich.1. #2100: the v3 calendar timeline (the App's
            # plan rows, LIO-message.3/.4) takes rich.1 only, and its rows carry nothing from it but `rich.memory.used`.
            if 'accepts' in params and (not multiple or params['accepts'] not in ((RICH_VERSION,) if calendar else (FOLLOWUPS_VERSION, RICH_VERSION))):
                raise ValueError('unsupported accepts')
            conversation = params.get('conversation_id')
            if conversation is not None and not LIO_CHAT_PATTERN.fullmatch(conversation):
                raise InvalidInput('invalid Lio conversation identifier')
            before = message_id(params['before']) if 'before' in params else None
        except (ValueError, UnicodeError):
            return _failure(400)
        try:
            return await run_in_threadpool(_timeline, calendar_boundary if calendar else boundary, resolve_runs,
                                           calendar_cards if calendar else trip_cards, memory_cards, token,
                                           conversation, before, multiple,calendar,
                                           ('plan-memory' if calendar else 'rich') if params.get('accepts') == RICH_VERSION else 'accepts' in params,
                                           trip_receipt_reader if not calendar else None)
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
            selected = calendar_boundary if calendar else boundary
            receipt = await run_in_threadpool(selected.query_lio, token, original_id)
        except Exception as exc:
            return _failure(message_failure(request, exc, False).status_code)
        value = None
        if receipt is not None:
            if receipt.requires_exploration:
                return _failure(400)
            if not calendar and receipt.requires_new_lio:
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

    @app.get('/v2/lio/itinerary-preview')
    async def itinerary_preview(request: Request):
        token = _token(request)
        if token is None:
            return _failure(401)
        try:
            params = _query(request, ('conversation_id', 'message_id'))
            cid = params['conversation_id']
            if LIO_CHAT_PATTERN.fullmatch(cid) is None:
                raise InvalidInput('invalid Lio conversation identifier')
            mid = message_id(params['message_id'])
        except (ValueError, UnicodeError):
            return _failure(400)
        try:
            return await run_in_threadpool(_itinerary_preview, boundary, resolve_runs, token, cid, mid)
        except Exception as exc:
            return _failure(message_failure(request, exc, False).status_code)
