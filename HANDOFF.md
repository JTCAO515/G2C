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
| Last updated | 2026-10-27T00:00:00Z |

## Active Work

- P0 repo hygiene and minimal CI: docs/dispatch/P0-repo-hygiene.md (not started)

## Accepted Assumptions

- Static review only at main 8fac0dff5e50ce08c277b65f7322a4ea64d77e65; pytest and swift test were not run (UNRUN).
- Inference to verify: delivery slowness comes mainly from process and in-repo composition overhead, not technical difficulty.
- ADR-0002 technology stack (AgentScope, DBOS, ReMe, Supabase Auth) remains candidate, not verified in combination.

## Frozen Decisions

- accepted: ADR-0001 product and user-control boundaries.
- accepted: model qwen3.8-flash with Beijing endpoint profile (spikes/runtime/REPORT.md); real calls still UNRUN.
- accepted: JT authorized this PR (handoff.json, ADR-0004, P0 dispatch) and direct merge to main.
- proposed: ADR-0004 delivery flow and repo hygiene; items 3, 5, 6 need JT confirmation.

## Changed Files

| Path | Reason |
| --- | --- |
| `docs/handoff.json` | Repository-owned machine handoff source (ADR-0004 item 1). |
| `HANDOFF.md` | Rendered from docs/handoff.json. |
| `docs/adr/0004-delivery-flow-and-repo-hygiene.md` | Proposed delivery flow and repo hygiene decision. |
| `docs/adr/README.md` | Index ADR-0004. |
| `docs/dispatch/P0-repo-hygiene.md` | Codex dispatch for P0. |

## Verification Evidence

| Status | Command | Result | Artifact |
| --- | --- | --- | --- |
| pass | `python3 -m json.tool docs/handoff.json` | handoff.json is valid JSON. | — |
| pass | `node ~/.claude/skills/jtcoding-skills/scripts/handoff.js check --project .` | Schema valid and HANDOFF.md current at authoring time. | HANDOFF.md |
| pass | `git diff --stat origin/main -- backend ios spikes contracts pyproject.toml uv.lock` | No business code changed by this PR. | — |
| not-run | `CJ_ENV=local uv run pytest -q backend/tests backend/cj_api/tests` | Not run during review; to be established by P0 CI. | — |
| not-run | `swift test (ios/Modules/CJShell)` | Not run during review; to be attempted in P0 CI. | — |

## Blockers

| Blocker | Owner | Unblock condition |
| --- | --- | --- |
| Repository visibility (PUBLIC, no license, 618 files with local paths). | JT | JT chooses PUBLIC or PRIVATE. |
| Whether to remove in-repo sha256 pins and move evidence out of the repo (ADR-0004 items 3, 5). | JT | JT accepts or rejects; required before P1. |
| P2 values: city, primary login, minimum iOS (suggested Beijing, email OTP, iOS 17). | JT | JT confirms values; required before P2 real acceptance. |
| Process simplification (ADR-0004 item 6). | JT | JT accepts or rejects. |

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
