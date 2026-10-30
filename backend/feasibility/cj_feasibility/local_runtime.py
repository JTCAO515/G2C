"""Explicit local FEAS consumer of B's frozen manual NEEDS runtime.

No writer, resolver policy, alternative AUTH or dispatch permission is added.
"""
import os
from pathlib import Path

from cj_api.composition import CompositionUnavailable
from cj_api.local_app import LocalDatabase
from cj_api.local_needs import protected_reader
from cj_api.local_worker_context import checker_for
from .formal_current import CurrentFormalNeedsRead,FormalReadLimits


def current_reader(*,conninfo_path,auth_dir,limits,run_context=None):
    if os.environ.get('CJ_ENV')!='local' or type(limits) is not FormalReadLimits:
        raise CompositionUnavailable('explicit bounded local FEAS current reader required')
    database=LocalDatabase(conninfo_path,run_context=run_context,needs_context=True)
    return CurrentFormalNeedsRead(protected_reader(database,checker_for(Path(auth_dir))),limits)
