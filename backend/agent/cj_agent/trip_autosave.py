"""Receipt effects around one Lio trip publication (ADR-0012 decision 8, LIO-answer-rich.1 "Stored").

Every Lio trip write reaches `worker._step(binding, publish, 'trip_proposal:'…, draft=True)` with the
Lio publisher as `worker.drafts`. Its call sites wrap that step with :func:`publish`. With the write's
repository autosave off (the default) this is exactly the step. With it on, the intent
`{"action_id":…,"status":"unknown"}` is committed as its own RUN event before the step (outside the
trip lock), then `saved` after it, or `not_saved` when the step refused before any commit. A step that
ends any other way (commit unknown, budget, cancellation) leaves the intent: the reader then trusts only
cj_trip_receipt. A receipt write that fails is logged and never fails the answer.
"""
import logging

from cj_message.lio_trip_receipt import effect

_audit = logging.getLogger('cj_usage.audit')


def _enabled(repository):
    from cj_trip.autosave import enabled
    return repository is not None and enabled(repository)


def reason(error):
    """The contract reason of a refused write, or None: version conflict, protected points, too large."""
    from cj_trip.autosave import AutosaveConflict, WithdrawnConflict
    from cj_trip.domain import Conflict
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, AutosaveConflict):
            return 'too_large' if error.code == 'too_large' else 'protected'
        if isinstance(error, WithdrawnConflict) or (isinstance(error, Conflict) and error.args == ('trip version conflict',)):
            return 'conflict'
        error = error.__cause__ or error.__context__
    return None


def _write(worker, binding, state, action_id, status, reason=None):
    try:
        value = effect(action_id, status, reason)
    except ValueError:
        _audit.info('LIO_RICH_EFFECT_DROPPED run_id=%s effect=lio_trip_receipt', binding.run_id)
        return state
    try:
        return worker._event(binding, state, 'effect_committed', value)
    except Exception as error:
        _audit.info('LIO_TRIP_RECEIPT_UNAVAILABLE run_id=%s status=%s error=%s', binding.run_id, status,
                    type(error).__name__)
        try:
            return worker.runs.snapshot(binding)
        except Exception:
            return state


def publish(worker, binding, repository, action_id, step):
    """`step()` returns `(state, result)` like `worker._step`; so does this."""
    if not _enabled(repository):
        return step()
    from cj_agent.draft import DraftRejected
    from cj_trip.structured import FieldRejected
    _write(worker, binding, worker.runs.snapshot(binding), action_id, 'unknown')
    try:
        state, result = step()
    except (DraftRejected, FieldRejected) as error:
        # Refused before the commit (the sole commit point raises before any Trip write).
        _write(worker, binding, worker.runs.snapshot(binding), action_id, 'not_saved', reason(error))
        raise
    return _write(worker, binding, state, action_id, 'saved'), result
