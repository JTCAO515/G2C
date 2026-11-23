"""Closed-by-default HK composition for the ECB reference-rate route."""

import json
import os
from pathlib import Path
import stat

from cj_api.currency_tools import CurrencyRates, register_currency_route
from cj_api.local_account_admission_v2 import account_checker_for
from cj_api.plugin_tools import PluginCalls

from .configuration import ECB_INTERNAL_SUBJECTS
from .plugin_roster import generate_plugin_subjects


STATE = Path('/plugin-state/ecb.sqlite')


def configured_reference_subjects(raw):
    values = json.loads(raw)
    if type(values) is not list or not values or any(type(subject) is not str for subject in values):
        raise ValueError('explicit internal currency roster required')
    roster = frozenset(values)
    if len(roster) != len(values) or not roster.issubset(generate_plugin_subjects()):
        raise ValueError('currency roster must use original internal subjects')
    return roster


def register_runtime_currency(app, auth, database, *, state=STATE):
    raw = os.environ.get(ECB_INTERNAL_SUBJECTS)
    if raw is None:
        register_currency_route(app)
        return
    try:
        roster = configured_reference_subjects(raw)
        directory, entry = state.parent.lstat(), state.lstat()
        if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid()
                or stat.S_IMODE(directory.st_mode) != 0o700
                or not stat.S_ISREG(entry.st_mode) or entry.st_uid != os.getuid()
                or stat.S_IMODE(entry.st_mode) != 0o600 or entry.st_nlink != 1):
            raise ValueError('ECB quota state requires owned private files')
    except (OSError, RecursionError, ValueError):
        register_currency_route(app)
        return
    checker = account_checker_for(auth, database, selected_subjects=roster)
    register_currency_route(app, currency=CurrencyRates(state), checker=checker, internal=roster,
                            calls=PluginCalls(state, require_existing=True))
