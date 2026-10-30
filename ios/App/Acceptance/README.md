# Shell structure acceptance (#157)

Run on an available iOS 17.5 simulator with Xcode's native XCTest input:

```sh
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
python3 -B ios/App/Acceptance/check_shell_structure.py \
  --simulator '<iOS-17.5-UDID>' --output '<new-directory-outside-repository>'
```

The script first tests the ordinary App entry and actual CJShell, then builds a
separate, visibly labelled synthetic host using the same ShellView and public
readonly MemoryClient. Both run in the isolated `space.go2china.shell.acceptance`
bundle, preserving the development App's data and keys. The synthetic server
binds only loopback, returns empty/failing memory reads, audits requests, and
rejects writes. It supplies no real account, token, cloud data or model access.

The four XCTest methods cover:

- Four tabs and their order in both languages; ordinary App language navigation,
  typed draft preservation and persisted language after relaunch.
- Account, language, help and privacy entry reachability with unconfigured,
  empty and failed memory views in both languages; account stays unverified.
- Language changes preserve synthetic business references, draft revision and
  navigation, with no extra memory requests or writes.
- Plugins show the existing unavailable description, expose no pretend tool
  buttons, make no extra requests, and show no system permission prompt.

The generated Xcode projects, results, logs and screenshots remain in the output
directory. A PASS requires both variants, all four tests, and zero failed or
skipped tests in the native result summaries. Prior output directories cannot be
overwritten. Screenshot attachments are retained inside each `.xcresult`.

`ShellFixtureApp.swift` and `ShellStructureUITests.swift` are referenced only by
these external test projects. They are absent from the repository App target and
excluded from the macOS development-configuration package. The ordinary App,
Release behavior, CJAuth and production write gates are unchanged.

This verifies UI structure and local fixture behavior. It does not approve help,
privacy or support wording (#159), prove real authentication/storage, or replace
the separate accessibility/state suite below or real VoiceOver/device acceptance (L3 #29).

## Accessibility and state samples (#158)

Use `--suite accessibility` for the ordinary App's complete system accessibility
checks on the four roots and language selection in both languages, plus the labelled fixture's maximum text, assistant
states, readonly Trip/memory states, long content and keyboard scenarios. Five
XCTest methods must pass with no skips; keyboard cases type and retain mixed
Chinese/English text in the Chinese UI and English text in the English UI:

```sh
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
python3 -B ios/App/Acceptance/check_shell_structure.py --suite accessibility \
  --simulator '<iOS-17.5-UDID>' --output '<new-external-evidence-directory>' \
  --build-dir '<external-reusable-build-cache>'
```

`--build-dir` is optional. Reusing compiler outputs does not overwrite previous
reports or native test results. Verbose Xcode sysdiagnose collection is disabled
because it can hang after a failed audit; the audit failure, XCTest output,
screenshots and xcresult still remain and still fail the run. The audit handler
returns false for every issue: nothing is filtered or accepted as an exception.

The fixture's Trip client uses the public readonly initializer, memory-only
synthetic session material, no pending store and no TripLiveWrites. Its memory
client is also readonly. Loading responses wait for an explicit test release;
all observed business requests must remain GETs. Assistant state and long-text
samples are presentation data, not evidence of a real model or backend outcome.

The physical VoiceOver listening, focus and activation checks remain UNRUN under
L3 #29, linked from #7/#158 per ADR-0007. Apple states that VoiceOver is not
available in Simulator; system accessibility audits do not replace it:
[Apple accessibility testing](https://developer.apple.com/documentation/accessibility/performing-accessibility-testing-for-your-app).

## Message sending and recovery (#164)

`check_messages.py` uses the actual App in a separate Simulator bundle, the signed
`app_from_environment` entry, a fresh private PG cluster and Simulator Keychain.
It does not inject a history configuration or bypass runtime roles. The formal
local entry must expose configured history routes (prerequisite #198); a 503 is
an acceptance failure, not an empty history.

```sh
CJ_PG_BINDIR='<PostgreSQL-17-bin>' uv run --locked python -B ios/App/Acceptance/check_messages.py \
  --simulator '<iOS-17.5-UDID>' --output '<new-external-evidence-directory>' \
  --build-dir '<external-reusable-build-cache>'
```

The six Debug cases cover both languages: actual send, conversation/message
pagination, language stability, encrypted unsent draft reopening, and unknown
responses injected before/after real commit. A restored unaccepted original
requires a fresh status read and explicit confirmation before the exact ID/bytes
are submitted again. A committed original is recovered by query without another
POST. A seventh Release case requires no development sending capability or API
requests. The test fixture provisions conversations through the existing server
API; the App's new write capability remains limited to message POST.

`--diagnostic-test <method>` runs only one named scenario and reports PARTIAL_PASS
on success; it cannot establish the complete acceptance. Reports retain runtime
source hashes, native results/screenshots, DB request/receipt proofs and token /
plaintext-draft scans. Before/after 503 faults are controlled local injections,
not evidence of a real external-service outage. No OTP, cloud service, paid model,
physical device or production deployment is involved.

## Protected original RUN and draft outcomes (#167 / #212)

`check_runs.py` runs one named native case per fresh private PostgreSQL cluster and
new development subjects. It requires `--run-context` and `--diagnostic-test`;
periods/budgets are never silently generated by the host. Follow
[LOCAL-RUN](../../../backend/cj_api/LOCAL-RUN.md) for an explicit CJ-LOCAL-RUN@1 file,
unit provider_call, FakeProvider only. Budget1 covers two ordinary messages (the
second is refused before answer) or one consider_trip message (draft refused).
Budget2 covers successful answer/draft and provider fault cases.

The driver invokes the real operator CLI for init-budget, put-needs and bind-needs;
API and run_once load the same profile. Only provider output/fault timing is
controlled by a FakeProvider subclass. No ledger resets, quota monkeypatches,
replacement repositories or manufactured HTTP refusal responses are used.
Each original is read after App restoration and a real worker CLI restart, with
unchanged ledger fingerprint, exposure and call counts. Cross-account reads must
be refused. Native accessibility audits use `.all` and accept no issues.

```sh
CJ_PG_BINDIR='<PostgreSQL-17-bin>' uv run --locked python -B ios/App/Acceptance/check_runs.py \
  --run-context '<explicit-context-file>' --diagnostic-test testDraftBudgetEnglish \
  --simulator '<iOS-17.5-UDID>' --output '<new-external-evidence-directory>' \
  --build-dir '<external-build-cache>'
```

Each named case remains PARTIAL_PASS until the complete required matrix is
independently aggregated. Preserve every historical FAIL and xcresult. Real tools,
real models/fees, cloud, physical VoiceOver/device and release remain separate.

Complete matrix (23 named cases; each gets a fresh private DB and new subjects):

```sh
CJ_PG_BINDIR='<PostgreSQL-17-bin>' uv run --locked python -B ios/App/Acceptance/check_run_budget.py \
  --budget-one-context '<explicit-budget1-context>' --budget-two-context '<explicit-budget2-context>' \
  --simulator '<iOS-17.5-UDID>' --output '<new-matrix-evidence-directory>' \
  --build-dir '<external-build-cache>'
```

The orchestrator retains every prior case, adds bilingual quota and provider-unknown
checks, pins the clean Git head and source hashes, and stops at any failed child.
A producer `unavailable` stream is retained as unknown with hidden text; only one
explicit original snapshot read may recover it after matching raw producer evidence,
with unchanged POST/provider/ledger. A refused stable read fails the case. No
automatic generation retry or v1 draft-status fallback is permitted.


## Registered @2 App acceptance (#244)

`check_registered_runs.py` consumes explicit `CJ-LOCAL-RUN@2` budget1/budget2
operator files (`output_limits` for model/tool/memory). It reuses #167's native
budget/unknown/stop and original recovery UI; the new assertions inspect actual
registered profile/requirement/binding/operation rows, IDs and immutable byte
fingerprints before/after worker CLI restart and App reopening. The original @1
matrix remains available through `check_run_budget.py`.

The twelve named @2 cases cover bilingual answer/draft denial, unknown and stop,
actual account switch/revocation, real signed-token expiry, and Release0 requests.
Revocation edits only the isolated development invitation file. Expiry waits for
an official one-minute development token and verifies actual API401; it does not
inject an HTTP rejection. Restoration uses the same canonical subject and never
reinitializes quotas or changes original periods/attempts. All AX issues remain
failures; logs/App files are checked for every minted token, key and plaintext
original. Real models/tools/fees/cloud/device acceptance remains separate.

```sh
CJ_PG_BINDIR='<PostgreSQL-17-bin>' uv run --locked python -B ios/App/Acceptance/check_registered_runs.py \
  --budget-one-context '<explicit-registered-budget1-context>' \
  --budget-two-context '<explicit-registered-budget2-context>' \
  --simulator '<iOS-17.5-UDID>' --output '<new-external-evidence-directory>' \
  --build-dir '<external-build-cache>'
```

`--case` runs one diagnostic and records PARTIAL_PASS only. Retain prior FAIL,
original reports and xcresults; a matrix PASS requires the complete named set.
