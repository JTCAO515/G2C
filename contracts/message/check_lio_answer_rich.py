"""Offline LIO-answer-rich.1 checks (#1984): schema plus the rules JSON Schema cannot say.

    python3 -B contracts/message/check_lio_answer_rich.py        # runs the examples file
    from check_lio_answer_rich import check; check(rich, answer)   # raises ValueError / ValidationError

No network, no server, no model. The server and the App run the same rules on what they send and read
(D-1 #1989, D-2 #1990, T-1 #1994, M-1 #1999, M-3 #2001); this file is the contract's reference.
"""
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import unicodedata

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

HERE = Path(__file__).resolve().parent
SCHEMA = json.loads((HERE / 'lio-answer-rich-schema.1.json').read_text(encoding='utf-8'))
EXAMPLES_PATH = HERE / 'lio-answer-rich-examples.1.json'
_HISTORY = json.loads((HERE / 'lio-trip-history-schema.4.json').read_text(encoding='utf-8'))
VALIDATOR = Draft202012Validator(
    SCHEMA, registry=Registry().with_resource(_HISTORY['$id'], Resource.from_contents(_HISTORY)),
    format_checker=FormatChecker())

MAX_RICH_BYTES = 16384
MAX_ANSWER_SCALARS = 200000
ENTITY_SPAN = (2, 32)
# A Chinese-name sequence that ends with one of these is a different place ("王府井站" is a station), so it is not linked.
ZH_STOP_SUFFIXES = ('路', '街', '站', '区', '市', '县', '镇', '村', '号线', '机场', '大道', '胡同', '口')
EN_STOP_SUFFIXES = (' Station', ' Road', ' Street', ' Avenue', ' Line', ' District', ' Airport')
# Characters that are not allowed in any displayed string: controls, separators, zero-width, bidi formatting.
_CONTROL = re.compile('[\x00-\x1f\x7f-\x9f​-‏ -‮⁠-⁤﻿]')
_FORBIDDEN_KEYS = {'phone', 'email', 'passport', 'name', 'origin', 'current_location', 'location', 'address_book', 'user'}
CHINA_LNG, CHINA_LAT = (73.0, 136.0), (3.0, 54.0)
# The App's registry names and the servers' fixed tables; the tests compare these with the code.
CARD_TOOLS = {'taxi': 'taxi', 'metro': 'metro-guide', 'transport': 'transport', 'currency': 'currency'}


def undo_action_id(action_id):
    """The server derives the undo action id from the save's action id, so two devices tapping undo agree."""
    return 'undo-' + sha256(action_id.encode('utf-8')).hexdigest()[:40]


def utf16_span(answer, start, end):
    """The same span in UTF-16 code units (what NSString / JavaScript would count): used to prove an example
    separates the two units."""
    return len(answer[:start].encode('utf-16-le')) // 2, len(answer[:end].encode('utf-16-le')) // 2


def _walk_strings(value, path='rich'):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_strings(item, f'{path}.{key}')
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_strings(item, f'{path}[{index}]')


def _cluster_safe(answer, start, end):
    """Both ends of the span sit on grapheme-cluster boundaries (the cases the schema's span rule can't see)."""
    def regional(index):
        return 0 <= index < len(answer) and 0x1F1E6 <= ord(answer[index]) <= 0x1F1FF
    if start > 0 and answer[start - 1] == '‍':
        return False
    # A flag is two regional indicators: a boundary between two of them may be the middle of a flag, so refuse it.
    if regional(start - 1) and regional(start) or regional(end - 1) and regional(end):
        return False
    if end < len(answer):
        following = answer[end]
        code = ord(following)
        if (following == '‍' or unicodedata.category(following) in ('Mn', 'Mc', 'Me')
                or 0xFE00 <= code <= 0xFE0F or 0xE0100 <= code <= 0xE01EF or 0x1F3FB <= code <= 0x1F3FF
                or code == 0x20E3 or 0xE0020 <= code <= 0xE007F):
            return False
    return True


def _entities(rows, answer):
    if answer is None:
        raise ValueError('entities need the answer they point into')
    if len(answer) > MAX_ANSWER_SCALARS:
        raise ValueError('answer is longer than the 200000 scalars the offsets allow')
    previous_end, seen = 0, set()
    for row in rows:
        start, end = row['start'], row['end']
        if not ENTITY_SPAN[0] <= end - start <= ENTITY_SPAN[1] or end > len(answer):
            raise ValueError('entity span outside the answer or outside 2..32 scalars')
        if start < previous_end:
            raise ValueError('entities must be sorted and must not overlap')
        previous_end = end
        if row['place_id'] in seen:
            raise ValueError('a place is linked only the first time it appears')
        seen.add(row['place_id'])
        piece = answer[start:end]
        if piece != piece.strip() or '\n' in piece or '\r' in piece:
            raise ValueError('an entity span is one run of text without edge blanks or line breaks')
        if not _cluster_safe(answer, start, end):
            raise ValueError('entity span cuts a grapheme cluster')
        if any(ch in piece for ch in '*_`[]()<>#|\\~!'):
            raise ValueError('an entity span carries Markdown characters')
        for suffix in ZH_STOP_SUFFIXES:
            if answer.startswith(suffix, end):
                raise ValueError('followed by a stop suffix: ' + suffix)
        for suffix in EN_STOP_SUFFIXES:
            if answer.startswith(suffix, end):
                raise ValueError('followed by a stop suffix: ' + suffix)
        if re.search(r'[A-Za-z0-9]', piece[-1:]) and end < len(answer) and re.match(r'[A-Za-z0-9]', answer[end]):
            raise ValueError('an English entity ends inside a word')
        if re.search(r'[A-Za-z0-9]', piece[:1]) and start > 0 and re.match(r'[A-Za-z0-9]', answer[start - 1]):
            raise ValueError('an English entity starts inside a word')


def _in_china(lng, lat):
    return CHINA_LNG[0] <= float(lng) <= CHINA_LNG[1] and CHINA_LAT[0] <= float(lat) <= CHINA_LAT[1]


def _cards(rows):
    kinds = [row['type'] for row in rows]
    if len(set(kinds)) != len(kinds):
        raise ValueError('one card per type')
    for row in rows:
        if row['open']['tool'] != CARD_TOOLS[row['type']]:
            raise ValueError('card type and tool disagree')
        parameters = row['open']['parameters']
        if len(json.dumps(parameters, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')) > 600:
            raise ValueError('parameters are longer than 600 bytes')
        if row['type'] == 'taxi' and not _in_china(parameters['lng'], parameters['lat']):
            raise ValueError('taxi destination is outside China')
        if row['type'] == 'currency' and 'cny_per_unit' in row.get('data', {}) and float(row['data']['cny_per_unit']) <= 0:
            raise ValueError('a currency rate is above 0')
        if row['type'] == 'transport':
            if parameters['from'] == parameters['to']:
                raise ValueError('transport needs two different cities')
            data = row['data']
            if (data['from']['id'], data['to']['id']) != (parameters['from'], parameters['to']):
                raise ValueError('transport data must name the same cities as the parameters')


def _receipt(row):
    if row['status'] == 'saved':
        undo = row['undo']
        if undo['state'] == 'available':
            target = undo['target']
            kind = undo.get('kind', 'restore')
            if undo['action_id'] != undo_action_id(row['action_id']):
                raise ValueError('undo action id is derived from the save action id')
            if (target['trip_id'], target['expected_version']) != (row['trip_id'], row['committed_version']):
                raise ValueError('undo target must be the committed version')
            if kind == 'withdraw_created':
                if row['committed_version'] != 1:
                    raise ValueError('only the save that created the trip is undone by removing it')
            else:
                if row['committed_version'] < 2:
                    raise ValueError('the first version of a trip has nothing to restore')
                if target['restore_version'] != row['committed_version'] - 1:
                    raise ValueError('undo restores the immediately preceding version')
        for day in row.get('summary', {}).get('days', []):
            if day['added'] + day['updated'] + day['removed'] == 0:
                raise ValueError('a day in the summary changed something')
        numbers = [day['day'] for day in row.get('summary', {}).get('days', [])]
        if numbers != sorted(set(numbers)):
            raise ValueError('summary days are unique and ascending')


def _memory(row):
    if 'used' in row and row['used_total'] < len(row['used']):
        raise ValueError('used_total is at least the number of listed items')
    if 'used' in row and len({item['item_id'] for item in row['used']}) != len(row['used']):
        raise ValueError('a memory item is listed once')


def check(rich, answer=None):
    """Raise unless `rich` is a valid LIO-answer-rich.1 object for this row's `answer`."""
    VALIDATOR.validate(rich)
    if len(json.dumps(rich, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) > MAX_RICH_BYTES:
        raise ValueError('rich is longer than 16384 bytes')
    for path, value in _walk_strings(rich):
        if _CONTROL.search(value) or value != value.strip():
            raise ValueError(f'{path}: control, separator, zero-width or bidi character, or edge blank')
    if 'entities' in rich:
        _entities(rich['entities'], answer)
    if 'cards' in rich:
        _cards(rich['cards'])
    if 'trip_receipt' in rich:
        _receipt(rich['trip_receipt'])
    if 'memory' in rich:
        _memory(rich['memory'])
    _privacy(rich)
    return True


def _privacy(rich):
    """Entities and cards say only what the table lists: no names of people, no contact data, no user position."""
    def keys(value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from keys(item)
        elif isinstance(value, list):
            for item in value:
                yield from keys(item)
    for part in ('entities', 'cards'):
        for key in keys(rich.get(part, [])):
            if key in _FORBIDDEN_KEYS:
                raise ValueError('forbidden field in ' + part + ': ' + key)


def run_examples(path=EXAMPLES_PATH):
    examples = json.loads(Path(path).read_text(encoding='utf-8'))
    answers = examples['answers']
    def verify(example):
        answer = answers[example['answer']]
        check(example['rich'], answer)
        # `pieces` is what the entities are meant to point at; an offset counted in the wrong unit lands elsewhere
        found = [answer[row['start']:row['end']] for row in example['rich'].get('entities', [])]
        if 'pieces' in example and found != example['pieces']:
            raise ValueError('entity offsets do not point at the intended text')
    for example in examples['valid']:
        verify(example)
    for example in examples['invalid']:
        try:
            verify(example)
        except Exception:   # a ValueError from the rules or a jsonschema ValidationError
            continue
        raise AssertionError('invalid example passed: ' + example['name'])
    return len(examples['valid']), len(examples['invalid'])


if __name__ == '__main__':
    valid, invalid = run_examples()
    print(f'LIO-answer-rich.1: {valid} valid and {invalid} invalid examples checked')
    sys.exit(0)
