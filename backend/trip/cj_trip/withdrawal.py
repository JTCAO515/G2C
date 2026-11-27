"""Undo of the automatic save that created a Trip: LIO-trip-undo.5 (ADR-0012 revision 1, #1994 part 3).

There is no version before 1 to restore, so the undo appends version 2 with the exact bytes of version 1
(basis ``lio-withdraw.1``, one of ``autosave.UNDO_BASES``) and, in the same transaction, writes the
``cj_trip_withdrawal`` mark. Nothing is deleted: versions, receipts, origins, tombstones and commit times
stay. From then on the sole commit point refuses every write to the Trip (``autosave.refuse_withdrawn``),
the Trip list leaves it out and the conversation's selection reads it as absent, so the next Lio plan
creates a new Trip.

Preconditions, all checked inside the Trip transaction (and the 24 hours again before commit):
the current version is 1 with the request's hash and content version; version 1 was committed by a Lio
basis with the autosave flag (switch on at write time, so it has a receipt); the database clock is
before its commit time + 24 h; every point of version 1 has origin ``lio`` (no point the traveler
touched); it is still the conversation's selected Trip; it is not withdrawn yet. A replay of the same
action id with the same input returns the committed receipt; the same id with other input conflicts.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import re

from cj_strict_json import reject_duplicates
from .autosave import (LIO, LIO_BASES, UNDO_WINDOW, WITHDRAW_BASIS, WithdrawnConflict, _origins_at, items,
                       schema_present, withdrawn)
from .domain import Conflict, Denied, Proposal, ProposalDetail, identifier, packed
from .lio_history import _current_for_undo
from .needs_action_store import NeedsActions
from .needs_lineage import current_origin

# Private canonical input (stored as cj_trip_needs_action.original_input); never on the wire.
VERSION = 'TRIP-lio-withdraw.1'
CONTENT_VERSIONS = ('structured.1', 'structured.2', 'structured.3', 'structured.4')
_FIELDS = {'version', 'action_id', 'trip_id', 'expected_version', 'original_hash', 'content_version'}


@dataclass(frozen=True, repr=False)
class Withdraw:
    raw: bytes
    action_id: str
    trip_id: str
    expected_version: int
    original_hash: str
    content_version: str

    @classmethod
    def parse(cls, raw):
        if type(raw) is not bytes or not 0 < len(raw) <= 1024:
            raise ValueError('bounded original withdrawal input required')
        try:
            value = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate withdrawal field'))
        except (ValueError, RecursionError):
            raise ValueError('strict complete withdrawal JSON required') from None
        if type(value) is not dict or set(value) != _FIELDS or value['version'] != VERSION or packed(value) != raw:
            raise ValueError('exact canonical withdrawal input required')
        if type(value['expected_version']) is not int or value['expected_version'] != 1:
            raise ValueError('only the version that created the Trip can be withdrawn')
        digest = value['original_hash']
        if type(digest) is not str or re.fullmatch('[0-9a-f]{64}', digest) is None:
            raise ValueError('original Trip hash required')
        if value['content_version'] not in CONTENT_VERSIONS:
            raise ValueError('explicit original content version required')
        return cls(raw, identifier(value['action_id']), identifier(value['trip_id']), 1, digest,
                   value['content_version'])

    @classmethod
    def build(cls, action_id, trip_id, expected_version, original_hash, content_version):
        return cls.parse(packed(dict(version=VERSION, action_id=action_id, trip_id=trip_id,
                                     expected_version=expected_version, original_hash=original_hash,
                                     content_version=content_version)))


def _eligible(repository, cur, current):
    """Version 1 is an automatic Lio save, inside its 24 hours (DB clock), with only Lio points."""
    cur.execute('SELECT p.basis_version,t.autosave,t.committed_at+%s>clock_timestamp() FROM cj_trip_receipt r '
                'JOIN cj_trip_proposal p ON (p.scope,p.proposal_id)=(r.scope,r.proposal_id) '
                'JOIN cj_trip_commit_time t ON (t.scope,t.action_id)=(r.scope,r.action_id) '
                "WHERE r.scope=%s AND r.trip_id=%s AND r.committed_version=1 AND r.kind='accept'",
                (UNDO_WINDOW, repository.scope, current.trip_id))
    rows = cur.fetchall()
    if len(rows) != 1 or rows[0][0] not in LIO_BASES or rows[0][1] is not True:
        raise Denied('only an automatic save that created the Trip can be withdrawn')
    if rows[0][2] is not True:
        raise Denied('autosave undo window expired')
    origins = _origins_at(repository, cur, current.trip_id, 1)
    if any(origins.get(item['id']) != LIO for item in items(json.loads(current.content))):
        raise Conflict('withdrawal would hide a point the traveler owns')


def withdraw(repository, request):
    if not isinstance(request, Withdraw):
        raise ValueError('validated withdrawal required')
    action = pending = current = None

    def final(cur):
        if current is not None:
            _eligible(repository, cur, current)
        repository._final_action_eligibility(cur, action, pending)

    with repository.transaction(before_commit=final) as cur:
        receipt = NeedsActions._previous(repository, cur, request)
        if receipt is not None:
            return receipt
        if not schema_present(cur):
            raise Denied('withdrawal requires the 0061 Trip audit tables')
        if withdrawn(repository, cur, request.trip_id):
            raise WithdrawnConflict()
        current = _current_for_undo(repository, cur, request)
        if current.version != 1 or json.loads(current.content).get('content_version') != request.content_version:
            raise Conflict('withdrawal target differs')
        _eligible(repository, cur, current)
        origin = current_origin(cur, repository, current)
        cur.execute('SELECT trip_id,trip_version FROM cj_trip_needs_current WHERE scope=%s AND needs_scope=%s AND needs_id=%s',
                    (repository.scope, origin['needs_scope'], origin['needs_id']))
        if cur.fetchone() != (current.trip_id, current.version):
            raise Conflict('withdrawal requires the conversation\'s selected Trip')
        cur.execute('SELECT EXTRACT(EPOCH FROM clock_timestamp())')
        proposal = Proposal('lio-withdraw-' + sha256(request.raw).hexdigest(), current.trip_id, current.version,
                            WITHDRAW_BASIS, int(cur.fetchone()[0]) + 300, current.content)
        digest = repository._publish_in_tx(cur, proposal)
        # The new version has the bytes of version 1, so it keeps version 1's source association.
        source = origin['source']
        cur.execute('INSERT INTO cj_trip_needs_basis(scope,proposal_id,message_scope,run_id,needs_scope,needs_id,'
                    'needs_version,source_input,source_sha256,proposed_input) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (repository.scope, proposal.proposal_id, origin['message_scope'], origin['run_id'],
                     origin['needs_scope'], origin['needs_id'], origin['needs_version'],
                     source, sha256(source).hexdigest(), origin['proposed']))
        action = repository.confirm.issue(repository.scope, ProposalDetail(proposal, digest, 'pending'),
            action_id=request.action_id, kind='accept', candidate_hash=digest).action
        receipt, pending = repository._act_in_tx(cur, action)
        cur.execute('INSERT INTO cj_trip_needs_action VALUES(%s,%s,%s,%s,%s)',
                    (repository.scope, request.action_id, proposal.proposal_id, request.raw, action.raw()))
        cur.execute('INSERT INTO cj_trip_withdrawal(scope,trip_id,withdrawn_version,undo_action_id) VALUES(%s,%s,%s,%s)',
                    (repository.scope, receipt.trip_id, receipt.committed_version, request.action_id))
        cur.execute('UPDATE cj_trip_needs_current SET trip_version=%s WHERE scope=%s AND needs_scope=%s AND needs_id=%s',
                    (receipt.committed_version, repository.scope, origin['needs_scope'], origin['needs_id']))
        return receipt


def receipt(repository, request, needs_scope, needs_id):
    """The committed withdrawal of this conversation (needs_scope, needs_id) for this exact input, or None.

    Unlike the restore lookup it cannot ask the conversation's current selection: after the withdrawal
    the Trip is no longer selected. It checks the withdrawal mark and the source association instead."""
    if not isinstance(request, Withdraw):
        raise ValueError('validated withdrawal required')
    with repository.transaction() as cur:
        found = NeedsActions._previous(repository, cur, request)
        if found is None:
            return None
        cur.execute('SELECT w.trip_id,w.withdrawn_version,b.needs_scope,b.needs_id FROM cj_trip_withdrawal w '
                    'JOIN cj_trip_receipt r ON (r.scope,r.action_id)=(w.scope,w.undo_action_id) '
                    'JOIN cj_trip_needs_basis b ON (b.scope,b.proposal_id)=(r.scope,r.proposal_id) '
                    'WHERE w.scope=%s AND w.undo_action_id=%s', (repository.scope, request.action_id))
        if cur.fetchone() != (request.trip_id, found.committed_version, needs_scope, needs_id):
            raise Denied('original withdrawal association unavailable')
        return found
