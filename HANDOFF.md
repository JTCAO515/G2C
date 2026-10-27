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
| Phase | P2b draft to formal Trip (PR open) -> P2c identity and iOS |
| Accepted Issue | CJ-014 / CJ-015 (P2b); plan in docs/dispatch/P2-walking-skeleton.md |
| Owner | JT (operator); Claude architecture/review; Codex implementation |
| Last updated | 2026-10-27T11:00:00Z |

## Active Work

- P2b on branch feat/p2b-draft-to-trip (PR pending CI).

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
| `backend/agent/cj_agent/draft.py` | Model JSON -> canonical pending TRIP document -> trusted publish. |
| `backend/agent/cj_agent/worker.py, provider.py` | consider_trip drafts via a second model call; system prompt parameter. |
| `backend/cj_api/local_app.py` | TRIP routes, derived TRIP scope, local confirmation. |
| `backend/agent/tests/*, scripts/run_worker.py, scripts/provider_smoke.py` | Draft tests, e2e draft->accept/reject, real provider smoke. |
| `docs/dispatch/P2-walking-skeleton.md, backend/README.md` | P2b record and usage. |

## Verification Evidence

| Status | Command | Result | Artifact |
| --- | --- | --- | --- |
| pass | `uv run --locked python -B scripts/test.py` | 56/56 groups incl. 18 agent tests (provider + draft). | — |
| pass | `uv run --locked python -B scripts/pg_suites.py` | 11/11 groups; e2e 5/5 incl. draft -> accept -> formal Trip v1 read back, reject -> no Trip, foreign user refused, replay idempotent, double accept 409, invalid model draft -> no proposal. | — |
| pass | `scripts/provider_smoke.py (DashScope qwen3.8-flash, Beijing endpoint)` | 4/4 real requests: zh/en streamed answers, zh/en drafts valid as TRIP proposals (2026-10-27). | — |
| not-run | `GitHub Actions ci.yml` | Read from the P2b PR checks. | — |

## Blockers

No blockers recorded.

## Next Smallest Action

- Action: After P2b merges: P2c - iOS 17 App main target wired to ShellView calling P2a/P2b endpoints (local dev token first), then Supabase email OTP once the operator authorizes a test project.
- Expected observation: Simulator: send a zh/en message, see streamed answer, accept a draft, see the formal trip.
- Resume command: `gh pr checks --repo JTCAO515/G2C`

## Rollback

git revert the merge commit of this PR; documentation only, no data, credentials or external resources touched.

## Mandatory Reading Order

1. [HANDOFF.md](HANDOFF.md)
2. [docs/dispatch/P2-walking-skeleton.md](docs/dispatch/P2-walking-skeleton.md)
3. [docs/adr/0004-delivery-flow-and-repo-hygiene.md](docs/adr/0004-delivery-flow-and-repo-hygiene.md)
4. [backend/README.md](backend/README.md)
5. [README.md](README.md)
6. [AGENTS.md](AGENTS.md)

## Integrity Check

```bash
npm run handoff:check
npm run docs:check
```
