"""Exact current accepted source association, reused by edit and planning reads."""
from hashlib import sha256
import json
from .domain import Action,Denied
from cj_needs.domain import decode,validate_fields


def current_origin(cur,repository,trip):
    cur.execute('SELECT r.action_id,r.proposal_id,r.candidate_hash,r.original_input,b.message_scope,b.run_id,b.needs_scope,b.needs_id,b.source_input,b.source_sha256,b.proposed_input '
        'FROM cj_trip_receipt r JOIN cj_trip_needs_basis b ON (b.scope,b.proposal_id)=(r.scope,r.proposal_id) '
        "WHERE r.scope=%s AND r.trip_id=%s AND r.committed_version=%s AND r.kind='accept'",(repository.scope,trip.trip_id,trip.version))
    rows=cur.fetchall()
    if len(rows)!=1:raise Denied('exact accepted source association unavailable')
    row=rows[0];proposal,digest,status=repository._proposal(cur,row[1])
    if (status!='accepted' or proposal.trip_id!=trip.trip_id or proposal.expected_version+1!=trip.version
            or proposal.content!=trip.content or digest!=row[2]):raise Denied('accepted source/Trip mismatch')
    raw=bytes(row[3])
    action=Action(*json.loads(raw))
    if action.raw()!=raw or (action.action_id,action.kind,action.proposal_id,action.candidate_hash)!=(row[0],'accept',row[1],digest):
        raise Denied('original accepted action mismatch')
    source=bytes(row[8])
    if sha256(source).hexdigest()!=row[9]:raise Denied('retained source integrity mismatch')
    proposed=bytes(row[10]);fields=decode(proposed);validate_fields(fields,complete=True)
    return dict(message_scope=row[4],run_id=row[5],needs_scope=row[6],needs_id=row[7],source=source,proposed=proposed)
