"""Explicit Lio4 admission and projection; never relabel an old original."""
import json
import re
from typing import Literal

from fastapi import Request
from starlette.concurrency import run_in_threadpool
from cj_message.demo_dialogue import LIO_VERSION_V4,LIO_CHAT_PATTERN,message_id
from cj_message.domain import InvalidInput,Unavailable
from cj_run.core import Binding
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from cj_needs.domain import decode,InvalidInput as InvalidProfileInput

from .lio_dialogue_routes import _failure,_json,_query,_message
from .message_routes import BodyError,_read_body,_token,message_failure
from .lio_exploration_policy import _Group
from .lio_exploration_factors import BY_KEY

PRESENTATION='lio_presentation.1:'
PROGRESS='lio_progress.1:'


def merged_presentation(sections):
    parts=[segment['text'] for segment in sections['segments']]
    parts += [group['question']+'\n'+' / '.join(option['display_text'] for option in group['options']) for group in sections['question_groups']]
    parts += [notice['text'] for notice in sections['notices']]
    if sections['exits']:parts.append(' / '.join(button['display_text'] for button in sections['exits']))
    return '\n\n'.join(parts)


class _DTO(BaseModel):
    model_config=ConfigDict(strict=True,extra='forbid')


class _Segment(_DTO):
    purpose:Literal['response','direction','question','notice','summary']
    text:str=Field(min_length=1,max_length=12000)


class _Exit(_DTO):
    id:str=Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')
    display_text:str=Field(min_length=1,max_length=500)
    send_text:str=Field(min_length=1,max_length=500)


class _Presentation(_DTO):
    segments:list[_Segment]=Field(max_length=32)
    question_groups:list[_Group]=Field(max_length=4)
    # WP4 has no code-produced weather/opening notice source yet. A new typed
    # WP8 notice projection must be supplied before nonempty records are read.
    notices:list=Field(max_length=0)
    exits:list[_Exit]=Field(max_length=4)


def _presentation(state,locale):
    empty=dict(segments=[],question_groups=[],notices=[],exits=[])
    if state is None or state.status!='completed':return empty
    values=[effect.removeprefix(PRESENTATION) for effect in state.effects if effect.startswith(PRESENTATION)]
    if not values:return empty
    # This is persisted data, not an arbitrary object accepted from the client.
    try:value=_Presentation.model_validate(decode(values[-1].encode()))
    except (ValidationError,InvalidProfileInput) as error:
        raise Unavailable('stored exploration presentation unavailable') from error
    keys=[group.factor_key for group in value.question_groups]
    if len(set(keys))!=len(keys) or not set(keys)<=BY_KEY.keys():
        raise Unavailable('stored exploration question factors unavailable')
    for group in value.question_groups:
        ids=[option.id for option in group.options]
        if len(set(ids))!=len(ids) or any(not key.startswith(group.factor_key+'.') for key in ids):
            raise Unavailable('stored exploration options unavailable')
    return value.model_dump()


def _progress(state,locale):
    if state is not None and state.status not in ('queued','running'):return None
    values=[] if state is None else [effect.removeprefix(PROGRESS) for effect in state.effects if effect.startswith(PROGRESS)]
    if values:
        value=json.loads(values[-1])
        if not isinstance(value,dict):raise Unavailable('stored exploration progress unavailable')
        kind=value.get('kind')
        expected={'kind','text','duration_days'} if kind=='planning_started' else {'kind','text'}
        if (kind not in ('waiting','planning_started') or value.keys()!=expected or
                not isinstance(value['text'],str) or not value['text'].strip()):
            raise Unavailable('stored exploration progress unavailable')
        if kind=='planning_started' and (type(value['duration_days']) is not int or not 1<=value['duration_days']<=366):
            raise Unavailable('stored planning duration unavailable')
        return value
    return dict(kind='waiting',text='正在看看你的旅行想法。' if locale=='zh' else 'Looking at your travel ideas.')


def timeline(boundary,resolve_runs,trip_cards,memory_cards,profile_cards,token,cid,before):
    def read(context):
        def project():
            page=context.lio_exploration_timeline(cid,before)
            bindings=[Binding(context.scope,page.conversation_id,page.generation,item.message_id,item.run_id,item.sequence)
                      for item in page.messages]
            states=resolve_runs(context.scope).lio_timeline(bindings)
            messages=[]
            for item,binding,(state,expired) in zip(page.messages,bindings,states,strict=True):
                # Actual4 is a separate source capability. Before WP8 installs
                # the rich writer/read interface, a4 preview has no Trip receipt.
                if item.protocol==LIO_VERSION_V4:
                    if state is not None and state.draft_outcome is not None:
                        raise Unavailable('rich itinerary requires its explicit reader')
                    trip=None
                else:
                    trip=trip_cards.read(token,binding,protocol=item.protocol)
                memory=(memory_cards.project(context,token,item.message_id,item.run_id)
                        if memory_cards is not None and state is not None and state.status=='completed' else None)
                value=_message(item,state,expired=expired,trip=trip,memory=memory)
                sections=_presentation(state,item.locale)
                # Until the new producer publishes sections, preserve the real
                # plain answer rather than showing an empty replacement bubble.
                if not sections['segments'] and value['answer']:
                    sections=dict(sections,segments=[dict(purpose='response',text=value['answer'])])
                if any(sections.values()) and merged_presentation(sections)!=value['answer']:
                    raise Unavailable('filtered answer differs from stored exploration presentation')
                profile=profile_cards.project(context,token,binding,state,item.locale)
                messages.append(dict(value,**sections,profile=profile,progress=_progress(state,item.locale)))
            if context.lio_exploration_timeline(cid,before)!=page:
                raise Unavailable('exploration page changed during projection')
            return dict(version='LIO-timeline.4',conversation_id=page.conversation_id,
                        messages=messages,next_before=page.next_before)
        # Reuse the canonical MESSAGE lock through C projections and final AUTH.
        return context.with_lio_timeline_projection(project)
    return boundary.with_history_context(token,read)


def register_lio_exploration_routes(app,boundary,resolve_runs,trip_cards,profile_cards,*,prepare_scope,memory_cards=None):
    @app.post('/v4/lio/messages')
    async def send(request:Request):
        token=_token(request)
        if token is None:return _failure(401)
        try:
            raw=await _read_body(request,16384)
            receipt=await run_in_threadpool(boundary.receive_lio,token,raw,prepare_scope=prepare_scope,version=LIO_VERSION_V4)
        except BodyError as error:return _failure(error.status)
        except Exception as error:return _failure(message_failure(request,error,True).status_code)
        return _json(dict(version='LIO-message-receipt.4',message_id=receipt.message_id,conversation_id=receipt.conversation_id))

    @app.get('/v4/lio/messages')
    async def lookup(request:Request):
        token=_token(request)
        if token is None:return _failure(401)
        try:
            params=_query(request,('message_id','input_sha256'))
            mid=message_id(params['message_id']);digest=params['input_sha256']
            if re.fullmatch('[0-9a-f]{64}',digest) is None:raise InvalidInput('original digest required')
            receipt=await run_in_threadpool(boundary.query_lio,token,mid)
        except (ValueError,UnicodeError):return _failure(400)
        except Exception as error:return _failure(message_failure(request,error,False).status_code)
        value=None
        if receipt is not None:
            if receipt.protocol!=LIO_VERSION_V4:return _failure(400)
            if receipt.input_sha256!=digest:return _failure(409)
            value=dict(version='LIO-message-receipt.4',message_id=receipt.message_id,conversation_id=receipt.conversation_id)
        return _json(dict(version='LIO-message-lookup.4',receipt=value))

    @app.get('/v4/lio/timeline')
    async def history(request:Request):
        token=_token(request)
        if token is None:return _failure(401)
        try:
            params=_query(request,(),('conversation_id','before'))
            cid=params.get('conversation_id');before=params.get('before')
            if cid is not None and LIO_CHAT_PATTERN.fullmatch(cid) is None:raise InvalidInput('conversation required')
            if before is not None:message_id(before)
        except (ValueError,UnicodeError):return _failure(400)
        try:
            value=await run_in_threadpool(timeline,boundary,resolve_runs,trip_cards,memory_cards,profile_cards,token,cid,before)
        except Exception as error:return _failure(message_failure(request,error,False).status_code)
        return _json(value)
