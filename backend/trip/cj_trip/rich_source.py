"""New-mode source binding, not AUTH, collection permission or write authority.

The host supplies already protected originals, installed policy, accepted profile
states and eligible observation projections. None comes from model Trip JSON.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import re

from cj_strict_json import reject_duplicates
from cj_place.models import identifier as provider_id
from .domain import identifier, packed
from .structured import SourceRejected, _date, _fields, _text

VERSION = 'TRIP-rich-source.1'
FACTORS = ('city', 'duration_days', 'season', 'first_visit', 'party_type', 'interests',
           'pace', 'lodging_tier', 'dietary', 'must_see', 'avoid', 'mobility', 'arrival', 'departure')
STATES = ('unknown', 'known', 'not_needed', 'inferred', 'default', 'memory')


def digest(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise SourceRejected('sha256', 'canonical SHA256 required')


def source_ref(value):
    _fields(value, {'provider', 'kind', 'reference', 'sha256'}, 'source', 'exact rich source reference required')
    if (value['provider'], value['kind']) not in (
            ('amap', 'place'), ('amap', 'route'), ('amap', 'name'),
            ('wikidata', 'name'), ('visitor', 'tip'),
            ('checks', 'weather'), ('checks', 'day_opening'), ('trip', 'retained_item'), ('needs', 'fixed_item')):
        raise SourceRejected('source', 'explicit provider and observation kind required')
    _text(value['reference'], 4096)
    digest(value['sha256'])


@dataclass(frozen=True, repr=False)
class RichSource:
    """Frozen validation input. Creating this value does not admit an operation."""
    raw: bytes

    @property
    def document(self):
        return json.loads(self.raw)

    def observation(self, reference, kind):
        source_ref(reference)
        if reference['kind'] != kind:
            raise SourceRejected('source.kind', 'observation kind mismatch')
        for record in self.document['records']:
            if {k: record[k] for k in ('provider', 'kind', 'reference', 'sha256')} == reference:
                return record['payload']
        raise SourceRejected('source', 'source outside captured eligible originals')

    def reason(self, factor):
        if self.document['profile_states'].get(factor) not in ('known', 'memory'):
            raise SourceRejected('reason_refs', 'reason requires an accepted known or memory factor')

    def date_check(self, value):
        if not any(record['provider'] == 'checks' and record['kind'] == value['kind']
                   and packed(record['payload']) == packed(value) for record in self.document['records']):
            raise SourceRejected('date_checks', 'date check differs from the captured code-produced result')

    def retained_base(self, value):
        return any(record['provider'] == 'trip' and record['kind'] == 'retained_item'
                   and packed(record['payload'].get('item')) == packed(value)
                   for record in self.document['records'])

    def protected_base(self, value):
        return any((record['provider'], record['kind']) in (('trip', 'retained_item'), ('needs', 'fixed_item'))
                   and packed(record['payload'].get('item')) == packed(value)
                   for record in self.document['records'])


def capture(raw, *, expected_original, expected_plan_now, expected_policy, accepted_profile_states, eligible_records):
    """Bind a private source artifact to the host's protected, same-operation inputs.

    Caller must obtain these expected inputs through the actual admitted
    original/profile/Memory/provider readers. Equality is not authentication.
    Historical reads use content grammar, not a newly fabricated live capture.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= 1_000_000:
        raise SourceRejected('source', 'bounded source bytes required')
    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate source field'))
    except (ValueError, RecursionError):
        raise SourceRejected('source', 'strict complete source JSON required') from None
    _fields(value, {'version', 'original', 'plan_now', 'policy', 'profile_states', 'records'},
            'source', 'exact rich source artifact required')
    if value['version'] != VERSION:
        raise SourceRejected('source.version', 'new rich source version required')
    original = value['original']
    _fields(original, {'protocol', 'message_id', 'run_id', 'input_sha256', 'question_day'},
            'source.original', 'exact original binding required')
    if original['protocol'] != 'LIO-message.4' or packed(original) != packed(expected_original):
        raise SourceRejected('source.original', 'actual admitted LIO-message.4 original required')
    identifier(original['message_id']); identifier(original['run_id'])
    digest(original['input_sha256']); _date(original['question_day'])
    _fields(value['policy'], {'id', 'sha256'}, 'source.policy', 'fixed code policy required')
    identifier(value['policy']['id']); digest(value['policy']['sha256'])
    if packed(value['policy']) != packed(expected_policy):
        raise SourceRejected('source.policy', 'installed code policy provenance required')
    if packed(value['plan_now']) != packed(expected_plan_now):
        raise SourceRejected('source.plan_now', 'protected actual plan-now decision required')
    if value['plan_now'] is not None:
        _fields(value['plan_now'], {'kind', 'original', 'policy'}, 'source.plan_now', 'actual plan-now decision required')
        trigger = value['plan_now']['original']
        _fields(trigger, {'protocol', 'message_id', 'run_id', 'input_sha256', 'question_day'},
                'source.plan_now.original', 'exact original plan-now binding required')
        if (value['plan_now']['kind'] != 'plan_now' or trigger['protocol'] != 'LIO-message.4'
                or packed(value['plan_now']['policy']) != packed(value['policy'])):
            raise SourceRejected('source.plan_now', 'actual trigger and applied code policy required')
        identifier(trigger['message_id']); identifier(trigger['run_id'])
        digest(trigger['input_sha256']); _date(trigger['question_day'])
    states = value['profile_states']
    if (type(states) is not dict or not states.keys() <= set(FACTORS)
            or any(state not in STATES for state in states.values())
            or packed(states) != packed(accepted_profile_states)):
        raise SourceRejected('source.profile_states', 'accepted profile states required; no model promotion')
    if value['plan_now'] is None and 'default' in states.values():
        raise SourceRejected('source.profile_states', 'code defaults require their actual plan-now provenance')
    records = value['records']
    if type(records) is not list or len(records) > 256 or packed(records) != packed(eligible_records):
        raise SourceRejected('source.records', 'protected eligible observation projections required')
    seen = set()
    for record in records:
        _fields(record, {'provider', 'kind', 'reference', 'sha256', 'payload'},
                'source.records', 'exact captured observation required')
        ref = {k: record[k] for k in ('provider', 'kind', 'reference', 'sha256')}
        source_ref(ref)
        key = packed(ref)
        if key in seen or type(record['payload']) is not dict:
            raise SourceRejected('source.records', 'distinct object observations required')
        seen.add(key)
        if sha256(packed(record['payload'])).hexdigest() != record['sha256']:
            raise SourceRejected('source.records', 'observation projection digest mismatch')
        if record['kind'] == 'tip':
            payload = record['payload']
            _fields(payload, {'entry_id', 'entry_sha256', 'checked_on', 'expires_on', 'subject_key', 'item_ids', 'amap_ids'},
                    'source.tip', 'H content digest, dates and explicit applicability required')
            identifier(payload['entry_id']); digest(payload['entry_sha256'])
            _date(payload['checked_on']); _date(payload['expires_on'])
            if not payload['checked_on'] <= original['question_day'] < payload['expires_on']:
                raise SourceRejected('source.tip', 'H observation outside its checked validity period')
            for key in ('item_ids', 'amap_ids'):
                ids = payload[key]
                if type(ids) is not list or len(ids) > 60 or len(set(ids)) != len(ids):
                    raise SourceRejected('source.tip', 'bounded distinct applicability IDs required')
                for item_id in ids:
                    (provider_id if key == 'amap_ids' else identifier)(item_id)
            if not payload['item_ids']:
                raise SourceRejected('source.tip', 'explicit item applicability required')
            if payload['subject_key'] is None:
                if payload['amap_ids']:
                    raise SourceRejected('source.tip', 'general entry cannot claim venue identity')
            else:
                _text(payload['subject_key'], 128)
                if not payload['amap_ids']:
                    raise SourceRejected('source.tip', 'venue entry needs qualified provider identities')
    return RichSource(packed(value))
