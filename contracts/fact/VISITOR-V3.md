# FACT@3.0 — nationwide visitor guidance without a city (#1756)

Additive to FACT@2.0 (`VISITOR-V2.md`). `FACT-query.2` / `FACT-result.2`, their schema and their examples are unchanged and keep their exact behaviour.

`FACT-query.3` has `version` and `topic`, and an optional `city`. The topics and the city aliases are the same as v2. A city, when present, is a non-empty bounded string; `null` or an empty string is rejected, never read as "no city".

- **With a city**: matches exactly what `FACT-query.2` matches for that city (`cj_fact.visitor` maps the seven documented aliases; an unsupported city is `no_match`, never another city).
- **Without a city**: only **nationwide** entries match, i.e. entries whose `cities` name every catalogue city. An entry for some cities only is never returned, and no default or inferred city is used. With no nationwide entry for the topic, the result is `no_match` with `entries=[]`.

`FACT-result.3` has the same fields and rules as `FACT-result.2` (data origin, status, server `evaluated_at`, `catalogue_sha256`, bounded and id-ordered entries, expiry at Asia/Shanghai 00:00 on `expires_on`). Its `version` is `FACT-result.3`, and its `query` repeats the v3 query; a `city` key appears only if the query had one.

The request still cannot supply an evaluation date, owner, scope or permission. The catalogue, its approved hosts and its strict loading are the same as v2.

JSON shape: `visitor-schema.3.json`. Synthetic wire examples: `visitor-examples.3.json`. They are not facts and are never loaded as a catalogue.

Host wiring (the Lio tool argument, its description and calling without a confirmed city) is not part of this contract. It belongs to the dialogue path, which keeps the v2 host guarantees in `VISITOR-V2.md`: original AUTH/RUN/Meter guards, request binding, the approved uncertainty response, and no inference of eligibility, booking success, payment setup or identity.
