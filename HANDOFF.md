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
| Phase | P2a walking skeleton (PR open) -> P2b draft to formal Trip |
| Accepted Issue | CJ-009 / CJ-010 / CJ-002 (P2a); plan in docs/dispatch/P2-walking-skeleton.md |
| Owner | JT (operator); Claude architecture/review; Codex implementation |
| Last updated | 2026-10-27T09:00:00Z |

## Active Work

- P2a on branch feat/p2-walking-skeleton (PR pending CI).

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
| `backend/agent/cj_agent/` | ModelProvider (Fake, DashScope-compatible streaming) and RunWorker. |
| `backend/cj_api/run_events_routes.py` | GET /v1/run-events SSE over the protected display snapshot. |
| `backend/cj_api/local_app.py` | Local composition on real PostgreSQL with a local dev signing key. |
| `backend/cj_api/message_routes.py, backend/message/cj_message/*` | PUT /v1/conversations; MESSAGE open_conversation and acknowledge. |
| `contracts/api/openapi.json` | Add PUT /v1/conversations and GET /v1/run-events. |
| `scripts/dev_auth.py, scripts/run_worker.py, scripts/pg_suites.py` | Local identity, worker process, e2e group. |
| `docs/dispatch/P2-walking-skeleton.md, backend/README.md` | P2 plan and local run steps. |

## Verification Evidence

| Status | Command | Result | Artifact |
| --- | --- | --- | --- |
| pass | `uv run --locked python -B scripts/test.py` | 56/56 groups incl. 7 provider tests (MockTransport) and new MESSAGE open/ack tests. | — |
| pass | `uv run --locked python -B scripts/pg_suites.py` | 11/11 groups incl. e2e: zh/en streamed answers, Last-Event-ID resume without duplication, cross-user withholding, uninvited refusal, crash mid-answer -> unknown without resend. | — |
| not-run | `scripts/run_worker.py --real (DashScope qwen3.8-flash)` | No key provisioned; operator step in the P2 dispatch. | — |
| not-run | `GitHub Actions ci.yml` | Read from the P2a PR checks. | — |

## Blockers

No blockers recorded.

## Next Smallest Action

- Action: After P2a merges: P2b - structured Beijing trip draft from the model, validated into a TRIP proposal, accepted via /v1/trip-actions, formal Trip read back.
- Expected observation: e2e extended to proposal -> accept -> GET /v1/trips shows the formal version.
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
