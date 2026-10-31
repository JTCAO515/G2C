"""structured.2 retains explicit NEEDS minute precision without adding seconds."""
from datetime import time
import re
from .structured import _document,_date,_zone,_offset,_text,observation

VERSION='structured.2'


def _time(value):
    _text(value,8)
    if re.fullmatch(r'[0-9]{2}:[0-9]{2}(?::[0-9]{2})?',value) is None:
        raise ValueError('explicit local HH:MM or HH:MM:SS required')
    time.fromisoformat(value)


def event(value):
    if type(value) is not dict or set(value)!={'date','time','timezone','utc_offset'}:
        raise ValueError('explicit event observations required')
    for field,check in (('date',_date),('time',_time),('timezone',_zone),('utc_offset',_offset)):
        observation(value[field],check)


def validate_document(document):return _document(document,VERSION,event)
