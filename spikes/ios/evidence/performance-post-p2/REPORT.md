# CJ-004 bounded post-P2 performance evidence

**Status: capture and exact-UUID symbol attribution PARTIAL; overall performance acceptance UNKNOWN.** No runtime/source behavior change. Scope is only the original long-text insertion/scroll probe, not lifecycle, keyboard, C0, Auth, release or physical-device revalidation.

Input fixed head `584163e59e1be7d8e4d4b09070841447504b8784`, clean at intake. ProbeView source SHA-256 remains `eb1b4fab47051d0322e7ff419da49dba1569fa010b1070374d66affb8f1f0cd0`, identical to accepted P2 code. Reused existing Debug binary, **no rebuild**. Binary and complete dSYM were copied into ignored `.cache/performance-post-p2` before capture and hashes rechecked afterward (`provenance.json`, `installed-binary.json`, `derivation-verification.json`). Requested gpt-6.1-sol/medium per current Main record; effective UNKNOWN.

## Old trace: preserved limitation

Old trace UUID: `6A29186A-B590-361F-8DB7-A9ED29D88D4F`. Its original installed binary path no longer exists; the available built binary and dSYM are both `DC77E156-7E16-38C4-88E6-1E683DD7BAD6`, so neither was applied to the old trace.

The old trace retains a same-UUID `.symbolsarchive`. The local Apple `symbols` tool recognizes its UUID and reports 270 symbols / 2574 source-info entries, **0 dSYMs**. Checked all 24 distinct missing addresses accounting for 71 occurrences. Archive `__TEXT` is based at0; normalized each recorded address by the trace's actual load base `0x102204000`. Lookup results still lack function names (`old-unresolved-addresses.json`, `old-archive-lookups-target-first.log`). The initial command-argument ordering error is separately preserved, not hidden.

**Old71 remains unresolved.** Minimal recovery requires the original binary/dSYM or richer symbol data with UUID6A29186A; the current DC77E156 data cannot substitute. The original trace, export and old report were not changed. No old-source rebuild was attempted to manufacture a matching identity.

## One actual post-P2 capture

| Item | Actual identity/result |
|---|---|
| Device | only CJ004-iOS26-20261021, iPhone17 Pro, iOS26.5 (23F77), UDID B80AD40D-F779-4FE3-A36D-CFD4C4A19D83 |
| Host/tool | M5 Pro, macOS27.0.1; built-in Xcode27.1 / xctrace Time Profiler |
| Binary + dSYM UUID | **DC77E156-7E16-38C4-88E6-1E683DD7BAD6**, both arm64 |
| Installed binary SHA-256 | `532860895903c76afe6e482197655885ef3ff5d42788f0085c7a91579f6966ab`; exact match to preserved binary |
| Process | CJIOSSpike, PID44284, same device/bundle throughout |
| Recorded window | 2026-10-21 **21:27:52.721–21:28:13.297 Asia/Shanghai**, duration20.575704s, configured20s |
| Actual samples | 1370 rows, sample timestamps15.912258625–20.575257041s; statistical weight main1324ms / other46ms |
| Warning | recorder reports one table without a known input source; potential-hangs table has no rows at250ms threshold. This is not a no-hang guarantee |

The explicit PID attach first failed **before capture** with “Cannot find process”. Read-only diagnosis showed PID44284 still running, correct installed hash/UUID, and xctrace recognized the device. One bounded correction used the same pinned device UUID plus official process-name attach `CJIOSSpike`. It attached PID44284 and completed the single actual20s capture (`record.log` failure, `record-by-name.log` success). No process/device widening, host setting change, global install, all-process capture or prompt bypass.

Flow was issued after the recorder reported Starting: activate the existing Stream fixture, then attempt one downward and one upward drag inside that device's visible long-text area. The native UI call timed out at30s during the action/observation batch. Did not resend it. The subsequent screenshot shows long text, a changed scroll position and Follow latest (`after-capture.png`); before.png shows the starting layout. **Exact completion times of both drags and complete overlap with the20s window are UNKNOWN.** Samples cover the late active portion; do not claim the full insertion/scroll flow was captured. No lifecycle/Tab or keyboard case was repeated.

## Precise symbol resolution on the new trace

1. `xctrace symbolicate` was supplied only the DC77E156 dSYM and wrote a separate `by-name-symbolicated.trace`; raw and old traces stayed unchanged. Its processed export still had1911 unresolved first-party frame occurrences across227 unique addresses.
2. Used Apple `atos` with **the same UUID/architecture** and the trace's recorded load address `0x1043dc000`. The dSYM named217/227 addresses. The exact preserved Mach-O named8 further import stubs. Both UUIDs and hashes are recorded.
3. Created explicitly labelled **derived** XML containing only these name replacements. `atos-mapping.json` retains every original address, exact tool output and method. `derivation-verification.json` confirms all1370 rows and all non-name structure unchanged. This is not represented as an untouched native export.
4. Result: **225/227 missing addresses named; unresolved first-party occurrences1911→2 within this same new dataset**. This is not a comparison to the old71. `summary.json` preserves native-export limitations; `summary-atos-derived.json` preserves the two residuals and withholds hotspot conclusions.

Residual runtime addresses are `0x1047c5f47` and `0x1048ac0d3` (atos normalized preferred addresses `0x1003e9f47` / `0x1004d00d3`). Both matched dSYM and Mach-O return addresses without function names. No nearest-function guess was made. Minimal symbol-attribution requirement is richer named/debug coverage for these offsets in this exact DC77E156 image, or an independently verified symbolizer result. Reliable full-flow performance acceptance also needs bounded UI operations with timestamped completion inside the capture window. No further capture/tool retry is scheduled by this owner.

No FPS, frame percentiles, CPU wall-time utilization, no-jank or physical-device claim. The gate for complete first-party symbol attribution remains unmet, so known partial stacks are not promoted into a hotspot/optimization conclusion. No product minimum iOS decision.

## Artifacts and reproduction

Raw new trace, native symbolicated trace, immutable binary and complete dSYM remain under ignored `spikes/ios/.cache/performance-post-p2/`; old trace remains `.cache/resume-timeprofiler.trace`. Retain these for future exact-UUID work. Complete native and derived processed XML are losslessly compressed; `artifact-hashes.json` records original hashes. No compiled binary or whole trace is committed.

To reproduce the derived data after decompressing profile.xml.gz to a scratch file, run:

```sh
python3 scripts/symbolicate-profile.py <native-profile.xml> .cache/performance-post-p2/CJIOSSpike.app.dSYM/Contents/Resources/DWARF/CJIOSSpike <derived.xml> <mapping.json> .cache/performance-post-p2/CJIOSSpike.app/CJIOSSpike
python3 scripts/analyze-time-profile.py <derived.xml>
```

The derivation script rejects wrong UUID/architecture before accepting names. New code is only this evidence helper; app code, locks, OpenAPI and previous accepted checks are unchanged. Main should route this fixed evidence delta for review; Issue#4 remains open for its other real-service/device/accessibility requirements.
