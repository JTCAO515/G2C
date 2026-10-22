# Explicit manual-preview computation transport

Parent3090777b4e10a6135823e3342e5e8b6c34aa9e6b. Fixed consumer inspected:
CJ017036de8de060ea8d84dc976862907ec5fe9c978c7, its REPORT and PreviewTransport/PreviewEditor.
It correctly retained a draft when the old generic live transport refused POST. This
candidate changes only the shared transport, test and evidence; CJ017 source is untouched.

Public opt-in factory, returning the EXISTING NoRedirectTransport type:

```
NoRedirectTransport.readOnlyManualPreview(
    endpoint: MessageEndpoint,
    requestTimeout: TimeInterval,
    resourceTimeout: TimeInterval,
    validate: @escaping @MainActor @Sendable () throws -> Void
) throws -> NoRedirectTransport
```

Endpoint is explicit (existing HTTPS/explicit-loopback policy, request/response limits),
timeouts must be positive finite values, validator has NO default. Trusted host/CJ017
must capture actual original Trip/source/session bindings in that validator. It is not
new authentication, a client-supplied boolean or permission from request contents.
CJ017 can retain its public liveTransport:NoRedirectTransport parameter and adopt the
factory under its own writer; existing generic constructor remains gated.

The capability permits ONLY official Operations.previewManualTripEdit.id, POST,
exact /v1/trip-manual-previews with no appended query, configured baseURL, no explicit
request scheme/authority override, one supported JSON content-type and a body. Caller
labels cannot enable arbitrary operations. Request is bounded and forwarded as collected
bytes unchanged; no request decoding/re-encoding, patch, save, Proposal or Trip algorithm.
Default generic live writes stay blocked; PUT/DELETE/PATCH/other nonread methods are also
blocked. Existing GET/HEAD pass-through remains the generic read behavior, protected by
the actual consumer's configured request/auth guard; it is not new authorization.

Preview branch checks cancellation, bounds request collection, then calls validator
before outflow; checks validator/cancellation after underlying await and after bounded
response collection. Stale source/identity cannot return preview response. Session stays
ephemeral with cookies/cache/credential storage disabled and redirect delegate returning
nil before destination dispatch; 3xx rejects, no body is invalid. Missing/over-limit data
never becomes successful empty preview. Existing CJ017 PreviewTransport still owns
frozen official request binding, request_id/header/no-store/JSON/projection checks and
its final host settlement. This factory does not replace those independent guards.

PASS: Swift6.4/macOS, six new capability checks +two existing default-message POST/draft
PUT prohibition checks (8 total), evidence/readonly-preview-capability-tests.txt. Covers
actual generated c5 operation through injected interceptor, unchanged request bytes,
three validation points, exact-op/path/host/media constraints, no authority override,
request/response limits, retired identity, 3xx refusal, default and other writes closed,
explicit finite configuration. No URLSession request was sent. Test factory construction
creates a session only; URLSession delegate destination behavior is source/compile proof,
not a live redirect experiment. Initial test actor mutation needed MainActor.run; no
assertion weakened. No business network, Keychain/account, PG, signing or other resources.

c5 producer/export/Package/SDK inputs unchanged; no implicit re-export. No CJShell or
manual client adoption/UI/network acceptance claimed. Independent double review and
CJ017 exact fixed consumption still required. Existing69d/b868 HOLD unaffected.

Host-header P2 correction: the narrow preview branch now rejects ANY ordinary Host
header, case-insensitively, including duplicates and a nominally same-origin value.
Configured baseURL supplies authority; no raw body/header rewriting is used. See
evidence/PREVIEW-HOST-FIX.md for exact c5-base runtime patch and original failing probe.
