"""Lio Trip history and undo through the existing accepted Proposal ledger."""
from dataclasses import dataclass
from hashlib import sha256
import json

from cj_feasibility.proposed import evaluate
from cj_feasibility.validator import Candidate
from .domain import Conflict, Denied, Proposal, ProposalDetail, Trip, identifier, packed
from .needs_action_store import NeedsActions
from .needs_edit_store import NeedsEdits
from .needs_lineage import current_origin
from .planning_context import read_current


PLAN_BASIS = 'lio-plan.1'
EDIT_BASIS = 'lio-edit.1'


def plan_action_id(run_id):
    return 'lio-plan-' + run_id


def edit_action_id(run_id):
    return 'lio-edit-' + run_id


@dataclass(frozen=True)
class TripHead:
    trip_id: str
    version: int
    content_sha256: str

    @classmethod
    def from_trip(cls, trip):
        return cls(trip.trip_id, trip.version, sha256(trip.content).hexdigest())


def current_head(repository, needs_scope, needs_id):
    context = read_current(repository, needs_scope, needs_id)
    if context is None:
        return None
    return TripHead.from_trip(context.trip)


def plan_receipt(repository, binding):
    return _message_receipt(repository, binding, plan_action_id(binding.run_id), PLAN_BASIS)


def edit_receipt(repository, binding):
    return _message_receipt(repository, binding, edit_action_id(binding.run_id), EDIT_BASIS)


def _message_receipt(repository, binding, action_id, basis):
    with repository.transaction() as cur:
        found = repository._receipt(cur, action_id)
        if found is None:
            return None
        receipt, _ = found
        proposal, digest, status = repository._proposal(cur, receipt.proposal_id)
        cur.execute('SELECT m.scope,m.run_id,m.conversation_id,m.generation,m.message_id,m.sequence '
                    'FROM cj_trip_needs_basis b JOIN cj_message_receipt m ON (m.scope,m.run_id)=(b.message_scope,b.run_id) '
                    'WHERE b.scope=%s AND b.proposal_id=%s',
                    (repository.scope, proposal.proposal_id))
        original = (binding.scope, binding.run_id, binding.conversation_id, binding.generation,
                    binding.message_id, binding.message_sequence)
        if (cur.fetchone() != original or proposal.basis_version != basis
                or status != 'accepted' or receipt.kind != 'accept' or receipt.candidate_hash != digest
                or receipt.trip_id != proposal.trip_id or receipt.committed_version != proposal.expected_version + 1):
            raise Denied('original Lio Trip receipt association unavailable')
        return receipt


@dataclass(frozen=True)
class Undo:
    raw: bytes
    action_id: str
    trip_id: str
    expected_version: int
    original_hash: str

    @classmethod
    def parse(cls, raw):
        if type(raw) is not bytes or not 0 < len(raw) <= 1024:
            raise ValueError('bounded original undo required')
        value = json.loads(raw)
        if (type(value) is not dict or set(value) != {
                'version', 'action_id', 'trip_id', 'expected_version', 'original_hash'}
                or value['version'] != 'TRIP-lio-undo.1' or packed(value) != raw):
            raise ValueError('exact canonical undo input required')
        version, digest = value['expected_version'], value['original_hash']
        if type(version) is not int or not 2 <= version < 2**63 - 1:
            raise ValueError('undo requires a previous version')
        if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('original Trip hash required')
        return cls(raw, identifier(value['action_id']), identifier(value['trip_id']), version, digest)


def _revision(repository, cur, trip_id, version):
    cur.execute('SELECT proposal_id,candidate_hash FROM cj_trip_receipt '
                "WHERE scope=%s AND trip_id=%s AND committed_version=%s AND kind='accept'",
                (repository.scope, trip_id, version))
    rows = cur.fetchall()
    if len(rows) != 1:
        raise Denied('exact accepted Trip revision unavailable')
    proposal, digest, status = repository._proposal(cur, rows[0][0])
    if (status != 'accepted' or digest != rows[0][1] or proposal.trip_id != trip_id
            or proposal.expected_version + 1 != version):
        raise Denied('accepted Trip revision integrity')
    return Trip(trip_id, version, repository._content(proposal.content))


def revisions(repository, trip_id, *, before=None, limit=10):
    identifier(trip_id)
    if before is not None and (type(before) is not int or not 1 <= before < 2**63):
        raise ValueError('invalid history cursor')
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError('invalid history limit')
    with repository.transaction() as cur:
        current = NeedsEdits._trip(cur, repository, trip_id)
        start = current.version if before is None else min(current.version, before - 1)
        history = tuple(_revision(repository, cur, trip_id, version)
                        for version in range(start, max(0, start - limit), -1))
        if start == current.version and history[0] != current:
            raise Denied('current Trip revision integrity')
        return history


def _current_for_undo(repository, cur, request):
    current = NeedsEdits._trip(cur, repository, request.trip_id)
    if (current.version != request.expected_version
            or sha256(current.content).hexdigest() != request.original_hash):
        raise Conflict('original Trip changed')
    return current


def _protect_fixed(current, previous):
    before, after = json.loads(current.content), json.loads(previous.content)
    if before.get('content_version') != 'structured.2' or after.get('content_version') != 'structured.2':
        raise Denied('Lio undo requires structured.2 history')
    items = {item['id']: item for item in after['items']}
    old_sources = {source['id']: source for source in before['sources']}
    new_sources = {source['id']: source for source in after['sources']}
    for item in before['items']:
        if item['fixed'] == {'state': 'known', 'value': True}:
            if items.get(item['id']) != item or any(old_sources[ref] != new_sources.get(ref) for ref in item['source_refs']):
                raise Conflict('undo would change a fixed Trip item')


def _check_newer_needs(captured, previous_origin):
    before, revisions = captured.records()
    selected = frozenset(item['item_id'] for item in json.loads(previous_origin['proposed']).get('fixed_items', ()))
    if not {item['item_id'] for item in before.fields.get('fixed_items', ())} <= selected:
        raise Conflict('undo would omit a current source item')
    candidate = Candidate(before.needs_id, before.version, previous_origin['proposed'])
    report = evaluate(before, revisions, candidate, selected_fields=frozenset({'fixed_items'}),
                      selected_item_ids=selected)
    if report.status in ('INVALID', 'CONFLICT') or not any(
            check.code == 'PROTECTED_SCOPE_UNCHANGED' and check.status == 'PASS' for check in report.checks):
        raise Conflict('previous Trip conflicts with current source constraints')


def undo(repository, request):
    """Call inside a protected Lio Trip operation with its current NEEDS lease."""
    if repository.needs_edits is None:
        raise Denied('current source-bound Trip host required')
    source = repository.needs_edits.source
    with repository.transaction() as cur:
        receipt = NeedsActions._previous(repository, cur, request)
        if receipt is not None:
            return receipt
        current = _current_for_undo(repository, cur, request)
        active = current_origin(cur, repository, current)
    captured = source.capture(active['needs_id'], active['needs_version'])
    committed = False
    try:
        with source.hold(captured) as check:
            receipt = _append_undo(repository, request, active, captured, check)
            committed = True
            return receipt
    except BaseException as error:
        if committed:
            # A source or identity check can fail while the lease unwinds after
            # the Trip commit. The caller must reconcile the original action.
            error.commit_possible = True
        raise


def _append_undo(repository, request, active, captured, check):
    action = pending = None
    def final(cur):
        check()
        repository._final_action_eligibility(cur, action, pending)

    with repository.transaction(before_commit=final) as cur:
        receipt = NeedsActions._previous(repository, cur, request)
        if receipt is not None:
            return receipt
        current = _current_for_undo(repository, cur, request)
        previous = _revision(repository, cur, current.trip_id, current.version - 1)
        origin = current_origin(cur, repository, previous)
        if (active['needs_scope'], active['needs_id']) != (origin['needs_scope'], origin['needs_id']):
            raise Conflict('undo would restore a different Needs identity')
        NeedsEdits._selected(cur, repository, current, active)
        _protect_fixed(current, previous)
        if active['needs_version'] != origin['needs_version']:
            _check_newer_needs(captured, origin)
        cur.execute('SELECT EXTRACT(EPOCH FROM clock_timestamp())')
        proposal = Proposal('lio-undo-' + sha256(request.raw).hexdigest(), current.trip_id,
                            current.version, 'lio-undo.1', int(cur.fetchone()[0]) + 300, previous.content)
        digest = repository._publish_in_tx(cur, proposal)
        source_input = active['source']
        cur.execute('INSERT INTO cj_trip_needs_basis(scope,proposal_id,message_scope,run_id,needs_scope,needs_id,'
                    'needs_version,source_input,source_sha256,proposed_input) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (repository.scope, proposal.proposal_id, active['message_scope'], active['run_id'],
                     active['needs_scope'], active['needs_id'], active['needs_version'],
                     source_input, sha256(source_input).hexdigest(), origin['proposed']))
        action = repository.confirm.issue(repository.scope, ProposalDetail(proposal, digest, 'pending'),
            action_id=request.action_id, kind='accept', candidate_hash=digest).action
        receipt, pending = repository._act_in_tx(cur, action)
        cur.execute('INSERT INTO cj_trip_needs_action VALUES(%s,%s,%s,%s,%s)',
                    (repository.scope, request.action_id, proposal.proposal_id, request.raw, action.raw()))
        cur.execute('UPDATE cj_trip_needs_current SET trip_version=%s WHERE scope=%s AND needs_scope=%s AND needs_id=%s',
                    (receipt.committed_version, repository.scope, active['needs_scope'], active['needs_id']))
        return receipt
