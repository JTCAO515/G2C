# CJ-012 bounded HTTPS transport candidate

Parent: `80ba4ae5527875ce375d22f3439f8e3256e2c4d6`, clean before this authorized
continuation. Status: **CODE_READY / author transport checks PASS; independent
Review/Testing PENDING**. Source and evidence stay only in backend/place/** and
contracts/place/**; no other owner or root writes. First product source write:
backend/place/cj_place/https_transport.py. No messages sent to other threads.

## Delivered and actual evidence

Standard-library-only asynchronous fixed-origin/path/query HTTPS transport,
explicit expiring server credential configuration, final credentialed URL cap,
bounded header/framing/body reads, strict TLS/hostname, one monotonic original
query/credential deadline including close, cancellation/close/late failure
handling, no redirects/cookies/proxy/retries. Existing request/response classes,
UTC parser, IDs/coordinates, source metadata and closed execute are reused.
Public/negative semantics and limitations: [transport contract](../../../../contracts/place/HTTPS-TRANSPORT.md).

Python3.14.7 / OpenSSL3.6.4, installed stdlib. Fixture certificate generator:
/usr/bin/openssl, invoked only for disposable synthetic test TLS files.
No dependency/global/root-lock change or install was required.

- [initial-tests.log](initial-tests.log): **15 methods PASS**. The expected
  rejected TLS handshakes emitted server-side ConnectionResetError diagnostics;
  this initial log is retained unedited, not reported as a test failure or hidden.
- [candidate-tests.log](candidate-tests.log): **19 methods PASS** after adding
  synchronous-close failure, cancellation during close, late close and late
  connect checks. Expected test-server handshake reset diagnostics are captured
  only for the exact negative TLS test; unrelated loop diagnostics are delegated
  to the normal handler. All sensitive/error paths return safe fixed codes.
- [expiry-deadline-checks.log](expiry-deadline-checks.log): **4 methods PASS**
  after bounding the deadline by credential expiry as well as original query
  timeout/max-age. This includes expiry during call, pre-I/O rejection,
  slow-drip total timeout and late connect. Unchanged19-case evidence is reused
  for the unaffected paths; no extra full parser suite was rerun.

- [exact-query-check.log](exact-query-check.log): **1 method / four endpoints PASS**
  after strengthening the actual wire assertion to compare every exact original
  query pair plus the injected sentinel; path and parsed result binding checked.

The actual loopback TLS bytes pass into the original parser for search/detail /
walking/driving, retaining original binding and timestamp object. Tests check
exact outbound host/path/query and key injection, missing/expired/altered inputs,
URL byte cap, Content-Length/chunk/EOF body caps, header/framing/encoding errors,
truncation, malformed JSON -> original invalid_response, 302 no follow and429
-> original error taxonomy, no Cookie despite Set-Cookie, no proxy/environment
credential/keylog use, literal/JSON-escaped secret echo refusal, no secret in
request/credential/result repr or logs, TLS wrong hostname/untrusted issuer,
transport/close exception prose sanitization, close-abort and no retry after
cancellation/late/unknown. All provider data/key values are synthetic.

## Reproduce

Explicitly starts task-private numeric loopback TLS and requires the installed
openssl executable. It is not part of default test discovery:

```sh
PYTHONPATH=backend/place python3.14 -B backend/place/tests/https_transport_checks.py
```

The final expiry-specific delta was checked with:

```sh
PYTHONPATH=backend/place:backend/place/tests python3.14 -B -m unittest -v https_transport_checks.LoopbackTLSTests.test_expiry_during_call_drops_late_response https_transport_checks.LoopbackTLSTests.test_expired_missing_credentials_and_stale_future_time_do_not_dial https_transport_checks.LoopbackTLSTests.test_total_deadline_stops_slow_drip_and_no_retry https_transport_checks.LoopbackTLSTests.test_late_connect_return_after_timeout_cannot_send_request
```

Only the private _connect test seam is patched. The production dial has no
endpoint override and is independently inspected using AsyncMock (zero external
DNS/network). Each fake server binds127.0.0.1:0, closes on teardown; temporary TLS
keys are mode0600 inside a mode0700 task directory, loaded only by fixture contexts,
never system trust. Disposable fixtures are cleaned; no old data is touched.

## Evidence boundary and next

Original parser32+6, UTC13+4, original FAIL/time/exponent logs are retained and
reused; parser/runtime model files are unchanged. No real Gaode request/DNS,
account/key/env secret, fee, old DB, Keychain, external resource, new permission,
root API or AUTH/USAGE/RUN operation occurred. No transport registration/push/PR /
merge/deploy/Issue/HANDOFF update or child delegation occurred.

Low-level callable code is not authorization. Existing accepted dispatch-context,
current AUTH/shared claim/cancel fence, trusted scope/original-attempt/input and
receipt provenance public signatures remain undefined. No fake allow/Protocol /
wrapper replaces them. execute is still unconditionally unavailable. Real
provider compatibility/signature profile/cost/cities/I/root/device/CI/deployment
remain UNRUN. Next: original Main/Review/Testing consume the fixed candidate;
no author self-approval or real outbound activation.
