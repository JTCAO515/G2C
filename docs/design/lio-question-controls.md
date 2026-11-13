# Lio exploration question controls (#933)

## Scope

This preparation slice supplies native SwiftUI question controls and a value-based
selection draft, exercised through the existing simulator acceptance project with
local examples. It does not enable LIO-message.4, change the HTTP client, or add a
route to the Beta/Production app. Minimum iOS remains 17.0; D5 tokens are reused.

The consumer design is recorded in [#925](https://github.com/JTCAO515/G2C/issues/925#issuecomment-6857856938)
against draft `6dd364d5a7d27fd00a1057d4e283489618e77c87`. That acknowledgement
does not freeze the contract. Runtime admission waits for the merged contract;
real-service integration also waits for WP4 deployment.

## Mapping and interactions

| Contract design | Presentation value / behavior |
|---|---|
| `message_id` | Draft identity; a different message clears selections |
| `question_groups[].factor_key` | `LioQuestionGroup.id` |
| `question`, `multiple` | Heading; multiple choice or exclusive single choice |
| `options[].id`, `display_text`, `send_text` | Stable selection identity, visible label, outgoing text |
| Complete question-group snapshot | Preserve identical groups; clear changed or removed groups |

Tapping an option only changes the draft. A selected option can be deselected.
There is no additional “Other” option. “Done, continue / 好了，继续” sends the
selected `send_text` values as one ordinary message, in group and option array
order, separated by one LF. A partial answer is valid; no answer leaves this
button disabled. The later integration must retain the ordinary composer and
the server-provided exits, so skipping these questions remains possible.

The parent owns the draft alongside its account and conversation, rather than
inside a transient row. It must discard it on account/conversation replacement
and reconcile it with each complete snapshot. `canSend` comes from the parent's
existing current-message and send state; the callback uses the ordinary guarded
message path. These views neither authorize sends nor acknowledge saves.

Values here are presentation values, not decoders. The eventual wire boundary
must validate identifiers, option counts, lengths and single-line `send_text`
against the accepted contract before constructing them. Controls do not repeat
that boundary validation internally.

## Accessibility and remaining integration

Options are native buttons with selected traits and 44-point minimum targets.
Question headings are exposed as headings. The grid uses two columns normally
and one at accessibility text sizes; text wraps without fixed line limits.
The form contains its children without replacing their individual identifiers.

The simulator cases cover both languages and appearances, single/multiple and
partial answers, one callback per submit, unchanged-snapshot selection retention,
read-only controls and large text. They run the complete `.all` AX audit without
an issue filter. Automated AX evidence is separate from a VoiceOver walkthrough.

Still pending in #933: ordered segment bubbles, profile editing, notices, exits,
the normal chat integration, old-message regression and reader walkthrough.
The shared `LioHome.swift` remains owned by open PR917; this slice does not edit it.
