# Lio exploration v4 — draft consumer contract for #925

Specification authority: #922 and JT's 2026-11-13 decisions, including comment
6848017500. This draft adds LIO-message.4 on the frozen #860/#862 v3 calendar
contract. It does not install an HTTP route, start an exploration session, issue a
new original capability, change a migration, or enable a model/tool call.

The schema is `lio-exploration-schema.4.json`; bilingual and progress examples are
`lio-exploration-examples.4.json`. The offline checker resolves only the committed
v3 dependency. Its examples are synthetic, not an AUTH/source/publishing grant.
Final independent review, exact CI, consumer confirmation and deployment are UNRUN.

## Envelope and original identity

The v4 send envelope keeps v3's text, locale, message_id and mutually exclusive
conversation_id/new_conversation fields, with only version changed. Receipt and
lookup gain .4 versions; timeline gains LIO-timeline.4. Unknown input properties
are refused. Options and profile edits are ordinary text, not extra request fields.

Exact bytes and the original owner/MID/CID/generation/RUN remain the source of
identity and recovery. Presentation identifiers do not grant writes or permission
to retry. Native v4 admission needs a separately reviewed source-origin capability
and actual consumer; this contract-only slice must not label a v3 origin as v4.
Existing v1/v2/v3 routes, frozen contracts and stored content are unchanged.

## Display order and joint replies

For each message, render segments in array order, followed by question_groups in
array order, then notices, then exits. Profile is a separate editable summary.
There is no inferred interleaving or matching by text. Each notice has a stable id
for replacement/deduplication. Question factors, profile factors, notice ids and
exit ids are unique in their respective arrays. An option id begins with its
factor_key and a dot and is unique within that group.
New v4 identifiers and Card3 hashes explicitly reject control characters rather
than relying on an end anchor. Card3 evidence references must contain nonblank
text; their presence still does not authenticate source evidence.

Every response still contains answer. In a v4 presentation it is the plain-text
projection: segment texts, each question plus its display options, notice texts,
and the exit labels, separated by blank lines. A structured renderer shows the
sections once, without also displaying answer. A text renderer uses answer.
Legacy messages projected into a v4 timeline keep their original answer and have
empty new arrays and progress=null; their original versions are not rewritten.
Old endpoints continue their original plain-text behavior.

Each poll is a complete message snapshot. Replace the presentation from that
snapshot; if a question group or its options change, clear its prior local
selections rather than submitting stale option text or duplicating bubbles.

Choose any subset of questions. For multiple choice, preserve option wire order,
not tap order. Join selected send_text values with one newline, in group wire
order, and send one ordinary message through the existing send boundary. Single
choice allows at most one selection. With no choice, the joint-send button does
not send an empty message; typing is always available. No Other option is added.
The offline joint_reply helper documents this encoding; it is not server admission.

Profile state is known / not_needed / inferred / default / memory, matching the
internal context's five states. Profile edits use ordinary text such as “节奏改为：轻松”
or “Change my travel pace to relaxed”; there is no profile mutation endpoint.
Internal source quotes, memory grants and factor inference remain server concerns.

## Progress and exits

Progress is null, waiting(kind/text), or planning_started(kind/text/duration_days).
Only planning_started carries days. The day bound matches the existing sourced
intake's 1–366; clients do not fill missing days. Terminal messages have null
progress. Unknown kinds are invalid rather than a cue to expose internal data.
The text is safe user-facing prose, not a tool name, RUN identifier or debug log.

Exit ids are stable server presentation identifiers; the action remains sending
send_text as an ordinary message. Exploration producers must include
continue_refining and plan_now every round. The latter produces the next plan;
WP4 enforces that policy and the scene-specific question/exit counts. Adjustment
and on-day actions also use ordinary text. No button bypasses source, AUTH,
TripProposal, confirmation, billing or UNKNOWN recovery guards.

## Limits and remaining implementation

Question groups have at most four groups and exactly three or four options;
notices at most two, exits at most four. Presentation text remains bounded and
option and exit send_text is nonblank and explicitly excludes CR, LF and Unicode
line separators and C0/C1 control characters, including a trailing separator. Joint replies therefore have
one unambiguous separator; a regex end anchor alone is insufficient.
These transport bounds do not replace #922's language/scene lengths, dynamic
question counts, candidate-factor restrictions, code-generated notices, defaults
or safety filters; WP3/WP4/WP8 enforce those production policies.

The trip field is a strict union of frozen LIO-trip-card.2, new
LIO-trip-card.3, and null. Card2 remains byte-for-byte unchanged for
structured.1–3. Card3 explicitly summarizes structured.4 with the existing
trip_id/trip_version/content_version/content_sha256/title/calendar/days/date_checks
fields. Its calendar and checks cannot be legacy null; day_index stays contiguous,
empty rest days remain, and dated days follow the stated start date. The four
date-check states retain v3's original meaning: undated is not_checked/date_not_set,
dated unobserved is unknown, and clear/conflict requires actual evidence.

Card3 adds no opaque data, price, booking status, geometry, theme/area, legs or
lodging fields. WP7/WP11's explicitly versioned protected detail read supplies
kind/place/note/tip/reason_refs, adjacent legs, day theme/area and lodging.
Consumers match ID/version/content hash before showing that detail and do not
put structured.4 through old edit or undo payloads. Old source/memory types still
refer to the frozen v3 schema. The new summary cannot reconstruct or authenticate
full canonical content, source authority, factual accuracy or a save receipt.

The non-null summary examples are explicitly synthetic; their demonstration
hashes do not claim a real protected structured.4 document. WP7/WP8 still owe the
actual document, source, publisher, read/undo versions and native proofs. This
draft enables no structured.4 writer or native v4 admission.
The exploration rollback switch belongs to the server, defaults on for the new
mode, and is not a client-controlled flag or A/B assignment.
