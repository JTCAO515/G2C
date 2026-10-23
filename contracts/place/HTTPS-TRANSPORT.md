# CJ-012 fixed Gaode v3 HTTPS candidate

Parent `80ba4ae5527875ce375d22f3439f8e3256e2c4d6`. Internal Python candidate,
not a new public HTTP contract or accepted canonical dispatch API. Source:
[https_transport.py](../../backend/place/cj_place/https_transport.py).
Pure PLACE models, request binding, parser, original timestamps and execute are
unchanged from the accepted parent. The new module is not auto-exported or
registered with any root, RUN, USAGE or other owner.

## Exact callable surface

Explicitly import from `cj_place.https_transport`:

- `ProviderCredentials(api_key, expires_at)`: trusted server host's per-call
  configuration. Required aware expiry, strict ASCII key shape (16–256
  alphanumeric/underscore/hyphen). No environment lookup or default key. This is
  this candidate's supported key profile, not proof of provider eligibility or
  an authorization token. Host determines lifetime and disposes of the object;
  Python immutable strings do not offer secure erasure. Repr hides all fields.
- `await fetch_candidate(config, prepared_request, credentials) -> TransportResult`:
  consumes the existing exact Config and PreparedRequest. Rejects missing/wrong
  typed input, changed binding, path/origin/query tampering, expired credentials,
  future/expired original query and credentialed URL overflow before dialing.
- `TransportResult(state, reason, response=None)`: state is received/rejected/unknown.
  Received only means a complete bounded HTTP receipt. It does not claim provider
  business success, truthful places, execution authorization or settled cost.
  Rejected means this invocation refused before I/O. Unknown never permits a
  retry/new attempt here. Response is the existing original class; no secret URL,
  headers, cookies, raw error or exception prose is returned. Its repr hides body.
  Caller cancellation propagates as sanitized CancelledError after close/abort;
  preserve original attempt/unknown accounting, not a non-dispatch inference.

Use the original `parse_response(config, request, receipt.response, now=...)`
only for received receipts. The private TLS fixture chain labels evidence
synthetic. Existing default unverified_bytes remains conservative; TLS receipt
alone does not upgrade Source truth/freshness or authenticate a user/attempt.

## Fixed network and credential boundaries

The production private dial function fixes `restapi.amap.com:443`, TLS hostname
and normal verified trust roots; minimum TLS1.2, ALPN HTTP/1.1. There is no public
host/port/URL, SSLContext, dial callback, proxy, cookie jar or redirect option.
Only the four original v3 paths and recomputed exact parameters are accepted.
Credentials are appended to a local outbound request buffer after validation;
they never enter PreparedRequest, Source, binding digest or stored input.
No environment key, provider account, global config, retry or connection pool.

The module constructs SSLContext directly rather than using a helper that can
honor SSLKEYLOGFILE. It performs no log calls. Non-200 bodies and all response
headers are discarded; status alone is retained for the existing error parser.
Literal or JSON-decoded escaped key echoes in 200 bodies cause unknown with no
Response. If the strict existing JSON inspection cannot complete (including
duplicate keys, truncation, invalid UTF-8/Unicode, unsupported root or depth), the
transport also fails unknown/response_secret_check_unavailable **without a
Response/body**. A later parser rejection cannot repair a low-level body leak.
Inspectable nonsecret JSON remains the exact received bytes, including whitespace
and escape spelling; no source normalization or reconstruction is performed.
This is a conservative supported-JSON-profile boundary, not a general classifier
for arbitrary transformed/hashed secrets or a regex encoding guarantee. No
provider prose or body should be used as operational logging. Test credentials
are explicit synthetic sentinels, never actual secrets.

A monotonic deadline covers connect/TLS, send/drain, body, credential-echo check
and close. Remaining time is bounded by original query start's UTC elapsed time,
Config timeout/max-age and credential expiry. The candidate checks after late
connect and after close too; late completion cannot become a successful receipt
or start a request after the deadline. Conversion uses UTC instants, retaining
original request/Source timestamps and ID/coordinate precision.

Writer closes on every acquired-connection path. A failed/cancelled/timed-out
close aborts its transport, drops any receipt and stays unknown/cancelled. This
is local resource cleanup; it does not undo dispatch or settle provider cost.
Async standard-library I/O is cancellation-cooperative; arbitrary monkeypatched
Python is not a sandbox. No worker recovery or cross-store atomic fence is claimed.

## Narrow HTTP framing and limits

Final credentialed absolute URL <= existing Config.max_request_bytes. Response
body <= Config.max_response_bytes, checked before each bounded read/append;
Content-Length overflow refuses immediately. Supported response framing:
Content-Length, basic chunked, or connection-close delimitation. No decompression.

This profile caps headers at16KiB/100 fields/4KiB field line, and total consumed
wire bytes at body cap+16KiB. StreamReader has a16KiB buffer threshold (transport
backpressure may buffer beyond the threshold before pausing); this is not a
claim about exact OS/TLS packet reception. Reject ambiguous length/transfer or
repeated framing headers, unsupported encodings/interim responses, chunk
extensions/nonempty trailers, oversized chunk metadata and truncation. These
are conservative adapter policies, not guarantees that every Gaode deployment
uses the supported framing. Actual provider compatibility remains UNRUN.

Key-only Web Service requests are implemented. Accounts requiring an additional
signature or other provider configuration need a separately accepted extension;
there is no guessed signature algorithm or arbitrary parameter injection.

## Private verification and remaining gate

[https_transport_checks.py](../../backend/place/tests/https_transport_checks.py)
is explicitly invoked outside default test discovery. It generates a disposable
self-signed SAN restapi.amap.com certificate/key only inside task .local, trusts
it only in one test client context, and starts numeric127.0.0.1 ephemeral-port TLS
servers. It patches only the private dial function; no public endpoint override,
system trust installation, real Gaode DNS/request or real credential is used.
The production fixed dial arguments/TLS policy are separately inspected with an
AsyncMock that makes no connection. Private servers close and synthetic TLS
material is deleted at teardown; no existing files/resources are deleted.

The existing canonical **accepted dispatch context + exact original bound input /
attempt + current AUTH/claim/cancel fence + trusted receipt provenance** signatures
are still undefined at this parent. This candidate invents none. Real execute
remains unconditionally unavailable. There is no new Protocol, allow flag, budget
model, permission owner or second dispatch wrapper. Original domain owners must
provide that accepted seam before real product registration can be considered.

Real provider, permission/signature profile, costs, cities, latency, license,
AUTH/USAGE/RUN/root integration, device, CI/deployment and Issue13 I remain UNRUN.

## Primary sources

Checked 2026-10-23, read-only documentation:

- [Python asyncio streams](https://docs.python.org/3.14/library/asyncio-stream.html):
  verified TLS stream arguments, StreamReader limits/readexactly/readuntil and
  explicit close/wait_closed. Used instead of a blocking thread/client retry loop.
- [Python asyncio timeouts](https://docs.python.org/3.14/library/asyncio-task.html#timeouts):
  monotonic absolute timeout and cancellation behavior; late checks remain needed
  if an awaited implementation suppresses cancellation.
- [Python ssl](https://docs.python.org/3.14/library/ssl.html): PROTOCOL_TLS_CLIENT
  verifies chain and hostname; SSLKEYLOGFILE can affect create_default_context,
  so the candidate constructs a verified context directly without key logging.
- [Original Gaode source record](SOURCES.md): the same v3 endpoints and key/profile
  semantics were reused; no new provider endpoint/schema was inferred or queried.
