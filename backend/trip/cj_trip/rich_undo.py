"""Additive undo input data, not a handler, confirmation or write capability."""
from dataclasses import dataclass
import json

from cj_strict_json import reject_duplicates
from .domain import packed
from .lio_history import Undo
from .structured import _fields

VERSION = 'TRIP-lio-undo.3'


@dataclass(frozen=True, repr=False)
class RichUndo:
    raw: bytes
    action_id: str
    trip_id: str
    expected_version: int
    original_hash: str
    content_version: str

    @classmethod
    def parse(cls, raw):
        if type(raw) is not bytes or not 0 < len(raw) <= 1024:
            raise ValueError('bounded original rich undo input required')
        try:
            value = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate undo field'))
        except (ValueError, RecursionError):
            raise ValueError('strict complete undo JSON required') from None
        _fields(value, {'version', 'action_id', 'trip_id', 'expected_version', 'original_hash', 'content_version'},
                'undo', 'exact rich undo input required')
        if value['version'] != VERSION or packed(value) != raw:
            raise ValueError('new canonical rich undo version required')
        if value['content_version'] not in ('structured.1', 'structured.2', 'structured.3', 'structured.4'):
            raise ValueError('explicit original content version required')
        # Common scalar grammar only, never dispatch/store this private copy as
        # an old action. The returned raw bytes retain the new version and hash.
        fields = {k: v for k, v in value.items() if k != 'content_version'}
        fields['version'] = 'TRIP-lio-undo.1'
        old = Undo.parse(packed(fields))
        return cls(raw, old.action_id, old.trip_id, old.expected_version, old.original_hash, value['content_version'])
