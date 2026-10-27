# CJ-002 provider-entry P2 targeted repair

Parent fixed head: `50cd98fc200f21d81e9ff90bba7c91e82aa2b949`.
Original independent Testing: `<local>/Documents/Codex/2026-10-21/cj-testing/CJ-002-provider-entry/REPORT.md`.
This is author repair/self-test evidence, pending original independent gates. Real provider execution remains prohibited and UNRUN; workspace/region/endpoint/new credential handoff remains missing. JT Bailian balance-controlled test-spend authorization is unchanged.

## Changes

1. `provider_tls_context()` constructs `ssl.SSLContext(PROTOCOL_TLS_CLIENT)` directly and loads the already-pinned certifi CA bundle. It verifies hostname checking, CERT_REQUIRED and absent keylog_filename **before** passing that context to HTTPX. It does not call create_default_context, does not create/clear a keylog file, and does not change system trust. Existing HTTPX default CA authority (certifi) is preserved. SSLKEYLOGFILE cannot enable logging on this explicit context, even when set after module import.
2. `contains_secret` checks ordinary JSON escape tokens without requiring a complete JSON document. Up to six normalization passes detect ordinary Unicode escapes, escaped backslashes and mixed literal/escaped text; remaining escapes, ambiguous surrogate representations or inspection-size/depth overflow reject conservatively. Actual parsed ChatResponse fields still go through this check before appending, returning or DBOS completion persistence. Rejection returns only `SECRET_ECHO_REJECTED` with UNKNOWN cost, no response object. It does not rely on later structured-output validation. This is bounded JSON-escape inspection, not a claim to recognize every possible encoding.

No framework, dependency version, root configuration, global permission or live provider action changed. Original 17+3 and the prior 7 new-entry test groups were reused without rerun. Original FAIL and probe/log/results are untouched.

## Exact original probe and adjacent checks

`offline_security_probe.py` here is byte-identical to the independent probe (SHA-256 in result/manifest). It ran only against synthetic secrets/MockTransport, with sockets forbidden. Its new output is `offline-security-result.json`, stdout is `original-probe-rerun.log`.

The unchanged original probe **still exits 1**: its first check directly constructs *raw upstream* `httpx.AsyncHTTPTransport(trust_env=False)`, independently of our entry, and still reports ambient_TLS_keylog_enabled=true/file header created. This preserves the observed upstream behavior; we did not patch HTTPX or falsify that failure. Its actual provider_step section now reports escaped echo detected=true, outcome UNKNOWN, encoded response returned=false. Its own DBOS-at-rest scan remains false; no actual real-provider or at-rest leak is claimed.

`entry_security_regression.py` tests the repaired entry path, not the raw upstream default:

- Explicit verifying context under synthetic SSLKEYLOGFILE: keylog_filename=None, no keylog file created, actual HTTPX pool uses that exact context.
- Truncated/complete/nested/mixed Unicode escapes reject; harmless malformed JSON, ordinary safe JSON, Chinese/English and a harmless Unicode escape remain allowed. A beyond-bound normalization input rejects conservatively.
- Real installed DBOS + AgentScope/OpenAI SDK + MockTransport: four encoded-secret responses rejected with safe UNKNOWN receipts/no returned response; one adjacent safe response COMPLETE. All five actual provider-step transport constructions receive a verified keylog-disabled context; no synthetic keylog file appears and journal receipts contain no key.

Three targeted groups PASS, `entry-security-result.json` / `entry-security-regression.log`. This does not supersede independent Review/Testing or authorize real execution. The copied unmodified probe's aggregate exit remains 1 for the documented upstream raw-constructor check; only the repaired application path is claimed PASS.

Reproduce from the repository root using the existing isolated environment:

```sh
PYTHONPATH=spikes/runtime spikes/runtime/.venv/bin/python -B spikes/runtime/regressions/provider-p2/offline_security_probe.py
# expected aggregate exit 1 from raw HTTPX observation; inspect all fields
PYTHONPATH=spikes/runtime spikes/runtime/.venv/bin/python -B spikes/runtime/regressions/provider-p2/entry_security_regression.py
# expected exit 0, three targeted PASS groups
```

Both scripts recreate only fresh task-private temporary fixtures and remove those fixtures afterward; evidence files are retained. No original Testing files are written.
