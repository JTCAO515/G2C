# FACT@2.0 — maintained visitor guidance (#847)

Additive local catalog producer. FACT@1.0, its synthetic codecs, examples and
existing live entry-notice/weather paths remain unchanged.

`FACT-query.2` has exactly `version`, `topic`, `city`. Topics are payment,
passport_booking, transport, internet and emergency. City is an explicit bounded
name or administrative code, with the seven documented aliases mapped by
`cj_fact.visitor`; there is no default city, inferred location or trip date.
Unsupported cities produce no_match, rather than being substituted with Beijing.
The request cannot supply an evaluation date, owner, scope or permission.

`FACT-result.2` has the query, original host-issued request_ref,
`data_origin=maintainer_summary`, status matched/no_match, server evaluated_at,
catalogue_sha256 and entries. Each entry retains H's exact id/topic/cities,
text_zh/text_en/source_urls/checked_on/expires_on. These are maintainer summaries,
not official quotations/translations or synthetic facts. checked_on is a human
review day; expires_on is a maintenance deadline, not a government's policy end.
No web originals, excerpt spans or website content hashes are invented.
The catalog digest binds local input file names/bytes, not external page truth.

Only direct `entries/*.json` files under an explicit host-configured public
resource directory are read. Examples, docs and nested files are not facts.
The complete input is bounded to 1 MiB. Deserialization validates exact fields,
UTF-8, duplicate keys/ids, topics/cities, bounded text/arrays, HTTPS URLs within
the JT-confirmed exact-host inventory (#843/6818584957), and strict review dates.
Future checked_on or malformed data fail the operation; a missing/empty resource
directory is unavailable, not a successful no_match. No partial success hides a
bad entry elsewhere in the catalog.

Expiry is checked against the trusted server's Asia/Shanghai day on every lookup.
An entry expires at 00:00 on expires_on and is omitted; other valid entries remain
eligible. With no eligible matching entry, status=no_match and entries=[].
Outputs are bounded to 128 KiB, ordered by stable entry id; no truncation or
stale-cache fallback occurs. This module does not fetch, modify or extend sources.

JSON shape: visitor-schema.2.json. Synthetic positive/negative wire examples:
visitor-examples.2.json. Semantic source/date constraints are implemented at the
file boundary in cj_fact.visitor; a schema-shaped record alone is not source
approval or authenticated authority.

Host integration must retain original AUTH/RUN/Meter guards, request binding and
UNKNOWN/cancellation behavior. Local file reads have no external provider call or
payment; model calls remain separately metered. An actual tool registration,
installed-resource packaging, bilingual signed host test and independent red-line
review are required before enabling this producer. They are not supplied by
merely importing the catalog reader.

The Lio host must keep original source metadata internally, use text in the
requested language, avoid provider/interface text in the public answer, and use
the approved uncertainty response when no entry matches. It must not infer visa
eligibility, booking success, payment setup or personal identity from guidance.
