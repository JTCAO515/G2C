"""Structured manual candidate preparation; storage uses the original Trip ingress.

This module only interprets explicit edits. Its result is data, not a source lease,
confirmation or permission to publish/accept a Proposal.
"""
from dataclasses import dataclass
from hashlib import sha256
import json

from .domain import Conflict, Trip, identifier, packed
from .structured import validate_document

VERSION = 'TRIP-manual-edit.1'


@dataclass(frozen=True)
class ManualEdit:
    raw: bytes
    request_id: str
    trip_id: str
    expected_version: int
    original_hash: str
    title: str | None
    changes: tuple
    order: tuple | None

    @classmethod
    def parse(cls, raw):
        if type(raw) is not bytes or not 0 < len(raw) <= 1_000_000:
            raise ValueError('bounded immutable manual input required')
        doc = json.loads(raw)
        fields = {'version', 'request_id', 'trip_id', 'expected_version',
                  'original_hash', 'title', 'changes', 'order'}
        if type(doc) is not dict or set(doc) != fields or packed(doc) != raw:
            raise ValueError('exact canonical manual input required')
        if doc['version'] != VERSION:
            raise ValueError('unsupported manual input version')
        identifier(doc['request_id']); identifier(doc['trip_id'])
        if type(doc['expected_version']) is not int or doc['expected_version'] < 1:
            raise ValueError('original Trip version required')
        digest = doc['original_hash']
        if (type(digest) is not str or len(digest) != 64
                or any(c not in '0123456789abcdef' for c in digest)):
            raise ValueError('original content SHA256 required')
        if doc['title'] is not None and type(doc['title']) is not str:
            raise ValueError('explicit title edit or null required')
        if type(doc['changes']) is not list or len(doc['changes']) > 60:
            raise ValueError('bounded explicit changes required')
        seen = set(); changes = []
        for change in doc['changes']:
            if type(change) is not dict or set(change) != {'item_id', 'field', 'value'}:
                raise ValueError('exact item field selection required')
            identifier(change['item_id'])
            if type(change['field']) is not str:
                raise ValueError('explicit field name required')
            key = change['item_id'], change['field']
            if change['field'] not in ('text', 'schedule', 'fixed') or key in seen:
                raise ValueError('duplicate or unsupported selected field')
            seen.add(key)
            changes.append((change['item_id'], change['field'], packed(change['value'])))
        order = doc['order']
        if order is not None:
            if type(order) is not list or len(order) > 60:
                raise ValueError('bounded explicit order required')
            for item_id in order: identifier(item_id)
            if len(set(order)) != len(order): raise ValueError('duplicate order ID')
            order = tuple(order)
        if doc['title'] is None and not changes and order is None:
            raise ValueError('explicit edit required')
        return cls(raw, doc['request_id'], doc['trip_id'], doc['expected_version'],
                   digest, doc['title'], tuple(changes), order)


@dataclass(frozen=True)
class ManualCandidate:
    original: Trip
    content: bytes
    edit: ManualEdit
    diff: bytes


def prepare(original: Trip, edit: ManualEdit):
    """Call with the actual protected read. Never rebase stale user edits."""
    if (original.trip_id != edit.trip_id or original.version != edit.expected_version
            or sha256(original.content).hexdigest() != edit.original_hash):
        raise Conflict('original Trip changed; retain original manual input')
    before = json.loads(original.content)
    validate_document(before)
    if packed(before) != original.content: raise ValueError('canonical stored Trip required')
    after = json.loads(original.content)
    originals = {item['id']: item for item in before['items']}
    items = {item['id']: item for item in after['items']}
    selected = {}
    for item_id, field, raw in edit.changes:
        if item_id not in items: raise ValueError('unknown selected item')
        selected.setdefault(item_id, set()).add(field)
        items[item_id][field] = json.loads(raw)
    for item_id in selected:
        if items[item_id]['text'] != originals[item_id]['text']:
            items[item_id].update(verification='pending', evidence=[],
                                  source_category='user_provided', source_refs=[])
    referenced = {ref for item in after['items'] for ref in item['source_refs']}
    after['sources'] = [source for source in after['sources'] if source['id'] in referenced]
    validate_document(after)
    for item_id, fields in selected.items():
        old, new = originals[item_id], items[item_id]
        if fields == {'fixed'}:
            # Explicit lock/unlock has no incidental content/time edits.
            if new['fixed'].get('state') != 'known':
                raise ValueError('explicit known lock/unlock required')
        elif old['fixed'] != {'state': 'known', 'value': False}:
            raise Conflict('locked or unknown protection; unlock separately')
        elif 'fixed' in fields:
            raise ValueError('lock/unlock must be an independent selected edit')
        if new['text'] != old['text'] or new['schedule'] != old['schedule']:
            new.update(verification='pending', evidence=[])
    if edit.title is not None: after['title'] = edit.title
    if edit.order is not None:
        if set(edit.order) != set(items): raise ValueError('order must preserve original IDs')
        for index, item_id in enumerate(edit.order):
            if before['items'][index]['id'] != item_id:
                if originals[item_id]['fixed'] != {'state': 'known', 'value': False}:
                    raise Conflict('locked or unknown item cannot move')
        after['items'] = [items[item_id] for item_id in edit.order]
    validate_document(after)
    content = packed(after)
    if content == original.content: raise ValueError('manual edit has no change')
    diff = packed({'before': before, 'after': after, 'request_id': edit.request_id,
                   'trip_id': original.trip_id, 'expected_version': original.version})
    return ManualCandidate(original, content, edit, diff)
