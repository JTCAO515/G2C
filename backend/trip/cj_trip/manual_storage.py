"""Manual-unbound adapter into the sole original Proposal/act transaction.

Only called through the protected OperationContext. No client confirmation flag,
new Trip writer, model, source fallback or deletion path is provided.
"""
from dataclasses import dataclass
from hashlib import sha256

from .confirmation import ConfirmationSigner
from .domain import Conflict, Denied, Proposal, ProposalDetail, Trip, identifier
from .manual import prepare


@dataclass(frozen=True)
class PreparedManual:
    detail: ProposalDetail
    diff: bytes


def _configured(repository):
    if not repository.structured:
        raise Denied('explicit structured manual host required')


def _record(cur, repository, trip_id):
    cur.execute('SELECT version,content FROM cj_trip_record WHERE scope=%s AND trip_id=%s',
                (repository.scope, trip_id))
    row = cur.fetchone()
    if row is None: raise Denied('original Trip unavailable')
    return Trip(trip_id, row[0], repository._content(bytes(row[1])))


def prepare_manual(repository, edit):
    _configured(repository)
    with repository.transaction() as cur:
        cur.execute('SELECT original_input,proposal_id,diff FROM cj_trip_manual_basis WHERE scope=%s AND request_id=%s',
                    (repository.scope, edit.request_id))
        previous = cur.fetchone()
        if previous:
            if bytes(previous[0]) != edit.raw: raise Conflict('manual preparation ID input conflict')
            proposal, digest, status = repository._proposal(cur, previous[1])
            return PreparedManual(ProposalDetail(proposal,digest,status), bytes(previous[2]))
        original = _record(cur, repository, edit.trip_id)
        candidate = prepare(original, edit)
        # Import locally: FEAS uses Trip's strict grammar; neither module owns a
        # second time parser/constraint engine or an inferred NEEDS snapshot.
        from cj_feasibility.trip_time import evaluate
        report = evaluate(candidate.content)
        if report.status == 'CONFLICT': raise Conflict('manual candidate time conflict')
        cur.execute('SELECT EXTRACT(EPOCH FROM clock_timestamp())')
        expires_at = int(cur.fetchone()[0]) + 300
        proposal_id = 'manual.' + sha256(edit.raw).hexdigest()
        proposal = Proposal(proposal_id, original.trip_id, original.version,
                            'manual-unbound.1', expires_at, candidate.content)
        digest = repository._publish_in_tx(cur, proposal)
        cur.execute('INSERT INTO cj_trip_manual_basis(scope,request_id,proposal_id,original_input,original_content,diff) VALUES (%s,%s,%s,%s,%s,%s)',
                    (repository.scope,edit.request_id,proposal_id,edit.raw,original.content,candidate.diff))
        return PreparedManual(ProposalDetail(proposal,digest,'pending'),candidate.diff)


def save_manual(repository, save):
    _configured(repository)
    # The accepted host issuer is mandatory. Do not infer or reflect an issuer
    # from an arbitrary confirmation callback accepted by the legacy writer.
    if type(repository.confirm) is not ConfirmationSigner:
        raise Denied('canonical confirmation issuer required')
    action = None
    pending = None
    def final_eligibility(cur):
        repository._final_action_eligibility(cur, action, pending)
    with repository.transaction(before_commit=final_eligibility) as cur:
        cur.execute('SELECT original_input,original_action FROM cj_trip_manual_intent WHERE scope=%s AND action_id=%s',
                    (repository.scope,save.action_id))
        previous = cur.fetchone()
        if previous:
            if bytes(previous[0]) != save.raw: raise Conflict('manual save ID input conflict')
            receipt = repository._receipt(cur,save.action_id)
            if receipt is None or receipt[1] != bytes(previous[1]):
                raise Conflict('manual original receipt integrity')
            return receipt[0]
        if repository._receipt(cur,save.action_id) is not None:
            raise Conflict('action ID already used by another original input')
        proposal,digest,status = repository._proposal(cur,save.proposal_id)
        if digest != save.candidate_hash: raise Conflict('candidate changed')
        cur.execute('SELECT request_id,original_input,original_content FROM cj_trip_manual_basis WHERE scope=%s AND proposal_id=%s',
                    (repository.scope,save.proposal_id))
        basis = cur.fetchone()
        if basis is None: raise Denied('manual preparation basis unavailable')
        from .manual import ManualEdit
        edit = ManualEdit.parse(bytes(basis[1]))
        current = _record(cur,repository,proposal.trip_id)
        candidate = prepare(current,edit)
        if (current.content != bytes(basis[2]) or proposal.content != candidate.content
                or proposal.expected_version != current.version):
            raise Conflict('original manual basis changed')
        detail = ProposalDetail(proposal,digest,status)
        action = repository.confirm.issue(repository.scope,detail,action_id=save.action_id,
                                         kind='accept',candidate_hash=save.candidate_hash).action
        receipt,pending = repository._act_in_tx(cur,action)
        cur.execute('INSERT INTO cj_trip_manual_intent(scope,action_id,proposal_id,original_input,original_action) VALUES (%s,%s,%s,%s,%s)',
                    (repository.scope,save.action_id,save.proposal_id,save.raw,action.raw()))
        return receipt


def manual_preparation(repository, request_id):
    _configured(repository)
    identifier(request_id)
    with repository.transaction() as cur:
        cur.execute('SELECT proposal_id,diff FROM cj_trip_manual_basis WHERE scope=%s AND request_id=%s',
                    (repository.scope,request_id))
        row=cur.fetchone()
        if row is None:return None
        proposal,digest,status=repository._proposal(cur,row[0])
        return PreparedManual(ProposalDetail(proposal,digest,status),bytes(row[1]))
