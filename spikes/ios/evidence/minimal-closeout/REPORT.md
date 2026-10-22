# CJ-004 original-scope minimal closeout evidence

2026-10-22. Base `ad903eb19890552b419ec28b8cb613efed41b190`, clean at intake. This is an evidence-only delta for the original Issue#4, not a new task or product layer. App Swift/source hash, binary, lockfiles, schema, sample pacing and assertions are unchanged. No build, contract test, profile, account, network service, new runtime or device creation. Requested gpt-6.1-sol/medium per Main; effective UNKNOWN.

Only the existing **CJ004-iOS26-20261021**, UDID `B80AD40D-F779-4FE3-A36D-CFD4C4A19D83`, iOS26.5 (23F77), was restored. Installed binary SHA-256 `532860895903c76afe6e482197655885ef3ff5d42788f0085c7a91579f6966ab`, UUID `DC77E156-7E16-38C4-88E6-1E683DD7BAD6`; source hash remains `eb1b4fab47051d0322e7ff419da49dba1569fa010b1070374d66affb8f1f0cd0` (identity.json). Brand/C52D and CJ007 devices were not selected or operated. Old Keychain/Auth was not used.

## 1. Candidate-minimum runtime inventory — concrete gap

Read-only inventory found only **iOS17.5 and iOS26.5**, both available. Neither iOS18 runtime nor fixed Textual18 runtime evidence was found in the existing CJ004 Review/Testing records. See runtime-inventory.json; existing SOURCES.md and resume/SUPPLEMENT.md remain the package-floor/current-runtime record.

Therefore Textual's declared iOS18 minimum runtime row remains **UNRUN**. Native17.5 plain-text evidence cannot substitute for Textual18. No download, new simulator or product minimum-iOS decision was made. Minimal unblock is existing, authorized iOS18 evidence for dynamic type/selection/major VoiceOver behavior, or a separately authorized preparation decision by Main/JT. This does not invalidate the already recorded package platform/toolchain facts.

## 2. Incremental reading-position observation

**Author observation PASS for this narrow iOS26.5 case, following one specifically authorized correction.** Full profile/FPS/physical-device acceptance is neither required nor claimed here.

### First attempt retained as UNKNOWN

Recorded the device before launching the existing `--stream` mode; attempted one upward drag, then Follow latest. The video shows the stream active at t8 and completed by t10; the scroll/Follow latest state appeared later (t50). It therefore **did not prove the drag occurred during insertion**. See scroll-t08.png, scroll-t10.png, scroll-t50.png and video-metadata.json. Full original89.025s silent video is preserved at the exact cache path and SHA in first-video-provenance.json. It was not deleted or overwritten.

Main explicitly authorized one targeted correction for this unmet timing condition, without changing sample duration/code/assertions and without another profile.

### The single correction actually overlaps insertion

Started a second screen recording first. Issued **Start then immediate upward drag in the same native UI operation sequence**, using coordinates observed in the selected CJ004 Device Hub view. The action batch eventually timed out during execution/observation, so its ACK was not used as proof. The resulting video provides the actual sequence:

| Raw correction video time | Visible observation |
|---|---|
| t15 | Stop visible, generation active; no Follow latest yet in this frame |
| t18 | Stop and Follow latest both visible after the upward drag; reading anchor is the quote followed by “English with 中文地点” and the mixed-language paragraph |
| t20 | Stop and Follow latest still visible; the same heading/paragraph/list/link remain at the same reading position while insertion is still active |
| t22 / t25 | Stop gone; Follow latest remains. The same reading anchor is retained after completion; later text has grown below it instead of pulling the viewport to the end |
| Final Follow latest | Fresh MCP snapshot identified the actual Follow latest button; touch removed it and returned to the final message end. Generated diagnostic count **3960 characters / 50 updates / 5.2349065 seconds** is recorded in correction-follow.json |

Raw `scroll-correction.mp4` is committed,76.475s, no audio track. Relevant unmodified frames: correction-t15/18/20/22/25.png; correction-t75.png shows the final part of the record. Source remains the same50-update/100ms-paced fixture. These are authored synthetic rendering observations, not live server output, frame latency or a new no-jank guarantee. No third attempt or sample change occurred.

This fills the narrow original requirement that a deliberate reading-position change during incremental text is not visibly overridden. Duplicate-body protection remains the already double-reviewed P2 result at37bfe3a; it was not rerun or inferred from this video. Old71 frames/new225-of227 symbol records remain unchanged and are not promoted into FPS acceptance.

## 3. Major VoiceOver short path — UNKNOWN, no AX substitute

Only the CJ00426.5 device's VoiceOver was changed. Native Device Hub Settings readback was **off→on**, and after the attempt **off** again (voiceover-restoration.json, this chat's actual native readbacks). Host VoiceOver, signature/security permissions and other devices were not changed.

An initial stale-node preflight did not dispatch touch/swipes (SNAPSHOT_EXPIRED/MISSING). The vo-preflight-* images are not action evidence. After a fresh snapshot, one bounded live sequence attempted History→right/left→mixed body/link paragraph→composer→Trips activation. The **History action actually opened its local placeholder modal**, with a VoiceOver focus rectangle around the modal title. The automation sequence failed to dismiss that expected modal before continuing. Subsequent gesture/body/input/Tab attempts did not complete the intended path: the screenshots remain on that modal, despite tool ACKs. See voiceover-actions.json and vo-live-*.png. The local modal was then dismissed and VoiceOver restored off; no retry of the whole path was made.

No recorded/listened speech output was obtained. The available scoped simctl recording contains only a video track; no host-wide system audio or microphone capture was started and no permission change was requested. Consequently **real spoken labels, left/right focus progression through the complete path, and body/link/input/Tab activation remain UNKNOWN/UNRUN**. This is not a claim that AX labels or a focus rectangle pass VoiceOver. The observations do not establish a new source defect; no speculative code fix or guard was added.

Minimal remaining action: a human on the existing authorized CJ004 device must listen to the same short path, dismiss each local notice before continuing, verify left/right focus and actual activation, then record the observed utterances/order and restore VoiceOver off. A targeted audio-capable authorized test channel could also supply that evidence; a new brand device, real login or whole-App journey is not needed.

## Outcome against original scope

- Existing version/toolchain/limits, generated-client normal/error/interruption, mixed-language/list/link/selection records, conditional adoption/replacement and no-script/no-auto-link/blocked-media strategy remain reusable.
- Original incremental reading-position observation now has the narrow authored video PASS above; performance measurement already exists and no full-symbol/FPS requirement was added.
- **Remaining original-scope gaps are the iOS18 candidate-minimum row and major VoiceOver speech/gesture path.** They are not replaced by full-App/real-Auth/database/release requirements. Issue#4 is not closed by this owner.
- Device-at-close.json confirms both CJ004 devices Shutdown. Only26.5 was started this round. All preceding failures and old profile limitations are retained.

Videos/frames are scientific timing evidence. Container r_frame_rate metadata must not be interpreted as app rendering FPS. Extra extracted frames and the full first timing-attempt video are retained in the task cache with exact hashes; committed raw correction video allows independent extraction. No screenshot content was redrawn or altered.
