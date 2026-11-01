"""Original MESSAGE/RUN to the existing source-bound planning candidate."""
from hashlib import sha256
import json
from cj_message.domain import Command
from cj_run.core import Binding
from .domain import Denied,ProposalDetail,packed


class NeedsDiscovery:
    def __init__(self,actions):self.actions=actions

    def read(self,repository,query,encode):
        actions=self.actions;owner=actions.owner;database=actions.database
        with database.message_repository(owner).transaction() as tx:
            stored=tx.find(query.message_id)
            if stored is None or stored.receipt.run_id!=query.run_id:raise Denied('original message/run unavailable')
            try:command=Command.parse_v2(stored.raw)
            except (ValueError,UnicodeError) as exc:raise Denied('original NEEDS message version unavailable') from exc
            r=stored.receipt
            binding=Binding(owner,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence)
        source=actions.source;authority=source.message_context
        reference=authority.read_original(binding).public_value()
        run=database.run_repository(owner)
        state=run.recover(binding,require_clean_close=True).state
        with repository.transaction() as cur:
            cur.execute('SELECT b.proposal_id,b.source_input,b.source_sha256 FROM cj_trip_needs_basis b JOIN cj_trip_proposal p '
                'ON (p.scope,p.proposal_id)=(b.scope,b.proposal_id) WHERE b.scope=%s AND b.message_scope=%s AND b.run_id=%s '
                'AND p.basis_version=%s AND p.expected_version=0',(repository.scope,owner,binding.run_id,'needs-run-'+binding.run_id))
            rows=cur.fetchall()
        effects=tuple(e for e in state.effects if e.startswith('trip_proposal:'))
        requested=json.loads(command.raw)['creation_intent']=='consider_trip'
        def metadata(kind):
            with run.transaction(require_clean_close=True) as tx:
                if tx.get(binding)!=state:raise Denied('original RUN changed')
                with authority.hold_for_effect(binding) as lease:
                    if lease.reference.public_value()!=reference:raise Denied('original source changed')
                    data=encode(dict(state=kind,reference=reference,run_status=state.status,draft_outcome=state.draft_outcome,
                        needs_reference=None if command.needs_reference is None else dict(id=command.needs_reference[0],expected_version=command.needs_reference[1]),
                        source_profile=None,planning_context=None,proposal=None))
                    lease.check(binding);repository.guard('needs_discovery')
                    return data
        if not requested:
            if rows or effects or state.draft_outcome is not None:raise Denied('discussion cannot publish planning candidate')
            return metadata('not_requested')
        if command.needs_reference is None:raise Denied('original NEEDS planning reference required')
        if not rows:
            if effects:raise Denied('published original planning basis unavailable')
            if state.status=='unknown' or state.draft_outcome=='provider_unknown':kind='unknown'
            elif state.status in ('queued','running'):kind='pending'
            elif state.status=='completed' and state.draft_outcome in ('validation_failed','provider_failed','budget_exhausted'):kind='no_candidate'
            elif state.status in ('failed','cancelled','context_invalid'):kind='unavailable'
            else:raise Denied('original planning outcome unavailable')
            return metadata(kind)
        if len(rows)!=1 or state.status!='completed' or state.draft_outcome is not None:raise Denied('original planning state inconsistent')
        pid,raw,digest=rows[0];raw=bytes(raw)
        if effects!=('trip_proposal:'+pid,) or sha256(raw).hexdigest()!=digest:raise Denied('original planning association unavailable')
        # Same original canonical source as planning acceptance, not caller DTOs.
        with run.transaction(require_clean_close=True) as tx:
            if tx.get(binding)!=state:raise Denied('RUN changed during planning discovery')
            capture=source.capture(binding)
            if capture.raw!=raw or json.loads(raw)['reference']!=reference:raise Denied('original planning source changed')
            with source.hold_for_publication(binding) as check:
                cur=tx.cur;repository._lock_scope(cur)
                detail=ProposalDetail(*repository._proposal(cur,pid));p=detail.proposal
                if (p.basis_version!='needs-run-'+binding.run_id or p.expected_version!=0
                        or json.loads(p.content).get('content_version')!='structured.2'):raise Denied('original structured planning candidate required')
                retained=json.loads(raw)
                if packed(retained)!=raw:raise Denied('canonical planning source required')
                profile,context=actions.planning_context(cur,repository,pid,retained)
                identity=None if context is None else dict(trip_id=context[0],version=context[1],content_sha256=sha256(context[2]).hexdigest())
                check();repository.guard('needs_discovery')
                encoded=encode(dict(state='published',reference=reference,run_status=state.status,draft_outcome=None,
                    needs_reference=dict(id=retained['needs_id'],expected_version=retained['revision']),source_profile=profile,
                    planning_context=identity,proposal=detail))
                check();repository.guard('needs_discovery')
                return encoded
