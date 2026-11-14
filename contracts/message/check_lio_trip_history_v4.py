"""Offline new4 history/undo snapshot validation; no actual write permission."""
from pathlib import Path
import json

from jsonschema import Draft202012Validator,FormatChecker
from referencing import Registry,Resource
from .check_lio_v4 import _card3

HERE=Path(__file__).resolve().parent
SCHEMA=json.loads((HERE/'lio-trip-history-schema.4.json').read_text())
registry=Registry()
for file in ('trip-schema.2.json','lio-exploration-schema.4.json'):
    value=json.loads((HERE/file).read_text())
    registry=registry.with_resource(value['$id'],Resource.from_contents(value))
VALIDATOR=Draft202012Validator(SCHEMA,registry=registry,format_checker=FormatChecker())


def _target(target):
    if target['restore_version']!=target['expected_version']-1:
        raise ValueError('undo restores the immediately preceding immutable revision')


def validate(value):
    VALIDATOR.validate(value)
    if value['version']=='LIO-trip-undo.4':
        _target(value['target']);return
    if value['version']!='LIO-trip-history.4':return
    current=value['current'];history=value['history'];target=value['undo_target']
    cards=history+([current]if current is not None else [])
    if len({card['trip_id']for card in cards})>1:raise ValueError('history must belong to one trip')
    for card in cards:
        if card['version']=='LIO-trip-card.3':_card3(card)
    versions=[card['trip_version']for card in history]
    if versions!=sorted(set(versions),reverse=True):raise ValueError('history versions must be unique and descending')
    if current is not None:
        if any(card['trip_id']!=current['trip_id'] or card['trip_version']>=current['trip_version']for card in history):
            raise ValueError('history must belong to the same older trip revisions')
    if target is not None:
        _target(target)
        if current is None or (target['trip_id'],target['expected_version'],target['original_hash'],target['content_version'])!=(
                current['trip_id'],current['trip_version'],current['content_sha256'],current['content_version']):
            raise ValueError('undo target must bind the exact current snapshot')
        prior=next((card for card in history if card['trip_version']==target['restore_version']),None)
        if prior is None or (target['restore_hash'],target['restore_content_version'])!=(prior['content_sha256'],prior['content_version']):
            raise ValueError('undo target must bind the exact previous content')
    if value['next_before'] is not None and (not history or int(value['next_before'])!=history[-1]['trip_version'] or
                                            int(value['next_before'])>=2**63):
        raise ValueError('history cursor must be the final returned immutable version')
