# Registry and reservation original references

`FixtureOriginalReferences` adds a separately versioned private descriptor for
the two existing B source bodies. It does not change the frozen G envelope,
the legacy `OriginalReferences` format/kinds or the original body formats.
The collector gains an explicit optional router; the production worker factory
does not configure it in this slice. No fixture publisher is activated.

The trusted host supplies an existing qualified `FixtureUseRegistry`, its
selected original use bytes and an existing owned 0700 descriptor directory.
It never supplies body bytes from a candidate or a claim of expected state.
Registry reads return the actual canonical B policy file after current checks;
reservation reads reconstruct the actual durable original via `registry.read`.

Descriptors have `source` and `sha256`. Source fields are exactly `version`
(`G2C-fixture-original-reference.1`), original consumer `binding_sha256`, `kind`
(`registry` or `reservation`), `policy_sha256` and `use_sha256`. Registry
descriptors have null use hash, making the same independent frozen policy ref
stable across uses; reservations bind the exact original use bytes. The ref is
`original-<digest of descriptor>`, and the returned digest hashes original body
bytes. No body, token, C text or filesystem path is stored in a descriptor.

The original supplied token digest must match the original consumer session.
Current producer/consumer/source qualification and policy bytes/validity are
rechecked through the registry on both sides of access. Body bytes are read
again after persistence/resolution; changed sources are withheld. A saved
descriptor is integrity metadata, never cached ALLOWED or a bearer capability.
Files are 0600 O_EXCL/NOFOLLOW with fsync; the pinned directory identity cannot
be silently replaced. Partial/corrupt/unknown-ACK originals are retained and
never repaired into another reservation, dispatch or fee.

A resolver without a selected use locates the original use by its hash in the
actual retained reservation records, then applies the normal qualified read.
It can reconstruct older references after a process restart without a RAM-only
index. The collector selects metadata only when its owned descriptor exists;
only a missing descriptor permits legacy routing. Corruption, revocation or a
denied metadata read never falls back to another source. C metadata withdrawal
does not block unrelated E originals in the separate legacy directory.

`reservation_identity` derives the durable original namespace from the already
read actual reservation. It is independent of a policy's possibly repeated
ordinal and must be the host's input to fixture use identity, not an E label.
Registry references must remain independent of a future definition/use hash.
The final publisher still has to establish every independent source and issue
only currently permitted metadata; predicting a ref digest grants no authority.

## Verification and remaining work

Unit controls cover stable policy refs, actual record/hash reconstruction,
different-use/session rejection, current withdrawal, unknown ACK, corruption
and private-directory replacement. The signed private PG registry group now
also resolves actual policy/reservation sources under native MESSAGE admission
and current C/E AUTH, using real token digests. Financial identity/source
definition pins remain explicit local fixtures.

No full definition/use, permission policy, original-reader routing, source
preparation/cost inventory, disclosure scan or durable publication is invented
here. Existing reservation usage is never refunded. Full X01–X12 and paid E/F
activation remain UNRUN until those native sources and the consumer router
are composed, qualified and tested.
