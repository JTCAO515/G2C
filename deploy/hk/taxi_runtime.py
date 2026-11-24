"""Hong Kong composition for the closed-by-default taxi routes."""

import json
import logging
import os
from pathlib import Path
import stat
from uuid import uuid4

from cj_api.didi_mcp import DiDiMCPTransport
from cj_api.local_account_admission_v2 import account_checker_for
from cj_api.plugin_tools import PluginCalls
from cj_api.taxi_tools import DiDiInformation, TaxiService, register_taxi_routes

from .configuration import DIDI_MCP_KEY, TAXI_INTERNAL_SUBJECTS
from .plugin_roster import configured_plugin_subjects


COUNTS = Path('/plugin-state/taxi.sqlite')
TRANSLATION_TIMEOUT = 12
_LOGGER = logging.getLogger(__name__)


def relay_translator(send=None):
    """English place names via the caller's own metered TRANSLATION.1 relay (M4 entry 9, #1457)."""
    if send is None:
        from .translation_relay import socket_request as send

    def translate(token, text):
        raw = json.dumps(dict(version='TRANSLATION.1', request_id=str(uuid4()), kind='text',
                              source_lang='zh', target_lang='en', text=text), ensure_ascii=False).encode()
        status, body = send(token, raw, timeout=TRANSLATION_TIMEOUT)
        if status != 200 or type(body) is not dict or body.get('version') != 'TRANSLATION.1':
            return None
        items = body.get('items')
        if (type(items) is not list or len(items) != 1 or type(items[0]) is not dict
                or items[0].get('source_text') != text or type(items[0].get('translated_text')) is not str):
            return None
        return items[0]['translated_text']
    return translate


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
    register_taxi_routes(app, taxi=TaxiService(provider, translator=relay_translator()), checker=checker, internal=roster,
                         calls=PluginCalls(counts_path, require_existing=True))
