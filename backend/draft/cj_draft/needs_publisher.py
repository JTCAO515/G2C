"""Source-bound local structured publisher through the original Trip transaction."""
import json
import time
from hashlib import sha256
from cj_trip.domain import Proposal
from cj_trip.needs_plan import build
from cj_agent.draft import Draft,DraftRejected,proposal_id_for,trip_scope_for,PROPOSAL_TTL_SECONDS

SYSTEM='TRIP-model-plan.1: explicit structured.2 observations only; preserve original fixed/unselected source items; no source/evidence approval. UNKNOWN is not a default fact.'


class NeedsDraftPublisher:
    content_version='structured.2'
    system=SYSTEM
    def __init__(self,repository,source,clock=time.time):
        self.repository,self.source,self.clock=repository,source,clock
    def sources_for(self,binding):return self.source.capture(binding)
    def hold_for_publication(self,binding):return self.source.hold_for_publication(binding)
    def model_messages(self,binding,text,capture,messages):
        before,_=capture.records()
        return list(messages)+[dict(role='system',content=json.dumps(dict(version='TRIP-source-input.1',
            needs_id=before.needs_id,revision=before.version,fields=before.fields),ensure_ascii=False,separators=(',',':')))]
    def build_plan(self,raw,capture):return build(raw,capture)
    def check_trip_context(self,cur,binding,capture):return None
    def retain_trip_context(self,cur,proposal,binding,capture):return None
    def publish_for_message(self,binding,original,current,reply,capture,*,before_publish=None):
        self.source.check(binding,capture)
        if (current is None or current!=original or capture.binding!=binding
                or self.repository.scope!=trip_scope_for(binding.scope) or before_publish is None):
            raise DraftRejected('original publication authority unavailable')
        try:content,candidate,report=self.build_plan(reply.encode('utf8'),capture)
        except (ValueError,UnicodeError):raise DraftRejected('source-bound structured plan rejected') from None
        now=self.clock()
        proposal=Proposal(proposal_id_for(binding.run_id),'trip-'+binding.run_id,0,
            'needs-run-'+binding.run_id,int(now)+PROPOSAL_TTL_SECONDS,content)
        value=json.loads(capture.raw)
        def final(cur):
            self.source.check(binding,capture)
            before_publish()  # Original final deadline remains last, no SQL after it.
        with self.repository.transaction(before_commit=final) as cur:
            self.source.check(binding,capture)
            self.check_trip_context(cur,binding,capture)
            digest=self.repository._publish_in_tx(cur,proposal)
            cur.execute('SELECT source_sha256,proposed_input FROM cj_trip_needs_basis WHERE scope=%s AND proposal_id=%s',
                        (self.repository.scope,proposal.proposal_id))
            prior=cur.fetchone()
            if prior is not None:
                if prior!=(sha256(capture.raw).hexdigest(),candidate.content):raise DraftRejected('immutable source basis changed')
            else:
                cur.execute('INSERT INTO cj_trip_needs_basis(scope,proposal_id,message_scope,run_id,needs_scope,needs_id,needs_version,source_input,source_sha256,proposed_input) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (self.repository.scope,proposal.proposal_id,binding.scope,binding.run_id,value['needs_scope'],
                     value['needs_id'],value['revision'],capture.raw,sha256(capture.raw).hexdigest(),candidate.content))
            self.retain_trip_context(cur,proposal,binding,capture)
        return Draft(proposal.proposal_id,proposal.trip_id,digest)
