"""`rich.trip_receipt` of LIO-answer-rich.1 (#1984, ADR-0012, #1994 T-1): computed at every read.

Inputs: the RUN's `lio_trip_receipt:` effects, the authoritative receipt table (cj_trip_receipt with the
0061 commit time), the Trip's current head and the database clock. Nothing stored is trusted on its own:

* `saved` only when cj_trip_receipt has the accepted row for (scope, action_id); an effect that says
  `saved` without it reads `unknown`, an effect still `unknown` with it reads `saved` (contract R-7).
* `undo.state` is decided now: `available` (current version is the committed one with the same hash and
  the DB clock is before `until`), `expired`, `superseded` (a newer version that is not this save's undo),
  `undone` (the next version is an undo of it), `unavailable` (Trip gone, no undo route in this host, the
  original revisions are unreadable, or the pair of content versions has no undo: structured.1, or
  structured.2 next to structured.3/.4, which every undo entry refuses). `action_id` and `target` only in
  `available`.
* A save that created the Trip (version 1) is undone by withdrawing it (`undo.kind = withdraw_created`,
  LIO-trip-undo.5, ADR-0012 revision 1): `available` only while version 1 is still the only version, with
  the same hash, only Lio points and inside the 24 hours; `undone` once the Trip is withdrawn; `superseded`
  after any other newer version; `unavailable` where this host has no undo route.
* `first_autosave: true` (the account's first automatic save) goes on the wire; `TripReceipt.first` keeps
  the same flag for callers.

The timeline calls :func:`read` through `register_lio_dialogue_routes(trip_receipt_reader=...)` only when
the poll declared LIO-answer-rich.1 and the row has a receipt effect.
"""
from dataclasses import dataclass
from datetime import timezone
from hashlib import sha256
import json

from cj_message.lio_trip_receipt import last
from cj_trip.domain import Denied

CONTENT_VERSIONS = ('structured.1', 'structured.2', 'structured.3', 'structured.4')


@dataclass(frozen=True)
class TripReceipt:
    wire: dict
    first: bool


def undo_action_id(action_id):
    """`"undo-" + first 40 hex of sha256(save action id)`: two devices tapping undo send the same id."""
    return 'undo-' + sha256(action_id.encode('utf-8')).hexdigest()[:40]


def until(value):
    return value.astimezone(timezone.utc).isoformat(timespec='milliseconds')


# Content version pairs (saved, previous) an undo entry accepts: structured.2 only through the legacy undo
# (`_protect_fixed`), structured.3/.4 through calendar or rich undo (`rich_history.protect_fixed`).
_RESTORABLE = frozenset({('structured.2', 'structured.2'), *(
    (a, b) for a in ('structured.3', 'structured.4') for b in ('structured.3', 'structured.4'))})


def _created(repository, cur, trip_id, receipt, current, content, deadline):
    """Undo state of the save that created the Trip (version 1): withdrawing it (LIO-trip-undo.5)."""
    from cj_trip.autosave import LIO, _origins_at, items, withdrawn
    if withdrawn(repository, cur, trip_id):
        return dict(state='undone', until=deadline)
    if current != 1:
        return dict(state='superseded', until=deadline)
    if sha256(content).hexdigest() != receipt.content_sha256:
        return dict(state='unavailable')
    cur.execute('SELECT clock_timestamp()<%s', (receipt.undo_until,))
    if cur.fetchone()[0] is not True:
        return dict(state='expired', until=deadline)
    origins = _origins_at(repository, cur, trip_id, 1)
    if any(origins.get(item['id']) != LIO for item in items(json.loads(content))):
        return dict(state='superseded', until=deadline)
    if receipt.content_version not in CONTENT_VERSIONS:
        return dict(state='unavailable')
    target = dict(trip_id=trip_id, expected_version=1, original_hash=receipt.content_sha256,
                  content_version=receipt.content_version)
    return dict(state='available', kind='withdraw_created', action_id=undo_action_id(receipt.action_id),
                until=deadline, target=target)


def _undo(repository, cur, trip_id, version, receipt, undo_route):
    if receipt is None:
        return dict(state='unavailable')
    deadline = until(receipt.undo_until)
    cur.execute('SELECT version,content FROM cj_trip_record WHERE scope=%s AND trip_id=%s', (repository.scope, trip_id))
    head = cur.fetchone()
    if head is None or not undo_route:
        return dict(state='unavailable')
    current, content = head[0], bytes(head[1])
    if version == 1:
        return _created(repository, cur, trip_id, receipt, current, content, deadline)
    if current > version:
        from cj_trip.autosave import UNDO_BASES
        cur.execute('SELECT p.basis_version,p.expected_version FROM cj_trip_receipt r JOIN cj_trip_proposal p '
                    'ON (p.scope,p.proposal_id)=(r.scope,r.proposal_id) '
                    "WHERE r.scope=%s AND r.trip_id=%s AND r.committed_version=%s AND r.kind='accept'",
                    (repository.scope, trip_id, version + 1))
        following = cur.fetchone()
        undone = following is not None and following[0] in UNDO_BASES and following[1] == version
        return dict(state='undone' if undone else 'superseded', until=deadline)
    if current != version or sha256(content).hexdigest() != receipt.content_sha256:
        return dict(state='unavailable')
    cur.execute('SELECT clock_timestamp()<%s', (receipt.undo_until,))
    if cur.fetchone()[0] is not True:
        return dict(state='expired', until=deadline)
    if (receipt.content_version not in CONTENT_VERSIONS or receipt.restore_version != version - 1
            or receipt.restore_content_version not in CONTENT_VERSIONS or receipt.restore_hash is None
            or (receipt.content_version, receipt.restore_content_version) not in _RESTORABLE):
        return dict(state='unavailable')
    target = dict(trip_id=trip_id, expected_version=version, original_hash=receipt.content_sha256,
                  content_version=receipt.content_version, restore_version=receipt.restore_version,
                  restore_hash=receipt.restore_hash, restore_content_version=receipt.restore_content_version)
    return dict(state='available', action_id=undo_action_id(receipt.action_id), until=deadline, target=target)


def project(repository, cur, run_id, effects, *, undo_route):
    """The receipt of one RUN, or None. `repository` is the account's Trip repository (its scope)."""
    value = last(effects)
    if value is None:
        return None
    from cj_trip.lio_history import edit_action_id, plan_action_id
    action_id = value['action_id']
    if action_id not in (plan_action_id(run_id), edit_action_id(run_id)):
        return None  # a receipt names only this RUN's own Lio write
    cur.execute("SELECT trip_id,committed_version FROM cj_trip_receipt WHERE scope=%s AND action_id=%s AND kind='accept'",
                (repository.scope, action_id))
    row = cur.fetchone()
    if row is None or row[1] is None:
        if value['status'] == 'not_saved':
            wire = dict(status='not_saved', action_id=action_id)
            if 'reason' in value:
                wire['reason'] = value['reason']
            return TripReceipt(wire, False)
        return TripReceipt(dict(status='unknown', action_id=action_id), False)
    trip_id, version = row
    from cj_trip.autosave import autosave_receipt
    try:
        receipt = autosave_receipt(repository, cur, action_id)
    except Denied:
        receipt = None
    first = receipt is not None and receipt.first
    wire = dict(status='saved', action_id=action_id, trip_id=trip_id, committed_version=version,
                undo=_undo(repository, cur, trip_id, version, receipt, undo_route))
    if first:
        wire['first_autosave'] = True
    return TripReceipt(wire, first)


def read(database, owner, run_id, effects, *, undo_route):
    """Read-side entry for one timeline row of account scope `owner`; no database work without an effect."""
    if last(effects) is None:
        return None
    from cj_agent.draft import trip_scope_for
    from cj_trip.postgres import Repository
    repository = Repository(lambda: database.connect(owner), trip_scope_for(owner), structured=True)
    with repository.transaction() as cur:
        return project(repository, cur, run_id, effects, undo_route=undo_route)
