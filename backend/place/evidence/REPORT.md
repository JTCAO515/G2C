# CJ-012 Gaode PLACE local candidate

Status: **CODE_READY, author checks PASS, independent Review/Testing PENDING**.
Issue 13 remains open; this does not claim full PLACE@1.0 or real-service acceptance.

- Owner scope: `backend/place/**`, `contracts/place/**` only.
- Repository: `<local>/Documents/Codex/2026-10-21/cj-012-place`.
- Branch: `cj/012-place`.
- Fixed base: `8deb696f8149b4f5aa70c767be6c3a263b036227`.
- Fixed source/public-contract head: `dd4c375a731bbaef1d436bc3e88466040ac02294`.
- Source manifest: [source-manifest.json](source-manifest.json), hashes of all 16
  source-commit paths. This report/manifest are an evidence-only follow-up.
- Clone source: clean local `cj-publish/Go2China`, fixed base checked before clone,
  original remote `https://github.com/JTCAO515/Go2China.git`; clone used
  `--no-hardlinks`. The clone's origin remains its explicit local source.
- First product write: `backend/place/cj_place/models.py`; no shared/root writes.
- Model request updates consumed; current model effective **UNKNOWN**. No session
  restart, model/global configuration change or child-agent delegation occurred.

## Delivered

Typed immutable Place/Route/Source/Result; fixed Gaode v3 search/detail and
walking/driving request preparation; strict response parsing and original-request
correlation; exact POI/branch/entry roles and GCJ-02 values; raw Chinese names and
addresses; distinct unknown/missing/invalid/empty/zero values; explicit query time
and m/s estimate semantics. Specified departure remains unsupported, never silently
changed to current conditions. No fuzzy merge, invented English, coordinate
conversion, cache, Trip mutation, new JWT/authority, alternate API or framework.

Public consumption shape, minimal missing host seam and limitations:
[contracts/place/README.md](../../../contracts/place/README.md).
Sources were verified against [official documentation](../../../contracts/place/SOURCES.md).
Positive/negative runnable consumers:
[contracts/place/examples.py](../../../contracts/place/examples.py).

## Actual checks

Python **3.14.7**, macOS, installed interpreter
`/opt/homebrew/opt/python@3.14/bin/python3.14`; stdlib only, no dependency install.
Declared range follows root >=3.12,<3.15; other Python versions **UNRUN**.

| Evidence | Result and scope |
|---|---|
| [initial-tests.txt](initial-tests.txt) | 30 author test methods PASS before extra projection/numeric probes. |
| [final-tests.txt](final-tests.txt) | 31 PASS after entrance projection and additional documented rate codes; historical filename retained. |
| [extreme-exponent-before.txt](extreme-exponent-before.txt) | Deliberate new malformed-number probe ERROR: uncaught Decimal.InvalidOperation. Original failure retained. |
| [candidate-tests.txt](candidate-tests.txt) | **32 PASS** after catching DecimalException at parser boundary; includes that exact regression and prior 31 methods. |
| [candidate-examples.txt](candidate-examples.txt) | **6 synthetic consumer examples PASS**, actual public classes, no duplicate schema. |
| `git diff --check` | PASS before source commit; 16 paths all inside granted scope. |

Coverage includes same-name distinct provider IDs/entrances, exact detail mismatch,
route identity/role/mode/coordinate binding, original Chinese/Unicode, official
English unknown, absent/empty-array/null/invalid values, real string zero, empty
pages versus failure, count consistency, stale/deadline/time ordering, future and
past specified departure, provider failure and documented rate codes, HTTP errors
and redirects, duplicate keys at nested levels, invalid UTF-8/surrogates, deep JSON,
oversized responses, extreme exponent, missing configuration, no retries,
cooperative cancellation propagation, exception-prose/log redaction, closed real
entry, and source/evidence attribution.

Reproduce from root with a compatible installed Python:

```sh
PYTHONPATH=backend/place python3.14 -B -m unittest discover -s backend/place/tests -v
PYTHONPATH=backend/place python3.14 -B contracts/place/examples.py
```

All input data is explicitly synthetic. No socket/HTTP provider call, real secret,
old DB/account, cloud resource, permission change, production data or paid call.
Only official documentation and read-only Issue retrieval used network. The GitHub
connector returned null fields; normal read-only `gh issue view 13` obtained the
Issue. Documentation-open timeouts used official indexed text, never business API.
An initial read targeted absent `backend/pyproject.toml`; the actual root file was
then located/read. These preparation failures are not tests or service evidence.

## Remaining boundaries / next

- **UNRUN**: real Gaode requests, account/API permissions, approved cities, actual
  Chinese/English query quality, physical coordinate alignment, provider
  latency/cost/license/retention, AUTH/USAGE/RUN real protected execution, root
  API/UI, CJ016/CJ035 acceptance, CI, database, device, deployment and Issue 13 I.
- Production `execute` is unconditionally unavailable, even with Config.
  Config/parsed identity/digest do not authorize network or settle cost.
- The fixture transport is trusted offline Python with cooperative timeout; not a
  sandbox, bounded real HTTP stream, atomic cancellation fence or durable exit.
  Response-byte limits apply before JSON decode; future transport must also cap
  streaming and the final credential-injected URL. No credentials are accepted
  or loaded by this module.
- Need accepted canonical dispatch context + original attempt/input-byte binding
  and approved host transport/receipt seam from original RUN/USAGE/AUTH/CJ005
  owners. Current base explicitly keeps real RUN dispatch closed. No new guard or
  synthetic allow can replace that seam. Exact gap is recorded in the contract.
- Consumer must retain Result.source and inspect each Observed field. OK does not
  guarantee address/coordinates/measurements exist or that a route is feasible;
  `unverified_bytes` never means authenticated provider data. Provider-updated
  time remains unknown; local age policy is not a freshness guarantee.
- Next: Main routes this fixed source/evidence candidate to existing Review and
  Testing; CJ035 can pin its types/examples for bounded local consumption. This
  owner waits for their findings; no self-approval, push, PR, merge, Issue edit,
  new thread or HANDOFF modification.
