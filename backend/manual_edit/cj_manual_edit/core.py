"""Immutable local manual edits. No storage, confirmation issuer or write adapter."""
from dataclasses import dataclass, replace
import json

from cj_trip.domain import Proposal, Trip, identifier, packed


class Unsupported(ValueError):
    pass


class SaveUnavailable(RuntimeError):
    pass


def _document(content):
    # Trip is a read DTO with no validator; validate its current canonical shape.
    # Proposal independently validates again at the only candidate-export boundary.
    if type(content) is not bytes or not 0 < len(content) <= 1_000_000:
        raise ValueError('bounded immutable content required')
    doc = json.loads(content)
    if type(doc) is not dict or set(doc) != {'title', 'items'}:
        raise Unsupported('only canonical title/items are supported')
    if type(doc['title']) is not str or not doc['title'].strip():
        raise ValueError('nonempty title required')
    if type(doc['items']) is not list or not doc['items']:
        raise ValueError('nonempty items required')
    seen = set()
    for item in doc['items']:
        if type(item) is not dict or set(item) != {'id', 'text', 'verification', 'evidence'}:
            raise Unsupported('time/day/place/lock fields are unsupported')
        identifier(item['id'])
        if item['id'] in seen:
            raise ValueError('duplicate item ID')
        seen.add(item['id'])
        if type(item['text']) is not str or not item['text'].strip():
            raise ValueError('nonempty text required')
        if item['verification'] not in ('pending', 'verified'):
            raise ValueError('invalid verification')
        if type(item['evidence']) is not list or not all(type(x) is str and x for x in item['evidence']):
            raise ValueError('invalid evidence')
        if item['verification'] == 'verified' and not item['evidence']:
            raise ValueError('verified requires evidence')
    if packed(doc) != content:
        raise ValueError('exact canonical UTF-8 content required')
    return doc


def _trip(trip):
    if type(trip) is not Trip:
        raise ValueError('original Trip required')
    identifier(trip.trip_id)
    if type(trip.version) is not int or trip.version < 1:
        raise ValueError('existing Trip version required')
    return _document(trip.content)


def _ids(ids, known):
    if type(ids) is not tuple or any(type(x) is not str for x in ids):
        raise ValueError('explicit immutable IDs required')
    if len(ids) != len(set(ids)) or not set(ids) <= known:
        raise ValueError('duplicate or unknown ID')


@dataclass(frozen=True)
class Change:
    # JSON values encoded as canonical bytes retain exact Unicode and whitespace.
    path: tuple[str, ...]
    before: bytes
    after: bytes


@dataclass(frozen=True)
class Draft:
    original: Trip
    selected_ids: tuple[str, ...]
    title_selected: bool
    # Host read context only. None means protection completeness is UNKNOWN.
    protected_ids: frozenset[str] | None
    content: bytes

    def __post_init__(self):
        before = _trip(self.original)
        after = _document(self.content)
        old = {x['id']: x for x in before['items']}
        new = {x['id']: x for x in after['items']}
        _ids(self.selected_ids, set(old))
        if type(self.title_selected) is not bool:
            raise ValueError('explicit title selection required')
        if self.protected_ids is not None:
            if type(self.protected_ids) is not frozenset or not self.protected_ids <= set(old):
                raise ValueError('trusted protected IDs must belong to original Trip')
        protected = self.protected_ids or frozenset()
        if old.keys() != new.keys():
            raise ValueError('IDs cannot be added, removed or renumbered')
        if not self.title_selected and before['title'] != after['title']:
            raise ValueError('title is outside selected scope')
        selected = set(self.selected_ids)
        for index, item in enumerate(after['items']):
            item_id = item['id']
            original = old[item_id]
            if item_id not in selected or item_id in protected:
                if packed(item) != packed(original) or before['items'][index]['id'] != item_id:
                    raise ValueError('unselected/protected item must stay exact and in position')
            if item['text'] != original['text']:
                if item['verification'] != 'pending' or item['evidence'] != []:
                    raise ValueError('changed text cannot inherit or acquire evidence')
            elif packed(item) != packed(original):
                raise ValueError('unchanged text must retain its original fact state')

    @property
    def protection_status(self):
        return 'UNKNOWN' if self.protected_ids is None else 'CONTEXT_ONLY'

    @property
    def diff(self):
        # Draft construction validated both immutable documents.
        before, after = json.loads(self.original.content), json.loads(self.content)
        changes = []
        if before['title'] != after['title']:
            changes.append(Change(('title',), packed(before['title']), packed(after['title'])))
        old_order = [x['id'] for x in before['items']]
        new_order = [x['id'] for x in after['items']]
        if old_order != new_order:
            changes.append(Change(('items', 'order'), packed(old_order), packed(new_order)))
        old = {x['id']: x for x in before['items']}
        for item in after['items']:
            if item != old[item['id']]:
                changes.append(Change(('items', 'id', item['id']), packed(old[item['id']]), packed(item)))
        return tuple(changes)

    def to_proposal(self, *, proposal_id, basis_version, expires_at, expected_version):
        # All metadata comes from trusted composition, never inferred or generated.
        if type(expected_version) is not int or expected_version != self.original.version:
            raise ValueError('host expected version must equal original version')
        return Proposal(proposal_id, self.original.trip_id, expected_version,
                        basis_version, expires_at, self.content)

    def save(self):
        raise SaveUnavailable('CJ015 confirmation/transaction and feasibility integration unavailable')


def edit(original, *, expected_version, original_content, selected_ids,
         title_selected=False, title=None, text_updates=(), order=None,
         protected_ids=None):
    """Build a draft bound to exact original version/content, no automatic rebase."""
    doc = _trip(original)
    if type(expected_version) is not int or expected_version != original.version:
        raise ValueError('original version mismatch')
    if type(original_content) is not bytes or original_content != original.content:
        raise ValueError('exact original content mismatch')
    known = {x['id'] for x in doc['items']}
    _ids(selected_ids, known)
    if type(text_updates) is not tuple:
        raise ValueError('immutable text updates required')
    updates = {}
    for update in text_updates:
        if type(update) is not tuple or len(update) != 2:
            raise ValueError('ID/text pair required')
        item_id, text = update
        if type(item_id) is not str or item_id not in selected_ids or item_id in updates:
            raise ValueError('duplicate or unselected update')
        if type(text) is not str or not text.strip():
            raise ValueError('nonempty text required')
        updates[item_id] = text
    if title is not None:
        if not title_selected:
            raise ValueError('title is outside selected scope')
        doc['title'] = title
    for item in doc['items']:
        if item['id'] in updates and updates[item['id']] != item['text']:
            item.update(text=updates[item['id']], verification='pending', evidence=[])
    if order is not None:
        _ids(order, known)
        if set(order) != known:
            raise ValueError('order must contain exactly the original ID set')
        by_id = {x['id']: x for x in doc['items']}
        doc['items'] = [by_id[x] for x in order]
    return Draft(original, selected_ids, title_selected, protected_ids, packed(doc))


@dataclass(frozen=True)
class EditSession:
    """Read observation only; conflict/unknown are sticky until explicit new editing."""
    draft: Draft
    status: str = 'LOCAL'
    observed: Trip | None = None

    def __post_init__(self):
        if type(self.draft) is not Draft or self.status not in ('LOCAL', 'CONFLICT', 'UNKNOWN'):
            raise ValueError('invalid local session')
        if self.observed is not None:
            _trip(self.observed)
            if self.observed.trip_id != self.draft.original.trip_id:
                raise ValueError('foreign Trip observation')

    def observe(self, current):
        if current is None:
            return replace(self, status='UNKNOWN')
        _trip(current)
        if current.trip_id != self.draft.original.trip_id:
            raise ValueError('foreign Trip observation')
        same = current == self.draft.original
        status = self.status if same else 'CONFLICT'
        # UNKNOWN is never cleared by seeing a matching version: no action receipt.
        if self.status == 'UNKNOWN':
            status = 'UNKNOWN'
        return replace(self, status=status, observed=current)

    @property
    def can_save(self):
        return False

    def save(self):
        raise SaveUnavailable('save unavailable; preserve original draft and reconcile at host')
