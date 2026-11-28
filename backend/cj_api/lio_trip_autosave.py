"""Chat autosave switch (ADR-0012, #1994 T-1; own account list #2127), behind CJ_LIO_TRIP_AUTOSAVE.

`off` (the default) changes nothing: no Lio write is compared, no receipt effect is written and the
v4 undo routes stay unregistered in the Hong Kong host. `on` turns autosave on only for the accounts in
CJ_LIO_TRIP_AUTOSAVE_SUBJECTS_JSON, a list of its own: the one-screen layout list no longer turns autosave
on (putting a real person on the layout list must not start saving for them). Not set, empty or `[]`: closed
for everybody. Not valid (not JSON, not a list, a name that is not an invite-cohort account, a repeated name):
closed for everybody and one audit line. Neither it nor the layout switch can fail a worker.
"""
import json
import logging
import os

SWITCH = 'CJ_LIO_TRIP_AUTOSAVE'
SUBJECTS = 'CJ_LIO_TRIP_AUTOSAVE_SUBJECTS_JSON'
MODES = ('off', 'on')
_audit = logging.getLogger('cj_usage.audit')


def autosave_mode():
    value = os.environ.get(SWITCH, 'off')
    if value not in MODES:
        _audit.warning('LIO_TRIP_AUTOSAVE_INVALID value_length=%d mode=off', len(value))
        return 'off'
    return value


def autosave_subjects():
    """The accounts autosave is on for; empty while the switch is off, the list is not set or empty, or it is unusable."""
    if autosave_mode() != 'on':
        return frozenset()
    raw = os.environ.get(SUBJECTS)
    if raw is None or not raw.strip():
        return frozenset()
    from .lio_answer_layout import _SUBJECT   # the same invite-cohort account names as the layout list
    try:
        values = json.loads(raw)
        if (type(values) is not list or len(set(map(repr, values))) != len(values)
                or any(type(value) is not str or _SUBJECT.fullmatch(value) is None for value in values)):
            raise ValueError('autosave subjects must be distinct invite-cohort account names')
    except ValueError as error:
        _audit.warning('LIO_TRIP_AUTOSAVE_SUBJECTS_INVALID error=%s mode=off', type(error).__name__)
        return frozenset()
    return frozenset(values)


def autosave_for(scope):
    """True only for an account scope on the list while the switch is `on`; None otherwise (Repository.autosave)."""
    from .local_app import ISSUER, scope_for
    return True if scope in {scope_for(ISSUER, subject) for subject in autosave_subjects()} else None


def undo_sources(database, typed_memory):
    """The rich undo holder that makes the host register `POST /v4/lio/trip-undos` and
    `GET /v4/lio/trip-undo-receipts` (LIO-trip-undo.4) for its Lio accounts, or None while the switch is off.

    LIO-answer-rich.1 Decision 1: every autosave receipt is undone through these routes, also for
    conversations of `POST /v2/lio/messages`. Their structured.1–3 Trips go to the existing legacy and
    calendar undo; structured.4 needs this holder. All of them reach `_append_undo` and its 24 hour check.
    Off: None, so the host registers nothing new (the routes stay 404 as today)."""
    if autosave_mode() != 'on':
        return None
    from cj_memory.api_scope_hold import ApiMemoryScopeHolder
    from cj_trip.rich_undo_sources import ApiRichUndoSources
    return ApiRichUndoSources(database, ApiMemoryScopeHolder(database, typed_memory))
