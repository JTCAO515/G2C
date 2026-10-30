"""Current source-bound manual preparation/save; original Trip act is sole writer."""
from copy import deepcopy
from hashlib import sha256
import json
from .domain import Trip,Proposal,ProposalDetail,Denied,Conflict,packed
from .manual_needs import NeedsEdit,prepare
from .manual_storage import PreparedManual
from cj_needs.domain import validate_fields
from cj_feasibility.validator import Candidate
from cj_feasibility.proposed import evaluate


def checked(original,request,source,previous_fields):
    candidate=prepare(original,request.edit)
    from cj_feasibility.trip_time_v2 import evaluate as evaluate_time
    if evaluate_time(candidate.content).status=='CONFLICT':raise Conflict('explicit Trip time conflict')
    before,revisions=source.records()
    if before.needs_id!=request.needs_id or before.version!=request.needs_version:raise Denied('original current source mismatch')
    fields=deepcopy(before.fields);old={v['item_id']:v for v in fields.get('fixed_items',[])}
    previous={item['item_id']:item for item in previous_fields.get('fixed_items',[])}
    document=json.loads(candidate.content);proposed=[]
    for item in document['items']:
        if item['id'] in old:value=deepcopy(old[item['id']])
        else:
            # Prior model intent's proposed participants are retained from its
            # original source-bound candidate by the caller, never guessed here.
            if item['id'] not in previous:raise Denied('original adopted intent unavailable')
            value=deepcopy(previous[item['id']])
        value['description']=item['text']
        # Trip-local lock does not silently rewrite the canonical NEEDS intent.
        # A source lock may only be removed after an explicit NEEDS correction.
        if item['id'] in old and old[item['id']]['locked']=={'state':'known','value':True} and item['fixed']!={'state':'known','value':True}:
            raise Conflict('correct the explicit NEEDS fixed source before unlocking')
        for edge in ('start','end'):
            place=deepcopy(value[edge]['place'])
            value[edge]={key:deepcopy(item['schedule'][edge][key]) for key in ('date','time','timezone')}
            value[edge]['place']=place
        proposed.append(value)
    fields['fixed_items']=proposed;validate_fields(fields,complete=True)
    selected=frozenset(item_id for item_id,field,raw in request.edit.changes if field in ('text','schedule')) | frozenset(set(previous)-set(old))
    selected |= frozenset(item['item_id'] for item in proposed if item['item_id'] in old and old[item['item_id']]['locked']=={'state':'known','value':False} and item!=old[item['item_id']])
    needs_candidate=Candidate(before.needs_id,before.version,packed(fields))
    report=evaluate(before,revisions,needs_candidate,selected_fields=frozenset({'fixed_items'}),selected_item_ids=selected)
    if report.status in ('INVALID','CONFLICT') or not any(c.code=='PROTECTED_SCOPE_UNCHANGED' and c.status=='PASS' for c in report.checks):
        raise Conflict('current source/protected constraints rejected')
    return candidate,needs_candidate,report


class NeedsEdits:
    def __init__(self,current_source):self.source=current_source
    def prepare(self,repository,request):
        edit=request.edit
        with repository.transaction() as cur:
            cur.execute('SELECT original_input,proposal_id,diff FROM cj_trip_needs_edit WHERE scope=%s AND request_id=%s',(repository.scope,request.request_id))
            previous=cur.fetchone()
            if previous:
                if bytes(previous[0])!=request.raw:raise Conflict('edit ID input conflict')
                p,d,s=repository._proposal(cur,previous[1]);return PreparedManual(ProposalDetail(p,d,s),bytes(previous[2]))
        source=self.source.capture(request.needs_id,request.needs_version)
        with self.source.hold(source) as check:
            def final(cur):check()
            with repository.transaction(before_commit=final) as cur:
                cur.execute('SELECT original_input,proposal_id,diff FROM cj_trip_needs_edit WHERE scope=%s AND request_id=%s',(repository.scope,request.request_id))
                prior=cur.fetchone()
                if prior is not None:
                    if bytes(prior[0])!=request.raw:raise Conflict('edit ID input conflict')
                    p,d,s=repository._proposal(cur,prior[1]);return PreparedManual(ProposalDetail(p,d,s),bytes(prior[2]))
                original=self._trip(cur,repository,edit.trip_id)
                root=self._origin(cur,repository,original)
                if root['needs_id']!=request.needs_id:raise Denied('Trip source cannot be retargeted')
                self._selected(cur,repository,original,root)
                candidate,needs_candidate,report=checked(original,request,source,root['proposed'])
                cur.execute('SELECT EXTRACT(EPOCH FROM clock_timestamp())');expires=int(cur.fetchone()[0])+300
                p=Proposal('needs-manual.'+sha256(request.raw).hexdigest(),original.trip_id,original.version,'needs-manual.1',expires,candidate.content)
                digest=repository._publish_in_tx(cur,p)
                cur.execute('INSERT INTO cj_trip_needs_basis(scope,proposal_id,message_scope,run_id,needs_scope,needs_id,needs_version,source_input,source_sha256,proposed_input) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (repository.scope,p.proposal_id,root['message_scope'],root['run_id'],root['needs_scope'],request.needs_id,request.needs_version,
                     source.raw,sha256(source.raw).hexdigest(),needs_candidate.content))
                cur.execute('INSERT INTO cj_trip_needs_edit(scope,request_id,proposal_id,trip_id,original_input,original_content,diff) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                    (repository.scope,request.request_id,p.proposal_id,original.trip_id,request.raw,original.content,candidate.diff))
                return PreparedManual(ProposalDetail(p,digest,'pending'),candidate.diff)
    def query(self,repository,request_id):
        with repository.transaction() as cur:
            cur.execute('SELECT proposal_id,diff FROM cj_trip_needs_edit WHERE scope=%s AND request_id=%s',(repository.scope,request_id))
            row=cur.fetchone()
            if row is None:return None
            p,d,s=repository._proposal(cur,row[0]);return PreparedManual(ProposalDetail(p,d,s),bytes(row[1]))
    def save(self,repository,request):
        from .needs_action_store import NeedsActions
        with repository.transaction() as cur:
            previous=NeedsActions._previous(repository,cur,request)
            if previous is not None:return previous
            cur.execute('SELECT original_input FROM cj_trip_needs_edit WHERE scope=%s AND proposal_id=%s',(repository.scope,request.proposal_id))
            row=cur.fetchone()
            if row is None:raise Denied('original manual basis unavailable')
            edit=NeedsEdit.parse(bytes(row[0]))
        source=self.source.capture(edit.needs_id,edit.needs_version)
        action=None;pending=None
        with self.source.hold(source) as check:
            def final(cur):check();repository._final_action_eligibility(cur,action,pending)
            with repository.transaction(before_commit=final) as cur:
                previous=NeedsActions._previous(repository,cur,request)
                if previous is not None:return previous
                p,digest,status=repository._proposal(cur,request.proposal_id)
                if digest!=request.candidate_hash:raise Conflict('original candidate changed')
                current=self._trip(cur,repository,p.trip_id)
                root=self._origin(cur,repository,current)
                self._selected(cur,repository,current,root)
                candidate,needs_candidate,report=checked(current,edit,source,root['proposed'])
                if p.content!=candidate.content or p.expected_version!=current.version:raise Conflict('original manual candidate changed')
                cur.execute('SELECT source_input FROM cj_trip_needs_basis WHERE scope=%s AND proposal_id=%s',(repository.scope,p.proposal_id))
                if bytes(cur.fetchone()[0])!=source.raw:raise Denied('current source basis changed')
                action=repository.confirm.issue(repository.scope,ProposalDetail(p,digest,status),action_id=request.action_id,kind='accept',candidate_hash=digest).action
                receipt,pending=repository._act_in_tx(cur,action)
                cur.execute('INSERT INTO cj_trip_needs_action VALUES(%s,%s,%s,%s,%s)',(repository.scope,request.action_id,p.proposal_id,request.raw,action.raw()))
                cur.execute('UPDATE cj_trip_needs_current SET trip_version=%s WHERE scope=%s AND trip_id=%s AND trip_version=%s RETURNING trip_id',
                            (receipt.committed_version,repository.scope,receipt.trip_id,current.version))
                if cur.fetchall()!=[(receipt.trip_id,)]:raise Conflict('current selected Trip changed')
                return receipt
    @staticmethod
    def _selected(cur,repository,trip,origin):
        cur.execute('SELECT trip_id,trip_version FROM cj_trip_needs_current WHERE scope=%s AND needs_scope=%s AND needs_id=%s',
                    (repository.scope,origin['needs_scope'],origin['needs_id']))
        if cur.fetchone()!=(trip.trip_id,trip.version):raise Conflict('edit the current explicitly selected Trip or select a new plan')

    @staticmethod
    def _trip(cur,repository,trip_id):
        cur.execute('SELECT version,content FROM cj_trip_record WHERE scope=%s AND trip_id=%s',(repository.scope,trip_id));row=cur.fetchone()
        if row is None:raise Denied('original Trip unavailable')
        return Trip(trip_id,row[0],repository._content(bytes(row[1])))
    @staticmethod
    def _origin(cur,repository,trip):
        from .needs_lineage import current_origin
        value=current_origin(cur,repository,trip)
        value['proposed']=json.loads(value['proposed'])
        return value
