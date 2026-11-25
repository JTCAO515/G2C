# Read-only installed-App prequalification boundary

This is a separate adapter for B's `B-App-prequalification-lease.2`, not an
extension of the frozen `B-App-login-lease.1`. Its state is
`READ_ONLY_PREQUALIFICATION_ISSUED`; it grants neither business smoke nor release
qualification. No credential file is read, no text is typed, and no account or
conversation is created.

`validate_prequalification_lease` consumes original bytes, an independently
approved whole-file SHA256, the independently approved complete metadata and an
aware current time. App and SDK objects are compared as canonical JSON bytes
and separately hashed. It binds B's current source/image, two distinct simulator
UDIDs and exactly one Chinese and one English identity. Each identity retains
the actual subject, default conversation ID and **string** generation. Missing
or guessed generations are not substituted. The issued interval must contain the
current time and last at most 600 seconds. Under [JT’s decision](https://github.com/JTCAO515/G2C/issues/495#issuecomment-7042305501), it may start at any hour or cross midnight.

`ReadOnlyApp` wraps the existing pinned external native controller. Its caller
must supply the approved lease reader, a current clock and an installed-App
and SDK verifier. The verifier must compare the actual installed binary and
the native-controller source/artifact with the approved metadata; passing an
App dictionary is not evidence of an installed App. The wrapper revalidates
the original grant, artifact, bundle and locale-specific device before **each**
native dispatch, including the two taps used to open history. It passes the
same interval to the native dispatch-time fence. The read-only `snapshot` and
`audit_all` actions use the separate `snapshot_in_window` and
`audit_all_in_window` native operations, never the legacy diagnostic snapshot.
The native runner validates the current interval when it consumes the queued
operation, immediately before the AX read and screenshot, and before exporting
the screenshot. An expired interval produces a safe read-window rejection and
ends that scoped runner; it returns no partial nodes or screenshot proof. The
consumer also requires the original screenshot name and complete node/audit
proof before clearing its barrier. A failed verification or
unknown ACK leaves the wrapper stopped; it does not replay the action.

Only fixed read actions are exposed: launch in the bound language, activate,
snapshot, menu/history, Earlier, up/down scroll, complete `audit_all` and stop.
The existing native audit retains `.all` without a filtering closure and still
requires an already usable ordinary Home. No generic tap/type, sign-in,
new-chat or send command is exposed by this adapter.

The legacy `snapshot`, original login permission and `stop` cleanup remain
unchanged. The added operations require a newly verified complete SDK pin;
they do not upgrade an old issued package or fall back when its SDK lacks them.

`select_existing_default` currently fails closed. The old App's AX history rows
do not expose the business conversation ID; a title or ordinal must not be
treated as that ID. A separately verified mapping must be agreed with B before
this selection can be enabled. This limitation is explicit rather than a
partial successful history qualification.

Local unit controls cover packet rejection and native-dispatch boundaries.
They are not an actual installed-App audit, complete real history, Hong Kong
qualification, C's fourteen checks, physical-device acceptance or permission to
upload TestFlight. Original accessibility failures remain open in #1100.

The native regression below uses only the separate Debug driver host on a
task-owned simulator without an ordinary App installation. It checks a valid
scoped snapshot, legacy diagnostic compatibility, and queues each scoped read
until its interval expires. Both refusals must export no partial proof, preserve
the original request and keep the next-action barrier closed. It does not run an
ordinary Home audit or use an account or service:

```text
python3 -B ios/App/Acceptance/check_lio_read_window.py --simulator <owned-empty-simulator> --output <outside-repo-evidence> --build-dir <outside-repo-build>
```
