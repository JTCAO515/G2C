# CJ006 exact manual-client/shared repair consumption

Basec954541178162f29f81d03a5d60383408fcba7de and original25-function/iOS/single-c5 evidence remain intact. Both independent HOLD reports were read first: CJ-017-readonly-preview-client/REPORT.md (same-revision preparation) and CJ-009-readonly-preview-transport/REPORT.md (ordinary Host forwarding).

## Exact inputs and source compatibility

- Client preparation repairdb4885593825f726c6eeefe459e53529708b6d7d imported unchanged as a4cd594 (parent79).
- Shared ordinary-Host repair94c50ab6650e9defb0f7df6d7ccbb2bff250c947 imported unchanged as c5b32f8 from the specified isolated cj-009-preview-host-fix tree, not the newer9d/5d shared tree.
- Final client combinatione292f2073b27086b887b3f9abc9bc23969c013df imported unchanged as d5efe49. It changes tests/evidence/docs only; production source/Package/lock equaldb. Its preceding4c4d15 prep is not republished over the already exact94 import.

**No CJShell production source adjustment was necessary.** The public editor/prepare/cancel APIs used by the existing form remain compatible. Host/Package/lock bytes matchc954, exact current client subtree matchese292 and shared subtree matches94. c5 export/other module pins stay unchanged; the existing single-SDK graph is reused, not reconstructed. No new transport, fallback, provider, authority or permission was implemented in Shell.

## Host-specific before/after checks

Client-only host regression before intake: nested prepare at first/last source validation plus cancel/old-close case FAIL7 assertions (`preparation-before.txt`). The old outer work is deliberately unused; the callback-newer work sends0 requests and remains loading. Afterdb,4 targeted host functions/5 cases PASS (`preparation-after.txt`): callback-newer preparation runs once without the old caller, cancel retains original intent, old close cannot retire renewed entry, and edit/source ABA controls stay qualified positives.

Shared host regression before94: inject an ordinary Host header between the real PreviewTransport and actual shared NoRedirectTransport. Both same-origin synthetic.invalid and conflicting other.invalid reach the underlying in-process interceptor and show local success, FAIL4 assertions (`host-header-before.txt`). This proves forwarding of metadata, not actual DNS/URLSession behavior or server auth bypass.

Afterdb+94: **8 targeted host functions/11 cases PASS** (`combined-host-tests.txt`). Covers both nested preparation callback positions, cancel/old-close/new entry, source/editor ABA, normal no-Host closed-get→server diff/can_save=false success, legacy generic POST refusal, same/conflicting Host rejection with unchanged draft/version, and final shared-validator foreground/edit-ABA retirement. Only the affected cases were run; original25 was not rerun. Test transport injection stays internal and exercises the real closed Trip source, generated Client, actual editor and shared readonly capability, with no network.

## Exact original probes retained and replayed

Imported original IndependentPreparationTests.swift and IndependentPreviewHostTests.swift were compared byte-for-byte with the independent Testing snapshots; their hashes are in provenance.json. No original assertion was changed.

- Original preparation method replayed in the exact final client package:1 function PASS (`original-preparation-replay.txt`).
- Original Host method standalone shared-package setup was blocked by an outdated tracked Package.resolved missing the current Auth's supabase dependency under --disable-automatic-resolution (`shared-standalone-lock-failure.txt`). No lock/source/cache checkout was changed to resolve it.
- That self-contained original Host test was copied BYTE-EXACT into the authorized CJShell Tests area and replayed in the already valid c5 host graph:1 function PASS (`original-host-replay.txt`). This avoids a different SDK or dependency resolution and preserves the setup failure separately. This is author-side exact-probe replay, not the Main's independent acceptance gate.

Client's own e2927-method combination evidence, producer db19-method evidence and shared94 eleven-method evidence remain attributed upstream; they do not substitute for these actual host/probe results.

## Compilation and remaining gates

PASS: one unsigned arm64 iOS17 simulator-target CJShell build after both source repairs (`ios-build.txt`). e292 later added only docs/evidence/tests, so no redundant graph compile was run. The standalone probes subsequently compiled only their targeted macOS test contexts. Manifests/locks/export and host product code remain unchanged. Default other write gates, can_save=false and save/confirmation/lock/feasibility limitations are retained.

No real URLSession request, DNS/socket, account/credential activation, Keychain, SQL/PG, provider, App/simulator launch, device/VoiceOver, signing, deployment, save or full Issue22/I acceptance. The original two HOLDs remain pending Main's independent re-review; author passes do not lift them automatically. All old failure evidence andc954 are preserved.

Commands use established module-cache environment and --disable-sandbox/--disable-automatic-resolution. Host package scratch /tmp/cj006-sdk-host-build/cache /tmp/cj006-spm-cache with the8 named filters in combined-host-tests.txt. iOS uses existing /tmp/cj006-memory-ios, SDKROOT unset, arm64-apple-ios17.0-simulator/iPhoneSimulator27.1,target CJShell. Exact preparation probe uses CJManualPreviewClient with /tmp/cj006-preview-repair-probe; exact Host probe ultimately uses CJShell --filter IndependentPreviewHostTests. No unrelated full suite repeated.
