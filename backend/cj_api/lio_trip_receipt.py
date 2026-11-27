"""`rich.trip_receipt` of LIO-answer-rich.1 (#1984, ADR-0012, #1994 T-1): computed at every read.

Inputs: the RUN's `lio_trip_receipt:` effects, the authoritative receipt table (cj_trip_receipt with the
0061 commit time), the Trip's current head and the database clock. Nothing stored is trusted on its own:

* `saved` only when cj_trip_receipt has the accepted row for (scope, action_id); an effect that says
  `saved` without it reads `unknown`, an effect still `unknown` with it reads `saved` (contract R-7).
* `undo.state` is decided now: `available` (current version is the committed one with the same hash and
  the DB clock is before `until`), `expired`, `superseded` (a newer version that is not this save's undo),
  `undone` (the next version is an undo of it), `unavailable` (Trip gone, no undo route in this host, or
  the original revisions are unreadable). `action_id` and `target` only in `available`.
* A first save that created the Trip (version 1) has no previous version to restore; the contract's
  `saved` needs `committed_version >= 2`, so such a receipt is not sent (contract gap, see #1994).
* `first` (the account's first automatic save, #1994 acceptance) is returned beside the wire object and
  never put on it: LIO-answer-rich.1 defines no field for it.

The rich envelope that carries this object is not assembled in this image yet (no `CJ_LIO_ANSWER_RICH`
reader); its author calls :func:`read` for a row only when the poll declared LIO-answer-rich.1.
"""
from dataclasses import dataclass
from datetime import timezone
from hashlib import sha256

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


def _undo(repository, cur, trip_id, version, receipt, undo_route):
    if receipt is None:
        return dict(state='unavailable')
    deadline = until(receipt.undo_until)
    cur.execute('SELECT version,content FROM cj_trip_record WHERE scope=%s AND trip_id=%s', (repository.scope, trip_id))
    head = cur.fetchone()
    if head is None or not undo_route:
        return dict(state='unavailable')
    current, content = head[0], bytes(head[1])
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
            or receipt.restore_content_version not in CONTENT_VERSIONS or receipt.restore_hash is None):
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
    if version < 2:
        return None
    from cj_trip.autosave import autosave_receipt
    try:
        receipt = autosave_receipt(repository, cur, action_id)
    except Denied:
        receipt = None
    wire = dict(status='saved', action_id=action_id, trip_id=trip_id, committed_version=version,
                undo=_undo(repository, cur, trip_id, version, receipt, undo_route))
    return TripReceipt(wire, receipt is not None and receipt.first)


def read(database, owner, run_id, effects, *, undo_route):
    """Read-side entry for one timeline row of account scope `owner`; no database work without an effect."""
    if last(effects) is None:
        return None
    from cj_agent.draft import trip_scope_for
    from cj_trip.postgres import Repository
    repository = Repository(lambda: database.connect(owner), trip_scope_for(owner), structured=True)
    with repository.transaction() as cur:
        return project(repository, cur, run_id, effects, undo_route=undo_route)
