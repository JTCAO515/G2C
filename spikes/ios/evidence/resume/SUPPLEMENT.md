# CJ-004 resume: keyboard / accessibility / performance delta

Recovery base `1dd735e6066e703bdabd1eb70c7d31a120d098e7`; P2 code fix `37bfe3a88882898840fad1d6ecbd925439a8b160`. Only `spikes/ios/**`. Original dirty was empty, no unknown task write found, all original artifacts preserved. Requested model from current HANDOFF: gpt-6.1-sol/medium; effective UNKNOWN. No remote write/PR/merge/deploy, no account/provider/cloud work.

## Keyboard and selection

**iOS17.5 author observation PASS for the tested subset**: reboot/launch of the same CJ004 native build with `--keyboard` showed the full software keyboard without the former slide-typing tutorial (`ios17-keyboard.png`, `ui17-before.json`). Typed ASCII via the tool; the existing Chinese input method composed it, and the final value was `Keyboardprobe` (not a claim of byte-exact typing). Send produced the local-only/no-send notice and dismissed the keyboard (`ios17-send-local.png`, `ui17-send-local.json`). Held the actual child Toggle AX node: value changed 0→1→0. Long press produced Copy/Share selection menu (`ios17-selection.png/json`); no sharing executed.

**iOS26.5 author observation PASS for software-keyboard visibility / layout subset**: initial focus existed but keyboard was hidden. Selected the exact CJ004 device in native Device Hub, then Device > Keyboard > Toggle Software Keyboard. Full keyboard and composer above it were visible (`ios26-keyboard-visible.png`, `ui26-keyboard-visible.json`). No global keyboard preference was edited. Sample stream could run with keyboard visible and reached 3960 characters. This is not full IME, keyboard-switching or real-send acceptance.

Two earlier sources of false confidence are now explicit: tap/AX ACK without changed screen is not PASS; SwiftUI Toggle parent/child nodes have different physical hit points. Actual child switch state and subsequent screenshots, not ACK alone, support the new observations. Earlier UNKNOWN evidence remains in the original report.

## VoiceOver

**PARTIAL observation; full speech/gesture acceptance remains UNKNOWN/UNRUN.** On the CJ004 iOS26.5 device, Device Hub > Device > Accessibility > VoiceOver actually displayed the first-use gesture notice; dismissed it with a double click. The app then showed VoiceOver's thick focus rectangle around the composer (`ios26-voiceover-enabled.png`). Activating the locally labelled Voice control through Device Hub's AX action displayed the bilingual unavailable notice (`ios26-voiceover-action.png/json`), with no recording/network action. A single right swipe did not visibly move focus from the editing field; `ios26-voiceover-next.png` preserves that limitation. AX activation is not proof that normal VoiceOver double-tap/navigation is correct.

Restored the same device's VoiceOver to off, then explicitly read **Settings inspector → VoiceOver, Value: off** in the native Device Hub. Host VoiceOver and other devices were not changed. After toggling/reinstall, the MCP accessibility snapshot sometimes returned one element while pixels showed a running app. Subsequent P2 lifecycle validation used native observed screenshot coordinates; see P2-LIFECYCLE.md. This is a tooling limitation, not a reason to infer speech correctness.

No sound recording/listening evidence or iOS17 VoiceOver gesture acceptance was acquired. For a human check: select the CJ004 iOS26.5 simulator, enable only its VoiceOver from the menu above; dismiss the notice; listen while swiping left/right through history/Muse/gift, mixed-language body, links, composer and four Tabs; activate the local unavailable actions; check focus is visible and order useful; finally disable that same device's VoiceOver. Record the observed speech/order and screenshot. Physical-device acceptance remains separate and UNRUN.

## Performance observation

One built-in **Time Profiler** capture on the **pre-P2** code (`1dd735e`, unchanged original binary UUID `6A29186A-B590-361F-8DB7-A9ED29D88D4F`), CJ004 iPhone17 Pro / iOS26.5 (23F77), macOS27.0.1 on M5 Pro, Xcode27.1. Explicit attached PID10709, 10-second configured window; trace duration 10.577483s, 20:07:29.839–20:07:40.417 Asia/Shanghai. Flow: from stable Assistant, start the 3960-character synthetic stream while software keyboard is visible; observe completion. Diagnostic insertion time 5.199019624999999s includes 100ms pacing.

Capture completed with a warning about one table lacking a known input source. Exported processed `time-profile` contains 2218 sampled rows, 1890ms main-thread and 328ms other-thread statistical sample weight. The first-party UUID in exported stacks matches the original binary read before the P2 rebuild. **71 unresolved first-party frame occurrences remain**, so the script withholds hotspot conclusions. `potential-hangs.xml` has no rows at the 250ms threshold, but that and the warning cannot establish a general no-hang PASS. No FPS, frame latency percentile, release build or physical-device performance claim.

Artifacts: timeprofiler-record.log, timeprofiler-toc.xml, time-profile-summary.json, potential-hangs.xml; complete processed tables losslessly gzipped with hashes in supplement-hashes.json. Raw `.trace` retained only at `spikes/ios/.cache/resume-timeprofiler.trace`. Recompute summary by decompressing time-profile.xml.gz into a scratch file and running `scripts/analyze-time-profile.py <file>`. No ETTrace runtime/framework was installed or linked, no global profiling config changed. This is a **limited pre-fix observation**, not a post-fix performance acceptance; P2's own dynamic lifecycle result is independent.

## P2 and handoff

Reported source P2 has the explicit cancellation/generation fix and actual iOS26.5 Tab-switch / fresh-start PASS at fixed head37bfe3a (see P2-LIFECYCLE.md). Only both affected SwiftUI targets were incrementally rebuilt. Existing transport/C0 generation and module tests were reused, not rerun. Current remaining acceptance includes independent re-review/Testing, complete VoiceOver speech/gesture behavior, exact minimum-runtime acceptance, real services/Auth, physical device and release. Product minimum iOS remains JT/CJ-001's decision. No Issue closed.
