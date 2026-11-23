"""Hong Kong composition for the closed-by-default taxi routes."""

import logging
import os
from pathlib import Path
import stat

from cj_api.didi_mcp import DiDiMCPTransport
from cj_api.local_account_admission_v2 import account_checker_for
from cj_api.plugin_tools import PluginCalls
from cj_api.taxi_tools import DiDiInformation, TaxiService, register_taxi_routes

from .configuration import DIDI_MCP_KEY, TAXI_INTERNAL_SUBJECTS
from .plugin_roster import configured_plugin_subjects


COUNTS = Path('/plugin-state/taxi.sqlite')
_LOGGER = logging.getLogger(__name__)


def register_runtime_taxi(app, auth, database, *, counts_path=COUNTS):
    key = os.environ.get(DIDI_MCP_KEY)
    raw_roster = os.environ.get(TAXI_INTERNAL_SUBJECTS)
    if key is None or raw_roster is None:
        register_taxi_routes(app)
        return

    try:
        roster = configured_plugin_subjects(raw_roster)
        parent = counts_path.parent.lstat()
        entry = counts_path.lstat()
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
                or stat.S_IMODE(parent.st_mode) != 0o700
                or not stat.S_ISREG(entry.st_mode) or entry.st_uid != os.getuid()
                or stat.S_IMODE(entry.st_mode) != 0o600 or entry.st_nlink != 1):
            raise ValueError('taxi_quota_state_requires_owned_private_files')
        provider = DiDiInformation(DiDiMCPTransport(key))
    except (OSError, ValueError):
        _LOGGER.warning('ALERT taxi_configuration_unavailable')
        register_taxi_routes(app)
        return

    checker = account_checker_for(auth, database, selected_subjects=roster)
    register_taxi_routes(app, taxi=TaxiService(provider), checker=checker, internal=roster,
                         calls=PluginCalls(counts_path))
