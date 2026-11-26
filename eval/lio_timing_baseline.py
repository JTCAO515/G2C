"""First-text baseline from content-free log lines (W2-3, #1729).

Reads exported log text (API and worker, any order, other lines ignored), joins
LIO_TIMING_ACCEPTED and LIO_TIMING by message key and reports, in milliseconds from
the API accepting the message:

  first_progress  first tool-progress effect or first visible text
  first_text      first visible answer text
  terminal        the RUN's terminal event
  queue           acceptance to worker pickup

Each value gets count, p50, p95 and max (nearest-rank). A RUN without an accepted line
(for example a message sent before the API logged acceptance) is counted as unmatched
and left out. It never calls a model or a service.

Usage:
  python -m eval.lio_timing_baseline worker.log api.log
  python -m eval.lio_timing_baseline --status completed - < combined.log
"""
import argparse
import json
import math
import re
import sys

ACCEPTED = re.compile(r'LIO_TIMING_ACCEPTED message_key=(?P<key>[0-9a-f]{16}) accepted_ms=(?P<accepted>\d+)')
RUN = re.compile(r'LIO_TIMING message_key=(?P<key>[0-9a-f]{16}) run_id=(?P<run>\S+) picked_up_ms=(?P<picked>\d+) '
                 r'started_ms=(?P<started>\d+|-) first_progress_ms=(?P<first_progress>\d+|-) '
                 r'first_text_ms=(?P<first_text>\d+|-) terminal_ms=(?P<terminal>\d+|-) '
                 r'terminal=(?P<terminal_kind>\S+) status=(?P<status>\S+)')
MEASURES = ('queue', 'first_progress', 'first_text', 'terminal')


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def parse(lines):
    accepted, runs = {}, []
    for line in lines:
        match = ACCEPTED.search(line)
        if match:
            # A retried send of the same message keeps its first acceptance.
            accepted.setdefault(match['key'], int(match['accepted']))
            continue
        match = RUN.search(line)
        if match:
            runs.append(match.groupdict())
    return accepted, runs


def summarize(lines, *, status=None):
    accepted, runs = parse(lines)
    samples = {name: [] for name in MEASURES}
    unmatched = 0
    counted = 0
    statuses = {}
    for run in runs:
        statuses[run['status']] = statuses.get(run['status'], 0) + 1
        if status is not None and run['status'] != status:
            continue
        if run['key'] not in accepted:
            unmatched += 1
            continue
        counted += 1
        queue = int(run['picked']) - accepted[run['key']]
        samples['queue'].append(queue)
        for name in MEASURES[1:]:
            if run[name] != '-':
                samples[name].append(queue + int(run[name]))
    report = dict(version='LIO-timing-baseline.1', runs=len(runs), counted=counted, unmatched=unmatched,
                  statuses=statuses, status_filter=status)
    for name, values in samples.items():
        report[name] = (dict(count=len(values), p50_ms=percentile(values, 0.5), p95_ms=percentile(values, 0.95),
                             max_ms=max(values)) if values else dict(count=0))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('logs', nargs='+', help="log files, or '-' for stdin")
    parser.add_argument('--status', help='only RUNs that ended with this worker status, e.g. completed')
    args = parser.parse_args(argv)
    lines = []
    for path in args.logs:
        if path == '-':
            lines.extend(sys.stdin)
        else:
            with open(path, encoding='utf-8', errors='replace') as handle:
                lines.extend(handle)
    json.dump(summarize(lines, status=args.status), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
