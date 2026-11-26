"""Classify a pull request's changed paths for ci.yml (JT approved 2026-11-24, #1445).

Reads `git -c core.quotePath=false diff --name-only --no-renames -z BASE...HEAD` (NUL- or
newline-separated) from stdin and prints GitHub step outputs. Only pull requests are
classified; main pushes always run every job, and any error here prints nothing, so every job
still runs (fail open). A C-quoted path is treated as unknown and also runs every job.

- docs_only:   every path is documentation -> heavy jobs skip (python keeps the handoff check).
- ios_only:    every path is under ios/ or documentation, at least one under ios/ ->
               the PostgreSQL shards skip; python, swift-packages and swift run.
- web_only:    every path is the website (web/), its offline checks (scripts/test_web_*) or
               documentation, at least one website path -> the PostgreSQL shards skip; python
               (which runs the website's node and Python checks) and swift-packages run, and swift
               follows app_changed as before (2026-11-26, the coordinating thread per JT's
               pre-authorization: the website is a static site plus Vercel functions that no
               backend test or App build reads). Any other path runs every job.
               scripts/test_web_* is reserved for the website's offline checks: a script there
               must not read backend/, deploy/ or the App, or a website-only pull request would
               skip the shards that test what it reads.
- app_changed: some path can affect the Swift packages or the App build -> swift (the one macOS
               job: App build and package tests) runs; when false it skips. Swift tests read
               contracts/ and digital-assets/,
               the package inventory lives in .github/, .gitattributes changes checkouts, and
               tooling/release/ holds the flag list and script of the Beta build step (#1762).
"""
import re
import sys

DOCS = re.compile(r'^(docs/|HANDOFF\.md$)')
IOS_OR_DOCS = re.compile(r'^(ios/|docs/|HANDOFF\.md$)')
WEB = re.compile(r'^(web/|scripts/test_web_[^/]+$)')
WEB_OR_DOCS = re.compile(r'^(web/|scripts/test_web_[^/]+$|docs/|HANDOFF\.md$)')
APP = re.compile(r'^(ios/|contracts/|digital-assets/|\.github/|tooling/release/|\.gitattributes$)')


def split(data):
    return data.split('\0') if '\0' in data else data.splitlines()


def classify(paths):
    paths = [p for p in paths if p]  # no strip: a name with edge spaces is its own path
    if not paths:
        raise ValueError('no changed paths')
    flag = lambda value: 'true' if value else 'false'
    if any(p.startswith('"') for p in paths):
        # A C-quoted path cannot be classified reliably: run every job.
        return {'docs_only': 'false', 'ios_only': 'false', 'web_only': 'false', 'app_changed': 'true'}
    return {
        'docs_only': flag(all(DOCS.match(p) for p in paths)),
        'ios_only': flag(all(IOS_OR_DOCS.match(p) for p in paths) and any(p.startswith('ios/') for p in paths)),
        'web_only': flag(all(WEB_OR_DOCS.match(p) for p in paths) and any(WEB.match(p) for p in paths)),
        'app_changed': flag(any(APP.match(p) for p in paths)),
    }


def main():
    outputs = classify(split(sys.stdin.read()))
    sys.stdout.write(''.join(f'{key}={value}\n' for key, value in outputs.items()))


if __name__ == '__main__':
    main()
