"""Private model data for the native4 pipeline; no source or publication grant."""
from hashlib import sha256
import json
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,field_validator

SKELETON='LIO-exploration-plan-skeleton.1'
WORDING='LIO-exploration-plan-wording.1'


class Data(BaseModel):
    model_config=ConfigDict(strict=True,extra='forbid',frozen=True)


class PlaceName(Data):
    name_zh:str=Field(min_length=1,max_length=80)
    name_en:str=Field(min_length=1,max_length=80)

    @field_validator('name_zh','name_en')
    @classmethod
    def literal_name(cls,value):
        if not value.strip()or '|'in value or any(ord(c)<32 or 127<=ord(c)<=159 or 0xD800<=ord(c)<=0xDFFF for c in value):
            raise ValueError('one bounded proposed name required')
        return value


class Meal(Data):
    period:Literal['lunch','dinner']
    place:PlaceName


class Day(Data):
    day_index:int=Field(ge=1,le=366)
    area:str=Field(min_length=1,max_length=100)
    sights:list[PlaceName]=Field(max_length=4)
    meals:list[Meal]=Field(max_length=2)


class Lodging(Data):
    area:str=Field(min_length=1,max_length=100)
    recommendations:list[PlaceName]=Field(min_length=2,max_length=3)


class Skeleton(Data):
    version:Literal['LIO-exploration-plan-skeleton.1']
    title:str=Field(min_length=1,max_length=100)
    days:list[Day]=Field(min_length=1,max_length=366)
    lodging:Lodging


class WordingRow(Data):
    item_id:str=Field(min_length=1,max_length=96,pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$')
    reason:str|None=Field(max_length=400)
    reason_refs:list[str]=Field(max_length=14)
    tip:str|None=Field(max_length=400)


class Wording(Data):
    version:Literal['LIO-exploration-plan-wording.1']
    items:list[WordingRow]=Field(max_length=60)


def response_format(profile):
    model={SKELETON:Skeleton,WORDING:Wording}[profile]
    return dict(type='json_schema',json_schema=dict(name=profile.replace('-','_').replace('.','_'),
        strict=True,schema=model.model_json_schema()))


def response_format_sha256(profile):
    return sha256(json.dumps(response_format(profile),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
