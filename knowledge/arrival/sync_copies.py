"""Write the two copies of the arrival (entry) rules from their one source (#1730).

`arrival-rules.v1.json` here is the only source. The App bundles a byte-identical copy and the
Hong Kong backend reads another; neither copy is edited by hand.
`backend/fact/tests/test_arrival_rules.py` fails CI when any copy differs from the source.

Usage (from the repository root):
    python3 -B knowledge/arrival/sync_copies.py          # rewrite both copies
    python3 -B knowledge/arrival/sync_copies.py --check  # exit 1 if a copy is out of date
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'knowledge/arrival/arrival-rules.v1.json'
COPIES = (ROOT / 'ios/Modules/CJShell/Sources/CJLioUser/Resources/LioArrivalRules.v1.json',
          ROOT / 'backend/fact/cj_fact/arrival_rules.v1.json')


def stale():
    raw = SOURCE.read_bytes()
    return [path for path in COPIES if not path.is_file() or path.read_bytes() != raw]


def main(argv):
    if '--check' in argv:
        out_of_date = stale()
        for path in out_of_date:
            print(f'{path.relative_to(ROOT)} differs from {SOURCE.relative_to(ROOT)}; run knowledge/arrival/sync_copies.py',
                  file=sys.stderr)
        return 1 if out_of_date else 0
    raw = SOURCE.read_bytes()
    for path in COPIES:
        path.write_bytes(raw)
        print(f'wrote {path.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
