"""Run experiments on new private PG; append-only report per invocation."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import time
import traceback

from runtime import ROOT, private_database


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--only', nargs='+')
    args = parser.parse_args()
    # Refuse overwriting prior FAIL/UNKNOWN evidence.
    args.output.mkdir(parents=True, exist_ok=False)
    from isolation import EXPERIMENTS
    experiments = EXPERIMENTS
    if args.only:
        unknown = set(args.only) - {row[0] for row in experiments}
        if unknown:
            parser.error('unknown experiment: ' + ', '.join(sorted(unknown)))
        experiments = [row for row in experiments if row[0] in args.only]
    report = dict(commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
                  environment=dict(python=platform.python_version(), platform=platform.platform(),
                                   database='fresh private Unix socket PG / cj_m1_runtime',
                                   provider='FakeProvider only', external_calls=0), experiments=[])
    for name, run, trigger, expected in experiments:
        row = dict(id=name, trigger=trigger, expected=expected,
                   started_at=datetime.now(timezone.utc).isoformat())
        start = time.monotonic()
        try:
            with private_database(name):
                row['actual'] = run()
            row['status'] = 'PASS'
        except Exception:
            row.update(status='FAIL', actual={'traceback': traceback.format_exc()})
        row['elapsed_seconds'] = time.monotonic() - start
        report['experiments'].append(row)
        (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(name, row['status'], flush=True)
    return int(any(row['status'] != 'PASS' for row in report['experiments']))


if __name__ == '__main__':
    raise SystemExit(main())
