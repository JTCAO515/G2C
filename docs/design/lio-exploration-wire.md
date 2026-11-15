# WP10 exploration data boundary

Consumer: frozen WP2 #925 / PR953. `LioExplorationWire` reads only the explicit
LIO-timeline.4 envelope. It does not add HTTP4, a send/original factory, a receipt
reader, a protected source or an App route. Old timeline .1/.2 parsers remain
unchanged and reject the new envelope. Minimum iOS remains 17.

The data keeps ordered segments, question groups and options, profile states,
notices with their source data, exits and typed progress. Option/exit send text
is a single nonblank line with no C0/C1 or Unicode line separators. Factor/option
identities are scoped and unique. Terminal rows cannot retain progress. When
structured body sections exist, the compatibility answer must equal their exact
ordered plain-text projection; profile-only updates do not erase a plain answer.
Native conversation, MID and cursor bindings retain their existing safeguards.

Trip is a closed union: genuine Card2 content .1–3, genuine Card3 content .4, or
null. Rich summaries retain their version/hash/calendar/all days including rest
days and the two date checks. An internal Card2 field-validation copy cannot
escape as an old card or source; the public value remains a separate rich type.
A summary does not authorize detail, edit, undo or save. Current full content must
still come from the matching protected WP7 reader.

Citation raw URLs/timestamps remain data; the link projection permits only HTTPS
without credentials. The user-display boundary retains the existing public-text
and service-host filters. Memory tags use the existing validated tag model and
are offered only for completed rows. No memory is saved by decoding a tag.

The existing frozen Card2 reader is included as the necessary public data-type
prerequisite, without any of #863's activation, transport, UI or session changes.
Its original byte observations grant no source or write permission. Actual
normal-chat wiring waits for the shared Home file lock and WP4 deployment.
Synthetic fixture/module/code-review results are separate from actual HTTP4,
source eligibility, voice-reader walkthrough, HK/device and JT G12 results.

## Display bridge and local acceptance

A separate display projection maps these validated fields into the existing
segment/profile/notice/exit view and question draft. It preserves wire order,
uses the existing public-text/service-host filters, and never sends automatically.
Profile edits and selected options remain ordinary text callbacks. The explicit
legacy projection keeps only real old/plain answer fields; it does not synthesize
new profile/progress values. No normal Home or actual API4 is enabled.

The decoded synthetic fixture exercises both languages and light/dark with full
AX. The existing question/large-text/reply methods remain. The disabled Continue
button now owns its D5 colours through a native ButtonStyle instead of unreadable
system dimming; its disabled behavior and empty-selection gate are unchanged.
Earlier selector/setup and disabled-contrast failure records remain external.
