#!/usr/bin/env python3
"""Render/check HANDOFF.md from docs/handoff.json using only the standard library."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def render(data):
    def cell(value):
        return str(value).replace('|', r'\|').replace('\n', '<br>')

    lines = [
        '# Project Handoff', '',
        '> Generated from `docs/handoff.json`; edit the JSON, not this file.',
        '> Run `python3 -B scripts/handoff.py render`, then `python3 -B scripts/handoff.py check`.',
        '> Repository files, Git, Issue and CI state remain authoritative.', '',
        '## Five-Minute Takeover', '',
        '1. Run `git fetch origin` and `git status --short --branch`; preserve unrelated work.',
        '2. Read the mandatory files below in order.',
        '3. Check open PRs and their exact-head CI before extending the current slice.',
        '4. Execute only the next action; keep external-resource authorization separate.',
        '5. Update the JSON and render this file before stopping.', '',
        '## Snapshot', '', '| Field | Current value |', '| --- | --- |',
    ]
    for label, key in [('Objective', 'objective'), ('Status', 'status'), ('Phase', 'currentPhase'),
                       ('Accepted Issue', 'acceptedIssue'), ('Owner', 'owner'),
                       ('Last updated', 'lastUpdated')]:
        lines.append(f'| {label} | {cell(data[key])} |')
    for heading, key in [('Active Work', 'activeWork'), ('Accepted Assumptions', 'assumptions'),
                         ('Frozen Decisions', 'decisions'), ('Architecture Contracts', 'architectureContracts')]:
        lines += ['', f'## {heading}', ''] + [f'- {v}' for v in data[key]]
    lines += ['', '## Changed Files', '', '| Path | Reason |', '| --- | --- |']
    lines += [f'| `{cell(v["path"])}` | {cell(v["reason"])} |' for v in data['changedFiles']]
    lines += ['', '## Verification Evidence', '', '| Status | Command | Result | Artifact |', '| --- | --- | --- | --- |']
    for v in data['verification']:
        lines.append(f'| {cell(v["status"])} | `{cell(v["command"])}` | {cell(v["summary"])} | {cell(v["artifact"] or "—")} |')
    for heading, key in [('Blockers', 'blockers'), ('Risks', 'risks'), ('Operator Actions', 'operatorActions')]:
        lines += ['', f'## {heading}', ''] + ([f'- {v}' for v in data[key]] or ['None recorded.'])
    action = data['nextAction']
    lines += ['', '## Next Smallest Action', '', f'- Action: {action["description"]}',
              f'- Expected observation: {action["expectedObservation"]}',
              f'- Resume command: `{action["command"]}`', '', '## Rollback', '', data['rollback'],
              '', '## Mandatory Reading Order', '']
    lines += [f'{i}. [{p}]({p})' for i, p in enumerate(data['mandatoryReadingOrder'], 1)]
    lines += ['', '## Integrity Check', '', '```bash', 'python3 -B scripts/handoff.py check', '```', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('render', 'check'))
    args = parser.parse_args()
    data = json.loads((ROOT / 'docs/handoff.json').read_text())
    if data['readingOrder'] != data['mandatoryReadingOrder']:
        raise SystemExit('handoff reading orders differ')
    for path in data['mandatoryReadingOrder']:
        if not (ROOT / path).is_file():
            raise SystemExit(f'missing mandatory reading: {path}')
    content = render(data)
    target = ROOT / 'HANDOFF.md'
    if args.command == 'render':
        target.write_text(content)
        print('HANDOFF.md rendered')
    elif target.read_text() != content:
        raise SystemExit('HANDOFF.md is stale; run python3 -B scripts/handoff.py render')
    else:
        print('HANDOFF.md matches docs/handoff.json; mandatory reading exists')


if __name__ == '__main__':
    main()
