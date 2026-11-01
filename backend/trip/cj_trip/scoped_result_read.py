"""Current-source read of an immutable, non-acceptable original result."""
from dataclasses import replace
from hashlib import sha256
import json

from cj_auth.interfaces import AdmissionStatus
from cj_api.local_app import scope_for
from cj_message.edit_reference import EditAuthority
from cj_message.domain import Command
from cj_manual_edit.scoped import Request
from cj_run.core import Binding
from cj_draft.scoped_publisher import memory_descriptor
from .domain import Denied,packed
from .scoped_discovery import ReadRunRepository


def read(actions,repository,result_id,encode):
    database=actions.database
    def admit():
        value=actions.checker.check(actions.token)
        if value.status is not AdmissionStatus.ALLOWED:raise Denied('result admission unavailable')
        return value.principal
    principal=admit();owner=scope_for(principal.issuer,principal.subject)
    with repository.transaction() as cur:
        cur.execute('SELECT message_scope,run_id,kind,original_input,input_sha256,trip_id,trip_version,original_trip,scope_input,needs_input,memory_input,model_input,explanation,report '
            'FROM cj_trip_scoped_result WHERE scope=%s AND result_id=%s',(repository.scope,result_id))
        row=cur.fetchone()
    if row is None or row[0]!=owner:raise Denied('original result unavailable')
    _,run_id,kind,original,digest,trip_id,trip_version,trip,scope,needs,memory,reply,explanation,report=row
    original,trip,scope,needs,memory,explanation=map(bytes,(original,trip,scope,needs,memory,explanation))
    reply=None if reply is None else bytes(reply);report=None if report is None else bytes(report)
    try:
        command=Command.parse_v4(original);retained=json.loads(scope)
        request=Request.parse(packed(retained['request']))
        if packed(retained)!=scope or sha256(original).hexdigest()!=digest:raise ValueError('canonical original result required')
        with database.message_repository(owner).transaction() as tx:
            stored=tx.find(command.message_id)
            if stored is None or stored.raw!=original or stored.receipt.run_id!=run_id:raise Denied('original result association unavailable')
            r=stored.receipt
            binding=Binding(owner,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence)
        run_repository=database.run_repository(owner)
        authority=EditAuthority(database.message_repository(owner),admit,ReadRunRepository(run_repository),result_mode=True)
        reference=authority.read_original(binding).public_value()
        if retained!=dict(version='TRIP-scoped-basis.1',reference=reference,request=json.loads(request.raw)):
            raise Denied('original result reference changed')
        expected_trip=reference['trip_context']
        if (trip_id,trip_version,sha256(trip).hexdigest())!=(expected_trip['id'],expected_trip['expected_version'],expected_trip['content_sha256']):
            raise Denied('original result Trip association changed')
        with run_repository.transaction(require_clean_close=True) as tx:
            state=tx.get(binding)
            effect='scoped_result:'+kind+':'+result_id
            if state.status!='completed' or state.scoped_result!=(kind,result_id) or state.effects!=(effect,):
                raise Denied('original completed result unavailable')
            cur=tx.cur
            # Only a stale identity/version marker is returned here, never any
            # Memory-derived explanation, source text, original reply or scope.
            cur.execute('SELECT version FROM cj_trip_record WHERE scope=%s AND trip_id=%s',(repository.scope,trip_id))
            current=cur.fetchone()
            if current is None:raise Denied('original result Trip unavailable')
            if current[0]!=trip_version:
                raw=encode(dict(result_id=result_id,state='stale',expected_version=trip_version,current_version=current[0],result=None))
                repository.guard('scoped_result_stale');return raw
        captured=actions.configuration.memory.bind_readonly(database,owner,principal.subject,admit,message_context=authority).capture(binding)
        if memory_descriptor(captured)!=memory:raise Denied('original result Memory changed')
        source=authority.capture(binding)
        if (source.original_utf8,source.trip_content,source.reference.public_value())!=(original,trip,reference):
            raise Denied('original result source changed')
        prepared=actions.publisher._prepare(binding,source,actions.token)
        state=prepared.state
        expected=json.loads(state.scope.request.raw);expected['language']=request.language
        if expected!=json.loads(request.raw) or state.needs.raw!=needs:raise Denied('original result selection/NEEDS changed')
        prepared=replace(prepared,state=replace(state,scope=replace(state.scope,request=request)))
        # RUN first; short Trip capture released before Memory. Then current
        # Memory -> NEEDS -> Trip SHARE. Refresh checks take compatible SHARE,
        # never a Trip UPDATE held while another connection waits for SHARE.
        with run_repository.transaction(require_clean_close=True) as tx:
            current_run=tx.get(binding)
            if current_run.status!='completed' or current_run.scoped_result!=(kind,result_id) or current_run.effects!=(effect,):
                raise Denied('original result RUN changed')
            with authority.hold_for_effect(binding,source_lock=False) as lease,captured.hold(binding),actions.publisher.hold_sources(lease,prepared) as check:
                cur=tx.cur
                cur.execute('SELECT scope FROM cj_trip_scope WHERE scope=%s FOR SHARE',(repository.scope,))
                if cur.fetchone() is None:raise Denied('original Trip owner unavailable')
                cur.execute('SELECT version,content FROM cj_trip_record WHERE scope=%s AND trip_id=%s',(repository.scope,trip_id))
                if cur.fetchone()!=(trip_version,trip):raise Denied('original result Trip changed')
                fresh,fresh_report=actions.publisher.explanation(prepared.state,reply)
                if fresh is None or fresh.status!=kind.upper() or fresh.raw!=explanation or fresh_report!=report:
                    raise Denied('original deterministic result changed')
                value=dict(result_id=result_id,kind=kind,reference=reference,explanation=json.loads(explanation),
                           feasibility=None if report is None else json.loads(report))
                encoded=encode(dict(result_id=result_id,state='current',expected_version=trip_version,current_version=trip_version,result=value))
                check();captured.check();lease.check(binding);repository.guard('scoped_result_return')
                return encoded
    except (ValueError,TypeError,KeyError,UnicodeError) as exc:
        raise Denied('original result content unavailable') from exc
