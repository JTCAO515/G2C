"""C336 source-bound scoped candidates on B's actual RUN cursor, no second writer."""
from contextlib import contextmanager
from dataclasses import dataclass,replace
from hashlib import sha256
import json,time
from cj_message.edit_protocol import PUBLISHER_ABI,PreparedEdit,EditConfiguration
from cj_api.local_app import LocalDatabase,scope_for,ISSUER,AUDIENCE
from cj_api.local_needs import protected_reader
from cj_needs.revision_lease import RevisionLease
from cj_message.needs_binding import needs_scope_for
from cj_trip.domain import Trip,Proposal,Denied,Conflict,packed
from cj_trip.postgres import Repository
from cj_trip.needs_lineage import current_origin
from cj_trip.current_needs_source import CurrentNeedsSource
from cj_manual_edit.scoped import Request,resolve,preview
from cj_feasibility.scoped_trip import check as check_constraints
from cj_memory.scoped_capture import ScopedMemoryConfiguration,snapshot_bytes
from cj_agent.draft import trip_scope_for,DraftRejected


def memory_descriptor(run):
    raw=snapshot_bytes(run)
    if len(raw)>4_000_000:raise Denied('bounded original Memory snapshot required')
    selected=run.owner.selection
    return packed(dict(snapshot_sha256=sha256(raw).hexdigest(),payload_sha256=sha256(run.payload).hexdigest(),
        context=dict(kind=run.context.kind,id=run.context.id),subject=selected.subject,slots=sorted(selected.slots),max_bytes=selected.max_bytes))


@dataclass(frozen=True,repr=False)
class ScopedState:
    binding:object
    source:object
    scope:object
    needs:object
    previous:bytes
    memory:bytes
    token:str


class ScopedPublisher:
    abi=PUBLISHER_ABI
    def __init__(self,database,checker,credentials,memory,confirmation,limits,*,language,clock=time.time):
        if language not in ('zh-Hans','en'):raise ValueError('explicit prompt language required')
        self.database,self.checker,self.credentials,self.memory=database,checker,credentials,memory
        self.confirmation,self.limits,self.language,self.clock=confirmation,limits,language,clock
        def resolve_owner(principal):
            owner=scope_for(principal.issuer,principal.subject)
            return lambda:database.connect(owner),owner,needs_scope_for(owner)
        self.needs_lease=RevisionLease(checker,resolve_owner,environment='local',issuer=ISSUER,audience=AUDIENCE)

    def repository(self,owner):return Repository(lambda:self.database.connect(owner),trip_scope_for(owner),self.confirmation,structured=True)

    def prepare(self,binding,source):
        return self._prepare(binding,source,self.credentials(binding.scope))

    def resolve_source(self,binding,source):
        ref=source.reference.public_value()
        if ref['modification_intent']!='propose_scoped_edit':raise DraftRejected('explicit modification intent required')
        trip=Trip(ref['trip_context']['id'],ref['trip_context']['expected_version'],source.trip_content)
        selection=(dict(kind='dates',dates=[ref['trip_context']['day']['date']]) if ref['trip_context']['day'] is not None
                   else dict(kind='items',item_ids=list(source.selected_item_ids)))
        request=Request.parse(packed(dict(version='TRIP-scoped-request.1',request_id='scoped-'+binding.run_id,
            trip_id=trip.trip_id,expected_version=trip.version,original_hash=ref['trip_context']['content_sha256'],
            text=json.loads(source.original_utf8)['text'],language=self.language,selection=selection)))
        return resolve(trip,request)

    def capture_state(self,binding,source,token,scope):
        ref=source.reference.public_value();trip=scope.original
        current=CurrentNeedsSource(self.database,self.checker,token,protected_reader(self.database,self.checker))
        needs=current.capture(ref['needs_reference']['id'],ref['needs_reference']['expected_version'])
        repository=self.repository(binding.scope)
        with repository.transaction() as cur:
            cur.execute('SELECT version,content FROM cj_trip_record WHERE scope=%s AND trip_id=%s',(repository.scope,trip.trip_id))
            row=cur.fetchone()
            if row is None or (row[0],bytes(row[1]))!=(trip.version,trip.content):raise Denied('original Trip changed before model')
            cur.execute('SELECT 1 FROM cj_trip_receipt r JOIN cj_trip_needs_basis b ON (b.scope,b.proposal_id)=(r.scope,r.proposal_id) '
                "WHERE r.scope=%s AND r.trip_id=%s AND r.committed_version=%s AND r.kind='accept'",(repository.scope,trip.trip_id,trip.version))
            previous=current_origin(cur,repository,trip)['proposed'] if cur.fetchone() is not None else packed({})
        run=self.memory.registry.captured(binding)
        return ScopedState(binding,source,scope,needs,previous,memory_descriptor(run),token)

    def _prepare(self,binding,source,token):
        return self.prepare_ready(binding,source,token,self.resolve_source(binding,source))

    def prepare_ready(self,binding,source,token,scope):
        if scope.status!='READY':raise DraftRejected(scope.reason_zh+' / '+scope.reason_en)
        permitted=tuple(item for item in scope.selected_ids if item in source.selected_item_ids)
        if not permitted or set(permitted)!=set(source.selected_item_ids):raise DraftRejected('original resolved selection requires clarification')
        scope=replace(scope,selected_ids=permitted)
        state=self.capture_state(binding,source,token,scope)
        ref=source.reference.public_value();trip=scope.original;request=scope.request;needs=state.needs
        system=packed(dict(version='TRIP-scoped-model.1',instruction='Return only the exact canonical TRIP-manual-edit JSON, '
            'within selected IDs. Preserve fixed/unknown and all unselected values; do not set intent, owner, evidence or sources.',
            edit_version='TRIP-manual-edit.2' if ref['content_version']=='structured.2' else 'TRIP-manual-edit.1',
            request_id=request.request_id,trip_id=trip.trip_id,expected_version=trip.version,original_hash=request.original_hash,
            language=self.language,selected_item_ids=list(scope.selected_ids),original_content=json.loads(trip.content),
            needs_fields=needs.records()[0].fields)).decode()
        return PreparedEdit(system,state)

    @contextmanager
    def hold_sources(self,publication,prepared):
        state=prepared.state;binding=state.binding
        publication.check(binding)
        if publication.reference!=state.source.reference:raise Denied('captured original selection changed')
        run=self.memory.registry.captured(binding);run.check()
        if memory_descriptor(run)!=state.memory:raise Denied('captured Memory changed')
        with self.needs_lease.hold(state.token,binding) as check:
            check();yield check

    def validate_reply(self,state,reply):
        result=preview(state.scope,reply)
        if result.candidate is None:raise DraftRejected(result.reason_zh+' / '+result.reason_en)
        candidate,report,verification=check_constraints(result.candidate.content,state.needs,json.loads(state.previous),state.scope.selected_ids,self.limits)
        return result.candidate,candidate,report,verification

    def publish_in_transaction(self,publication,prepared,reply):
        state=prepared.state;publication.check(state.binding)
        original=publication.lock_trip()
        if original!=state.scope.original.content:raise Denied('captured Trip bytes changed')
        try:candidate,needs_candidate,report,verification=self.validate_reply(state,reply.encode())
        except (ValueError,Conflict) as exc:raise DraftRejected(str(exc)) from None
        trip=state.scope.original;repository=self.repository(state.binding.scope)
        proposal=Proposal('scoped-'+state.binding.run_id,trip.trip_id,trip.version,'scoped-edit.1',int(self.clock())+300,candidate.content)
        report_raw=packed(dict(status=report.status,checks=[dict(code=c.code,status=c.status,missing=list(c.missing),zh=c.zh,en=c.en) for c in report.checks],
            output_check=dict(accepted=verification.accepted,codes=list(verification.codes),zh=verification.zh,en=verification.en)))
        scope_raw=packed(dict(version='TRIP-scoped-basis.1',reference=state.source.reference.public_value(),request=json.loads(state.scope.request.raw)))
        if len(report_raw)>1_000_000:raise DraftRejected('bounded feasibility explanation required')
        publication.before_write()
        repository._publish_in_tx(publication.cursor,proposal)
        cur=publication.cursor
        cur.execute('INSERT INTO cj_trip_scoped_basis(scope,proposal_id,message_scope,run_id,original_input,original_trip,scope_input,needs_input,memory_input,model_input,diff,report) '
            'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(repository.scope,proposal.proposal_id,state.binding.scope,state.binding.run_id,
            state.source.original_utf8,trip.content,scope_raw,state.needs.raw,state.memory,reply.encode(),candidate.diff,report_raw))
        before,_=state.needs.records()
        cur.execute('INSERT INTO cj_trip_needs_basis(scope,proposal_id,message_scope,run_id,needs_scope,needs_id,needs_version,source_input,source_sha256,proposed_input) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (repository.scope,proposal.proposal_id,state.binding.scope,state.binding.run_id,needs_scope_for(state.binding.scope),before.needs_id,before.version,
             state.needs.raw,sha256(state.needs.raw).hexdigest(),needs_candidate.content))
        return proposal.proposal_id


def local_configuration(*,conninfo_path,auth_dir,run_context,memory,credentials,confirmation,limits,language):
    import os
    from cj_api.composition import CompositionUnavailable
    from cj_api.local_worker_context import checker_for
    from pathlib import Path
    from cj_trip.confirmation import ConfirmationSigner
    from cj_memory.edit_runtime import EditRuntimeConfiguration
    if os.environ.get('CJ_ENV')!='local' or type(memory) is not EditRuntimeConfiguration or type(confirmation) is not ConfirmationSigner:
        raise CompositionUnavailable('explicit actual C edit configuration required')
    database=LocalDatabase(conninfo_path,run_context=run_context,travel_context=True,needs_context=True)
    tracked=ScopedMemoryConfiguration(memory)
    publisher=ScopedPublisher(database,checker_for(Path(auth_dir)),credentials,tracked,confirmation,limits,language=language)
    configuration=EditConfiguration(tracked,publisher)
    database.edit_configuration=configuration
    return database,configuration
