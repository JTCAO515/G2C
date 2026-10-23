# CJ FACT internal consumer candidate

Owner: CJ-034 / Issue #16. Version: `CJ-FACT-INTERNAL@0.1.0-rc.1`.
Fixed local Python contract; **not frozen FACT@1.0, official OpenAPI, source
approval, authentication, or an enabled tool**. Consumer confirmation and original
Review/Testing are pending. Only CJ-005 may wire the root API afterward.

## Public calls and data

Import `cj_fact` with `PYTHONPATH=backend/fact`. Pure evidence/policy modules
remain stdlib-only. The optional HTTPS primitive uses module-local pinned
`h11==0.16.0`; see `backend/fact/uv.lock`. No root dependency change.

- `parse_document(*, source_url, retrieved_at, content_type, body: bytes,
  policy: SourcePolicy, synthetic: bool) -> Document`: bounded UTF-8 plain text or
  strict JSON. HTML/XML/compression/other charsets are rejected. Does not infer facts.
- `extract_structured_evidence(document, *, evidence_id, fact_key, policy) -> Evidence`:
  narrowly parses the layout below; all values retain exact source spans. A future
  accepted provider adapter is required for a different source layout.
- `evaluate(query: Query, evidence: tuple[Evidence, ...]) -> Result`: deterministic,
  no IO, no identity or authorization claims. IDs must be unique within the input.
- `RestrictedAcquisition(policy=None).fetch(url: str) -> Document`: async, always
  raises `FactFailure('production_integration_unavailable')`, even with a policy.
- `RestrictedAcquisition(policy).fetch_synthetic(url, *, resolve, transport,
  retrieved_at, cancelled: asyncio.Event) -> Document`: async, explicit synthetic
  injection only. No production resolver/dispatch is registered. The separate
  low-level HTTPS candidate below is not automatically connected here. All returned documents
  are marked synthetic. See acquisition details in the module README.

`Document` holds source URL, aware retrieval/query timestamp, media type, **exact
original bytes**, UTF-8 text, SHA256 property, and synthetic flag. No lossy
normalization. `Excerpt(start, end, text)` uses Unicode text offsets, end exclusive,
checked against this original text. `Declared(value, excerpt)` binds each extracted
field to its source. It proves attribution, **not semantic accuracy or source
truth**. Direct Evidence construction is for explicit trusted extraction; do not
use model-supplied metadata as verified source declarations. For JSON, use the
extractor so missing fields cannot be guessed from prose.

`Evidence` contains ID, caller-selected semantic fact key, Document, exact value,
optional regions / inclusive DateRange / conditions / publication time / expiry,
and optional explanations. No PLACE/CJ-012 dependency: region/fact/condition keys
are opaque exact strings supplied by a known caller. There is no country-to-city
inference, timezone inference or expansion of a source's geography.

`Query` requires fact_key, region, inclusive dates, tuple of unique condition
key/value pairs and aware evaluated_at. This is a caller's query, not authenticated
scope, person identity, proof of passport/nationality, or permission.

`Result` contains original Query, status, every Assessment (with original Evidence,
status/reason codes), optional original_value, and fixed Chinese/English status
summaries. Only overall `supported` returns original_value. Consumers must retain
source URL/bytes/hash, timestamps, scope, conditions, missing fields and synthetic
flag; none of those can be dropped when constructing a citation card.

## Deterministic status rules

| State | Meaning |
| --- | --- |
| `supported` | Supplied explicit declarations cover this query and fresh eligible values agree exactly. This is evidence applicability, not real-world truth, provider approval or eligibility advice. |
| `unsupported_or_out_of_range` | Different fact/region/condition, or any query date outside the declared inclusive window. No forecast extrapolation. |
| `expired` | evaluated_at is at or beyond the explicitly declared expiry instant. |
| `conflicting` | At least two otherwise applicable fresh original values differ byte-for-text, with no attempt to choose a preferred source or translate away the conflict. |
| `unknown` | Missing scope/condition/expiry, required query condition missing, future observation/publication, no evidence, or mixed unresolved evidence. |

Per evidence: wrong fact -> out of range; observation after evaluation or
publication after retrieval -> unknown; expired -> expired; scope/condition
mismatch -> out of range; remaining missing fields -> unknown; otherwise supported.
Timestamp ordering compares actual instants using UTC comparison views,
including same-ZoneInfo DST folds. Retrieval/publication freshness, expiry and
publication-before-expiry validation share this rule. Original timestamp
objects, offsets, fold values and source excerpts are retained unchanged.
DateRange still compares inclusive source calendar dates without UTC conversion.
Aware timestamps must also have a representable UTC instant (Python years
1 through 9999). Document, Query and each optional Evidence timestamp validate
this before use; out-of-range instants raise safe ValueError
`instant_out_of_range`. Structured source timestamp rejection maps to existing
FactFailure `invalid_structured_evidence`, including when a companion optional
timestamp is absent. No offset relabeling, clamping or validity substitution.

A missing publication date remains absent but alone does not invalidate other
explicit scope and expiry declarations. Missing expiry is unknown even when the
travel date window is known: forecast coverage does not imply freshness lifetime.

Aggregate: differing supported values -> conflicting; otherwise any unknown ->
unknown; otherwise one or more supported -> supported; all expired -> expired;
all out of range -> out of range; remaining mixtures/empty -> unknown. Expired or
out-of-range sources remain visible in assessments even if another source supports
the query. No latest-source-wins rule. Equality is conservative exact original
text/JSON-literal equality, not semantic equivalence.

## Narrow structured layout

`synthetic-cases.json` is executable fixture input, **not a second official API or
an adopted provider schema**. Source JSON must be an object:

- `value`: required non-null JSON scalar; raw JSON literal is preserved, including
  quotes/escapes, negation, currency and dates. No conversion to a translated fact.
- `regions`: optional nonempty array of explicit region strings.
- `dates`: optional object with exactly `start` and `end`, ISO calendar dates.
- `conditions`: optional object with string values; `{}` explicitly declares no
  conditions. Missing/null is unknown, different from an empty declaration.
- `published_at`, `expires_at`: optional ISO datetime strings with explicit offset.

Missing/null optional fields stay missing; malformed types fail closed with safe
codes. Unknown fields stay in original bytes only. No source-supplied fact_key,
ID, system prompt, shell/tool, budget or explanation is executed or adopted.

Explanations are separate `Explanation(language='zh'|'en', text,
kind='source_excerpt'|'machine_translation'|'model_explanation', original=Excerpt)`.
A source_excerpt must exactly equal its original excerpt; this label does **not**
claim that a source is official or approved. Derived text is unverified annotation,
never used by evaluate or as original_value. Original negation/currency/date and
conditions always remain available separately. No translation/model is called;
translation faithfulness and actual bilingual citation UI require later acceptance.
The fixed bilingual status summaries explain applicability only, not legal advice.

## Failure / ownership / integration gaps

`FactFailure` carries safe codes only, not URL, content, credentials or underlying
transport exception strings. Invalid manual model construction raises safe
ValueError codes. No implicit retries, replacement action IDs, cost zeroes, usage
settlement, RUN completion, JWT validation or cross-user store is introduced.

At base `8deb696f8149b4f5aa70c767be6c3a263b036227`, AUTH public admission,
USAGE Meter/LocalExit and RUN original binding were inspected read-only. RUN
`Service.dispatch` remains closed; LocalExit requires an explicitly synthetic
executor. Those APIs do not supply a canonical live FACT one-shot exit with an
atomic current-admission/cancel/claim fence. This module does not bypass them.

Smallest missing owner seam before real dispatch: a canonical public one-shot
exit that binds the existing trusted scope + **original** RUN/USAGE command and
input bytes, performs current admission/cancellation/claim checks at dispatch,
and returns the original typed outcome/receipt or explicit unknown for read-only
reconciliation. This is a semantic/signature requirement for existing owners,
**not a new FACT grant/token/Protocol or accepted wire**. Main should obtain its
exact existing public type/signature from AUTH/USAGE/RUN owners; CJ-005 then maps
the fixed Result/FactFailure through the sole official API. Do not invent those
types or substitute sequential caller booleans. Until then fetch stays disabled.

Independent blockers: (1) production source selection, permitted regions/scenarios,
licensing/cache/retention policy; (2) public-target pinned-socket/TLS validation beyond task-local fixtures; (3)
canonical AUTH/USAGE/RUN exit and unknown/cancel behavior; (4) root official wire,
chat/citation UI, real source and Issue16 I acceptance. All remain UNRUN/UNKNOWN as
applicable. No caching/persistence, user data, credential or new resource exists
in this slice. Consumer confirmation remains pending; do not close Issue16.

## Optional pinned HTTPS primitive (local TLS candidate)

`from cj_fact.https_transport import PinnedHTTPSTransport` is an explicit opt-in
import, not part of the existing `cj_fact.__all__` or a registered agent tool.
Constructor: `(policy: SourcePolicy, *, tls_context: ssl.SSLContext,
max_header_bytes: int, max_wire_bytes: int, max_reads: int)`; all three limits are
explicit positive integers. Context must require hostname/certificate verification
and have no TLS keylog file. It is host-owned configuration, never source data;
no ambient credentials, proxies, cookies or client credential discovery occurs.

`await transport(target: PinnedTarget) -> InjectedResponse` reuses the original
response shape. It validates canonical allowed HTTPS origin/hostname, every public
DNS-answer IP already carried by the target, target byte bound and finite deadline.
Exactly the first validated numeric address is attempted, once, on443. An already
connected numeric socket is handed to asyncio TLS with `server_hostname` set to
the original hostname. Both actual TCP/TLS peers are checked; Host and URL stay
bound to that original hostname. There is no DNS call/fallback in this primitive,
second-address retry, redirect follow, connection reuse or authority grant.

Request is GET only with fixed Host/Accept/identity encoding/Connection-close
headers. h11 owns HTTP/1 framing. Header/wire bytes, wire reads, decoded body bytes,
body data-event chunks and one total monotonic deadline are bounded; 1xx/upgrade,
ambiguous TE+CL, invalid framing, trailers, unsupported200 content/encoding,
truncation and oversize are rejected. Header/status returns do not consume or
follow redirects: the existing acquisition layer owns per-hop policy validation.
Response.close works before body iteration. Errors/cancellation/deadline abort
the socket; an unread response also has a deadline close timer. Callers must close
responses. Body iteration and connection use the same deadline. No TLS shutdown
wait extends that deadline.

FactFailure safe codes include `tls_certificate_invalid`, `timeout`,
`peer_not_pinned`, `https_exchange_failed`, `https_body_failed` and bounded
HTTP-policy codes. Native task cancellation propagates. Failure/timeout/cancel
after request transmission means delivery or result can be UNKNOWN; it is not a
claim that the source never received GET, zero cost, a usage receipt, RUN terminal
state or permission to retry. No receipt/settlement is invented here.

Private `_exchange` is used directly only by the task's127.0.0.1 ephemeral-port
TLS fixtures. There is no loopback override parameter on the public constructor,
callable, SourcePolicy or production fetch. The fixture's self-signed certificate
is trusted only by its explicit test SSLContext; system trust is unchanged. This
is trusted test Python, not a sandbox. Actual loopback TLS/SNI/peer/cancel evidence
is in `backend/fact/evidence/https/REPORT.md`; no public source/DNS/provider call
has been made. IPv6 live transport, public networking and provider readiness remain
UNRUN. Production `RestrictedAcquisition.fetch` still unconditionally rejects.
The canonical AUTH/USAGE/RUN exit and accepted source selection are still required
before this primitive may be wired to a real business dispatch.
