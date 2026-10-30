"""Actual source leases plus the original act implementation; no second writer."""
from contextlib import nullcontext
from hashlib import sha256
import json
from .domain import Conflict,Denied,ProposalDetail


class NeedsActions:
    def __init__(self,database,owner,source):self.database,self.owner,self.source=database,owner,source

    def apply(self,repository,request):
        # Original action reconciliation must precede any current source check.
        with repository.transaction() as cur:
            previous=self._previous(repository,cur,request)
            if previous is not None:return previous
            proposal,digest,status=repository._proposal(cur,request.proposal_id)
            if digest!=request.candidate_hash:raise Conflict('original candidate changed')
            if not proposal.basis_version.startswith('needs-run-'):raise Denied('use explicit source-bound editor save')
            cur.execute('SELECT message_scope,run_id,source_input,source_sha256 FROM cj_trip_needs_basis WHERE scope=%s AND proposal_id=%s',
                        (repository.scope,proposal.proposal_id))
            row=cur.fetchone()
            if row is None or row[0]!=self.owner:raise Denied('original source basis unavailable')
            raw=bytes(row[2])
            if sha256(raw).hexdigest()!=row[3]:raise Denied('original source integrity unavailable')
            value=json.loads(raw);reference=value['reference']
        from cj_run.core import Binding
        binding=Binding(self.owner,reference['conversation_id'],reference['generation'],reference['message_id'],
                        reference['run_id'],reference['sequence'])
        from contextlib import ExitStack
        with ExitStack() as leases:
            if request.kind=='accept':
                # RUN before M/T and NEEDS; no Trip lock is held while acquiring.
                leases.enter_context(self.database.run_repository(self.owner).transaction())
                with repository.transaction() as cur:
                    completed=self._previous(repository,cur,request)
                    if completed is not None:return completed
                captured=self.source.capture(binding)
                if captured.raw!=raw:raise Denied('original source capture changed')
                check=leases.enter_context(self.source.hold_for_publication(binding))
            else:check=lambda:None
            pending=None;action=None
            def final(cur):
                check()
                repository._final_action_eligibility(cur,action,pending)
            with repository.transaction(before_commit=final) as cur:
                previous=self._previous(repository,cur,request)
                if previous is not None:return previous
                proposal,digest,status=repository._proposal(cur,request.proposal_id)
                if digest!=request.candidate_hash:raise Conflict('original candidate changed')
                check()
                action=repository.confirm.issue(repository.scope,ProposalDetail(proposal,digest,status),
                    action_id=request.action_id,kind=request.kind,candidate_hash=request.candidate_hash).action
                receipt,pending=repository._act_in_tx(cur,action)
                cur.execute('INSERT INTO cj_trip_needs_action(scope,action_id,proposal_id,original_input,original_action) VALUES(%s,%s,%s,%s,%s)',
                    (repository.scope,request.action_id,request.proposal_id,request.raw,action.raw()))
                if receipt.committed_version is not None:
                    source=json.loads(raw)
                    cur.execute('INSERT INTO cj_trip_needs_current(scope,needs_scope,needs_id,trip_id,trip_version) VALUES(%s,%s,%s,%s,%s) '
                        'ON CONFLICT(scope,needs_scope,needs_id) DO UPDATE SET trip_id=EXCLUDED.trip_id,trip_version=EXCLUDED.trip_version',
                        (repository.scope,source['needs_scope'],source['needs_id'],receipt.trip_id,receipt.committed_version))
                return receipt

    @staticmethod
    def _previous(repository,cur,request):
        cur.execute('SELECT original_input,original_action FROM cj_trip_needs_action WHERE scope=%s AND action_id=%s',
                    (repository.scope,request.action_id))
        row=cur.fetchone()
        if row is not None:
            if bytes(row[0])!=request.raw:raise Conflict('action ID input conflict')
            receipt=repository._receipt(cur,request.action_id)
            if receipt is None or receipt[1]!=bytes(row[1]):raise Conflict('original receipt integrity')
            return receipt[0]
        if repository._receipt(cur,request.action_id) is not None:raise Conflict('action ID input conflict')
        return None
