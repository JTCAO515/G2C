"""B dialogue projection over C's protected original planning discovery."""
import json

from cj_agent.draft import trip_scope_for
from cj_auth.interfaces import AdmissionStatus
from cj_draft.needs_local import publisher
from cj_message.travel_reference import MessageContextAuthority
from cj_trip.auth_boundary import Boundary
from cj_trip.domain import Denied, packed
from cj_trip.needs_action import NeedsAction
from cj_trip.needs_action_store import NeedsActions
from cj_trip.scoped_discovery import DiscoveryQuery

from .local_account_admission_v2 import account_checker_for
from .local_app import scope_for


class DialogueTripCards(Boundary):
    def __init__(self, database, auth_dir, selected_subjects, confirmation_signer):
        self.database=database
        checker=account_checker_for(auth_dir,database,selected_subjects=selected_subjects)

        def resolve(principal):
            owner=scope_for(principal.issuer,principal.subject)
            return lambda:database.connect(owner),trip_scope_for(owner)

        super().__init__(checker,resolve,confirmation_signer,structured=True)

    def _bind(self, token):
        repository,principal,guard=super()._bind(token)
        owner=scope_for(principal.issuer,principal.subject)

        def admit():
            result=self.checker.check(token)
            if result.status is not AdmissionStatus.ALLOWED or result.principal!=principal:
                raise Denied('original dialogue Trip admission changed')
            return result.principal

        authority=MessageContextAuthority(self.database.message_repository(owner),admit)
        source=publisher(self.database,self.checker,authority,lambda:token,owner).source
        actions=NeedsActions(self.database,owner,source)
        repository.needs_actions=actions

        def bound_guard(stage):
            guard(stage)
            if repository.needs_actions is not actions:
                raise Denied('dialogue Trip source binding changed')

        return repository,principal,bound_guard

    def read(self, token, binding, proposal_id):
        def project(value):
            detail=value['proposal']
            reference=value['reference']
            if (value['state']!='published' or detail is None or detail.proposal.proposal_id!=proposal_id
                    or (reference['message_id'],reference['run_id'],reference['conversation_id'])
                       != (binding.message_id,binding.run_id,binding.conversation_id)):
                raise Denied('original dialogue Trip card unavailable')
            proposal=detail.proposal
            sources=[dict(source_id=source['id'],label=source['text'],state='unknown')
                     for source in json.loads(proposal.content)['sources']]
            card=dict(card_id=proposal_id,version=1,status='pending',proposal_id=proposal_id,
                      trip_id=proposal.trip_id,expected_trip_version=proposal.expected_version,
                      candidate_hash=detail.candidate_hash,days=value['days'])
            return packed(dict(card=card,sources=sources))

        query=DiscoveryQuery(binding.message_id,binding.run_id)
        encoded=self.with_operation(token,lambda context:context.discover_demo_needs(query,project))
        value=json.loads(encoded)
        return value['card'],value['sources']


    @staticmethod
    def _adoption_receipt(value):
        if value is None:
            return b'null'
        return packed(dict(kind=value.kind,proposal_id=value.proposal_id,candidate_hash=value.candidate_hash,
                           trip_id=value.trip_id,committed_version=value.committed_version))

    def adopt(self, token, intent):
        request=NeedsAction.parse(packed(dict(version='TRIP-needs-action.1',action_id=intent.trip_action_id,
            kind='accept',proposal_id=intent.proposal_id,candidate_hash=intent.candidate_hash)))
        response=self.with_operation(token,lambda context:self._adoption_receipt(context.act_needs(request)))
        return json.loads(response)

    def original_adoption(self, token, intent):
        response=self.with_operation(token,
            lambda context:self._adoption_receipt(context.query_action(intent.trip_action_id)))
        return json.loads(response)
