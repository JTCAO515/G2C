"""Read-only original MESSAGE/RUN discovery of a source-current C candidate."""
from contextlib import contextmanager
from dataclasses import dataclass
import json
import re
from urllib.parse import parse_qsl

from cj_auth.interfaces import AdmissionStatus
from cj_api.local_app import scope_for
from cj_message.edit_reference import EditAuthority
from cj_run.core import Binding
from .domain import Denied,ProposalDetail
from .domain import packed
from cj_manual_edit.scoped import Request


@dataclass(frozen=True)
class DiscoveryQuery:
    message_id:str
    run_id:str
    @classmethod
    def parse(cls,pairs):
        values=dict(pairs)
        if len(pairs)!=2 or set(values)!={'message_id','run_id'}:raise ValueError('exact original message/run query required')
        for value in values.values():
            if type(value) is not str or not value.strip() or '\0' in value or len(value.encode('utf8'))>2048:
                raise ValueError('bounded original UTF-8 identity required')
        return cls(values['message_id'],values['run_id'])


def parse_discovery_query(raw):
    if len(raw)>12400:raise ValueError('bounded original query required')
    value=raw.decode('ascii')
    if re.search(r'%(?![0-9A-Fa-f]{2})',value):raise ValueError('invalid URI encoding')
    return DiscoveryQuery.parse(parse_qsl(value,keep_blank_values=True,strict_parsing=True,encoding='utf8',errors='strict'))


class ReadRunRepository:
    def __init__(self,original):self.original=original
    @contextmanager
    def transaction(self):
        with self.original.transaction(require_clean_close=True) as tx:yield tx


class ScopedDiscovery:
    def __init__(self,actions):self.actions=actions

    def read(self,repository,query,encode):
        actions=self.actions;database=actions.database
        def admit():
            value=actions.checker.check(actions.token)
            if value.status is not AdmissionStatus.ALLOWED:raise Denied('discovery admission unavailable')
            return value.principal
        principal=admit();owner=scope_for(principal.issuer,principal.subject)
        with database.message_repository(owner).transaction() as tx:
            stored=tx.find(query.message_id)
            if stored is None or stored.receipt.run_id!=query.run_id:raise Denied('original message/run unavailable')
            r=stored.receipt
            binding=Binding(owner,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence)
        original_run=database.run_repository(owner)
        authority=EditAuthority(database.message_repository(owner),admit,ReadRunRepository(original_run))
        reference=authority.read_original(binding).public_value()
        state=original_run.recover(binding,require_clean_close=True).state
        with repository.transaction() as cur:
            cur.execute('SELECT proposal_id,message_scope,run_id,original_input,original_trip,scope_input,needs_input,memory_input,model_input '
                'FROM cj_trip_scoped_basis WHERE scope=%s AND message_scope=%s AND run_id=%s',(repository.scope,owner,binding.run_id))
            rows=cur.fetchall()
        effects=tuple(v for v in state.effects if v.startswith('trip_proposal:'))
        requested=reference['modification_intent']=='propose_scoped_edit'
        def metadata(result):
            # No candidate bytes use Memory. Still retain the real RUN/M/TRAVEL/
            # NEEDS/Trip source guards through encoding, in the original order.
            with original_run.transaction(require_clean_close=True) as tx:
                if tx.get(binding)!=state:raise Denied('RUN changed during discovery')
                with authority.hold_for_effect(binding) as lease:
                    if lease.reference.public_value()!=reference:raise Denied('original reference changed')
                    encoded=encode(dict(state=result,reference=reference,run_status=state.status,
                                        draft_outcome=state.draft_outcome,proposal=None))
                    lease.check(binding);repository.guard('scoped_discovery')
                    return encoded
        if not requested:
            if rows or effects or state.draft_outcome is not None:raise Denied('discussion cannot have a scoped candidate')
            return metadata('not_requested')
        if not rows:
            if effects:raise Denied('original published candidate basis unavailable')
            outcome=state.draft_outcome
            if state.status=='unknown' or outcome=='provider_unknown':result='unknown'
            elif state.status in ('queued','running'):result='pending'
            elif state.status=='completed' and outcome in ('validation_failed','provider_failed','budget_exhausted'):result='no_candidate'
            elif state.status in ('failed','cancelled','context_invalid'):result='unavailable'
            else:raise Denied('original candidate outcome unavailable')
            return metadata(result)
        if len(rows)!=1 or state.status!='completed' or state.draft_outcome is not None:
            raise Denied('original scoped candidate state inconsistent')
        row=rows[0];proposal_id=row[0];basis=row[1:]
        if effects!=('trip_proposal:'+proposal_id,):raise Denied('original RUN/candidate association inconsistent')
        try:
            captured=actions.capture_sources(basis,ReadRunRepository(original_run),readonly=True)
            if captured.binding!=binding or captured.source.reference.public_value()!=reference:
                raise Denied('original discovery reference changed')
        except (ValueError,TypeError,KeyError,UnicodeError) as exc:
            raise Denied('original scoped candidate source unavailable') from exc
        def current():repository.guard('scoped_discovery')
        # Reuse B's real completed-RUN source lease and C's actual Memory/NEEDS
        # checks. The guarded cursor executes reads only: no act/effect/put/write.
        with captured.authority.publication(binding,captured.source,phase='accept',deadline=current) as lease:
            lease.enter_source(captured.memory.hold(binding))
            lease.enter_source(actions.publisher.hold_sources(lease,captured.prepared))
            if lease.lock_trip()!=bytes(basis[3]):raise Denied('original discovery Trip changed')
            cur=lease.cursor
            detail=ProposalDetail(*repository._proposal(cur,proposal_id))
            cur.execute('SELECT scope_input,diff,report FROM cj_trip_scoped_basis WHERE scope=%s AND proposal_id=%s '
                'AND message_scope=%s AND run_id=%s',(repository.scope,proposal_id,owner,binding.run_id))
            found=cur.fetchone()
            if found is None:raise Denied('original scoped candidate unavailable')
            public=tuple(bytes(v) for v in found)
            try:
                retained=json.loads(public[0])
                if packed(retained)!=public[0]:raise Denied('canonical original scope projection required')
                original_request=Request.parse(packed(retained['request']))
                expected=json.loads(captured.prepared.state.scope.request.raw)
                # Language is presentation data. A rebuilt bilingual host must
                # retain the original request rather than invent another action.
                expected['language']=original_request.language
                if retained!=dict(version='TRIP-scoped-basis.1',reference=reference,request=expected):
                    raise Denied('original scoped selection projection changed')
            except (ValueError,TypeError,KeyError,UnicodeError) as exc:
                raise Denied('original scoped selection unavailable') from exc
            if (detail.proposal.content!=captured.candidate.content or public[1]!=captured.candidate.diff
                    or original_request.request_id!=captured.prepared.state.scope.request.request_id):raise Denied('original scoped candidate changed')
            lease.before_write()
            encoded=encode(dict(state='published',reference=reference,run_status=state.status,draft_outcome=None,
                                proposal=(detail,public)))
            lease.before_write()  # Final currentness after complete bounded encoding.
            return encoded
