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
or guessed generations are not substituted. The issued interval is current,
at most 600 seconds, and entirely inside one Beijing 08:00–23:00 day.

`ReadOnlyApp` wraps the existing pinned external native controller. Its caller
must supply the approved lease reader, a current clock and an installed-App
and SDK verifier. The verifier must compare the actual installed binary and
the native-controller source/artifact with the approved metadata; passing an
App dictionary is not evidence of an installed App. The wrapper revalidates
the original grant, artifact, bundle and locale-specific device before **each**
native dispatch, including the two taps used to open history. It passes the
same interval to the native dispatch-time fence. A failed verification or
unknown ACK leaves the wrapper stopped; it does not replay the action.

Only fixed read actions are exposed: launch in the bound language, activate,
snapshot, menu/history, Earlier, up/down scroll, complete `audit_all` and stop.
The existing native audit retains `.all` without a filtering closure and still
requires an already usable ordinary Home. No generic tap/type, sign-in,
new-chat or send command is exposed by this adapter.

`select_existing_default` currently fails closed. The old App's AX history rows
do not expose the business conversation ID; a title or ordinal must not be
treated as that ID. A separately verified mapping must be agreed with B before
this selection can be enabled. This limitation is explicit rather than a
partial successful history qualification.

Local unit controls cover packet rejection and native-dispatch boundaries.
They are not an actual installed-App audit, complete real history, Hong Kong
qualification, C's fourteen checks, physical-device acceptance or permission to
upload TestFlight. Original accessibility failures remain open in #1100.
