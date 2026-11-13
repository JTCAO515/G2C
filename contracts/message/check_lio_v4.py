"""Offline #925 wire validation; no admission, source authority or write grant."""
import json
from datetime import date,timedelta
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

HERE = Path(__file__).resolve().parent
SCHEMA = json.loads((HERE / 'lio-exploration-schema.4.json').read_bytes())
LEGACY = json.loads((HERE / 'trip-schema.2.json').read_bytes())
REGISTRY = Registry().with_resource(LEGACY['$id'], Resource.from_contents(LEGACY))
VALIDATOR = Draft202012Validator(SCHEMA, registry=REGISTRY, format_checker=FormatChecker())


def _unique(rows, key):
    values = [row[key] for row in rows]
    if len(values) != len(set(values)):
        raise ValueError('duplicate presentation identifier: ' + key)


def merged_answer(message):
    """The v4 plain-text projection follows the exact visible section order."""
    parts = [segment['text'] for segment in message['segments']]
    parts += [group['question'] + '\n' + ' / '.join(option['display_text'] for option in group['options'])
              for group in message['question_groups']]
    parts += [notice['text'] for notice in message['notices']]
    if message['exits']:
        parts.append(' / '.join(button['display_text'] for button in message['exits']))
    return '\n\n'.join(parts)


def joint_reply(groups, selected):
    """Synthetic consumer example: partial choices, wire order, one ordinary text."""
    parts = []
    for group in groups:
        chosen = selected.get(group['factor_key'], ())
        allowed = {option['id'] for option in group['options']}
        if (len(chosen) != len(set(chosen)) or not set(chosen) <= allowed
                or not group['multiple'] and len(chosen) > 1):
            raise ValueError('invalid selected option identifiers')
        parts += [option['send_text'] for option in group['options'] if option['id'] in chosen]
    if set(selected) - {group['factor_key'] for group in groups}:
        raise ValueError('unknown selected question group')
    return '\n'.join(parts)


def _card3(card):
    days=card['days']
    if [day['day_index'] for day in days] != list(range(1,len(days)+1)):
        raise ValueError('card days must have contiguous indices')
    dated=card['calendar']['state']=='dated'
    if dated:
        first=date.fromisoformat(card['calendar']['start_date'])
        if [day['date'] for day in days] != [(first+timedelta(days=i)).isoformat()for i in range(len(days))]:
            raise ValueError('card dates differ from their calendar ordinals')
    items=[item for day in days for item in day['items']]
    _unique(items,'item_id')
    item_ids={item['item_id']for item in items}
    checks=card['date_checks']
    if {check['kind']for check in checks} != {'weather','day_opening'}:
        raise ValueError('card date checks must retain both distinct kinds')
    for check in checks:
        if not set(check['day_indices']) <= set(range(1,len(days)+1)) or not set(check['item_ids']) <= item_ids:
            raise ValueError('card date check references are outside the summary')
        if not dated and (check['state']!='not_checked' or check['reason']!='date_not_set' or check['evidence_refs']):
            raise ValueError('undated card cannot claim date-dependent observations')
        if dated and (check['state']=='not_checked' or check['state'] in ('clear','conflict') and not check['evidence_refs']):
            raise ValueError('dated card requires explicit unknown or sourced check result')


def validate(value):
    VALIDATOR.validate(value)
    if value['version'] != 'LIO-timeline.4':
        return
    _unique(value['messages'], 'message_id')
    for message in value['messages']:
        card=message['trip']
        if card is not None and card['version']=='LIO-trip-card.3':
            _card3(card)
        for name, key in (('question_groups', 'factor_key'), ('profile', 'factor_key'),
                          ('notices', 'id'), ('exits', 'id')):
            _unique(message[name], key)
        for group in message['question_groups']:
            _unique(group['options'], 'id')
            if any(not option['id'].startswith(group['factor_key'] + '.') for option in group['options']):
                raise ValueError('option identifier must be scoped to its question factor')
        if message['status'] in ('completed', 'failed') and message['progress'] is not None:
            raise ValueError('terminal message cannot retain planning progress')
        if any(message[name] for name in ('segments', 'question_groups', 'notices', 'exits')):
            if message['answer'] != merged_answer(message):
                raise ValueError('plain answer differs from its presentation projection')
