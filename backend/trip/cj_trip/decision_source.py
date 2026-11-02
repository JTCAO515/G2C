"""Read the current accepted Trip decision, not generated text as Memory truth."""
from dataclasses import dataclass
from hashlib import sha256

from .domain import Trip,Conflict,Denied,identifier
from .manual_origin import accepted_origin,MAX_BYTES


@dataclass(frozen=True)
class DecisionQuery:
    trip_id:str
    expected_version:int
    content_sha256:str

    def __post_init__(self):
        identifier(self.trip_id)
        if type(self.expected_version) is not int or not 1<=self.expected_version<=2**63-1:
            raise ValueError('positive original Trip version required')
        value=self.content_sha256
        if type(value) is not str or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('exact original Trip content digest required')


@dataclass(frozen=True,repr=False)
class AcceptedDecision:
    trip_id:str
    version:int
    content_sha256:str
    action_id:str
    proposal_id:str
    candidate_hash:str
    content:bytes
    # Data only: these fields grant no future Trip/Memory write or history scan.


def read(repository,query,project,max_source_bytes,max_result_bytes):
    if (type(max_source_bytes) is not int or not 1<=max_source_bytes<=MAX_BYTES
            or type(max_result_bytes) is not int or not 1<=max_result_bytes<=1_000_000):
        raise ValueError('explicit bounded decision source and response required')
    with repository.transaction() as cur:
        cur.execute('SELECT version,content FROM cj_trip_record WHERE scope=%s AND trip_id=%s',
                    (repository.scope,query.trip_id))
        row=cur.fetchone()
        if row is None:raise Denied('accepted Trip unavailable')
        raw=bytes(row[1])
        if len(raw)>max_source_bytes:raise Denied('accepted Trip source exceeds bound')
        if row[0]!=query.expected_version or sha256(raw).hexdigest()!=query.content_sha256:
            raise Conflict('accepted Trip source version or content changed')
        trip=Trip(query.trip_id,row[0],repository._content(raw))
        proposal,action,_=accepted_origin(cur,repository.scope,trip,max_source_bytes)
        value=AcceptedDecision(trip.trip_id,trip.version,query.content_sha256,action.action_id,
            proposal.proposal_id,action.candidate_hash,trip.content)
        result=project(value)
        if type(result) is not bytes or len(result)>max_result_bytes:
            raise Denied('bounded materialized decision source required')
        return result
