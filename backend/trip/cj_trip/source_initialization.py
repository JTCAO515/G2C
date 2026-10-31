"""Explicit protected-legacy initialization using actual original source leases."""
import base64
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import json

from .domain import Conflict, Denied, Proposal, ProposalDetail, Trip, packed, validate_legacy_document
from .initialization import Initialization, initialize
from .manual import ManualSave
from .manual_origin import accepted_origin, run_origin, MAX_BYTES
from .manual_storage import PreparedManual

BASIS='source-initialization.1'


@dataclass(frozen=True,repr=False)
class SourceInitialization:
    raw:bytes
    needs_id:str
    needs_version:int
    initialization:Initialization
    @property
    def request_id(self):return self.initialization.request_id
    @classmethod
    def parse(cls,raw):
        from .domain import identifier
        if type(raw) is not bytes or not 0<len(raw)<=1_000_000:raise ValueError('bounded original initialization required')
        d=json.loads(raw)
        if (type(d) is not dict or set(d)!={'version','needs_reference','initialization'}
                or d['version']!='TRIP-source-initialize.1' or packed(d)!=raw):raise ValueError('canonical source initialization required')
        ref=d['needs_reference']
        if type(ref) is not dict or set(ref)!={'id','expected_version'}:raise ValueError('explicit original NEEDS required')
        identifier(ref['id'])
        if type(ref['expected_version']) is not int or not 1<=ref['expected_version']<=128:raise ValueError('bounded source version required')
        return cls(raw,ref['id'],ref['expected_version'],Initialization.parse(packed(d['initialization'])))


class SourceInitializationSave(ManualSave):
    @classmethod
    def parse(cls,raw):return cls._parse(raw,'TRIP-source-initialize-save.1')


def _basis(raw):
    if not 0<len(raw)<=8_000_000:raise Denied('bounded initialization basis required')
    d=json.loads(raw)
    if (type(d) is not dict or set(d)!={'version','request','source'}
            or d['version']!='TRIP-source-initialize-basis.1' or packed(d)!=raw):raise Denied('source initialization basis unavailable')
    request=base64.b64decode(d['request'],validate=True);source=base64.b64decode(d['source'],validate=True)
    if base64.b64encode(request).decode()!=d['request'] or base64.b64encode(source).decode()!=d['source']:
        raise Denied('canonical source basis required')
    return SourceInitialization.parse(request),source


class SourceInitializations:
    def __init__(self,database,owner,source):self.database,self.owner,self.source=database,owner,source

    def _original(self,cur,repository,request):
        edit=request.initialization
        cur.execute('SELECT version,content FROM cj_trip_record WHERE scope=%s AND trip_id=%s',(repository.scope,edit.trip_id))
        row=cur.fetchone()
        if row is None:raise Denied('original accepted Trip unavailable')
        trip=Trip(edit.trip_id,row[0],bytes(row[1]));document=json.loads(trip.content)
        validate_legacy_document(document)
        if packed(document)!=trip.content or trip.version!=1:raise Conflict('explicit original legacy root required')
        # The immutable accepted root and original RUN effect, not a basis label
        # or a client-supplied reference, establish the original source binding.
        proposal,action,size=accepted_origin(cur,repository.scope,trip,MAX_BYTES)
        if not proposal.basis_version.startswith('run-') or proposal.expected_version!=0:raise Denied('original RUN root required')
        binding,command=run_origin(cur,self.owner,proposal,MAX_BYTES-size)
        if command.needs_reference!=(request.needs_id,request.needs_version):raise Denied('original NEEDS cannot be retargeted')
        return trip,binding

    @contextmanager
    def _hold(self,repository,request,expected_source=None):
        with repository.transaction() as cur:original,binding=self._original(cur,repository,request)
        # RUN -> original M/TRAVEL -> original NEEDS -> Trip, never invert locks.
        with self.database.run_repository(self.owner).transaction():
            capture=self.source.capture(binding)
            if expected_source is not None and capture.raw!=expected_source:raise Denied('original source capture changed')
            with self.source.hold_for_publication(binding) as check:
                yield original,binding,capture,check

    def prepare(self,repository,request):
        with repository.transaction() as cur:
            cur.execute('SELECT original_input,proposal_id FROM cj_trip_manual_basis WHERE scope=%s AND request_id=%s',(repository.scope,request.request_id))
            prior=cur.fetchone()
            if prior is not None:
                original,_=_basis(bytes(prior[0]))
                if original.raw!=request.raw:raise Conflict('original initialization ID input conflict')
                prior_id=prior[1]
            else:prior_id=None
        if prior_id is not None:return self.query(repository,request.request_id)
        with self._hold(repository,request) as (original,binding,capture,check):
            def final(cur):check()
            with repository.transaction(before_commit=final) as cur:
                current,current_binding=self._original(cur,repository,request)
                if (current,current_binding)!=(original,binding):raise Conflict('original initialization changed')
                cur.execute('SELECT original_input,proposal_id,diff FROM cj_trip_manual_basis WHERE scope=%s AND request_id=%s',(repository.scope,request.request_id))
                prior=cur.fetchone()
                if prior is not None:
                    old,raw=_basis(bytes(prior[0]))
                    if old.raw!=request.raw or raw!=capture.raw:raise Conflict('initialization input conflict')
                    p,d,s=repository._proposal(cur,prior[1]);return PreparedManual(ProposalDetail(p,d,s),bytes(prior[2]))
                candidate=initialize(current,request.initialization)
                from cj_feasibility.trip_time import evaluate
                if evaluate(candidate.content).status=='CONFLICT':raise Conflict('initialization time conflict')
                cur.execute('SELECT EXTRACT(EPOCH FROM clock_timestamp())');expires=int(cur.fetchone()[0])+300
                p=Proposal('source-init.'+sha256(request.raw).hexdigest(),current.trip_id,current.version,BASIS,expires,candidate.content)
                retained=packed(dict(version='TRIP-source-initialize-basis.1',request=base64.b64encode(request.raw).decode(),source=base64.b64encode(capture.raw).decode()))
                if len(retained)+len(candidate.diff)>8_000_000:raise Denied('bounded original initialization source required')
                check();digest=repository._publish_in_tx(cur,p)
                cur.execute('INSERT INTO cj_trip_manual_basis(scope,request_id,proposal_id,original_input,original_content,diff) VALUES(%s,%s,%s,%s,%s,%s)',
                    (repository.scope,request.request_id,p.proposal_id,retained,current.content,candidate.diff))
                return PreparedManual(ProposalDetail(p,digest,'pending'),candidate.diff)

    def query(self,repository,request_id):
        with repository.transaction() as cur:
            cur.execute('SELECT original_input,proposal_id,diff FROM cj_trip_manual_basis WHERE scope=%s AND request_id=%s',(repository.scope,request_id))
            row=cur.fetchone()
            if row is None:return None
            request,source=_basis(bytes(row[0]));p,d,s=repository._proposal(cur,row[1])
            if p.basis_version!=BASIS:raise Denied('source initialization basis version required')
        # A recovered preview does not renew source authority or rebase its Trip.
        with self._hold(repository,request,source) as (_,_,_,check):
            check();return PreparedManual(ProposalDetail(p,d,s),bytes(row[2]))

    @staticmethod
    def _previous(repository,cur,request):
        cur.execute('SELECT original_input,original_action FROM cj_trip_manual_intent WHERE scope=%s AND action_id=%s',(repository.scope,request.action_id))
        row=cur.fetchone()
        if row is not None:
            if bytes(row[0])!=request.raw:raise Conflict('original action bytes changed')
            receipt=repository._receipt(cur,request.action_id)
            if receipt is None or receipt[1]!=bytes(row[1]):raise Denied('original initialization receipt mismatch')
            return receipt[0]
        if repository._receipt(cur,request.action_id) is not None:raise Conflict('original action ID already used')
        return None

    def receipt(self,repository,action_id):
        with repository.transaction() as cur:
            cur.execute('SELECT original_input FROM cj_trip_manual_intent WHERE scope=%s AND action_id=%s',(repository.scope,action_id))
            row=cur.fetchone()
            if row is None:return None
            raw=bytes(row[0])
            if json.loads(raw).get('version')!='TRIP-source-initialize-save.1':return None
            return self._previous(repository,cur,SourceInitializationSave.parse(raw))

    def save(self,repository,request):
        from cj_needs.domain import Denied as NeedsDenied
        from cj_run.core import Denied as RunDenied
        try:return self._save(repository,request)
        except (Conflict,Denied,NeedsDenied,RunDenied):
            # Concurrent original acceptance may have advanced the Trip/source.
            # Read only that original receipt; never retry a write or swallow ACK UNKNOWN.
            with repository.transaction() as cur:prior=self._previous(repository,cur,request)
            if prior is not None:return prior
            raise

    def _save(self,repository,request):
        with repository.transaction() as cur:
            prior=self._previous(repository,cur,request)
            if prior is not None:return prior
            cur.execute('SELECT original_input FROM cj_trip_manual_basis WHERE scope=%s AND proposal_id=%s',(repository.scope,request.proposal_id))
            row=cur.fetchone()
            if row is None:raise Denied('original initialization unavailable')
            initialization,retained=_basis(bytes(row[0]))
        action=None;pending=None
        with self._hold(repository,initialization,retained) as (original,binding,capture,check):
            def final(cur):check();repository._final_action_eligibility(cur,action,pending)
            with repository.transaction(before_commit=final) as cur:
                prior=self._previous(repository,cur,request)
                if prior is not None:return prior
                current,current_binding=self._original(cur,repository,initialization)
                if (current,current_binding)!=(original,binding):raise Conflict('original Trip changed')
                p,digest,status=repository._proposal(cur,request.proposal_id)
                candidate=initialize(current,initialization.initialization)
                if p.basis_version!=BASIS or p.expected_version!=current.version or p.content!=candidate.content or digest!=request.candidate_hash:
                    raise Conflict('exact original initialization required')
                action=repository.confirm.issue(repository.scope,ProposalDetail(p,digest,status),action_id=request.action_id,kind='accept',candidate_hash=digest).action
                receipt,pending=repository._act_in_tx(cur,action)
                cur.execute('INSERT INTO cj_trip_manual_intent(scope,action_id,proposal_id,original_input,original_action) VALUES(%s,%s,%s,%s,%s)',
                    (repository.scope,request.action_id,p.proposal_id,request.raw,action.raw()))
                return receipt
