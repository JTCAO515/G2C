# Exploration reply presentation (#933)

This local preparation uses the field design acknowledged in
[#925](https://github.com/JTCAO515/G2C/issues/925#issuecomment-6857856938).
It does not install a wire decoder, HTTP endpoint or normal App entry. Runtime
integration still requires the merged WP2 contract and WP4 deployment. The later
[Card3 proposal](https://github.com/JTCAO515/G2C/issues/925#issuecomment-6859697924)
has a design acknowledgement only; it does not enable structured.4 consumption.

## Display and ordinary messages

The parent applies each complete snapshot and its question draft together.
Profile entries are an independent summary. Body sections follow the received
order: segments, questions, notices, exits. Stable notice IDs identify the same
notice across refreshes; the view does not append a new copy on every poll.

- Each segment is a separate answer bubble. The existing Markdown parser and
  public-display checks produce its content.
- Questions use the native controls described in [question controls](lio-question-controls.md).
  Neither dates, party size nor any other group is a prerequisite for an exit.
- Profile buttons open an editor containing the displayed preference. Send passes
  the user's text to the ordinary message callback; Cancel sends nothing. The
  view does not update the server snapshot or save a long-term memory itself.
- Notices show their text and, when available, a public reference labelled
  “Source / 来源”. They do not print a tool or service name as the button label.
- Exit and adjustment buttons pass the received `send_text` verbatim to the same
  ordinary message callback. They do not call separate planning or writing APIs.

The caller supplies the existing current-message/send gate and must retain its
account, conversation and source checks at dispatch. It owns the normal composer,
statuses, memory consent, trip actions and progress events. Progress animation
belongs to #913. Display values here do not grant write authority.

## Compatibility and text layout

The combined `answer` is displayed only when segments, questions, notices and
exits are empty. A profile-only update still keeps the existing answer. This
avoids showing both the structured sections and their plain compatibility
projection.

`LioReplyTextBlock` lays out the existing attributed Markdown result with a
uniform text style per native Text view. Heading sizes, inline emphasis, links,
list indentation and original separators remain represented. Headings receive
the native heading trait. This keeps different font sizes in separate layout
nodes; it introduces neither Textual nor another parser or dependency. The
existing normal-chat renderer has not been changed in this preparation.

The eventual wire boundary must validate every new display field and public
source, using the accepted version and the existing public-display policy before
constructing these values. Unknown fields/variants are not inferred by views.

## Acceptance scope

Local fixtures cover ordered bubbles, partial question answers, direct planning
without selections, profile send/cancel, stable refreshes, notice references,
exit messages, read-only state and plain/profile-only compatibility. Automated
AX and accessibility-tree assertions are separate from a VoiceOver walkthrough.
No fixture result proves HTTP4, protected rich-trip reads, real-service behavior
or JT's G12 acceptance. Normal chat integration waits for its shared-file lock
and prerequisites; no release is made from this private preparation alone.
