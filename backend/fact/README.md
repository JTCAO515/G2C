# CJ-034 FACT local source/applicability slice

Product code: `cj_fact/model.py`, `policy.py`, `acquisition.py`, `structured.py`.
Public consumption contract: [contracts/fact](../../contracts/fact/README.md).
Zero runtime dependencies; repository Python >=3.12,<3.15. Author verified with
installed CPython 3.14.7; other interpreters are UNRUN. No global configuration or
shared lockfile change is needed.

From repository root:

```sh
PYTHONPATH=backend/fact /opt/homebrew/bin/python3.14 -B -m unittest discover -s backend/fact/tests -v
PYTHONPATH=backend/fact /opt/homebrew/bin/python3.14 -B backend/fact/tests/check_examples.py
```

All test DNS answers and bodies are synthetic. No socket, server, real resolver,
provider call, credential, database, cost or model call occurs.

## Restricted acquisition

SourcePolicy is trusted host configuration, not user/model/source input. Origins
are an exact tuple of canonical `https://host` strings. It also requires explicit
positive byte/chunk/timeout/JSON depth/node limits and a redirect limit (0..10).
Empty/unconfigured origins fail closed; no production target or default budget.
The fixture values are test parameters only, not recommended production limits.

URL checking rejects credentials/userinfo, fragments, backslashes, controls,
unexpected ports, numeric/IP literals, single-label hosts, trailing dots, IDN or
noncanonical host forms. Canonical explicit :443 becomes default HTTPS. Each
redirect is checked before resolution and every DNS answer must contain only
public IPs. Private, loopback, link-local, shared/metadata, multicast, unspecified,
reserved, mapped/transition/translation address forms are denied. Every hop
receives a PinnedTarget with fixed hostname, validated address set, byte limit and
one shared monotonic deadline. A synthetic response must have the exact requested
URL and a public peer from that set. Auto-followed redirects and cycles are denied.
Redirect bodies are never consumed; responses are closed. No cookies, auth or
ambient proxy/credential fields are accepted by this transport input.

**This is executable policy and injected-response validation, not a live SSRF
protection claim.** Injected Python is trusted synthetic fixture code, not a
sandbox. It must cooperate with asyncio cancellation and close its own resources
if cancelled before returning a response. A peer assertion cannot prove DNS/socket
pinning or TLS SNI/certificate validation. Consequently production fetch is always
disabled; there is no resolver or networking library fallback. The existing JWKS
client is purpose-specific and was not copied into a second generic HTTP framework.

Streaming enforces byte and chunk counts even without Content-Length, exact length
when present, total timeout across DNS/transport/body/redirects, explicit Event
cancellation and native task cancellation. Bodies close on normal/error/cancel.
The caller's task cancellation propagates; explicit Event cancellation raises
`cancelled`. No retry follows timeout or any unknown transport result.

Only UTF-8 text/plain and application/json with optional UTF-8 charset and identity
encoding are accepted. Invalid UTF-8, NUL/empty bodies, duplicate JSON keys,
non-finite numbers, unpaired surrogate escapes, depth/node/size excess and malformed
JSON fail explicitly. Original bytes are retained; no HTML, script, entity
expansion, commands, translation or prompt construction occurs. JSON depth is
checked before decoding; bytes bound memory and nodes bound decoded traversal.
Parse entry is pure bounded local processing and has no asynchronous cancel point;
streaming yields between chunks so deadline and cancellation can run.

No automatic HTML scraping is claimed. Accepted future production source adapters
must use an explicitly allowed format/field mapping; never silently infer expiry,
place or eligibility from missing metadata or search summaries.

## Evidence

See [evidence/REPORT.md](evidence/REPORT.md) for fixed-source hashes, author checks,
known limitations and UNRUN layers. Independent Review/Testing remain pending.
