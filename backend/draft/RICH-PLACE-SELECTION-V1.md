# Explicit place selection source (#931)

This is a private component candidate. It does not enable native4, install the L
host, grant provider calls, qualify a deployment, or establish G6. Existing
`RichProviderContextSource` and `LioRichPublisher` remain the default.

## Versions and ownership

| Artifact | New opt-in version | Existing version |
| --- | --- | --- |
| Selection result | `LIO-place-selection.1` | No old selection result exists |
| Combined live source | `TRIP-RICH-PLACE-SELECTION-SOURCE.1` | `TRIP-RICH-PROVIDER-SOURCE.1` unchanged |
| Retained plan source | `TRIP-RICH-PLAN-SOURCE.2` | `.1` remains readable and unchanged |
| Publisher policy | `LIO-rich-selection-pipeline.1` | `LIO-rich-pipeline.1` unchanged |

No TRIP structured.1–4, MESSAGE, provider-result/outcome schema, applied migration,
source-ref kind, signing, or authorization version is changed. Only the new plan
source adds `place_selection_version` and `place_selections`; it retains the full
original `provider_records` and `provider_outcomes`. New history consumers check
the retained v2 selection against those bytes, then enter the same historical
MESSAGE, current Memory/profile, NEEDS and Trip holders. Retained data does not
grant a live capture, a new query or an undo permission.

## Selection rule

The C source is installed with the actual registered provider reader. Its issued
capture must contain all eligible place/route records and original outcomes.
Sealing remains outside RUN/Memory/NEEDS/Trip publication locks. It performs no
query, replay, Meter mutation, first-result choice or model matching.

Each POI outcome must be the original `tool.lio_poi2.1` keyword request
(`TextSearch` or `Nearby`) with nonempty code-owned targets. A target occurs in
one original keyword operation only. All place records must have the exact
`operation_id + ':poi:' + amap_id` reference of that operation, with their actual
payload digest. A place observed by another query cannot establish this target's
match. POIDetail has no original keyword and is refused by this opt-in component;
the host must not fabricate one. Original route observations do not establish an
item lookup failure.

For a complete terminal original page, compare the original query keyword with
the observed `name_zh` of its eligible place records, using exact string equality:

| Original / eligible observations | Selection | Fallback target? |
| --- | --- | --- |
| `unavailable`, zero items | `unavailable / provider_unavailable` | Yes |
| `ok`, zero items | `unavailable / empty_page` | Yes |
| `ok`, nonempty, zero exact eligible places | `unavailable / no_exact_eligible_place` | Yes |
| Exactly one exact eligible place | `matched / unique_exact_place` | No |
| More than one exact place | `ambiguous / multiple_exact_places` | No |
| No operation, UNKNOWN/unsettled, wrong/missing binding | No eligible target | No |

The provider's original `status`, `item_count`, paid attempt, raw reply hash and
all eligible records remain unchanged. Selection unavailability says no unique
usable name was established by this code rule; it does not say the provider page
was empty or the venue does not exist. Ambiguity requires the host to withhold the
candidate; it must not silently pick the first item or call it unavailable.

Each result carries the target, operation ID, original keyword, canonical outcome
SHA, complete same-operation eligible refs, selection status/reason and the exact
selected record (or null). Formatting limits or unsupported English rendering do
not turn an existing exact place into an unavailable observation.

## Host composition

Explicitly compose `RichPlaceSelectionContextSource` and
`LioSelectedRichPublisher`; a new source on the old publisher is rejected, so
new selection fields cannot be written under the old plan-source version.

After genuine provider operations settle, call `seal_providers(binding, calendar)`.
Within the actual `hold_for_publication(binding)` frame, call
`place_selection(binding, capture, target, keyword=original_stop_name)`.
The keyword must equal the actual registered target query. Use its
`selected_record` as the one selection result, then format the observed Chinese
name/address/unchanged GCJ-02 coordinate. Do not import a second matching rule or
accept a model-supplied success/failure marker. Returned dictionaries are display
copies, not capabilities; changing one cannot change the source's fallback set.

The new source exposes only those POI targets whose issued selection status is
`unavailable`. The existing assembly and publisher still require explicit
`UNCONFIRMED_SKELETON`, complete source-covered `unconfirmed_items`, unconfirmed
place state, original locks, checks and final sole-writer eligibility. A matched,
ambiguous, absent or foreign target cannot be promoted by an assembly flag.

New operations invalidate the old provider seal. If routes are collected after
selection, seal again and use the current capture for assembly/publication;
never promote an expired selection copy. Copied, foreign, replaced, closed or
changed provider/profile/calendar holders remain invalid. Final checks still run
through the existing publisher transaction and rollback path.

## Verification and integration

`test_rich_place_selection.py` covers the code/source boundaries and preserves the
old source behavior. `rich_selection_pg.py` opts the existing signed native4
private-PG sole-writer fixture into nonempty `ok` pages with no exact match,
including final-check withdrawal rollback and historical v2 source readback.
`rich_selection_undo_pg.py` reuses the actual two-plan/append-only undo fixture
with the new source/publisher. All model/tool transports in these are synthetic.

The author slice is for L integration. Before shipment it still requires the
source-boundary independent review, exact CI, E's actual new scope, L's full
production composition, deployed source/image qualification and a new B window.
The national16 plan/IDs/budget are unchanged. P0 deployment and L's eight basic
cases remain ahead of C's actual nationwide acceptance.

## Scoped adjustment for WP5

The host may configure `LioSelectedRichPublisher(..., adjustment_authority=check)`
after issuing an actual adjustment decision under the current LIO-message.4
original. The check receives `(binding, original, adjustment)` and must confirm
the same owner, conversation, original MESSAGE/RUN, Trip head and authorized
operation under the actual current holder. The host supplies the genuine
calendar/profile/provider holders and checks for that original. An ordinary
generation profile that requires a literal plan-now trigger cannot issue the
adjustment decision.

Pass `RichAdjustment(head=TripHead(trip_id, version, content_sha256),
item_id=..., operation='replace' or 'remove')` to
`conditional_adjustment_source(binding, original, capture, checks, document,
adjustment)` for assembly and to
`publish_adjustment_for_message(binding, original, current, assembly, capture,
adjustment=adjustment, checks=checks, before_publish=...)` for commit. A
replacement keeps the ID and time slot of the authorized suggestion. A removal
drops just that item. The host supplies the complete candidate with current
eligible evidence, including exact affected route endpoints. Unconfirmed edges
are still represented as such. The publisher checks the unselected items,
metadata, untouched route legs and unselected NEEDS, then rechecks the original
authority in the sole existing publication transaction.

The return value is the existing rich plan receipt for this run, available via
`Repository.rich_plan_receipt(binding)` with `action_id`, `trip_id`,
`committed_version` and `candidate_hash`. The next Trip head uses the raw
content digest from the revision readback. History and rich undo use the
existing revision and source-hold paths.
