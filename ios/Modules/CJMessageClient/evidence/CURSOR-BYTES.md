# Opaque cursor byte identity P2

Parent 5885a18e22087405a1bdb7b8c1818830f8f635b5. Initial one-test failure reproduced
in cursor-bytes-before.txt: composed U+00E9 and decomposed U+0065 U+0301 tokens have
different UTF8 but Swift String equality deduplicated them and falsely required resync.
Wire permits opaque non-ASCII cursor values; no ASCII-only codec assumption is valid.

Two-line product correction: MessageReadCursor.seenCursors uses Set<Data>; nextRead
inserts Data(text.utf8). No Unicode normalization or token parsing. Equal byte tokens
still reject replay loops; different UTF8 tokens continue even if canonically equivalent.

PASS: 3 targeted tests in cursor-bytes-after.txt: differing UTF8 token sequence reaches
third page, actual same-token loop still resyncs, ordinary bound continuation works.
Swift6.4/macOS synthetic interception only, no network. Existing identity/limit evidence
reused. In-flight PUT files were preserved under ignored .build/put-held-cursor-repair;
post-fix tests ran with HEAD Recovery/Transport plus ONLY the read fix and without PUT
test source, then PUT files were restored. This commit excludes that unreviewed PUT work.
No generated source, schema, backend or shared files changed. Independent review pending.
