# Ordinary App basic-smoke coordinator (preparation)

These tools collect the separately installed ordinary Beta App through native UI. They do not qualify an App artifact, issue an account, grant a deployment window, run the C judge, or approve a release. Only the initial-setup profile of `LIO-basic-chain-plan.2` is implemented. Old default conversations and publicly failed messages remain intact.

## Inputs and separation

- C supplies the immutable plan and the complete App pin; B supplies a separately issued sign-in-only lease and the real source/image metadata. Every private file is externally SHA-pinned, strict JSON, owner-owned single-link regular0600, bounded, and opened without following a leaf symlink. The issued lease must cover the actual dispatch time and exact locale, subject, simulator and full App pin.
- `official_lio_sign_in.py` validates that lease before any input. Only the native XCTest process opens the existing invitation file; it types unchanged bytes into the existing SecureField and uses the normal Continue/consent action. The Python process does not read invitation contents. An existing signed-in session is preserved and requires B identity readback; neither branch signs out or swaps identity. A fixed private attempt marker keyed by the lease ID and locale is created exclusively before native work; changing the output directory cannot repeat that attempt. A missing ACK or uncertain result stops that attempt, and the marker is never cleared by this tool.
- Login is not business admission. `watch_lio_basic_smoke.py` separately checks C's next immutable step, then publishes a prepared UI observation. It waits for the matching server checkpoint/admission, checks the UI has not changed, and dispatches the one permitted action. No native message/conversation ID is invented from AX text. Every mutation is fenced again at actual native dispatch, including the configured interval and Beijing 08:00–23:00 restriction.

## Full history

`lio_history_projection.py` consumes the actual Lio byline position and the existing question/answer/failure elements from the same native snapshot. The App position is a UI ordinal and loaded-page count, **not** a business identity or permission. The producer requires the compatible App positions; older Apps remain unqualified rather than falling back to text matching.

`lio_paginated_capture.py` uses the actual Earlier button and real scroll-container bounds. It retains every repeated row, resets ordinal observations after prepend, and requires a complete census with no unread page/error/spinner. A historical visible failure has `answer: null`, `visible_failure: true` and its actual label; hidden partial wire text is never a UI body. A failure in a newly submitted last turn is still a failed smoke. Incomplete alternative histories cannot establish a unique conversation match.

The first body and completed-body times come from native monotonic observations, before the later offscreen-history census. An unobserved progress signal remains `NOT_OBSERVED`. Cold/background/lock recovery uses fresh single-snapshot projections while waiting for the visible page to settle, without Earlier taps, scrolling, or the previous census. That lifecycle observation is sealed before later history navigation; subsequent reads cannot replace it. In the approved initial-setup order C adds the default to accepted views after SM01, so SM03/SM04 do not add another default row.

## Evidence limits

Pure Python controls and simulator fixtures are local evidence only. Before any real run, review the precise producer head, qualify the actual App/binary and renderer, verify B's current source and issued lease, and obtain C's current checkpoint-fenced window. The coordinator currently has no real Hong Kong qualification; UI contrast failures and the unfinished full-history App surface remain separate blockers. No command here grants TestFlight or deployment approval.

## Installed-App audit before real admission

The native controller supports `audit_all` for an already-running, usable ordinary Home. It requires the real composer and New chat controls to be hittable, retains the same dispatch-time Beijing and issued-window checks, and calls the complete `.all` audit without a filtering closure. It does not launch, sign in, open a new conversation, send a message, clear data or install a fixture. On success its original response records `audit: all` plus a fresh native snapshot and screenshot. A thrown audit, missing ACK or stopped runner remains failure/UNKNOWN; the existing sticky barrier forbids proceeding or replaying through that controller. Original XCTest results stay as evidence.

This is a diagnostic command, not a qualification certificate. An installed App pin, B's current sign-in-only lease/identity readback, the complete default history and the actual audit outcome still need independent verification. Source/compile/ACK controls do not prove an actual Hong Kong audit PASS or authorize business smoke. Existing synthetic audit failures stay open; no actual audit is performed outside the authorized window.
