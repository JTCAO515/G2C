# CJ-035 PLACE consumer author evidence

Firstfixed retained: `a862a82504eae47ae5c44c13a45d34ae4edfeb03` on original
base `8deb696f8149b4f5aa70c767be6c3a263b036227`, branch `cj/035-feasibility`.
This delta changes only `backend/feasibility/**` and `contracts/feasibility/**`.
No source from NEEDS/PLACE, root files or other owners was edited.

## Fixed PLACE consumption

Pinned dependency: `dd4c375a731bbaef1d436bc3e88466040ac02294` from
`/Users/jtsm5p/Documents/Codex/2026-10-21/cj-012-place`. Its observed checkout
HEAD had moved to ec2d0a60e28ada64ac261185452070a3593cd6dc, clean, with only two
evidence-file additions relative to dd4. Read actual fixed files using `git show`
and used a fresh temporary `git archive dd4 backend/place contracts/place`
export for tests. No source checkout, branch, dependency, lock or config changed.
`routes-manifest.json` identifies exact exported library files and this consumer.
No copied PLACE DTOs are in this candidate.

First consumer business source: `backend/feasibility/cj_feasibility/routes.py`.
Public contract: `contracts/feasibility/ROUTES.md`. Runnable consumer demo:
`backend/feasibility/route_demo.py`. Types: original PLACE Result/Route/Observed/
Source/RouteQuery/PreparedRequest/Config; Window only binds explicit candidate item
IDs to the actual selected query plus explicit buffer/rest quantities.

## Local verification

Existing CPython 3.14.7, no installs or real services.
With PLACE_EXPORT set to the exact export root:

```sh
PYTHONPATH="$PLACE_EXPORT/backend/place:backend/feasibility:backend/needs:backend/auth" /opt/homebrew/bin/python3.14 -m unittest discover -s backend/feasibility/tests -p test_routes.py -v
PYTHONPATH="$PLACE_EXPORT/backend/place:backend/feasibility:backend/needs:backend/auth" /opt/homebrew/bin/python3.14 backend/feasibility/route_demo.py
/opt/homebrew/bin/python3.14 -m compileall -q backend/feasibility/cj_feasibility/routes.py backend/feasibility/route_demo.py backend/feasibility/tests/test_routes.py
git diff --cached --check
```

- `routes-first.txt`: initial 14 tests PASS, preserved.
- `routes-final.txt`: final 17 tests PASS, including every nonpresent duration
  state, original objects retained, identity/role/GCJ02/mode/digest/source binding,
  age boundary and anomalies, missing source/routes, explicit route selection,
  specified/past/future applicability, shared subject/cancellation, nonmutation,
  two languages, explicit buffer/rest/zero, unit/NaN/negative/raw mismatch,
  precise fractional amount under hostile Decimal context, candidate protection,
  and rejection of forged trust/future guarantees.
- `route-demo.txt`: actual PLACE prepare/parse_response + NEEDS public objects,
  synthetic 3600-second estimate against 900-second candidate window produces
  `required_exceeds_gap`; aggregate UNKNOWN, source remains synthetic.
- Compileall PASS and staged diff whitespace check PASS.
- Original NEEDS validator/test code is unchanged from firstfixed; its final
  29-test evidence is reused, not rerun. Original logs and manifest retained.
  Firstfixed source-manifest refers to that prior fixed candidate, not this delta.

## What it proves

Author local tests/conditional numeric behavior PASS. Explicit source/query age
is checked against original Config policy; original Result/Source/query/IDs/
roles/GCJ02/time/ref/digest are retained, not reduced to a number. Unknown
buffer/rest/duration never becomes zero. Arithmetic cannot release a candidate
that failed the original unselected/locked protection.

The fixed PLACE Source only permits synthetic/unverified_bytes. Therefore no
real-route feasible/conflict verdict is possible in this consumer version;
conditional relation and overall UNKNOWN remain separate. An explicit item to
endpoint mapping is a declaration, not independent confirmation from NEEDS text.
An at-query-time estimate cannot establish applicability at a different departure.
No caller trust override or invented Source category is accepted.

Independent Review/Testing PENDING. Real route evidence, trusted outbound/receipt
provenance, confirmed candidate endpoint mapping and date applicability, root API,
real provider, PG, App/device, complete rest/cost logic and Issue I gates UNRUN.
OR-Tools/bounded solver UNRUN; no placeholder solver or guessed speeds/buffers.
No push, PR, merge, deployment, key/Keychain access, provider request or domain write.
