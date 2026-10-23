# CJ-034 author evidence — local FACT slice

Historical baseline: `401d082bd2f0a47893f3049bf8e953229a68bb67`.
Instant-comparison repair: [time-fix/REPORT.md](time-fix/REPORT.md).
UTC representability repair: [range-fix/REPORT.md](range-fix/REPORT.md).
Current low-level HTTPS candidate: [https/REPORT.md](https/REPORT.md).
Original logs and source manifest below remain the baseline evidence.

Date: 2026-10-22, Asia/Shanghai. Base:
`8deb696f8149b4f5aa70c767be6c3a263b036227`.
Branch: `cj/034-fact`. Worktree:
`/Users/jtsm5p/Documents/Codex/2026-10-21/cj-034-fact`.
Candidate is fixed by the commit containing this report; exact product/contract/
test hashes are recorded in `source-sha256.json` (evidence files excluded).
Only `backend/fact/**` and `contracts/fact/**` are changed. No shared locks,
root API/registry, foreign module, iOS, original 13 docs or HANDOFF edits.

## Actual implementation

First product writes: `backend/fact/cj_fact/model.py` and `policy.py`.
Completed evidence model / deterministic applicability / bounded injected fetch /
strict plain+JSON parser / exact structured-field extraction. `__init__.py` fixes
explicit public exports; `contracts/fact/README.md` fixes internal shapes,
precedence and integration gaps. No empty protocol, generic network framework,
parallel AUTH/USAGE authority or duplicate official HTTP schema was introduced.

The clone source was clean with HEAD exactly equal to the base; its origin was
`https://github.com/JTCAO515/Go2China.git`. `clone --no-hardlinks` made an independent
object store; this clone's origin remains the explicit local Publish path. No
fetch, push, PR, merge, Issue mutation or external resource operation occurred.
The GitHub connector returned empty Issue fields; authorized read-only `gh issue
view 16 --repo JTCAO515/Go2China` returned the actual Issue16 body. Historical
"development not started" text did not supersede the current local-write grant.
One attempted read of guessed `backend/message/cj_message/boundary.py` was absent;
actual `auth_boundary.py` was located with rg. No file was created at that path.

## Checks actually executed

| Evidence | Result / scope |
| --- | --- |
| `unit-initial.txt` | 35 author unittest methods PASS before structured extractor addition. |
| `unit-structured.txt` | 42 author methods PASS after extractor addition. |
| `unit-final.txt` | **45 author methods PASS**, including final source terminology, publication/retrieval consistency and post-resolver deadline fence. Table-driven negative cases are subtests, not additional claimed methods. |
| `consumer-examples.txt` | Initial 9 fixed public synthetic scenarios PASS. |
| `consumer-final.txt` | **9 fixed public synthetic scenarios PASS** on final product source. |
| `scope-check.txt` | Staged diff paths restricted to the two owned directories; whitespace check PASS. |

Interpreter: existing `/opt/homebrew/bin/python3.14`, CPython 3.14.7. System
`python3` was 3.9.6 and was not used for validation. No dependency install, network,
server/socket, account, database, signing or device action. Original execution
logs are preserved; there were no failing unit assertions in this task. Initial
and intermediate passes are not represented as final-source acceptance.

Covered normal/missing/empty scope, condition mismatch/missing/explicit empty,
expired boundary, future forecast window, future observation/publication, exact
value conflicts, incomplete potentially applicable conflicting evidence, duplicate
IDs and immutable shapes. Chinese/English status summaries coexist with original
negation/currency/date/conditions; an intentionally wrong synthetic translation
cannot change the original value or be relabeled source_excerpt. It remains
unverified annotation, not a claim of translation fidelity.

Covered malicious source strings/extra JSON fields, strict media/UTF-8/encoding,
duplicate keys/nonfinite numbers/surrogates/depth/node bounds, exact raw bytes,
userinfo/ports/host normalization/IP spellings, private/metadata/mixed DNS answers,
public-peer mismatch, every redirect target, implicit redirect/cycle/count,
oversize/chunk/content-length failures, Event cancellation before IO/during DNS/
body/last chunk, native task cancellation, stalled DNS/body timeout, late resolver
return before dispatch, body cleanup and safe error redaction with no retry.

## Limits and next

**Author-local PASS only. Original independent Review/Testing pending.** No
self-approval or Issue closure. Network socket pinning/TLS is NOT proven; the real
fetch entry unconditionally fails closed. Injected Python is trusted cooperative
synthetic code, not a sandbox or production transport. `supported` means supplied
declarations fit the query; no source authenticity, verified identity or real
visa/booking eligibility follows.

UNRUN: real weather/web provider and source approval; supported region/scenario
choice; cache/licensing/retention decisions; real AUTH/USAGE/RUN one-shot dispatch
and cancellation/unknown receipt integration; root official wire/SSE/chat/citation
card; real bilingual translation fidelity; CI; database; device; release.
UNKNOWN: model effective settings, future production source availability/cost.

Next: Main routes this fixed candidate to the existing Review and Testing owners.
If accepted, the module contract can be consumed at this exact version; root wire
belongs to CJ-005. The minimal authoritative exit signature/semantics gap and
separate source/network-policy decisions are explicitly listed in the FACT
contract. They block real dispatch, not this delivered deterministic local slice.
