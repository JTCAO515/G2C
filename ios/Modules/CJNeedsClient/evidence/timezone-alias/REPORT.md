# Timezone alias compatibility repair — author evidence

Repair base: `8c28bcb2facef0c76ebf8b997101c6b18d44f17f`.
Repair head: the commit containing this report. Branch `cj/013-needs-client`.
Only `ios/Modules/CJNeedsClient/**` is authored. Original main/dependency pins,
POST-disabled public construction and all other module boundaries remain unchanged.
Independent Review/Testing of this repair is PENDING.

## Reproduction

Fixed producer `c821b34d607016c6dbc1020c203621841f1a60e8` accepts `Etc/UTC`,
`US/Eastern` and `PRC` in destination/overseas/event timezones. The script
`check_producer.py` reads the exact Git object, invokes actual `Command` and
`validate_fields(complete=True)`, checks original strings/bytes and demonstrates
that empty/invalid zone names remain rejected by that producer. `producer.json`
is the actual result. No database, network or product service ran.

`before.txt` runs the new tests against unchanged 8c28 product code. It fails all
9 legal-alias cases: 3 form encodings, 3 actual official generated Client detail
reads and 3 generated exact historical revision reads. It additionally fails the
nonempty-but-unvalidated wire control (10 failures total). The absent/missing/
unknown/uncertain/empty-string control already passes. These are real runtime
failures, not a compiler/setup error.

## Minimal change

The d688 formal `NeedsTimezoneObservationKnown.value` schema has `type: string`,
`minLength: 1`, and explicitly assigns IANA membership checking to the producer.
Removed the device `TimeZone.knownTimeZoneIdentifiers` whitelist. The shared
field validator now enforces that wire nonempty constraint only. It is consumed
by both form commands and detail/revision validation; no alias special cases,
normalization, device-timezone conversion, instant inference or default was added.
The server retains business validation: accepting a nonempty string for local
encoding does not mean it is a valid IANA zone, and the tests explicitly distinguish
that from the fixed producer's rejection of `Not/A_Real_Zone`.

`TimezoneAliasTests.swift` covers exact command UTF8 equality, destination and
overseas fields, event local date/time, generated detail fields, historical original
bytes, absence versus explicit missing/unknown/uncertain, and empty rejection.
README is updated to remove the old device-validation claim.

## Verification

- PASS: increment only, **5 test functions / 11 expanded cases**, `after.txt`.
  Command: `swift test --package-path ios/Modules/CJNeedsClient --filter TimezoneAliasTests`.
- PASS: exact fixed producer replay, `producer.json`; reproduce with
  `python3 evidence/timezone-alias/check_producer.py /path/to/cj-013-needs` from this module.
- PASS: unsigned generic iOS Simulator SDK compile, `ios.txt`, lossless full output
  `ios-full.txt.xz` and original SHA256 in `manifest.json`. No app/simulator launch.
- REUSED: original 8c28 **36 functions / 51 cases** remain valid for unaffected
  behavior; old logs and failures are untouched. No unrelated suite/PG rerun.
- PASS: scoped diff whitespace and changed source hashes in `manifest.json`.
- UNRUN: actual UI/device, host account/resources, Keychain, real product HTTP,
  model/source extraction, PostgreSQL, CJShell integration, CI and deployment.

The reported empty-pending/last-binding directory concern is still an unconfirmed
Review investigation, not an asserted defect or a repair in this commit. Pending
store/client/presentation source is unchanged. No push/PR/merge/Issue closure;
Main should route this fixed delta through the existing dual review gates.
