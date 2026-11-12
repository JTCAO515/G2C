"""Original date-action reads; call through the existing protected TRIP boundary."""
import base64
from hashlib import sha256
import json
from cj_needs.contract_v1 import decode_snapshot
from cj_feasibility.trip_time_v3 import evaluate
from .calendar_conversion import converted_content, check_conflicts
from .domain import Denied
from .lio_history import _revision
from .needs_action_store import NeedsActions

BASIS = 'lio-date-convert.1'

def unknown(request):
    return dict(version='TRIP-date-convert-receipt.1', action_id=request.action_id, trip_id=request.trip_id,
        original_version=request.expected_version, original_hash=request.original_hash, outcome='unknown',
        committed=None, trip_version=None, content_sha256=None, calendar=None, date_checks=None, conflicts=[])


def _provisional(day_count):
    return [dict(kind=k, state='unknown', day_indices=list(range(1, day_count+1)), item_ids=[],
        reason='date_evidence_pending', evidence_refs=[]) for k in ('weather', 'day_opening')]


def _time_conflicts(content):
    return [dict(kind='date_dependent', code=c.code, day_indices=[], item_ids=[],
        reason='requested calendar makes the declared interval inconsistent',
        evidence_refs=['trip-content:'+sha256(content).hexdigest()])
        for c in evaluate(content).checks if c.code in ('ITEM_TIME_REVERSED', 'ITEM_RELATIVE_REVERSED')]


def query(repository, request):
    """Protected caller supplies the same exact original input, never a new action."""
    with repository.transaction() as cursor:
        receipt = NeedsActions._previous(repository, cursor, request)
        if receipt is None:
            return None
        proposal, _, status = repository._proposal(cursor, receipt.proposal_id)
        if (proposal.basis_version != BASIS or proposal.trip_id != request.trip_id
                or proposal.expected_version != request.expected_version):
            raise Denied('original conversion association unavailable')
        document = json.loads(proposal.content)
        if receipt.kind == 'accept':
            if status != 'accepted' or receipt.committed_version != request.expected_version+1:
                raise Denied('original conversion receipt inconsistent')
            original = _revision(repository, cursor, request.trip_id, request.expected_version)
            before = json.loads(original.content)
            if (sha256(original.content).hexdigest() != request.original_hash
                    or any(document[k] != before[k] for k in ('items', 'sources', 'title', 'content_version'))):
                raise Denied('committed conversion changed original protected content')
            return dict(version='TRIP-date-convert-receipt.1', action_id=request.action_id, trip_id=request.trip_id,
                original_version=request.expected_version, original_hash=request.original_hash,
                outcome='converted', committed=True, trip_version=receipt.committed_version,
                content_sha256=sha256(proposal.content).hexdigest(), calendar=document['calendar'],
                date_checks=document['date_checks'], conflicts=list(check_conflicts(document['date_checks'])))
        if status != 'rejected' or sha256(proposal.content).hexdigest() != request.original_hash:
            raise Denied('original rejected conversion inconsistent')
        cursor.execute('SELECT source_input,source_sha256 FROM cj_trip_needs_basis WHERE scope=%s AND proposal_id=%s',
                       (repository.scope, proposal.proposal_id))
        row = cursor.fetchone()
        if row is None or sha256(bytes(row[0])).hexdigest() != row[1]:
            raise Denied('original rejected conversion source unavailable')
        source = json.loads(bytes(row[0]))
        snapshot = decode_snapshot(base64.b64decode(source['snapshot'], validate=True))
        transformed = converted_content(document, request.start_date, _provisional(len(document['days'])),
                                        snapshot.fields.get('fixed_items', ()))
        conflicts = list(transformed.conflicts) if transformed.content is None else _time_conflicts(transformed.content)
        if not conflicts:
            raise Denied('original conversion conflict evidence unavailable')
        return dict(version='TRIP-date-convert-receipt.1', action_id=request.action_id, trip_id=request.trip_id,
            original_version=request.expected_version, original_hash=request.original_hash, outcome='conflict',
            committed=False, trip_version=None, content_sha256=None, calendar=document['calendar'],
            date_checks=document['date_checks'], conflicts=conflicts)

