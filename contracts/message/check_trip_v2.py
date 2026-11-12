"""#860 offline LIO3 contract checks against explicitly synthetic protected reads."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from contracts.trip.check_structured_v3 import validate as validate_content
from cj_trip.structured import validate_document as validate_v1
from cj_trip.structured_v2 import validate_document as validate_v2
from cj_message.domain import Command
from cj_trip.domain import packed

HERE = Path(__file__).resolve().parent
SCHEMA = json.loads((HERE / 'trip-schema.2.json').read_bytes())


def require(value, reason):
    if not value:
        raise ValueError(reason)


def validator(definition):
    return Draft202012Validator({'$defs': SCHEMA['$defs'], '$ref': '#/$defs/' + definition},
                                format_checker=FormatChecker())


def original(reference, fixtures):
    mid = reference['message_id']
    expected = fixtures['source_receipts'].get(mid)
    require(expected == reference, 'protected canonical original reference mismatch')
    command = fixtures['source_messages'][mid]
    raw = packed(command)
    Command.parse_original(raw)
    require(reference['input_sha256'] == sha256(raw).hexdigest()
            and reference['message_version'] == command['version']
            and reference['conversation_id'] == command['conversation_id']
            and reference['generation'] == command['expected_generation']
            and type(reference['sequence']) is int
            and reference['sequence'] == command['expected_sequence'] + 1,
            'canonical MESSAGE bytes/receipt mismatch; outer wire digest is different')
    return command


def protected_content(digest, fixtures):
    matches = [c for c in fixtures['protected_contents'] if sha256(packed(c)).hexdigest() == digest]
    require(len(matches) == 1, 'protected original content digest unavailable')
    {'structured.1': validate_v1, 'structured.2': validate_v2,
     'structured.3': validate_content}[matches[0]['content_version']](matches[0])
    return matches[0]


def card(value, fixtures):
    content = protected_content(value['content_sha256'], fixtures)
    require({k: value[k] for k in ('trip_id', 'trip_version', 'content_sha256')}
            in fixtures['protected_card_records'] and type(value['trip_version']) is int,
            'fixture protected Trip identity/version mismatch')
    require(value['content_version'] == content['content_version'] and value['title'] == content['title'],
            'card must retain original content metadata')
    if content['content_version'] != 'structured.3':
        require(value['calendar'] is None and value['date_checks'] is None, 'legacy content must not be normalized')
        groups = {}
        for item in content['items']:
            day = item['schedule']['start']['date'].get('value')
            groups.setdefault(day, []).append(dict(item_id=item['id'], label=item['text'],
                start_time=item['schedule']['start']['time'].get('value'), end_time=item['schedule']['end']['time'].get('value'),
                fixed=item['fixed'].get('value')))
        require(value['days'] == [dict(date=d, items=groups[d]) for d in sorted(groups, key=lambda d: (d is None, d or ''))],
                'legacy days changed')
        return
    require(value['calendar'] == content['calendar'] and value['date_checks'] == content['date_checks'],
            'calendar/check metadata differs from protected content')
    expected = []
    for day in content['days']:
        items = [dict(item_id=i['id'], label=i['text'], start_time=i['schedule']['start']['time'].get('value'),
                      end_time=i['schedule']['end']['time'].get('value'), fixed=i['fixed'].get('value'))
                 for i in content['items'] if i['schedule']['start']['day_index'] == day['day_index']]
        expected.append(dict(day, items=items))
    require(value['days'] == expected, 'card omits/reorders a day or changes original item projection')


def check(definition, value, fixtures, *, conversion_input=None):
    """Fixture correlation only. Never authenticates a caller or authorizes a write."""
    validator(definition).validate(value)
    if definition == 'LioMessage3':
        require(value['text'].strip() and '\x00' not in value['text']
                and len(value['text'].encode()) <= 12000 and len(packed(value)) <= 16384,
                'original bounded UTF8 envelope required')
        require(value['message_id'].strip() and '\x00' not in value['message_id']
                and len(value['message_id'].encode()) <= 256, 'bounded original message ID required')
    elif definition == 'TripSelection2':
        require(type(value['expected_version']) is int, 'integer Trip version required')
        day = value['day']
        if day is not None and 'day_index' in day:
            require(type(day['day_index']) is int, 'integer ordinal required')
        if day is not None and 'timezone' in day:
            ZoneInfo(day['timezone'])
    elif definition == 'TripReference':
        ref = {k: value[k] for k in SCHEMA['$defs']['CanonicalMessageReference']['properties']}
        original(ref, fixtures)
        check('TripSelection2', value['selection'], fixtures)
        require((value['trip_id'], value['trip_version']) == (value['selection']['id'], value['selection']['expected_version']),
                'selection and protected Trip version mismatch')
        require(type(value['trip_version']) is int
                and all(value[k] == fixtures['reference_trip'][k] for k in fixtures['reference_trip']),
                'reference is not the fixture current protected Trip')
        content = protected_content(value['content_sha256'], fixtures)
        require(value['content_version'] == content['content_version'], 'protected content version mismatch')
        day = value['selection']['day']
        if day is not None:
            if content['calendar']['state'] == 'undated':
                require('day_index' in day and 1 <= day['day_index'] <= len(content['days']), 'undated ordinal out of range/mode')
            else:
                require('date' in day and day['date'] in {d['date'] for d in content['days']}, 'dated selector out of range/mode')
            if 'timezone' in day:
                require(day['timezone'] == fixtures['needs_basis']['fields']['destination_timezone']['value'],
                        'selector timezone not supported by current source')
        if value['selection']['item_id'] is not None:
            require(value['selection']['item_id'] in {i['id'] for i in content['items']}, 'item outside protected Trip')
    elif definition == 'FixedDays':
        original(value['reference'], fixtures)
        basis = fixtures['needs_basis']
        require(all(value[k] == basis[k] for k in ('needs_id', 'needs_version', 'needs_content_sha256')),
                'current protected NEEDS basis mismatch')
        require(value['needs_content_sha256'] == sha256(packed(basis['fields'])).hexdigest(), 'NEEDS bytes changed')
        expected = {i['item_id'] for i in basis['fields']['fixed_items']}
        ids = [b['item_id'] for b in value['bindings']]
        require(len(ids) == len(set(ids)) and set(ids) == expected, 'missing/duplicate/foreign fixed binding')
        for binding in value['bindings']:
            command = original(binding['source_reference'], fixtures)
            require(binding['quote'] in command['text'] and binding['quote'].strip(), 'fixed quote not in original source')
            require((binding['source_reference']['conversation_id'], binding['source_reference']['generation'])
                    == (value['reference']['conversation_id'], value['reference']['generation'])
                    and binding['source_reference']['sequence'] <= value['reference']['sequence'], 'foreign/future fixed source')
            indices = [binding['day_index'], binding['end_day_index']]
            require(all(type(i) is int and 1 <= i <= len(fixtures['protected_contents'][0]['days']) for i in indices)
                    and indices == fixtures['fixed_day_truth'][binding['item_id']],
                    'fixed ordinal differs from protected original compiler result')
    elif definition == 'Card2':
        card(value, fixtures)
    elif definition in ('History3', 'Timeline3'):
        cards = ([value['current']] + value['history'] if definition == 'History3'
                 else [m['trip'] for m in value['messages']])
        for item in cards:
            if item is not None:
                card(item, fixtures)
    elif definition == 'DateConvert':
        source = value['date_source']
        command = original(source['reference'], fixtures)
        require(source['quote'] in command['text'] and source['quote'].strip(), 'date quote not in original source')
        require(source['question_day'] == fixtures['question_days'][source['reference']['message_id']],
                'relative date was reanchored')
        require(value['start_date'] == fixtures['compiled_start_dates'][source['reference']['message_id']],
                'date differs from protected original compiler result')
        content = protected_content(value['original_hash'], fixtures)
        require(content['calendar']['state'] == 'undated' and type(value['expected_version']) is int,
                'date conversion needs the original undated basis')
    elif definition == 'DateReceipt':
        source = conversion_input or fixtures['conversion_input']
        require((value['action_id'], value['trip_id'], value['original_version'], value['original_hash'])
                == (source['action_id'], source['trip_id'], source['expected_version'], source['original_hash']),
                'conversion receipt original action/basis mismatch')
        if value['committed'] is True:
            require(type(value['trip_version']) is int and value['trip_version'] == source['expected_version'] + 1,
                    'conversion must append exactly one version')
            content = protected_content(value['content_sha256'], fixtures)
            require(content['calendar'] == value['calendar'] and content['calendar']['start_date'] == source['start_date']
                    and content['date_checks'] == value['date_checks'], 'committed conversion metadata mismatch')
            require(not any(c['kind'] == 'hard_fixed' for c in value['conflicts']), 'hard fixed conflict cannot commit')
            checks = [c for c in content['date_checks'] if c['state'] == 'conflict']
            require(len(checks) == len(value['conflicts']), 'date-check conflicts omitted or invented')
            for conflict in value['conflicts']:
                require(any(all(conflict[k] == c[k] for k in ('day_indices', 'item_ids', 'reason', 'evidence_refs'))
                            for c in checks), 'reported conflict differs from committed check evidence')


class MessageContractChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.examples = json.loads((HERE / 'trip-send-examples.2.json').read_bytes())

    def test_new_schema_and_positive_examples(self):
        Draft202012Validator.check_schema(SCHEMA)
        for row in self.examples['positive']:
            with self.subTest(case=row['name']):
                original_value = deepcopy(row['value'])
                check(row['definition'], row['value'], self.examples, conversion_input=row.get('conversion_input'))
                self.assertEqual(row['value'], original_value)

    def test_shape_negative_examples(self):
        for row in self.examples['schema_reject']:
            with self.subTest(case=row['name']):
                self.assertFalse(validator(row['definition']).is_valid(row['value']))

    def test_source_and_correlation_negative_examples(self):
        for row in self.examples['semantic_reject']:
            with self.subTest(case=row['name']):
                validator(row['definition']).validate(row['value'])
                with self.assertRaises(ValueError):
                    check(row['definition'], row['value'], self.examples, conversion_input=row.get('conversion_input'))

    def test_old_core_message_and_selector_are_not_extended(self):
        from cj_message.trip_context import TripSelection
        selector = self.examples['positive'][0]['value']
        with self.assertRaises(ValueError):
            TripSelection.parse(selector)
        self.assertNotEqual(sha256(packed(self.examples['canonical_message'])).hexdigest(),
                            sha256(packed(self.examples['outer_message'])).hexdigest())


if __name__ == '__main__':
    unittest.main(verbosity=2)
