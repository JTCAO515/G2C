# CJ-004 P2 cancellation/reentry delta

Base `1dd735e6066e703bdabd1eb70c7d31a120d098e7`; review `cj-review/CJ004-1dd735e/review-summary.json`, Spec P2 at old ProbeView.swift:125. Original Review was source-only and did not claim dynamic reproduction.

Fix: local fixture uses a distinct stream generation ID. Leaving Assistant or pressing Stop invalidates that generation, sets streaming=false and retains the current partial text. An explicit new start clears partial text and creates a new generation. Cancelled old tasks cannot append after an await or settle a newer generation. This is a disposable local fixture policy, not a formal RUN resume/cancel contract.

Source SHA-256 after fix: `eb1b4fab47051d0322e7ff419da49dba1569fa010b1070374d66affb8f1f0cd0`.

Actual dynamic regression on CJ004-iOS26-20261021, iPhone17 Pro / iOS26.5, unchanged fixed dependencies, new incremental build:

1. Started from a freshly launched Assistant with no stream.
2. In Device Hub, clicked the observed Stream fixture control then held/released Trips for 650ms. Trips actually appeared.
3. Returned to Assistant. Actual screen showed **Stopped locally at 1120 characters. Start begins a new fixture.** The partial was nonempty and no Stop control remained. See `lifecycle26-stopped-first.png`.
4. After additional observations and scroll operations, the stream had not resumed. Used the system status-bar scroll-to-top action; the explicit **Stream fixture** control was available.
5. Started a new fixture and used Follow latest. Actual result: **3960 characters / 50 updates / 5.188313670000004 seconds**, not 5080 (=1120+3960). See `lifecycle26-restart-complete.png`. No stuck streaming control.

Result: author dynamic **PASS** for the reported cancellation/reentry path and explicit fresh restart on iOS26.5. Both affected Textual26/native17 targets incremental build PASS (`build-lifecycle*.log.gz`, exact raw hashes in `lifecycle-build-hashes.json`). No transport/C0 tests or generation checks rerun: source change is confined to SwiftUI fixture lifecycle; prior valid evidence is reused.

Tool limitation: after toggling VoiceOver and reinstalling, MCP runtime snapshots returned a one-element tree while the app visibly rendered. Rather than treating that as an app pass/fail, the regression used the native Device Hub's observed screenshot coordinates and persisted simulator screenshots. The app's own stopped/completed character counts are diagnostic fixture observations, not server results or frame-performance measurements. Independent Review/Testing still required; Issue #4 not closed.
