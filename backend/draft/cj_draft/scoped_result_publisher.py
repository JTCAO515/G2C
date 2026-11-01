"""Publisher2: original non-acceptable scoped results on the sole RUN cursor."""
import json
from hashlib import sha256

from cj_message.edit_result_protocol import PUBLISHER_ABI,PreparedClarification,ScopedResult,EditResultConfiguration
from cj_manual_edit.scoped_explanation import explain
from cj_trip.manual import ManualEdit,prepare as prepare_one
from cj_trip.manual_needs import EditV2,prepare as prepare_two
from cj_trip.domain import Conflict,Denied,packed
from cj_agent.draft import DraftRejected
from cj_feasibility.scoped_trip import check as check_constraints
from .scoped_publisher import ScopedPublisher,local_configuration as candidate_configuration


def report_bytes(report,verification):
    return packed(dict(status=report.status,checks=[dict(code=c.code,status=c.status,missing=list(c.missing),zh=c.zh,en=c.en) for c in report.checks],
        output_check=dict(accepted=verification.accepted,codes=list(verification.codes),zh=verification.zh,en=verification.en)))


class ScopedResultPublisher(ScopedPublisher):
    abi=PUBLISHER_ABI

    def _prepare(self,binding,source,token):
        scope=self.resolve_source(binding,source)
        if scope.status!='READY':return PreparedClarification(self.capture_state(binding,source,token,scope))
        return self.prepare_ready(binding,source,token,scope)

    def explanation(self,state,reply):
        if state.scope.status!='READY':return explain(state.scope),None
        explanation=explain(state.scope,reply)
        if explanation is None:return None,None
        version=json.loads(state.scope.original.content)['content_version']
        candidate=(prepare_one if version=='structured.1' else prepare_two)(state.scope.original,(ManualEdit if version=='structured.1' else EditV2).parse(reply))
        if version=='structured.1':from cj_feasibility.trip_time import evaluate
        else:from cj_feasibility.trip_time_v2 import evaluate
        if evaluate(candidate.content).status=='CONFLICT':raise Conflict('explicit Trip time conflict')
        required=json.loads(explanation.raw)['required_selection']['item_ids']
        _,report,verification=check_constraints(candidate.content,state.needs,json.loads(state.previous),required,self.limits)
        return explanation,report_bytes(report,verification)

    def store_result(self,publication,prepared,reply,explanation,report,kind):
        state=prepared.state;publication.check(state.binding)
        if publication.lock_trip()!=state.scope.original.content:raise Denied('original result Trip changed')
        repository=self.repository(state.binding.scope)
        result_id='scoped-result-'+state.binding.run_id
        scope=packed(dict(version='TRIP-scoped-basis.1',reference=state.source.reference.public_value(),request=json.loads(state.scope.request.raw)))
        # All bytes and validation precede the last source/admission/deadline guard.
        values=(repository.scope,result_id,state.binding.scope,state.binding.run_id,kind,state.source.original_utf8,
            sha256(state.source.original_utf8).hexdigest(),state.scope.original.trip_id,state.scope.original.version,
            state.scope.original.content,scope,state.needs.raw,state.memory,reply,explanation.raw,report)
        cur=publication.cursor
        publication.before_write()
        cur.execute('INSERT INTO cj_trip_scoped_result(scope,result_id,message_scope,run_id,kind,original_input,input_sha256,trip_id,trip_version,original_trip,scope_input,needs_input,memory_input,model_input,explanation,report) '
            'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',values)
        return ScopedResult(kind,result_id)

    def publish_clarification_in_transaction(self,publication,prepared):
        explanation,report=self.explanation(prepared.state,None)
        return self.store_result(publication,prepared,None,explanation,report,'clarification_required')

    def publish_in_transaction(self,publication,prepared,reply):
        raw=reply.encode()
        try:explanation,report=self.explanation(prepared.state,raw)
        except (ValueError,Conflict) as exc:raise DraftRejected(str(exc)) from None
        if explanation is None:return super().publish_in_transaction(publication,prepared,reply)
        return self.store_result(publication,prepared,raw,explanation,report,'expansion_required')


def local_configuration(**kwargs):
    """Explicit publisher2, installed on the same DB before operator activation."""
    database,old=candidate_configuration(**kwargs);p=old.publisher
    publisher=ScopedResultPublisher(database,p.checker,p.credentials,p.memory,p.confirmation,p.limits,language=p.language,clock=p.clock)
    configuration=EditResultConfiguration(old.memory,publisher)
    database.edit_configuration=configuration
    return database,configuration
