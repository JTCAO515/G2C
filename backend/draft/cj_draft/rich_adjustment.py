"""Restrict a Source4 adjustment to one authorized, unlocked suggestion."""
from dataclasses import dataclass
import json

from cj_agent.draft import DraftRejected
from cj_trip.domain import identifier, packed
from cj_trip.lio_history import TripHead
from cj_trip.structured_v4 import parse

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

    def pair(leg):
        return leg['day_index'], leg['from_item_id'], leg['to_item_id']

    retained = {pair(leg): leg for leg in before['legs'] if item_id not in pair(leg)[1:]}
    for leg in document['legs']:
        original = retained.get(pair(leg))
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
