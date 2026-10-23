# Root verified-session opt-in consumption

Source `CJ-AUTH-SESSION-BINDING@0.1.0-rc.1`, exact AUTH
`a82e7fe0b22e990cba697b1ab8c668b85c502d53`, supplied independent source gates PASS
by Main. `session_auth_pins.json` fixes eight runtime file hashes; exporter reads
only fixed Git blobs. No copied verifier/checker/types, token minting, provider
implementation, schema, permissions or auth.sessions query is supplied by root.

Two explicit trusted Python host entry points are added to composition.py:

- `build_verified_session_checker(environment, jwt_configuration, verification_keys,
  session_access_provider)` (all keyword-only). Local-only, canonical
  JWTConfiguration with explicit SUPABASE_ACCESS_RC1. Returns original
  SessionAdmissionChecker(PyJWTVerifier(...), provider). No automatic token/profile
  detection. None keys/provider stays canonical UNKNOWN; malformed host object or
  principal-only evaluate(provider) is rejected, never adapted into session facts.
- `with_verified_session_read(checker, token, max_response_bytes, project)` (all
  keyword-only). Requires exact canonical SessionAdmissionChecker and explicit
 1..1048576 output cap. Creates a NEW original ProtectedReadBoundary per call and
  calls with_read_context using the ORIGINAL token and trusted synchronous final
  bytes callback. No cached session verdict or shared active read context. Callback
  owns authorized read/projection/BASE encoding and may recheck current context;
  final native admission must pass after those complete bytes.

Canonical source public verifier.verify_session obtains VerifiedSessionBinding
ONLY from verified claims in its original single verification flow. Root never
parses caller session_id/owner/email or reconstructs binding. Provider receives
that exact binding and must return original SessionAccessFacts(binding,
CJAccessFacts, session_active); current session AND member/email/invited remain
required. The provider must be the SAME accepted authority's current session and
access lookup, not a second membership store or a JWT-claims allow callback.
Real endpoint/table/role/query/credentials stay unset until a target is approved.

SessionAdmissionChecker inherits AdmissionChecker and its check(token) returns the
original AdmissionDecision shape, so canonical ProtectedReadBoundary consumes it
without a type bridge. check_session additionally offers binding only if ALLOWED;
that internal metadata is not a storage scope or permission capability.
Same issuer/subject/audience keeps stable data scope across A/B sessions/refresh;
no sid/iat/exp-derived new user/budget partition. Revoked A does not revoke B.
Mismatched late facts for another sid or token-time snapshot are UNKNOWN; a
provider returning stale but identically bound facts cannot be magically detected
here. Real authority freshness/atomic revocation remains that future host's duty.

Old source build_auth and root build_message_boundary/create_composed_app defaults
are unchanged. Existing manifests retain f3/8b. Source a82 changes admission.py /
jwt_adapter.py hashes, so this opt-in export must NOT silently replace those old
packages in a running legacy host. Later business-consumer cohosting requires an
explicit accepted dependency-pin/profile integration, never alias/hash bypass.
This patch does not enable FEAS or C2; default FEAS503 and the C2 resource package
are unchanged. No business write may use this read helper as a permission, rollback
proof or automatic retry: original possibly committed actions still reconcile by
original ID under their canonical domain lifetime.

Validation is actual root trace/error/ASGI **fixture-only protected route** invoking
these two root functions and the real canonical signed verifier/checker/read
context. It publishes no new product REST path/OpenAPI/model. Eight new cases plus
two old default regressions are in evidence/verified-session-opt-in/REPORT.md.
Synthetic locally signed token/session/current-facts fixture is explicit; no real
Supabase/session deletion/JWKS service, DB/network HTTP/Keychain/device/provider,
production permission or C2 acceptance is claimed. Source13/52 evidence is reused,
not rerun. Real host authority and existing business-factory integration remain
separate gates. No producer/SDK/SQL/permission/OpenAPI/generated/C2 changes.
