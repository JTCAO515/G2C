"""Compose canonical historical inputs, never issue authority from version equality."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from cj_trip.domain import Proposal, packed
from cj_needs.domain import Revision, Snapshot
from cj_memory.domain import Command, Context, Item
from cj_feasibility.validator import Report, evaluate


class InvalidInput(ValueError):
    pass


class Unavailable(RuntimeError):
    pass


@dataclass(frozen=True, repr=False)
class Binding:
    """Exact historical input manifest. This is not a current-context permit."""
    manifest: bytes


@dataclass(frozen=True, repr=False)
class Request:
    original: Proposal
    inputs: Binding


@dataclass(frozen=True, repr=False)
class SourceLink:
    """Association only: an original item/ref and canonical original source record."""
    item_id: str
    evidence_ref: str
    source: Revision | Item


@dataclass(frozen=True, repr=False)
class Review:
    status: str
    candidate: Proposal | None
    content_sha256: str | None
    needs_report: Report | None
    links: tuple[SourceLink, ...]
    missing: tuple[tuple[str, str], ...]
    reasons: tuple[str, ...]
    # Every result is historical/local. No save, feasibility or dispatch claim.
    can_publish: bool = field(default=False, init=False)


def _recorded_at(value):
    # datetime equality collapses DST folds and same-instant offset/zone
    # representations. Preserve the original representation, without UTC conversion.
    if type(value) is not datetime:
        raise InvalidInput('canonical recorded_at datetime required')
    zone = value.tzinfo
    if zone is None:
        identity = ['naive']
    elif type(zone) is timezone:
        identity = ['fixed', zone.tzname(None)]
    elif type(zone) is ZoneInfo:
        identity = ['iana', zone.key]
    else:
        raise InvalidInput('unsupported recorded_at timezone representation')
    return [value.isoformat(timespec='microseconds'), value.fold, identity]


def _source_record(source):
    if type(source) is Revision:
        if type(source.original_input) is not bytes or type(source.content) is not bytes:
            raise InvalidInput('original NEEDS source bytes required')
        return packed(['needs', source.needs_id, source.version, source.action_id,
                       source.original_input.decode('utf-8'), source.content.decode('utf-8'),
                       source.source_kind])
    if type(source) is Item and type(source.command) is Command:
        command = Command.parse(source.command.raw)
        if command != source.command:
            raise InvalidInput('MEMORY source must match original command bytes')
        return packed(['memory', command.raw.decode('utf-8'), source.version,
                       source.status, _recorded_at(source.recorded_at)])
    raise InvalidInput('canonical original source record required')


def _memory(context, subject, context_id):
    if (type(context) is not Context or type(context.items) is not tuple
            or type(context.epoch) is not int or context.epoch < 0
            or type(subject) is not str or not subject.strip()
            or (context_id is not None and (type(context_id) is not str or not context_id.strip()))):
        raise InvalidInput('explicit canonical historical MEMORY context required')
    rows, ids, slots = [], set(), set()
    for item in context.items:
        if type(item) is not Item or type(item.command) is not Command:
            raise InvalidInput('canonical MEMORY item required')
        command = Command.parse(item.command.raw)
        if (command != item.command or command.subject != subject or item.status != 'active'
                or command.kind == 'inference' or type(item.version) is not int or item.version < 1
                or type(item.recorded_at) is not datetime
                or (command.extent == 'current' and command.context_id != context_id)
                or command.item_id in ids or command.slot in slots):
            raise InvalidInput('MEMORY item/source/subject/context binding invalid')
        ids.add(command.item_id)
        slots.add(command.slot)
        rows.append(_source_record(item).decode('utf-8'))
    return [subject, context_id, context.epoch, rows]


def bind_inputs(snapshot, revisions, memory, *, subject, context_id):
    """Bind complete original records, not only revision/epoch counters.

    Detached Context is deliberately historical. Real consumers must keep
    consume_current/protected-read lifetimes; this helper grants no publication.
    """
    if type(snapshot) is not Snapshot or type(revisions) is not tuple:
        raise InvalidInput('canonical NEEDS snapshot and immutable full history required')
    report = evaluate(snapshot, revisions)
    if report.status == 'INVALID':
        raise InvalidInput('canonical NEEDS history rejected')
    manifest = packed([
        [snapshot.needs_id, snapshot.version, snapshot.content.decode('utf-8'), snapshot.source_kind],
        [[r.needs_id, r.version, r.action_id, r.original_input.decode('utf-8'),
          r.content.decode('utf-8'), r.source_kind] for r in revisions],
        _memory(memory, subject, context_id),
    ])
    return Binding(manifest)


def _proposal(original):
    if type(original) is not Proposal:
        raise InvalidInput('original canonical TRIP Proposal required')
    # Re-run the owner validator at the consumption boundary, preserve exact bytes.
    Proposal(original.proposal_id, original.trip_id, original.expected_version,
             original.basis_version, original.expires_at, original.content)
    return json.loads(original.content)


def request(original, snapshot, revisions, memory, *, subject, context_id):
    _proposal(original)
    return Request(original, bind_inputs(snapshot, revisions, memory,
                                        subject=subject, context_id=context_id))


def review(request, snapshot, revisions, memory, *, subject, context_id, links,
           cancelled, as_of):
    """Review an explicitly supplied, already-generated result. No IO or retries.

    Input failures raise. Cancellation, expiry and changed original inputs discard
    candidate bytes. UNKNOWN/CONFLICT retain bytes solely for local review.
    """
    if (type(request) is not Request or type(request.inputs) is not Binding
            or type(cancelled) is not bool or type(as_of) is not int or as_of < 0
            or type(links) is not tuple):
        raise InvalidInput('explicit request, cancellation, time and immutable links required')
    if cancelled:
        return Review('DISCARDED', None, None, None, (), (), ('CANCELLED',))
    doc = _proposal(request.original)
    if as_of >= request.original.expires_at:
        return Review('DISCARDED', None, None, None, (), (), ('EXPIRED',))
    current = bind_inputs(snapshot, revisions, memory, subject=subject, context_id=context_id)
    if current != request.inputs:
        return Review('DISCARDED', None, None, None, (), (), ('INPUT_BINDING_CHANGED',))
    report = evaluate(snapshot, revisions)
    items = {item['id']: item for item in doc['items']}
    seen = set()
    for link in links:
        if (type(link) is not SourceLink or type(link.item_id) is not str
                or type(link.evidence_ref) is not str or link.item_id not in items
                or link.evidence_ref not in items[link.item_id]['evidence']
                or (link.item_id, link.evidence_ref) in seen):
            raise InvalidInput('source must bind one original candidate item/evidence reference')
        sources = revisions if type(link.source) is Revision else memory.items if type(link.source) is Item else ()
        record = _source_record(link.source)
        if not any(record == _source_record(source) for source in sources):
            raise InvalidInput('source is absent from exact bound original inputs')
        seen.add((link.item_id, link.evidence_ref))
    # One opaque evidence reference cannot silently refer to different originals.
    by_ref = {}
    for link in links:
        record = _source_record(link.source)
        if link.evidence_ref in by_ref and by_ref[link.evidence_ref] != record:
            raise InvalidInput('conflicting original source for evidence reference')
        by_ref[link.evidence_ref] = record
    missing = []
    for item in doc['items']:
        if len(item['evidence']) != len(set(item['evidence'])):
            raise InvalidInput('duplicate evidence reference')
        if item['verification'] == 'verified':
            raise InvalidInput('supplier truth authority unavailable; verified output refused')
        if not item['evidence']:
            missing.append((item['id'], 'SOURCE_NOT_PROVIDED'))
        missing.extend((item['id'], ref) for ref in item['evidence'] if (item['id'], ref) not in seen)
    return Review('CONFLICT' if report.status == 'CONFLICT' else 'UNKNOWN', request.original,
                  sha256(request.original.content).hexdigest(), report, links, tuple(missing),
                  ('HISTORICAL_INPUTS_ONLY', 'TRIP_TIME_PLACE_BINDING_UNAVAILABLE',
                   'SUPPLIER_TRUTH_UNPROVEN', 'PUBLICATION_UNAVAILABLE'))


def production_factory():
    raise Unavailable('model/tool dispatch and cross-RUN/TRIP publication are not fixed')
