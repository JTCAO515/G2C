"""Item origin, tombstones, Lio write comparison and the autosave undo window (ADR-0012, #1994 T-1).

Domain layer only: no HTTP route, no environment read, no answer wiring. The sole commit point
``Repository._act_in_tx`` calls :func:`record_commit` inside its transaction, after the version
CAS and before the new version is written, for every accepted Proposal. The switch is injected as
``repository.autosave`` (``None`` by default = off; ``True`` = on); nothing here reads it from the
environment. With the switch off the only new effect is writing origin, tombstone and commit time
rows: a Lio write is not compared and an undo has no 24 hour limit (unless the version being undone
was itself committed as an autosave, which only happens with the switch on).

Writer of a commit, decided by the Proposal's ``basis_version`` only (never by model, App or
request fields). Every basis_version on main at 1fd4ad55:

====================================  ==========  =================================================
basis_version                          writer      path
====================================  ==========  =================================================
``lio-plan.1``                         lio         cj_draft.lio_plan plan (server self-signed)
``lio-edit.1``                         lio         cj_draft.lio_plan single replacement edit
``lio-calendar-plan.1``                lio         cj_draft.lio_calendar plan
``lio-calendar-edit.1``                lio         cj_draft.calendar_edit
``lio-rich-plan.1``                    lio         cj_draft.lio_rich plan / scoped adjustment
``lio-undo.1``                         undo        cj_trip.lio_history._append_undo (structured.1/2)
``lio-calendar-undo.1``                undo        cj_trip.calendar_history.undo
``lio-rich-undo.1``                    undo        cj_trip.rich_history.undo
``lio-date-convert.1``                 user        cj_draft.calendar_dates (date the person stated)
``needs-manual.1`` / ``needs-manual.2`` user       NEEDS edit/save (/v1/trip-needs-saves)
``manual-unbound.1``                   user        manual edit (manual_storage.save_manual)
``manual-initialization.1``            user        manual initialization
``source-initialization.1``            user        source initialization
``scoped-edit.1``                      user        cj_draft.scoped_publisher, accepted by the person
``run-<run_id>``                       user        cj_agent.draft legacy draft, /v1/trip-actions
``needs-run-<run_id>``                 user        cj_draft.needs_publisher draft, /v1/trip-needs-actions
anything else                          user        conservative default
====================================  ==========  =================================================

Origin rules (:func:`item_origins`): an item that was ``user`` in the previous version and is
still present stays ``user``. Lio write: new items and previous ``lio`` items are ``lio``. User
write: a new item or one whose bytes changed (``packed(item)``) is ``user``, an unchanged one keeps
its origin. Undo: each item keeps the origin of the restored version, except that an item that was
``user`` in the undone version stays ``user``. An item without a record (any version committed
before 0061) counts as ``user``.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import json

from .domain import Conflict, Denied, packed

# Upper bounds of one automatic Lio write (ADR-0012 decision 8): new items and new days.
MAX_NEW_ITEMS = 30
MAX_NEW_DAYS = 7
UNDO_WINDOW = timedelta(hours=24)

LIO_BASES = frozenset({'lio-plan.1', 'lio-edit.1', 'lio-calendar-plan.1', 'lio-calendar-edit.1',
                       'lio-rich-plan.1'})
UNDO_BASES = frozenset({'lio-undo.1', 'lio-calendar-undo.1', 'lio-rich-undo.1'})
LIO, USER, UNDO = 'lio', 'user', 'undo'


class AutosaveConflict(Conflict):
    """A Lio write the comparison refused; ``code`` is the reason, the whole write is refused."""
    CODES = ('user_item_changed', 'user_order_changed', 'tombstone_readded', 'too_large')

    def __init__(self, code):
        if code not in self.CODES:
            raise ValueError('unknown autosave refusal')
        super().__init__(code)
        self.code = code


def writer(basis_version):
    if basis_version in LIO_BASES:
        return LIO
    if basis_version in UNDO_BASES:
        return UNDO
    return USER


def items(document):
    value = document.get('items') if type(document) is dict else None
    return list(value) if type(value) is list else []


def days(document):
    value = document.get('days') if type(document) is dict else None
    return list(value) if type(value) is list else []


def amap_id(item):
    place = item.get('place')
    if type(place) is dict and place.get('state') == 'matched' and type(place.get('amap_id')) is str:
        return place['amap_id']
    return None


def _origin(origins, item_id):
    return origins.get(item_id, USER)


def item_origins(kind, previous_items, previous_origins, new_items, restored_origins=None):
    """Origin of every item of the new version, in its order. ``*_origins`` map item_id -> origin."""
    before = {item['id']: item for item in previous_items}
    result = {}
    for item in new_items:
        item_id = item['id']
        old = before.get(item_id)
        if old is not None and _origin(previous_origins, item_id) == USER:
            result[item_id] = USER
        elif kind == LIO:
            result[item_id] = LIO
        elif kind == UNDO:
            result[item_id] = _origin(restored_origins or {}, item_id)
        elif old is None or packed(old) != packed(item):
            result[item_id] = USER
        else:
            result[item_id] = _origin(previous_origins, item_id)
    return result


def tombstones(kind, previous_items, new_items):
    """(item_id, amap_id) of items a person's write removed; Lio writes and undo record none."""
    if kind != USER:
        return []
    present = {item['id'] for item in new_items}
    return [(item['id'], amap_id(item)) for item in previous_items if item['id'] not in present]


def check_lio_write(previous_items, previous_origins, tombstones, new_items, *, previous_days=(), new_days=()):
    """Switch-on comparison of one Lio write; raises AutosaveConflict, never writes partially."""
    after = {item['id']: item for item in new_items}
    users = [item for item in previous_items if _origin(previous_origins, item['id']) == USER]
    for item in users:
        changed = after.get(item['id'])
        if changed is None or packed(changed) != packed(item):
            raise AutosaveConflict('user_item_changed')
    user_ids = [item['id'] for item in users]
    kept = set(user_ids)
    if [item['id'] for item in new_items if item['id'] in kept] != user_ids:
        raise AutosaveConflict('user_order_changed')
    before = {item['id'] for item in previous_items}
    added = [item for item in new_items if item['id'] not in before]
    removed_ids = {item_id for item_id, _ in tombstones}
    removed_places = {place for _, place in tombstones if place is not None}
    for item in added:
        if item['id'] in removed_ids or (amap_id(item) is not None and amap_id(item) in removed_places):
            raise AutosaveConflict('tombstone_readded')
    old_days = {day.get('day_index') for day in previous_days if type(day) is dict}
    new_day_count = sum(1 for day in new_days if type(day) is dict and day.get('day_index') not in old_days)
    if len(added) > MAX_NEW_ITEMS or new_day_count > MAX_NEW_DAYS:
        raise AutosaveConflict('too_large')


def _origins_at(repository, cur, trip_id, version):
    if version < 1:
        return {}
    cur.execute('SELECT item_id,origin FROM cj_trip_item_origin WHERE scope=%s AND trip_id=%s AND trip_version=%s',
                (repository.scope, trip_id, version))
    return dict(cur.fetchall())


def _accepted_content(repository, cur, trip_id, version):
    cur.execute('SELECT p.content FROM cj_trip_receipt r JOIN cj_trip_proposal p '
                'ON (p.scope,p.proposal_id)=(r.scope,r.proposal_id) '
                "WHERE r.scope=%s AND r.trip_id=%s AND r.committed_version=%s AND r.kind='accept'",
                (repository.scope, trip_id, version))
    rows = cur.fetchall()
    return bytes(rows[0][0]) if len(rows) == 1 else None


def enabled(repository):
    return getattr(repository, 'autosave', None) is True


@dataclass(frozen=True)
class Commit:
    """What record_commit decided before the version is written; write() runs after it is."""
    trip_id: str
    version: int
    origins: dict
    removed: list
    autosave: bool

    def write(self, repository, cur, action_id):
        for item_id, origin in self.origins.items():
            cur.execute('INSERT INTO cj_trip_item_origin(scope,trip_id,trip_version,item_id,origin) VALUES(%s,%s,%s,%s,%s)',
                        (repository.scope, self.trip_id, self.version, item_id, origin))
        for item_id, place in self.removed:
            cur.execute('INSERT INTO cj_trip_item_tombstone(scope,trip_id,item_id,amap_id,trip_version) VALUES(%s,%s,%s,%s,%s)',
                        (repository.scope, self.trip_id, item_id, place, self.version))
        cur.execute('INSERT INTO cj_trip_commit_time(scope,action_id,autosave) VALUES(%s,%s,%s)',
                    (repository.scope, action_id, self.autosave))


def record_commit(repository, cur, proposal, previous_content):
    """Decide origins/tombstones for one accepted Proposal; with the switch on, compare a Lio write.

    ``previous_content`` is the current record (None for a new Trip). Raises AutosaveConflict
    before anything is written. The caller writes the version, then calls ``Commit.write``.
    """
    kind = writer(proposal.basis_version)
    version = proposal.expected_version + 1
    before = json.loads(previous_content) if previous_content is not None else None
    after = json.loads(proposal.content)
    previous_items, new_items = items(before), items(after)
    previous_origins = _origins_at(repository, cur, proposal.trip_id, proposal.expected_version)
    restored = None
    if kind == UNDO:
        # Undo appends the exact bytes of version-1. Anything else is treated as a person's write.
        if _accepted_content(repository, cur, proposal.trip_id, proposal.expected_version - 1) == proposal.content:
            restored = _origins_at(repository, cur, proposal.trip_id, proposal.expected_version - 1)
        else:
            kind = USER
    autosave = kind == LIO and enabled(repository)
    if autosave:
        cur.execute('SELECT item_id,amap_id FROM cj_trip_item_tombstone WHERE scope=%s AND trip_id=%s',
                    (repository.scope, proposal.trip_id))
        check_lio_write(previous_items, previous_origins, cur.fetchall(), new_items,
                        previous_days=days(before), new_days=days(after))
    return Commit(proposal.trip_id, version,
                  item_origins(kind, previous_items, previous_origins, new_items, restored),
                  tombstones(kind, previous_items, new_items), autosave)


def require_undo_window(repository, cur, current):
    """Shared by every undo entry (_append_undo): an autosave version is undoable for 24 h (DB clock).

    A version committed without autosave, or before 0061 (no record), keeps today's behaviour.
    """
    cur.execute('SELECT t.autosave,t.committed_at+%s<=clock_timestamp() FROM cj_trip_receipt r '
                'JOIN cj_trip_commit_time t ON (t.scope,t.action_id)=(r.scope,r.action_id) '
                "WHERE r.scope=%s AND r.trip_id=%s AND r.committed_version=%s AND r.kind='accept'",
                (UNDO_WINDOW, repository.scope, current.trip_id, current.version))
    row = cur.fetchone()
    if row is not None and row[0] is True and row[1] is not False:
        raise Denied('autosave undo window expired')


@dataclass(frozen=True)
class AutosaveReceipt:
    """Undo receipt of one automatic Lio write (ADR-0012 decision 5). Not yet wired to an answer."""
    action_id: str
    trip_id: str
    committed_version: int
    content_sha256: str
    content_version: str | None
    restore_version: int | None
    restore_hash: str | None
    restore_content_version: str | None
    undo_until: datetime
    first: bool


def _content_version(content):
    document = json.loads(content)
    value = document.get('content_version') if type(document) is dict else None
    return value if type(value) is str else None


def autosave_receipt(repository, cur, action_id):
    """The original receipt of an autosave commit, or None (unknown action or not an autosave)."""
    cur.execute('SELECT r.trip_id,r.committed_version,t.committed_at,t.committed_at+%s FROM cj_trip_receipt r '
                'JOIN cj_trip_commit_time t ON (t.scope,t.action_id)=(r.scope,r.action_id) '
                "WHERE r.scope=%s AND r.action_id=%s AND r.kind='accept' AND t.autosave",
                (UNDO_WINDOW, repository.scope, action_id))
    row = cur.fetchone()
    if row is None:
        return None
    trip_id, version, committed_at, undo_until = row
    content = _accepted_content(repository, cur, trip_id, version)
    if content is None:
        raise Denied('original autosave revision unavailable')
    previous = _accepted_content(repository, cur, trip_id, version - 1) if version > 1 else None
    if version > 1 and previous is None:
        raise Denied('original autosave restore revision unavailable')
    cur.execute('SELECT NOT EXISTS(SELECT 1 FROM cj_trip_commit_time WHERE scope=%s AND autosave '
                'AND (committed_at,action_id)<(%s,%s))', (repository.scope, committed_at, action_id))
    first = cur.fetchone()[0]
    return AutosaveReceipt(action_id, trip_id, version, sha256(content).hexdigest(), _content_version(content),
                           version - 1 if previous is not None else None,
                           sha256(previous).hexdigest() if previous is not None else None,
                           _content_version(previous) if previous is not None else None,
                           undo_until, first is True)
