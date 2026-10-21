# CJ005 composition pin + generated nullable query repair

Repair base `d886677a805db51759a3116f8d2c0d4f3b8dddb3`; candidate is the commit containing this report, exact head reported after commit. Same original writer/branch. Requested project default gpt-6.1-sol/medium, effective UNKNOWN. No domain source, DB/security configuration, external resource or moving head imported.

## 1. Exact AUTH pin and intended behavior

Publish correctly stopped on one mismatched runtime blob. AUTH is now pinned to reviewed `f3c8e5074eb27de0de6fef6dd7558763cbcf4291`; MESSAGE remains `cec92299aa77e74baafba473ecf9db7b926fbe4e`. All eight consumed runtime paths remain in composition_pins.json. AUTH interface/admission/init and four MESSAGE files are byte unchanged; only jwt_adapter SHA changed from `05f4311c952315e0140f291516c653538dfbd063b8f4426c5ea75dbd4f034b3d` to `ede933a2af99965ecaa8e7d58b950fc51fe38232538dd825c4a23bcf6d85aad5`. All 8/8 were also compared to the exact local Publish Git object `0248290`; this is not a fresh remote-main assertion.

Read the actual diff: new JWTConfiguration.profile defaults STRICT_V1, with an optional Supabase profile; strict still requires nbf and scalar matching audience. Returned audience now uses configured audience; strict equality makes this equivalent for the consumed valid inputs. Interfaces and gate have no delta. New cj_auth/composition.py is not imported by this factory and is deliberately not among the eight consumed modules. PyJWT/crypto/root lock are unchanged.

The CJ005 factory explicitly accepts only JWTProfile.STRICT_V1 for this slice. Passing SUPABASE_ACCESS_RC1 refuses composition, not automatic activation; its real issuer/profile/claims/session/membership acceptance needs its own authorized integration. Three targeted tests use synthetic RSA tokens: default strict rejects absent nbf/list audience, explicit strict goes through the real verifier/gate/query, current invitation denial still blocks repository access, other profile and missing config/keys refuse. `evidence/pin-update/strict-factory-tests.txt`: PASS3.

Fixed export helper now places each AUTH+MESSAGE commit tuple in a separate clone-local `.local/composition-deps/<auth>-<message>/...` directory, preserving the old flat export and evidence instead of overwriting/refusing the newly selected version. check-composition.sh uses that same exact tuple. `evidence/pin-update/export.txt`: PASS8 hashes/export. Runtime hash protection is retained; no fallback to moving source, no weakening of pin checks.

## 2. Nullable receipt field: source fix and actual generated consumer

CJ009 correctly found the old Swift MessageReceiptQueryResponse contained request_id only. The fixed official generator1.14.2 warned `Schema "null" is not supported ... skipping` for the previous `anyOf: [$ref MessageReceipt, type:null]` property; byte-identical regeneration and the old four Swift tests did not exercise the missing field. Original d886677 logs remain and cannot be called query-consumer PASS. `evidence/pin-update/nullable-before.txt` reproduces the actual old generated module compile error: no member receipt.

Only the canonical OpenAPI was changed, then official Python/Swift generation rerun: receipt remains required, using `oneOf: [$ref MessageReceipt, {enum:[null]}]`. MessageReceipt is an object, so the two branches are disjoint and valid JSON payloads remain exactly object-or-explicit-null. No endpoint/body/ID/retry semantics or migrations changed. Missing receipt remains invalid; null is not-observed only and never permission to resend. Original schema proposal remains historical, never generator input.

Generated Swift now has a required nonoptional receiptPayload enum: `.MessageReceipt(Components.Schemas.MessageReceipt)` or `.case2(OpenAPIValueContainer)`. **The container branch is not itself proof of null. Consumers must require container.value == nil; any non-null fallback is invalid, not not-observed.** No alternative wire model or generated-source hand edit is supplied. Actual generated type consumer is `tests/generated_receipt_consumer.swift`, built/linked against CJAPI and executed with no transport/listener:

- PASS actual typed receipt fields are readable.
- PASS explicit JSON null is recognized by container.value == nil.
- PASS missing receipt throws DecodingError.keyNotFound(receipt), never becomes null.
- PASS a non-null generic fallback is explicitly rejected, never treated as not-observed.

Reproduce `scripts/check-generated-receipt.sh` (M5 arm64/macOS14 engineering target); log `evidence/pin-update/generated-receipt-consumer.txt`. Initial compiler cache permission and test's mistaken public property name are separately retained in nullable-compiler-cache-before.txt / consumer-property-name-before.txt; corrected cache location and actual runtime `.value` API, without generated hand edits or weakened checks.

Python generation represents the null branch as a None-valued enum, not the prior optional property. Its JSON serialization remains explicit null; direct generated-model consumers must not assume `model.receipt is None`. Swift initializers now require receipt and query consumers must use the new generated enum/null guard. Receive-only consumers and the JSON wire are unchanged. Main was notified for CJ009 consumer update; consumer confirmation and independent delta review/testing remain pending for this final head.

`evidence/pin-update/schema-python-parity.txt`: PASS old/new schema validity on object/null/missing/wrong-type examples, generated Python object/null round-trip and missing/wrong-type rejection. Targeted actual HTTP query positive/null/opaque-ID regression PASS1 in query-response-regression.txt. Official generation drift check PASS, no unsupported-null warning in new output, generation-check.txt. No full original15 or unrelated Swift4 rerun; unaffected evidence reused. This repair does not transform historical deficient query evidence into a pass.

## Limits and next

Both changes need fixed-head delta Review/Testing and Publish pin recheck before integration. Remaining real PostgreSQL/JWKS/provider/authoritative membership/session/atomic revocation/physical device/deployment gaps are unchanged, UNRUN. No source change to backend/auth or backend/message, no root README/brand/UI/official migration/old VP operation, no provider-profile activation, network listener, push, merge or deployment.
