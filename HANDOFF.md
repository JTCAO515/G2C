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
| Last updated | 2026-10-27T03:00:00Z |

## Active Work

- P0 repo hygiene and minimal CI: docs/dispatch/P0-repo-hygiene.md (not started)

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
| `docs/adr/0004-delivery-flow-and-repo-hygiene.md` | Mark accepted and record JT decisions of 2026-10-27. |
| `docs/adr/README.md` | ADR-0004 status accepted. |
| `docs/scope.md` | City, minimum iOS and login rows confirmed per ADR-0004. |
| `docs/dispatch/P0-repo-hygiene.md` | Reflect accepted decisions; P1 next. |
| `docs/handoff.json` | Decisions accepted, blockers cleared. |
| `HANDOFF.md` | Rendered from docs/handoff.json. |

## Verification Evidence

| Status | Command | Result | Artifact |
| --- | --- | --- | --- |
| pass | `python3 -m json.tool docs/handoff.json` | handoff.json is valid JSON. | — |
| pass | `node ~/.claude/skills/jtcoding-skills/scripts/handoff.js check --project .` | Schema valid and HANDOFF.md current at authoring time. | HANDOFF.md |
| pass | `git diff --stat origin/main -- backend ios spikes contracts pyproject.toml uv.lock` | No business code changed by this PR. | — |
| not-run | `CJ_ENV=local uv run pytest -q backend/tests backend/cj_api/tests` | Not run during review; to be established by P0 CI. | — |
| not-run | `swift test (ios/Modules/CJShell)` | Not run during review; to be attempted in P0 CI. | — |

## Blockers

No blockers recorded.

## Next Smallest Action

- Action: Codex executes docs/dispatch/P0-repo-hygiene.md on branch chore/p0-repo-hygiene and opens a PR.
- Expected observation: PR with CI results, zero business-code diff, local paths removed, handoff refreshed.
- Resume command: `git fetch origin && git switch -c chore/p0-repo-hygiene origin/main`

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
