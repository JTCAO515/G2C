# Native4 client and conversation model

Refs #933 / #922. This consumes the frozen #925 fields and the merged WP4
routes from PR968. The Beta/Production composition keeps its existing selection;
real activation still requires WP4 deployment and native Home integration.
Rich protected readers/history/undo remain WP8 work. These data values grant no
Trip editing or source capability. Minimum deployment target remains iOS17.

## Explicit protocol and originals

`LioTimelineWire.Send` selects native4 explicitly. The existing initializer and
its default destination form retain message1/message2. The existing encrypted
journal stores a first native4 original before transmission; restoration validates
the closed new-chat request shape and retains the exact original bytes. Old
message2 first originals keep their own POST/lookup/receipt format when restored
by the same client. Unknown results remain query-only; no protocol fallback or
new-question retry is added. Definitive same-message retries reuse the staged
original only after a proven not-sent result.

The native4 receipt and lookup envelopes have closed keys and bind the actual
message/conversation identifiers. The lookup retains the exact nested receipt
byte range from the shared strict parser, including its escapes and spacing.
New native4 rejection proofs have a closed failure shape. Other access/server
failures remain unknown. These synthetic checks prove client handling, not real
metering, credentials, provider admission or an operator qualification.

Routes follow merged WP4: POST `/v4/lio/messages`, GET `/v4/lio/messages` with
original message ID/input digest, and GET `/v4/lio/timeline` with optional bound
conversation/cursor. Existing TLS, no-redirect, credential and before/after-await
lease callbacks remain. Old timeline1/2 decoding refuses native4 pages; the
explicit native4 read preserves its full typed payload.

## Field mapping

| Wire value | Consumer |
| --- | --- |
| message_id / text | UTF8-keyed question and turn, without ID normalization |
| conversation_id | Session read/send binding and the latest validated page's model identifier |
| next_before | Same-conversation automatic pagination; inclusive cursor responses are refused |
| segments, question_groups, profile, notices, exits | `LioTurn.exploration` immutable presentation and question data |
| progress | Typed waiting/planning signal retained on the same turn for the motion owner |
| trip | Actual calendar Card2 or rich Card3 variant retained on exploration data |
| memory | Existing completed-answer memory tags, explicit choice and public-text rules |
| answer | Canonical answer retained for copying; segments remain distinct for rendering |

`LioService.signedExplorationConversation` is separate from the existing signed
entrypoints. All entrypoints share the same observation, original-send, first
receipt, cancellation and pagination engine. A new factory does not switch the
App's normal user entry. Native4 metadata can change on a later validated read
even for a completed answer; an overlapping older page updates it instead of
preserving stale profile/action data. Legacy immutable-result behavior remains.

## Home presentation

The ordinary `LioHome` consumes `LioTurn.exploration` through the existing
segmented reply, question-form and profile editor components. The Home owns
selection drafts and the profile editor so dismissing the menu, scrolling or
entering the background does not discard an unfinished choice or edit. The editor
is presented above the lazy message rows, whose recycling cannot dismiss it.
Updated groups reconcile with the current typed
snapshot; a conversation switch clears the old selection scope. Only the latest
turn can send options, profile edits or exits. A delayed sheet action rechecks
the conversation identity and current turn before sending the ordinary text.

The composer and these controls share the existing ordinary-message submission
path, including timing, first-question continuity and entrance state. Option taps
do not send. A joint answer follows the snapshot order. The existing
`LioThinkingInput` maps the same turn's validated progress and announced day count
to the waiting component; the client does not invent a planning signal or days.
Legacy turns retain their existing renderer and typed calendar/rich cards stay
distinct from legacy saved-trip records.

Public projection checks progress and trip labels as well as segments, question
options and profile text. Typed metadata is not rendered as raw JSON or internal
status text. No new user-facing copy, third-party rendering library, manual read
button, source grant, signature or account setting is introduced. Textual remains
an assessment only. Beta/Production protocol selection, protected rich readers
and real-service/physical-device verification stay explicit remaining integration
gates. The actual-App synthetic HTTP acceptance exercises the same signed native4
client and Home, not a provider or deployed admission. It does not prove those
remaining gates.

## VoiceOver interaction acceptance

`check_lio_home.py --voiceover` runs a separate bilingual walk through Apple's
real VoiceOver service on an iOS27-or-newer simulator. It records actual spoken
output, selects two interests, checks one joint message, edits the profile,
reads the notice and source, follows an exit and sends from the composer. Each
language checks five intercepted messages. XCTest teardown restores the original
VoiceOver state even when an assertion fails. Earlier runtimes fail this explicit
mode instead of substituting accessibility-tree text. The App still supports
iOS17; this test-only API does not enter the App or replace the normal complete
audit suite. Run that suite separately without `--voiceover`. Both modes keep
builds, results and media outside the repository; neither enables native4 in Beta
or proves a deployed service or physical-device experience.
