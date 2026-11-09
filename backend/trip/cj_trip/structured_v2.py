"""structured.2 retains explicit NEEDS minute precision without adding seconds."""
from datetime import time
import re
from .structured import _document,_event,_text

VERSION='structured.2'


def _time(value):
    _text(value,8)
    if re.fullmatch(r'[0-9]{2}:[0-9]{2}(?::[0-9]{2})?',value) is None:
        raise ValueError('explicit local HH:MM or HH:MM:SS required')
    time.fromisoformat(value)


def event(value):
    _event(value,_time)


def validate_document(document):return _document(document,VERSION,event)
