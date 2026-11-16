"""Run C's unchanged publisher components with their explicit preview host.

The production-factory matrix runs separately with the real default. These
components supply their own plan through the old preview hook; selecting that
host here does not bypass any source, writer, receipt or withdrawal assertion.
"""
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'backend/cj_api/tests'),
                str(ROOT / 'backend/draft/tests')]
import run_worker

SCRIPTS = ('rich_selection_pg.py', 'rich_selection_undo_pg.py')


def main(script):
    if script not in SCRIPTS:
        raise ValueError('explicit rich publisher component required')
    original = run_worker.run_once

    def component(*args, **kwargs):
        return original(*args, **kwargs, lio_generation_factory=lambda: None)

    with patch.object(run_worker, 'run_once', component):
        runpy.run_path(str(ROOT / 'backend/draft/tests' / script), run_name='__main__')


if __name__ == '__main__':
    main(sys.argv[1])
