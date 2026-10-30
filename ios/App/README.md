# DEBUG simulator Trip host

This App keeps the ordinary disconnected shell in Release, on physical devices, or
when either explicit development input is missing/invalid. Only a DEBUG simulator
build reads:

- `G2C_DEV_API_BASE_URL`: exactly `http://127.0.0.1:<port>` (no credentials, query,
  fragment or non-root path), checked with `MessageEndpoint.allowLoopbackHTTP`.
- `G2C_DEV_TOKEN`: a local token from `scripts/dev_auth.py token`, supplied via
  `SIMCTL_CHILD_`; memory only, never persisted or written to Keychain/logs.
- Optional `G2C_DEV_PROPOSAL_ID`: preselects an existing local fixture proposal.

This is a trusted operator fixture root, not a production identity verifier. Local
dev issuer/audience/subject metadata only partitions simulator storage; the actual
API verifies the JWT and ownership on every request. Renewing a token for the same
local subject preserves the namespace; another subject gets a separate namespace.
No Supabase session or production CJAuth path is changed.

`SessionPersistence` is memory-only. `ScopedMessageKeyProvider` manages a random
simulator-Keychain key, separate from the token. `TripPendingStore` lives under the
App's Application Support `G2CDevelopmentTrip/<environment>/<account>` directory
(0700). Missing keys with existing data fail closed; keys/records are never erased
to recover availability. Restart restores original actions for query only.

The explicit host grants `TripLiveWrites` for the signed `app_from_environment`
fixture. Other tabs stay unconfigured. The existing proposal screen keeps its
decision/result card after an action ID is assigned; an original action cannot be
replaced by re-reading the draft while its outcome is unknown.
After that original reaches a verified terminal outcome, a different explicitly
selected proposal can be read and decided without removing the historical record.

## Local account flow (#161)

An explicit `G2C_DEV_ACCOUNT_MODE=1` selects the account flow instead of the legacy
direct Trip fixture above. It still requires the exact loopback base URL. Optional
`G2C_DEV_ACCOUNTS` is a JSON object from display label to operator-supplied local
token; these inputs remain in memory. Omit it (or use `{}`) to test restoration
without injecting any token. No production login, password collection or OTP is
enabled. Account controls remain inside Memory → Account.

Each sign-in first clears visible private content and retires the previous request.
A protected `GET /v1/message-receipts` verifies current server identity and invitation;
only then does the host save credential bytes using `KeychainSessionStore` in its
explicit endpoint-specific namespace (`M1.Development.Active`). No token is written
to UserDefaults or App files. The Trip host borrows the verified session operation;
invalidating Trip views does not clear the account's Keychain credential.

Restore is a user action. Relaunch does not automatically load credentials. Logout
stores the existing nonsecret block marker, so relaunch/restore cannot revive a
logged-out account. Network uncertainty keeps saved credentials and grants no new
private view. Backgrounding fences private content; foreground revalidates only
an already-active in-memory session, without an automatic Keychain load. Account
switches and logout invalidate outstanding results before callbacks can publish.

Native acceptance uses the actual App, a new private PG with the registered
migrations, and the signed local API. Its external XCTest project has an isolated
bundle/Keychain namespace and tests English/Chinese login, switching, logout,
relaunch without token injection, denied/expired/offline states and delayed old
responses. A Release variant receives the same development inputs but must remain
disconnected. The harness scans App files for token bytes; no secrets or runtime
databases belong in the repository.

```sh
CJ_PG_BINDIR='<PG17>/bin' uv run --locked python -B \
  ios/App/Acceptance/check_development_accounts.py \
  --simulator '<iOS-17.5-UDID>' --output '<external-output-directory>'
```

## Reproduce on iOS 17.5

Choose an available iOS 17.5 simulator UDID and a build/evidence directory outside
the repository. The script uses Xcode's native XCTest input, so Simulator.app and
AXe are not required. It generates an external UI-test project referencing the
actual App sources/packages; it does not add a test target to the repository project.

```sh
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
CJ_PG_BINDIR=/opt/homebrew/opt/postgresql@17/bin \
uv run --locked python -B scripts/check_ios_trip_confirm.py \
  --simulator '<iOS-17.5-UDID>' --output '<external-output-directory>'
```

The harness runs Debug/Release configuration tests and builds, then uses a fresh
private PG cluster, migrations, dedicated temporary signing keys and FakeProvider.
Actual UI clicks cover English/Chinese acceptance and formal detail version 1,
rejection without a Trip, committed-response loss followed by offline restart and
original-action reconciliation (exactly one `act`), and foreign-user refusal.
It also audits token absence in App files, pending-directory permissions, and a
Release App launched with all development variables that still remains disconnected.
The same-account regression also confirms a new proposal after restart and original
receipt reconciliation, while retaining the old action and formal Trip.

Xcode supplies **simulator** embedded entitlements and ad-hoc signing for Debug;
do not manually sign the host process with restricted iOS entitlements. The
entitlements setting applies only to the Debug simulator SDK. No Apple account,
certificate, provisioning profile or system setting is changed.

Output includes `report.json`, build/test logs, `.xcresult` and screenshots such as
`en-formal-detail.png`, `zh-formal-detail.png`, `unknown-offline-restart.png` and
`release-disconnected.png`. A failed/incomplete driver or scenario makes the script
fail; previous reports are retained. Evidence stays outside Git and is summarized
in the PR. No screenshots, tokens, keys or runtime databases belong in the repo.

The API/PG fixtures stop at the end. The simulator App is terminated; its encrypted
test records/Keychain keys remain in isolated development namespaces for inspection.
The harness does not delete unrelated App data or clear the simulator Keychain.

For the complete PG suite, also set `CJ_PG16_BINDIR` and `CJ_PG17_BINDIR` to the
installed major-specific binaries: the RUN suite deliberately requires PG16.
Do not change version assertions or solver budgets to make tests pass.

## Remaining gates

This proves the local simulator fixture flow, not real OTP, real-model quality,
physical-device, cloud, backup restoration or release acceptance. MESSAGE sending
remains unavailable. Follow [ADR-0007](../../docs/adr/0007-issue-closure-workflow.md)
for independent Codex review, green CI on the exact head, normal merge, and main-CI
verification before automatically continuing the queue. The current action and
blockers are in [HANDOFF.md](../../HANDOFF.md). Continue until M1 is complete or a
repository-level stop applies. MESSAGE activation still requires the separate
[ADR-0008](../../docs/adr/0008-message-send-permit.md) and
[MESSAGE-SEND@1](../../contracts/message/SEND-PERMIT.md) conditions; automatic
continuation does not authorize real OTP, models, devices, cloud resources or release.

## Explicit local Memory composition (#228 candidate)

`G2C_DEV_MEMORY_PROFILE` opts the DEBUG simulator host into manual Memory using
the current signed account. Its JSON is the same selected identity profile shape
used by `local-memory-policy.1`: `subjects`, `slots` (kind, collection_allowed,
semantic_resolved), `extents`, `context_ids`. The operator supplies matching
`CJ_LOCAL_MEMORY_POLICY` to the API. App choices convey no server authority;
server policy, consent and owner checks remain decisive. A missing profile keeps
Memory unconfigured; an invalid explicit profile fails composition visibly.
Release and physical devices do not compile this write initializer/root.

Manual saves retain their exact original operation and bytes before dispatch in
an account-scoped encrypted Memory journal. Definitive server failures use a
separate encrypted adjacent journal; old ciphertext and IDs remain unchanged.
A reopened failed original stays rejected when its receipt is absent, while a
missing receipt without that failure record remains unknown. A distinct explicit
new save is allowed after definite failure; the original is never resent. Up to three optional questions reuse this form
and can be skipped to chat. #227 effective-context consumption remains separate.
The native harness is `ios/App/Acceptance/check_memories.py` with explicit
`--run-context`, `--simulator`, external `--output` and `--build-dir`; it runs the
formal signed local API, fresh private PG and `run_once`/FakeProvider with an
explicit `local-memory-run.1` policy. Current-scope choices identify the actual
MESSAGE conversation, never a formal Trip. The matrix also verifies two owned
conversations and an actual refusal followed by operator policy reload and a
distinct new save. New L1
results are pending until actual reports exist; no real service is used.
