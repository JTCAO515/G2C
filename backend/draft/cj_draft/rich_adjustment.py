"""Restrict a Source4 adjustment to one authorized, unlocked suggestion."""
from dataclasses import dataclass
import json

from cj_agent.draft import DraftRejected
from cj_trip.domain import identifier, packed
from cj_trip.lio_history import TripHead
from cj_trip.place_selection import PLAN_SOURCE, validate_basis
from cj_trip.structured_v4 import parse
from .rich_calendar_source import original_reference

_SUGGESTIONS = frozenset(('sight', 'meal', 'free_time'))


@dataclass(frozen=True)
class RichAdjustment:
    head: TripHead
    item_id: str
    operation: str

    def __post_init__(self):
        identifier(self.item_id)
        if type(self.head) is not TripHead or self.operation not in ('replace', 'remove'):
            raise ValueError('exact Trip head and explicit scoped operation required')

    def basis(self):
        return dict(trip_id=self.head.trip_id, version=self.head.version,
                    content_sha256=self.head.content_sha256, item_id=self.item_id,
                    operation=self.operation)


def check_document(context, capture, adjustment, document):
    """Keep the original calendar, content and unaffected routes in the scope."""
    if context is None or TripHead.from_trip(context.trip) != adjustment.head:
        raise DraftRejected('scoped adjustment requires the exact current Trip')
    before = parse(context.trip.content)
    item_id = adjustment.item_id
    old = {item['id']: item for item in before['items']}
    target = old.get(item_id)
    snapshot, _ = capture.records()
    protected = {item['item_id'] for item in snapshot.fields.get('fixed_items', ())}
    if (target is None or item_id in protected or target['kind'] not in _SUGGESTIONS
            or target['fixed'] != dict(state='known', value=False)
            or target['verification'] != 'pending' or target['evidence']
            or target['source_category'] != 'unknown' or target['source_refs']):
        raise DraftRejected('only an unlocked original suggestion may be adjusted')
    wanted = [item['id'] for item in before['items']
              if adjustment.operation == 'replace' or item['id'] != item_id]
    if [item['id'] for item in document['items']] != wanted:
        raise DraftRejected('scoped adjustment cannot add or reorder Trip items')
    for key in ('title', 'calendar', 'days', 'lodging', 'sources'):
        if packed(document[key]) != packed(before[key]):
            raise DraftRejected('scoped adjustment changed original Trip metadata')
    for item in document['items']:
        if item['id'] != item_id:
            if packed(item) != packed(old[item['id']]):
                raise DraftRejected('scoped adjustment changed an unselected item')
            continue
        if (item['kind'] not in _SUGGESTIONS or item['schedule'] != target['schedule']
                or item['fixed'] != target['fixed'] or item['verification'] != 'pending'
                or item['evidence'] or item['source_category'] != 'unknown' or item['source_refs']
                or (item['text'], item['place']) == (target['text'], target['place'])):
            raise DraftRejected('replacement must be a new unconfirmed suggestion in the original slot')

    retained = {_pair(leg): leg for leg in before['legs'] if item_id not in _pair(leg)[1:]}
    for leg in document['legs']:
        original = retained.get(_pair(leg))
        if original is not None and packed(leg) != packed(original):
            raise DraftRejected('scoped adjustment changed an unaffected route')


def check_needs(context, candidate, item_id):
    """The adjusted suggestion is the only permissible change to proposed NEEDS."""
    before = json.loads(context.proposed)
    after = json.loads(candidate.content)
    for fields in (before, after):
        fields['fixed_items'] = [item for item in fields.get('fixed_items', ())
                                 if item['item_id'] != item_id]
    if packed(before) != packed(after):
        raise DraftRejected('scoped adjustment changed unselected NEEDS')


def _pair(leg):
    return leg['day_index'], leg['from_item_id'], leg['to_item_id']


def _key(record):
    return tuple(record[key] for key in ('provider', 'kind', 'reference', 'sha256'))


def _place_refs(place):
    return place.get('source'), place['name_en_source']


def _item_refs(item):
    tip = item['tip']
    return (*_place_refs(item['place']), None if tip is None else tip['source'])


def _references(document, *, adjusted_item=None, changed=False, before=None):
    """Split provider references by actual retained Trip position."""
    old_pairs = set() if before is None else {_pair(leg) for leg in before['legs']}
    for item in document['items']:
        if (item['id'] == adjusted_item) == changed:
            yield from _item_refs(item)
    for leg in document['legs']:
        pair = _pair(leg)
        affected = adjusted_item in pair[1:] or before is not None and pair not in old_pairs
        if affected == changed:
            yield leg['source']
    if not changed:
        for hotel in document['lodging']['recommendations']:
            yield from _place_refs(hotel['place'])


def _held_original(message, reference):
    original_reference(reference, current=True)
    saved = message.source_original(reference['message_id'])
    actual = saved.reference
    keys = ('conversation_id', 'generation', 'message_id', 'run_id', 'sequence',
            'input_sha256', 'message_version')
    if any(getattr(actual, key) != reference[key] for key in keys):
        raise DraftRejected('retained provider original changed')


def retained_evidence(context, document, adjusted_item, current_records, message):
    """Read accepted Trip evidence only under its real, current MESSAGE holder.

    Call after the scoped byte comparison. New positions must use current-RUN
    records before any retained record is joined to the validation source.
    """
    before = parse(context.trip.content)
    current_keys = {_key(record) for record in current_records}
    for ref in _references(document, adjusted_item=adjusted_item, changed=True, before=before):
        if ref is not None and _key(ref) not in current_keys:
            raise DraftRejected('changed suggestion or route needs current original evidence')

    basis = json.loads(context.needs_source)
    if basis['version'] != PLAN_SOURCE:
        raise DraftRejected('retained adjustment needs an accepted Source4 selection basis')
    validate_basis(basis)
    root = basis['calendar_basis']['fixed_bindings']['reference']
    available = {_key(record): dict(record=record, original=root)
                 for record in basis['rich_source']['records']}
    # The accepted basis also keeps the prior Trip's exact referenced records
    # so byte-restoring undo can recover the original product observations.
    for entry in basis.get('prior_trip_evidence', ()):
        available[_key(entry['record'])] = entry

    prior = {}
    for ref in _references(before):
        if ref is None:
            continue
        key = _key(ref)
        entry = available.get(key)
        if entry is not None:
            prior[key] = entry

    joined = {}
    originals = {}
    for ref in _references(document, adjusted_item=adjusted_item, before=before):
        if ref is None:
            continue
        key = _key(ref)
        if key in current_keys:
            continue
        entry = prior.get(key)
        if entry is None:
            raise DraftRejected('retained provider observation differs from current Trip')
        joined[key] = entry['record']
        originals[packed(entry['original'])] = entry['original']
    for reference in originals.values():
        _held_original(message, reference)
    return list(joined.values()), list(prior.values()), tuple(originals.values())


def recheck_retained(message, originals):
    for reference in originals:
        _held_original(message, reference)
