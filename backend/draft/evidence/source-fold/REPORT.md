# Exact source representation repair — author evidence

Parent candidate: `da88ed88800f8da85b6b1cb3967fda200e0d0116` (HOLD).
No rebase or upstream change. Only the existing two CJ014 write directories.

Review's exact `probe_source_fold.py` was copied unchanged from
`cj-review/CJ014-da88ed8/`; `before.txt` reproduces acceptance of a nonoriginal
MEMORY timestamp. It exits 0 because the original probe asserts the bug exists:
01:30 -04:00 and 01:30 -05:00 are different instants but datetime/dataclass
equality treats their source records as equal. This is the preserved original
semantic FAIL, not a successful acceptance check.

Minimal source fix: explicit original-record serialization is now used for both
SourceLink membership and evidence-reference conflict comparison. MEMORY time
representation includes wall time to microseconds, numeric offset, fold, and
timezone identity. No UTC conversion or inferred timestamp is introduced.
Request input manifests use that same representation so a fold-only change at
an otherwise equal UTC timestamp cannot hide behind isoformat equality. Only
stdlib naive/fixed-offset/ZoneInfo representations are supported; other tzinfo
implementations fail explicitly. NEEDS original source bytes and MEMORY command
raw UTF8 spelling are preserved, and inconsistent command fields are refused.

`after.txt` replays the unchanged Review probe. Exit 1 is the expected refusal:
`InvalidInput: source is absent from exact bound original inputs`, before any
result is returned. Its bug-success assertions are no longer reached.

Author tests: **29 PASS** in `final-tests.txt` on existing Python 3.14.7. The old
23 tests are retained; six neighboring cases cover different-instant DST folds,
same-instant different offset/zone/name, fold-only input changes with identical
ISO text, changed offset input binding, alternate raw JSON UTF8 spelling and
unmatched command fields, plus expiry just before/after the original bound.
The original unmodified fold source remains accepted for local UNKNOWN review.
Old logs including the Python 3.9 import failure are preserved.

Commands, from task root:

```sh
env PYTHONPATH=backend/draft:backend/draft/tests:backend/trip:backend/needs:backend/memory:backend/feasibility:backend/auth /opt/homebrew/bin/python3.14 backend/draft/evidence/source-fold/probe_source_fold.py
env PYTHONPATH=backend/draft:backend/trip:backend/needs:backend/memory:backend/feasibility:backend/auth /opt/homebrew/bin/python3.14 -m unittest discover -s backend/draft/tests -v
```

`input-manifest.json` records source hashes and rechecks actual canonical imports
against original fixed base `8ea1b35756726f60727f10deaf157c40b8df1072`.
No upstream files changed, dependency installation, DB, provider, model, secrets,
network listener or remote write. Production generation/persistence/publication
remain closed. Independent Review/Testing and CI are **UNRUN** on the repair;
original candidate remains HOLD until the existing independent gates pass.
