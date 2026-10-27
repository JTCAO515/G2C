# CJ-012 P2 secret/body response boundary repair

Parent `9b117260a22e9e4933ea412831902764be8996c5`. Author repair checks PASS;
original independent Review/Testing fixed-head recheck PENDING. Parent remains
HOLD until those roles accept the repair. Only PLACE scope is changed.

## Failure and minimal fix

Strict `_decode` rejects duplicate keys and truncated/invalid JSON. The parent
`_secret_in` converted inspection exceptions to False, allowing recoverable
Unicode-escaped synthetic credentials into TransportResult.response.body. A
subsequent parse failure did not remove the already exposed raw body.

First actual source write: backend/place/cj_place/https_transport.py. Decode
failure now raises fixed internal response_secret_check_unavailable; fetch returns
unknown without Response/body. No raw error/prose is exposed. Only200 bodies are
inspected: non-200 status handling already discards every header/body and remains
unchanged. Literal/decoded echo remains credential_echo_rejected with no body.

No regex attempts to enumerate encodings, no fail-open inspection result. An
uninspectable body is not evidence of absent sensitive data. Valid inspectable
nonsecret JSON is returned byte-for-byte; the original parser, public models,
UTC/source binding, endpoint/coordinate precision, execute and authentication /
usage/dispatch authority are unchanged. Supported profile/limitations updated in
[HTTPS-TRANSPORT.md](../../../../contracts/place/HTTPS-TRANSPORT.md).

## Exact original probes and real private TLS verification

The original file is copied byte-for-byte to
backend/place/tests/secret_echo_checks.py and cmp-verified against:
`<local>/Documents/Codex/2026-10-21/cj-testing/CJ-012-https-transport/secret_echo_checks.py`.
Its original secret-echo-probes.log remains untouched. Both tests use the actual
private TLS response/transport boundary, not only a direct helper call.

- [before.log](before.log): exact two probes reproduced **2 FAIL** on parent9b;
  retained without modification. Duplicate-key and truncated escaped sentinel
  each escaped through Response.body.
- [original-probes-after.log](original-probes-after.log): the same **2 PASS**
  after repair; neither returns a Response.
- [body-controls.log](body-controls.log): **2 methods PASS**: exact valid source
  bytes and binding/time preserved through transport→original parser; eight
  uninspectable non-literal-secret body variants also produce unknown/no Response
  (duplicate keys, truncation, invalid UTF-8, unsupported null/list roots, invalid
  Unicode surrogate, extreme exponent and depth). No claim to detect all secret
  transforms is made.
- [affected-checks.log](affected-checks.log): **4 methods PASS**, covering all
  four endpoints with exact original query+injected key and parse chain, literal /
  escaped credential echoes/no logging,302/429 handling, and changed malformed
  body behavior. The original malformed-body test previously required a received
  raw body before parser rejection; it is explicitly strengthened to require
  unknown/no body at the lower boundary. Other parent tests are unchanged.

Python3.14.7. All credentials/data are synthetic. Existing private TLS fixtures
bind numeric127.0.0.1 ephemeral ports, trust only their disposable cert in a
private client context, close servers and clean only that run's fixture files.
No system trust, provider DNS/request, real key/env/credential, old DB/Keychain,
fee, root API, shared lock or permissions changed. No new dependency.

```sh
PYTHONPATH=backend/place:backend/place/tests python3.14 -B backend/place/tests/secret_echo_checks.py
PYTHONPATH=backend/place:backend/place/tests python3.14 -B backend/place/tests/secret_body_controls.py
PYTHONPATH=backend/place:backend/place/tests python3.14 -B -m unittest -v https_transport_checks.LoopbackTLSTests.test_actual_tls_bytes_parse_for_all_four_fixed_endpoints https_transport_checks.LoopbackTLSTests.test_literal_and_json_escaped_secret_echo_are_not_returned_or_logged https_transport_checks.LoopbackTLSTests.test_redirect_and_http_failure_are_received_without_follow_or_secret https_transport_checks.LoopbackTLSTests.test_malformed_actual_body_fails_closed_before_response_boundary
```

## Preservation and next

Parent9b source/19PASS and all earlier initial/time/exponent FAIL/PASS artifacts
remain retained. The old evidence/audit.json files are historical records, not
updated to imply they describe this source. No unrelated parser suite, provider
semantics, shared domain or global test suite was rerun. The same pure parser /
model files compare byte-identically to parent. This source remains an
unregistered low-level candidate; execute is unavailable and canonical accepted
dispatch/current AUTH/claim/cancel/trusted receipt seam is still missing.

Next is original Review/Testing replay at the new fixed commit. No self-approval,
push/PR/merge/deploy, Issue/HANDOFF edit or messages to other threads. Real
provider/account/fees/cities/root/I acceptance remains UNRUN.
