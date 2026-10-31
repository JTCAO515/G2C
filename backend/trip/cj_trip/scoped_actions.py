"""Scoped explicit action/recovery through the original confirmation and act."""
import json
from .needs_action import NeedsAction
from .domain import Conflict,Denied,ProposalDetail,packed
from cj_message.edit_reference import EditAuthority
from cj_auth.interfaces import AdmissionStatus
from cj_api.local_app import scope_for
from cj_run.core import Binding,Denied as RunDenied
from cj_needs.domain import Denied as NeedsDenied
from cj_memory.runtime import RuntimeDenied
from cj_draft.scoped_publisher import memory_descriptor


class ScopedAction(NeedsAction):
    @classmethod
    def parse(cls,raw):return cls._parse(raw,'TRIP-scoped-action.1')


class ScopedActions:
    def __init__(self,database,configuration,token,checker):
        self.database,self.configuration,self.token,self.checker=database,configuration,token,checker
        self.publisher=configuration.publisher

    def previous(self,cur,repository,request):
        cur.execute('SELECT original_input,original_action FROM cj_trip_scoped_action WHERE scope=%s AND action_id=%s',(repository.scope,request.action_id))
        row=cur.fetchone();receipt=repository._receipt(cur,request.action_id)
        if row is not None:
            if bytes(row[0])!=request.raw or receipt is None or bytes(row[1])!=receipt[1]:raise Conflict('original scoped action input changed')
            return receipt[0]
        if receipt is not None:raise Conflict('action ID already belongs to another original action')
        return None

    def apply(self,repository,request):
        try:return self._apply(repository,request)
        except (Denied,Conflict,RunDenied,NeedsDenied,RuntimeDenied):
            # A concurrent original action may have committed after our initial
            # read. Reconcile only the original ID/bytes; never redispatch a write.
            with repository.transaction() as cur:
                previous=self.previous(cur,repository,request)
                if previous is not None:return previous
            raise

    def _apply(self,repository,request):
        with repository.transaction() as cur:
            previous=self.previous(cur,repository,request)
            if previous is not None:return previous
            proposal,digest,status=repository._proposal(cur,request.proposal_id)
            if digest!=request.candidate_hash:raise Conflict('original candidate hash changed')
            cur.execute('SELECT message_scope,run_id,original_input,original_trip,scope_input,needs_input,memory_input,model_input FROM cj_trip_scoped_basis WHERE scope=%s AND proposal_id=%s',
                        (repository.scope,proposal.proposal_id));row=cur.fetchone()
            if row is None:raise Denied('original scoped source unavailable')
        if request.kind=='reject':return self.reject(repository,request)
        reference=json.loads(bytes(row[4]))['reference'];owner=row[0]
        binding=Binding(owner,reference['conversation_id'],reference['generation'],reference['message_id'],row[1],reference['sequence'])
        def admit():
            value=self.checker.check(self.token)
            if value.status is not AdmissionStatus.ALLOWED or scope_for(value.principal.issuer,value.principal.subject)!=owner:
                raise Denied('actual scoped action identity unavailable')
            return value.principal
        principal=admit()
        authority=EditAuthority(self.database.message_repository(owner),admit,self.database.run_repository(owner))
        memory=self.configuration.memory.bind(self.database,owner,principal.subject,admit,message_context=authority).capture(binding)
        if memory_descriptor(memory)!=bytes(row[6]):raise Denied('original candidate Memory changed')
        source=authority.capture(binding)
        if (source.original_utf8,source.trip_content,source.reference.public_value())!=(bytes(row[2]),bytes(row[3]),reference):
            raise Denied('original scoped message/Trip changed')
        prepared=self.publisher._prepare(binding,source,self.token)
        if prepared.state.needs.raw!=bytes(row[5]):raise Denied('original candidate NEEDS changed')
        candidate,needs_candidate,report,verification=self.publisher.validate_reply(prepared.state,bytes(row[7]))
        if candidate.content!=proposal.content:raise Conflict('original scoped diff changed')
        action=None;pending=None;publication=None
        def final():
            repository.guard('scoped_commit')
            repository._final_action_eligibility(publication.cursor,action,pending)
        with authority.publication(binding,source,phase='accept',deadline=final) as publication:
            publication.enter_source(memory.hold(binding))
            publication.enter_source(self.publisher.hold_sources(publication,prepared))
            if publication.lock_trip()!=bytes(row[3]):raise Conflict('original Trip changed')
            cur=publication.cursor
            previous=self.previous(cur,repository,request)
            if previous is not None:return previous
            proposal,digest,status=repository._proposal(cur,request.proposal_id)
            action=repository.confirm.issue(repository.scope,ProposalDetail(proposal,digest,status),action_id=request.action_id,
                kind=request.kind,candidate_hash=request.candidate_hash).action
            pending=proposal
            publication.before_write()
            receipt,pending=repository._act_in_tx(cur,action)
            cur.execute('INSERT INTO cj_trip_scoped_action VALUES(%s,%s,%s,%s,%s)',(repository.scope,request.action_id,proposal.proposal_id,request.raw,action.raw()))
            # Keep an existing planning pointer consistent; do not choose another
            # Trip or rewrite an unselected plan when editing an archived Trip.
            cur.execute('SELECT trip_version FROM cj_trip_needs_current WHERE scope=%s AND trip_id=%s',(repository.scope,proposal.trip_id))
            pointers=cur.fetchall()
            if any(v!=(proposal.expected_version,) for v in pointers):raise Conflict('current planning pointer version changed')
            cur.execute('UPDATE cj_trip_needs_current SET trip_version=%s WHERE scope=%s AND trip_id=%s AND trip_version=%s',
                        (receipt.committed_version,repository.scope,proposal.trip_id,proposal.expected_version))
            publication.before_write()
            return receipt

    def reject(self,repository,request):
        action=None;pending=None
        def final(cur):repository._final_action_eligibility(cur,action,pending)
        with repository.transaction(before_commit=final) as cur:
            previous=self.previous(cur,repository,request)
            if previous is not None:return previous
            p,digest,status=repository._proposal(cur,request.proposal_id)
            if digest!=request.candidate_hash:raise Conflict('original candidate hash changed')
            action=repository.confirm.issue(repository.scope,ProposalDetail(p,digest,status),action_id=request.action_id,kind='reject',candidate_hash=digest).action
            receipt,pending=repository._act_in_tx(cur,action)
            cur.execute('INSERT INTO cj_trip_scoped_action VALUES(%s,%s,%s,%s,%s)',(repository.scope,request.action_id,p.proposal_id,request.raw,action.raw()))
            return receipt
