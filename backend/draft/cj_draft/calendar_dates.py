"""Source-bound date conversion and original-action reconciliation, no new writer."""
from hashlib import sha256
import json

from cj_feasibility.validator import Candidate
from cj_feasibility.trip_time_v3 import evaluate
from cj_needs.revision_lease import LeaseUnavailable
from cj_trip.calendar_conversion import DateConvert, converted_content, source_window_conflicts
from cj_trip.domain import CommitUnknown, Conflict, Denied, Proposal, packed
from cj_trip.lio_history import TripHead
from .calendar_commit import commit

from cj_trip.calendar_receipts import BASIS, query, unknown, _provisional, _time_conflicts



def convert(publisher, binding, original, current, raw, capture, before_publish):
    request = DateConvert.parse(raw)
    publisher.source.check(binding, capture)
    previous = query(publisher.repository, request)
    if previous is not None:
        return previous
    context = publisher.source.contexts[binding]
    if (current is None or current != original or context is None or before_publish is None
            or (request.trip_id, request.expected_version, request.original_hash)
            != (context.trip.trip_id, context.trip.version, sha256(context.trip.content).hexdigest())):
        raise Conflict('conversion original context/version/hash mismatch')
    expected = TripHead.from_trip(context.trip)
    publisher.require_lio(binding, original, expected)
    held = publisher.source.calendar_active.get()[1]
    reference = json.loads(request.source_reference)
    root = json.loads(capture.basis.fixed_bindings)['reference']
    if reference != root or request.start_date.isoformat() != capture.basis.start_date:
        raise LeaseUnavailable('date conversion requires this original MESSAGE compiled date')
    command = publisher.source._original(held, reference)
    if (request.quote not in json.loads(command.raw)['text']
            or held.question_day(reference) != request.question_day
            or held.compiled_date(reference, request.quote, request.question_day) != request.start_date):
        raise LeaseUnavailable('date is not the protected original compiled date')
    before, _ = capture.records()
    document = json.loads(context.trip.content)
    transformed = converted_content(document, request.start_date, _provisional(len(document['days'])),
                                    before.fields.get('fixed_items', ()))
    conflicts = list(transformed.conflicts)
    if transformed.content is not None:
        conflicts += _time_conflicts(transformed.content)
        conflicts += source_window_conflicts(json.loads(transformed.content), before.fields)
    kind = 'reject' if conflicts else 'accept'
    if kind == 'reject':
        content = context.trip.content
        # Rejection stores no new formal content or invented candidate fields.
        candidate = Candidate(before.needs_id, before.version, before.content)
    else:
        result = json.loads(transformed.content)
        result['date_checks'] = publisher.date_reader.read(binding, capture, result)
        content = packed(result)
        evaluate(content)  # Validate actual read-only result shape/correlation representation.
        from .lio_calendar import needs_projection
        candidate, _ = needs_projection(result, capture, {}, context)
    proposal = Proposal('lio-date-'+sha256(request.raw).hexdigest(), request.trip_id, request.expected_version,
                        BASIS, int(publisher.clock())+300, content)
    try:
        commit(publisher, binding, original, expected, capture, candidate, proposal, request.action_id,
               before_publish, request=request, kind=kind)
    except CommitUnknown:
        return unknown(request)
    result = query(publisher.repository, request)
    if result is None:
        raise Denied('committed conversion receipt unavailable; reconcile original')
    return result
