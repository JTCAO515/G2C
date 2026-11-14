"""Explicit native4 model input/output data; never a MESSAGE or write grant."""
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel,ConfigDict,Field

UNDERSTANDING='LIO-exploration-understanding.1'
RESPONSE='LIO-exploration-response.1'
PROFILES=(UNDERSTANDING,RESPONSE)


class DTO(BaseModel):
    model_config=ConfigDict(strict=True,extra='forbid',frozen=True)


class Quote(DTO):
    source_index:int=Field(ge=0)
    quote:str=Field(min_length=1,max_length=4000)


class ProfileUpdate(DTO):
    factor_key:str
    value:str | int | bool | list[str] | None
    state:Literal['known','not_needed','inferred']
    sources:list[Quote]=Field(min_length=1,max_length=8)


class Understanding(DTO):
    version:Literal['LIO-exploration-understanding.1']
    intent:Literal['explore','plan','adjust','practical','emergency']
    current_source_index:int=Field(ge=0)
    updates:list[ProfileUpdate]=Field(max_length=28)


class QuestionOption(DTO):
    id:str=Field(min_length=1,max_length=128)
    display_text:str=Field(min_length=1,max_length=400)


class QuestionGroup(DTO):
    factor_key:str
    question:str=Field(min_length=1,max_length=400)
    options:list[QuestionOption]=Field(min_length=3,max_length=4)


class ExplorationResponse(DTO):
    version:Literal['LIO-exploration-response.1']
    body:str=Field(max_length=12000)
    groups:list[QuestionGroup]=Field(max_length=4)


def response_format(profile):
    model={UNDERSTANDING:Understanding,RESPONSE:ExplorationResponse}[profile]
    return dict(type='json_schema',json_schema=dict(name=profile.replace('-','_').replace('.','_'),
        strict=True,schema=model.model_json_schema()))


def response_format_sha256(profile):
    return sha256(json.dumps(response_format(profile),ensure_ascii=False,sort_keys=True,
                             separators=(',',':')).encode()).hexdigest()


@dataclass(frozen=True)
class ExplorationInput:
    """A server-prepared packet, not a client-selectable schema/provider flag."""
    profile:str
    messages:bytes
    system:str
    provider:object
    origin:object
