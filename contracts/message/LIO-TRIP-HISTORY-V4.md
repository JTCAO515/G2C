# Lio4 history and original undo snapshot

This is an additive companion to frozen LIO-message.4. It changes no frozen
message4/trip1–3 file and introduces no message5. The new wire names are
LIO-trip-history.4, LIO-trip-undo.4 and LIO-trip-undo-receipt.4.

The new authenticated history reader returns current/history Card2 (original
structured1–3) or Card3 (structured4 summary). It preserves original trip ID,
version, content version, canonical hash, date state, day ordinals and empty rest
days. A legacy null calendar is not relabelled undated. Detail remains protected
TRIP-structured-read.3 and must match ID/version/hash before the richer UI uses it.

History entries are distinct, descending older revisions of the same trip.
Pagination carries the last returned version as next_before. A paginated response
with no current card supplies no undo_target. Unknown versions fail rather than
being relabelled or inserted into the old history3/Card2/undo endpoint.

An undo_target is explicit snapshot data, not an authorization or an opaque
permission token. It has trip_id, expected_version, original_hash, content_version
for the actual current revision, plus restore_version/restore_hash/
restore_content_version for the immediately previous immutable revision.

The ordinary action includes a stable action_id, conversation_id and that whole
target. The new host must recheck owner, selected CID→Trip binding, current
version/hash/content version, immutable previous version/hash/content version,
active source/profile/Memory/NEEDS fences and the actual new C undo3 handler
within its protected operation. DTO equality or a client-supplied target does not
grant a write. The existing sole commit path restores the prior bytes as a new
version; it never rewrites old content or sends a model/tool request.

The outer adapter can compile C's frozen TRIP-lio-undo.3 from the checked current
snapshot only after checking the exact prior target in that same operation. This
does not dispatch a new action as old undo1/2. Restoring old1–3 is allowed through
the explicit new rich consumer, while old detail/edit/undo interfaces keep their
own version gates. Unknown ACKs query the same action/target; no fresh ID or replay.

This document/schema/checker is a consumption design. Until actual protected
Source4/handler/routes and exact-head review/CI are completed, native history,
undo and formal writes remain UNRUN. Fixtures are not original authority,
physical-device, deployment or supplier acceptance.
