# CJ014 local review candidate

Read [internal scope and remaining seams](../../contracts/draft/README.md).
Only already-generated canonical structured results are accepted. Production
factory is closed and no source registry, candidate persistence or formal Trip
write exists. All tests use explicitly synthetic historical canonical records.

From repository root, using the already installed Python 3.14:

```sh
env PYTHONPATH=backend/draft:backend/trip:backend/needs:backend/memory:backend/feasibility:backend/auth /opt/homebrew/bin/python3.14 -m unittest discover -s backend/draft/tests -v
```

No installation, global package change, database, model, real tool, credentials
or external resources are required. The existing FEAS NEEDS evaluator is imported
directly; this slice does not load/install the solver's optional runtime.

## M1 model-ingress structure check (#168, partial)

The separate active ingress is `cj_agent.draft.DraftPublisher`. Its existing
model shape is `{title: string, items: [string, ...]}`; the host assigns item IDs
and stores canonical `cj_trip.domain.Proposal` bytes. Duplicate JSON keys
(including escaped spellings), invalid Unicode, parser nesting overflow,
unsupported fields and existing size/count violations reject the entire model
draft before repository publication. This does not change the accepted format
or the existing surrounding-prose compatibility.

`backend/agent/tests/e2e_local.py` checks the actual private-PG worker path: a
rejected draft creates no candidate, formal trip or RUN publication effect.
The already-completed chat answer remains separate from the rejected draft.

This is structural validation only. The persisted Proposal has no structured
date/time/place fields, and the model's free text is not a NEEDS declaration.
The existing FEAS evaluator requires authentic NEEDS inputs and cannot be fed
invented snapshots/revisions to claim that a draft passed travel constraints.
The time-overlap requirement and explicit end-to-end draft failure presentation
remain open on #168; no full #168 acceptance is claimed. A fixed owning mapping
and any required new contract version must be settled before that part proceeds.
