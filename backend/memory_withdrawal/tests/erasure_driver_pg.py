"""Signed composition2 waits before first dispatch; UNKNOWN stays read only."""
import os,tempfile
from pathlib import Path
from erasure_api_pg import exercise

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='c-erasure-driver-') as folder:
        exercise(Path(folder),Path(os.environ['CJ_E2E_CONNINFO']),composition=2)
    print('PASS actual signed composition2: busy preflight leaves every original step pending with zero execute, ready original POST dispatches once; subsequent UNKNOWN only reconciles, no hook retry or second Memory lock')
