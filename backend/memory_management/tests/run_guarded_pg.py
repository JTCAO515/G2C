"""Guarded delta checks against the working-tree MEMORY module and a fresh own PG."""
from pathlib import Path
from run_private_pg import main

ROOT = Path(__file__).resolve().parents[1]


def run():
    main(checks_file=ROOT/'tests/guarded_checks.py',
         label='CJ019 guarded delta / working-tree MEMORY / synthetic AUTH and real private PG')


if __name__ == '__main__':
    run()
