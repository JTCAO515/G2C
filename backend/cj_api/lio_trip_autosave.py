"""Chat autosave switch (ADR-0012, #1994 T-1), behind CJ_LIO_TRIP_AUTOSAVE.

`off` (the default) changes nothing: no Lio write is compared, no receipt effect is written and the
v4 undo routes stay unregistered in the Hong Kong host. `on` turns autosave on only for the accounts in
CJ_LIO_ANSWER_LAYOUT_SUBJECTS_JSON (LIO-answer-rich.1 "Switch": no new list variable), read through the
layout switch's own validation, so the list is in force only while CJ_LIO_ANSWER_LAYOUT is `one-screen`.
Any other value of either variable reads as off and writes one audit line; it never fails a worker.
"""
import logging
import os

SWITCH = 'CJ_LIO_TRIP_AUTOSAVE'
MODES = ('off', 'on')
_audit = logging.getLogger('cj_usage.audit')


def autosave_mode():
    value = os.environ.get(SWITCH, 'off')
    if value not in MODES:
        _audit.warning('LIO_TRIP_AUTOSAVE_INVALID value_length=%d mode=off', len(value))
        return 'off'
    return value


def autosave_subjects():
    """The accounts autosave is on for; empty while the switch is off or the list is unusable."""
    if autosave_mode() != 'on':
        return frozenset()
    from .lio_answer_layout import subjects
    try:
        return subjects()
    except ValueError as error:
        _audit.warning('LIO_TRIP_AUTOSAVE_SUBJECTS_INVALID error=%s mode=off', type(error).__name__)
        return frozenset()


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
