# Project Handoff

> Generated from `docs/handoff.json`. Edit the JSON source, then run
> `npm run handoff:render` or the installed Skill's `scripts/handoff.js render --project .`.
> This file is the fast human/agent entry point; repository files, git, and external systems remain authoritative.

## Five-Minute Takeover

1. Run `pwd` and `git status --short --branch`; preserve unrelated work.
2. Open the accepted Issue and read the mandatory files below in order.
3. Confirm the objective, assumptions, frozen decisions, blockers, and rollback before editing.
4. Re-run the most relevant recorded check or the resume command before extending the diff.
5. Execute only the next action below; update the JSON, this file, and verification evidence before stopping.

## Snapshot

| Field | Current value |
| --- | --- |
| Objective | Deliver G2C (foreign-visitor China travel assistant, iOS + CJ Agent backend) to invited beta via one real end-to-end path first; P0 makes the repository self-sufficient for takeover and makes CI the only source of green. |
| Status | active |
| Phase | P1-structure (PR open) -> P2-walking-skeleton |
| Accepted Issue | CJ-005 (https://github.com/JTCAO515/G2C/issues/5); P0 scope per docs/dispatch/P0-repo-hygiene.md |
| Owner | JT (operator); Claude architecture/review; Codex implementation |
| Last updated | 2026-10-27T06:00:00Z |

## Active Work

- P1 structure convergence on branch chore/p1-structure (PR pending CI).

## Accepted Assumptions

- Static review only at main 8fac0dff5e50ce08c277b65f7322a4ea64d77e65; pytest and swift test were not run (UNRUN).
- Inference to verify: delivery slowness comes mainly from process and in-repo composition overhead, not technical difficulty.
- ADR-0002 technology stack (AgentScope, DBOS, ReMe, Supabase Auth) remains candidate, not verified in combination.

## Frozen Decisions

- accepted: ADR-0001 product and user-control boundaries.
- accepted: model qwen3.8-flash with Beijing endpoint profile (spikes/runtime/REPORT.md); real calls still UNRUN.
- accepted (JT 2026-10-27): ADR-0004 delivery flow and repo hygiene, items 1-7.
- accepted (JT 2026-10-27): repository stays PUBLIC; local-path removal is mandatory.
- accepted (JT 2026-10-27): evidence moves out of repo and in-repo sha256 pins are removed, both executed in P1; no history rewrite.
- accepted (JT 2026-10-27): P2 scope Beijing single city, email OTP primary login, minimum iOS 17.
- accepted (JT 2026-10-27): process simplification, one PR per Issue slice, CI green plus one independent review, trunk-based.
- implemented (P1): single distribution `cj` keeps per-domain import names (cj_auth, ...) instead of renaming to cj.* subpackages.
- implemented (P1): domain tables stay in schema public; cj holds the migration ledger. Moving tables into cj is open.
- implemented (P1): historical evidence archived at tag evidence-archive-2026-10-27 (87120f9).

## Changed Files

| Path | Reason |
| --- | --- |
| `backend/cj_api/*.py` | Plain imports via MODULE_SETS; hash pins removed. |
| `pyproject.toml, uv.lock` | Single cj distribution; domain pyproject/uv.lock removed. |
| `scripts/test.py, scripts/pg_suites.py, scripts/migrate.py, scripts/check.sh` | Unified test, PostgreSQL suite and migration entry points. |
| `backend/migrations/` | Ordered manifest 1-10 with down files; README. |
| `backend/**/tests (selected)` | Working-tree instead of git exports; configurable PG bindir; drift fixes. |
| `**/evidence/ (1836 files)` | Untracked; archived at tag evidence-archive-2026-10-27. |
| `ios/Sources/CJProbeUI/ProbeView.swift` | Rename nested enum State to ProbeState. |
| `.github/workflows/ci.yml` | python, postgres, swift jobs, all blocking. |
| `README.md, backend/README.md, docs/engineering.md, docs/evidence.md, docs/adr/0004` | Docs for the new structure. |

## Verification Evidence

| Status | Command | Result | Artifact |
| --- | --- | --- | --- |
| pass | `uv run --locked python -B scripts/test.py` | 56/56 groups locally (Python 3.14.7). feasibility solver test is timing-sensitive under heavy host load. | — |
| pass | `uv run --locked python -B scripts/pg_suites.py` | All 9 groups locally on Homebrew PostgreSQL 16/17: migrations, message, run, needs, trip, feasibility, memory_management, memory, domain_runners. | — |
| pass | `scripts/migrate.py verify` | Versions 1-10 up, down to empty, up again (24 tables) on PG16 and PG17. | — |
| not-run | `swift test (ios root package)` | Local host has only CommandLineTools (no SwiftUI/Testing macro plugins); verified in CI swift job. | — |
| not-run | `GitHub Actions ci.yml (python, postgres, swift)` | Read from the P1 PR checks. | — |

## Blockers

No blockers recorded.

## Next Smallest Action

- Action: After the P1 PR is merged with green CI, write docs/dispatch/P2-walking-skeleton.md: CJ-007 email OTP -> CJ-009 message -> CJ-010 SSE stream with qwen3.8-flash -> CJ-014 draft -> CJ-015 accept into formal Trip, Beijing, zh+en, iOS 17 App wired to ShellView.
- Expected observation: P2 dispatch reviewed by JT; real provider and auth calls scoped with explicit authorization.
- Resume command: `gh pr checks --repo JTCAO515/G2C`

## Rollback

git revert the merge commit of this PR; documentation only, no data, credentials or external resources touched.

## Mandatory Reading Order

1. [HANDOFF.md](HANDOFF.md)
2. [docs/adr/0004-delivery-flow-and-repo-hygiene.md](docs/adr/0004-delivery-flow-and-repo-hygiene.md)
3. [backend/README.md](backend/README.md)
4. [backend/migrations/README.md](backend/migrations/README.md)
5. [README.md](README.md)
6. [AGENTS.md](AGENTS.md)

## Integrity Check

```bash
npm run handoff:check
npm run docs:check
```
