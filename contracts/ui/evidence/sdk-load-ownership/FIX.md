# SDK load settlement fix with canonical public ownership

Input CJ007 ab37bae6f91796f9156e29a18213eb250f3fda0c exposes existing ownsOperation unchanged. Normal intake merge a19db476ba81827fd2c281f96ca9fe9e06212761 preserves b24 Memory purpose. Visibility/comment conflict in SessionLifecycle was resolved using the entire exact ab37 file; no domain logic authored here. The earlier e18/5d failure log remains historical.

AccountHost captures trusted verification generation/ID before synchronous load, and rechecks these plus its UI/private request after load/error. Only catch settlement uses public ownsOperation: a displaced/retired original load retires its own wait/bookkeeping and publishes stale/idle, without reading/adopting/clearing or error-projecting replacement B. Same original blocked operation is still owned and surfaces blocked. isCurrent remains the prerequisite for usable results. No exception-name test or private SessionOperation/CJSession field is used; no business grant follows from ownership.

This change is limited to restore-load settlement. Clear paths remain unchanged: a successful explicit clear retires its token normally and retains its cleared result, not a fabricated B/replacement result.

24 relevant test functions PASS: IndependentSDKHostLoadTests4 + AccountSDKSessionHostTests11 + LocalSessionHostTests9. Replacement probe covers return/throw and changed/unchanged verified identity (four argument cases); B exact bytes/lifecycle/current operation stay healthy, host is idle/not restoring. Controls show storageUnavailable AND a same-original staleOperation-named failure still blocked. Explicit host clear inside load keeps cleared. Existing SDK/unknown/persistence/reentry checks remain green. No old32 full rerun; no device/network/Keychain.

The first git status reported an unrelated Xcode Package.resolved modified marker. Before intake its bytes and diff were captured in /tmp; the captured diff was empty. Captured bytes, pre-intake5d, incomingab37 and final tree all match SHA25669e139139d2a150b3e24f88d29add8bb9344f281801ea95ab9f7e5eec137af97. The marker later disappeared; its transient cause is UNKNOWN, not attributed to a content merge. No reset/cleanup was used. No CJShell Package/API path change is part of this host fix; subsequent pin alignment must be a separate commit.

Original product baseline e18 plus regression archive5d remain ancestors. Independent Review/Testing must decide closure; author PASS is not that closure. Public dependency is a separate producer input, not an ownership authority fork.
