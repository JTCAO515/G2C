# CJ-034 pinned HTTPS primitive — author evidence

Date:2026-10-23 Asia/Shanghai. Parent/base for this increment:
`611c39814f7f8cd2c017de60be20a746237e6266`.
Original project base remains8deb696f8149b4f5aa70c767be6c3a263b036227.
Worktree cj-034-fact, branch cj/034-fact, original sole FACT owner. Parent was
clean before the first write. Candidate is fixed by the containing commit;
`source-sha256.json` binds current product/test/contract/lock bytes.

## Implementation and dependency choice

First new product source: `backend/fact/cj_fact/https_transport.py`.
PinnedHTTPSTransport is a single GET socket/TLS primitive consuming existing
SourcePolicy/PinnedTarget and returning the existing InjectedResponse carrier.
No API route, resolver, provider selector, permission type or dispatch switch.
The optional class is imported directly from its module and is not automatically
exported/registered by cj_fact. Acquisition's only source changes are docstrings;
its production fetch remains unconditionally closed. All611 time/range fixes and
old FAIL artifacts remain byte-identical.

Stdlib asyncio opens one numeric socket to the first validated address, without
DNS re-resolution. That already-connected socket is handed to TLS with original
hostname SNI/certificate checking; kernel peers are checked before/after TLS.
One attempt only, port443 on the public callable, no pool/proxy/cookies/auth/
ambient credential discovery. HTTP framing is delegated to h11==0.16.0, already
available in the local uv cache; module-local offline sync/lock, no root change.
Explicit header/wire/read/body/chunk limits and total monotonic deadline cover
connect/handshake/headers/body. Unconsumed responses have a close timer. Close and
cancel abort immediately, including before body iteration. Errors are safe codes;
a timeout/cancel/transport failure after sending GET can mean UNKNOWN delivery/
result and never grants retry, zero cost, usage settlement or RUN completion.

Primary references consulted (documentation reads only):
- [asyncio numeric sock_connect](https://docs.python.org/3.14/library/asyncio-eventloop.html#asyncio.loop.sock_connect)
- [asyncio streams, sock ownership and server_hostname](https://docs.python.org/3.14/library/asyncio-stream.html#asyncio.open_connection)
- [h11 events/framing/Connection limits](https://h11.readthedocs.io/en/stable/api.html)

Installed CPython3.14.7/OpenSSL3.6.4/h11 0.16.0 were actually inspected. Other Python/platform TLS
implementations and IPv6 live sockets are UNRUN. Explicit SSLContext is host-owned
trust config; tests load only their task fixture certificate. No system trust edit,
user credential read or external provider/public DNS request occurred.

## Real local evidence versus synthetic/policy evidence

Tests create only127.0.0.1 ephemeral TLS/raw handshake servers. A fixture self-signed
certificate/key is generated inside a0700 task tempdir, loaded into explicit test
contexts, and that exact test tempdir is removed at completion. No certificate/key
is tracked or logged. Real TLS uses the SAME private numeric-socket implementation
that the public callable invokes after validation. The fixture alone supplies the
private primitive's loopback address/ephemeral port. Public SourcePolicy and
transport callable still reject private/mixed IP sets before socket creation;
there is no public loopback override. This is trusted fixture Python, no sandbox.

Actual socket tests assert:
- captured SNI and Host equal weather.example.test; response URL remains original;
  actual TCP/TLS peer is127.0.0.1; exact fixed GET headers include no credentials;
  patching getaddrinfo to fail and setting proxy env values does not change success;
- untrusted/wrong-host certificates reject before HTTP; a test-only peer-metadata
  mutation rejects before HTTP (mutation is a guard negative, not kernel proof);
- real chunked/content-length/EOF framing, ambiguous/duplicate/malformed headers,
  compression, oversize, chunks, wire byte/read bounds, trailers and truncation;
- no redirect follow; close before starting body iteration yields remote EOF;
- stalled handshake/header/body deadlines, native cancellation in handshake/body,
  existing acquisition Event cancellation during actual fixture IO, and abandoned
  unread-response expiry all close the actual socket, observed by remote EOF;
- actual connection failure is bounded/safe and sock_connect is awaited once.

Public callable invalid target/policy, all-answer validation, first-address/no-
retry selection and production fetch closure are unit/guard checks. The first-
public-address case uses a mocked private exchange and makes NO public connection.
It is not real external pinning evidence. Event-cancel composition uses synthetic
DNS metadata8.8.8.8 but the fixture calls the private loopback primitive;8.8.8.8 is
never contacted, and no successful document/peer is fabricated for that path.

## Executed results, retained failure and correction

- `loopback-initial.txt`:13 methods PASS. Expected certificate rejection produced
  server asyncio ConnectionResetError diagnostics; no assertion failure. Later
  fixture captures only explicitly expected handshake-rejection diagnostics and
  fails on unexpected loop errors instead of hiding them.
- `loopback-expanded.txt`:17 methods PASS after real EOF, handshake cancel/timeout,
  peer guard and wire bounds were added.
- `loopback-final.txt`:19 methods run,18 PASS/1 FAIL. The new actual-connect-failure
  test assumed an immediate refusal; this macOS bound-but-not-listening socket
  instead reached the total timeout. Transport safely closed and did not retry.
  This is a fixture expectation error; no production code was changed afterward.
- `connect-failure-control.txt`:that one method PASS after accepting exactly the
  documented safe outcomes https_exchange_failed or timeout, while still asserting
  one awaited socket attempt and zero HTTP requests. The exact same bound local
  socket setup was retained; no alternate endpoint/identity or weakened retry check.
  Thus all19 unique current transport methods have passing evidence; a second full
  suite was not run solely to replace the retained FAIL log.
- `acquisition-compatibility.txt`:17 existing affected acquisition methods PASS.
  Original pure evidence/time/consumer checks are reused; no unrelated full rerun.

Module-local offline commands:

```sh
uv sync --offline --frozen --project backend/fact --python /opt/homebrew/bin/python3.14
PYTHONPATH=backend/fact:backend/fact/tests backend/fact/.venv/bin/python -B -m unittest test_https_transport -v
PYTHONPATH=backend/fact:backend/fact/tests backend/fact/.venv/bin/python -B -m unittest test_fact.AcquisitionTests -v
```

No listener remains after the tests. Fixture-created https tempdirs are gone;
module-local venv/uv cache are ordinary local dependencies. No DB, old account,
public business DNS/provider call, fee, deployment or shared configuration change.

## Remaining gates

Author-local candidate ready for original Review/Testing, not self-approved.
Production fetch remains CLOSED with no enable boolean. Actual public-source
availability/region/licensing/cache/retention, canonical AUTH/USAGE/RUN one-shot
current-admission/cancel/claim/unknown-receipt boundary, root wire, live provider,
public DNS/IPv6/real-network TLS behavior, App citation card, real bilingual/source
acceptance, CI/device/release and Issue16 I remain UNRUN/UNKNOWN. Low-level local
TLS evidence does not grant a business dispatch or settle costs. No new authority,
provider or permission choice was made for JT.
