"""Classify a pull request's changed paths for ci.yml (JT approved 2026-11-24, #1445).

Reads `git diff --name-only --no-renames BASE...HEAD` from stdin and prints GitHub step
outputs. Only pull requests are classified; main pushes always run every job, and any error
here prints nothing, so every job still runs (fail open).

- docs_only:   every path is documentation -> heavy jobs skip (python keeps the handoff check).
- ios_only:    every path is under ios/ or documentation, at least one under ios/ ->
               the four PostgreSQL shards skip; python, swift-packages, swift and ios-app run.
- app_changed: some path can affect the Swift packages or the App build -> swift and ios-app
               run; when false they skip. Swift tests read contracts/ and digital-assets/,
               the package inventory lives in .github/, and .gitattributes changes checkouts.
"""
import re
import sys

DOCS = re.compile(r'^(docs/|HANDOFF\.md$)')
IOS_OR_DOCS = re.compile(r'^(ios/|docs/|HANDOFF\.md$)')
APP = re.compile(r'^(ios/|contracts/|digital-assets/|\.github/|\.gitattributes$)')


def classify(paths):
    paths = [p for p in (line.strip() for line in paths) if p]
    if not paths:
        raise ValueError('no changed paths')
    flag = lambda value: 'true' if value else 'false'
    return {
        'docs_only': flag(all(DOCS.match(p) for p in paths)),
        'ios_only': flag(all(IOS_OR_DOCS.match(p) for p in paths) and any(p.startswith('ios/') for p in paths)),
        'app_changed': flag(any(APP.match(p) for p in paths)),
    }


def main():
    outputs = classify(sys.stdin.read().splitlines())
    sys.stdout.write(''.join(f'{key}={value}\n' for key, value in outputs.items()))


if __name__ == '__main__':
    main()
