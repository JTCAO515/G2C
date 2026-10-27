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
| Phase | P0-repo-hygiene |
| Accepted Issue | CJ-005 (https://github.com/JTCAO515/G2C/issues/5); P0 scope per docs/dispatch/P0-repo-hygiene.md |
| Owner | JT (operator); Claude architecture/review; Codex implementation |
| Last updated | 2026-10-27T04:00:00Z |

## Active Work

- P0 repo hygiene and minimal CI on branch chore/p0-repo-hygiene (PR pending).

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

## Changed Files

| Path | Reason |
| --- | --- |
| `.github/workflows/ci.yml` | Minimal CI: blocking python, contracts and swift jobs; informational known-failing job. |
| `.gitignore` | Stop adding evidence logs, archives and recordings. |
| `README.md` | Current status and local check commands. |
| `AGENTS.md` | Repository-only entry point and ADR-0004 working rules. |
| `docs/engineering.md` | ADR-0004 supersession note, local handoff path, tooling status rows. |
| `docs/**/*.md` | Issue links moved from JTCAO515/Go2China to JTCAO515/G2C. |
| `545 text files (*.md and evidence/**/*.json\|txt\|log)` | /Users/jtsm5p replaced with <local>; files whose sha256 or git blob hash is referenced anywhere in the repo were skipped (66), as were 7 non-evidence source files. |
| `docs/handoff.json, HANDOFF.md` | P0 state. |

## Verification Evidence

| Status | Command | Result | Artifact |
| --- | --- | --- | --- |
| pass | `pytest -q backend/tests` | 4 passed (local, Python 3.14.7). | — |
| pass | `pytest -q tests in backend/{draft,fact,feedback,manual_edit,memory_jobs,memory_withdrawal,message,place,run,usage}` | All pass locally (feedback 41 skipped without PostgreSQL); identical before and after path replacement. | — |
| pass | `pytest evaluation/cj028/tests and ops/recovery-preflight` | 35 and 15 passed. | — |
| pass | `openapi-spec-validator contracts/api/openapi.json` | OK. | — |
| blocked | `swift test (ios root package)` | Local host has only CommandLineTools: library targets compile, CJAPITests fails with 'plugin for module TestingMacros not found'. Runs in CI on macos-15 with Xcode. | — |
| fail | `unittest discover -s backend/cj_api/tests` | 40 tests, 33 errors: CompositionUnavailable 'Pinned internal dependency content mismatch' (sibling sources differ from pinned hashes on main). P1 removes pins. | — |
| fail | `pytest backend/auth/tests` | 1 failed: test needs git object 8b6abb236cf10c1865a9cc8c6155bd8ac732c07e, absent from the repository. | — |
| fail | `pytest backend/cleanup/tests` | 2 failed: AssertionError 23 != 21. | — |
| blocked | `pytest backend/{needs,trip,feasibility}/tests` | Need local PostgreSQL 17 installation or TRIP_TEST_SOCKET; errors without it. | — |
| not-run | `backend/{memory,memory_management} *_checks.py` | Custom check scripts, not pytest-discoverable; fold into CI in P1. | — |
| not-run | `GitHub Actions ci.yml` | Result to be read from the P0 PR checks. | — |

## Blockers

No blockers recorded.

## Next Smallest Action

- Action: Merge the P0 PR once CI is green, then write docs/dispatch/P1-structure.md (single cj package, remove hash pins, move existing evidence out, ordered migrations with up/down in CI, fold known-failing suites into blocking CI).
- Expected observation: P0 merged on main with green blocking CI; P1 dispatch reviewed by JT.
- Resume command: `gh pr checks --repo JTCAO515/G2C`

## Rollback

git revert the merge commit of this PR; documentation only, no data, credentials or external resources touched.

## Mandatory Reading Order

1. [HANDOFF.md](HANDOFF.md)
2. [docs/adr/0004-delivery-flow-and-repo-hygiene.md](docs/adr/0004-delivery-flow-and-repo-hygiene.md)
3. [docs/dispatch/P0-repo-hygiene.md](docs/dispatch/P0-repo-hygiene.md)
4. [README.md](README.md)
5. [AGENTS.md](AGENTS.md)
6. [docs/engineering.md](docs/engineering.md)

## Integrity Check

```bash
npm run handoff:check
npm run docs:check
```
