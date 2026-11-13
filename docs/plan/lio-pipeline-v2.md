# #929 planning pipeline v2 — design draft

Authority: #922 §0.1, §2, §3.6–3.9 and G6/G9/G10; JT decisions in
#922/6848017500 override the earlier coordinate-conversion/Textual wording.
This is a design proposal for C co-sign, not implementation or an L2 result.
#919 and #862 remain first. New execution waits for WP2/WP3/WP4, WP0 and
C's explicit structured.4/WP7 plus assembly/WP9 contracts. No frozen legacy
contract, source guard, signature, budget exit or sole writer is replaced.

## Input, authority and selection

The new host consumes an admitted new-mode original plus the complete protected
profile/context. Each known factor has its original quote and MID; inference
cannot override an explicit answer, and defaults are marked and disclosed.
Explicit plan-now selects the next generation round, with no required city,
days/date/party questionnaire. An undated calendar remains undated. The new
mode's documented defaults do not enter the old v1/v2/v3 execution paths.

Factory selection is server code over actual source capability, never a prompt
marker, user option id, DTO hash or a global calendar flag. The server exploration
rollback switch defaults on for the new mode; turning it off selects the retained
compatible implementation before dispatch. It is not an A/B allocation, and a
failed supplier attempt never triggers a second strategy/model call.

C's existing `LioCalendarPublisher`, calendar source leases, date conversion,
protected CurrentNeedsSource, Trip CAS and `_act_in_tx` provide the existing
publication boundary to extend explicitly for structured.4. WP7 must define the
new original protocol acceptance and source references; a .4 original must never
be relabeled as .3 merely to pass an old source guard. #862's preserved original
wire and compatible rollback are prerequisites, not a new write grant.

## Eight steps

All module names marked “new” below are proposed seams, not current APIs.

| Step | Input and deterministic output | Code / owner | Failure behavior |
| --- | --- | --- | --- |
| 1 Understand | Original text, held profile, known/memory sources and scene → one compiled plan brief, city, duration, pace, date/arrival/departure facts, explicit defaults | L: existing sourced intake + WP3/WP4; new `local_lio_pipeline` host | No unquoted fact enters the profile. Invalid/uncertain AUTH, original source or Meter stops via its existing boundary. User-facing brief/progress is code-generated. |
| 2 Skeleton | Compiled brief → day/area/theme and typed sight/meal/lodging candidates with factor-key reason references | L host, registered model operation; C skeleton normalizer for WP7 | Strict schema ≤1536 output tokens, target about300. Complete shape required; no truncation repair, supplier retry or unchecked JSON. Preserve failure/UNKNOWN. |
| 3 Retrieve | Skeleton, city and exact names → bounded search/nearby/detail observations, raw POI IDs/GCJ-02/address/opening facts and provenance; lodging area +2–3 suggestions | L-owned `backend/place/**`; new explicit v2 tools in `real_services` | Known terminal missing/failed tool data leaves only the original skeleton suggestion as unconfirmed. Never manufacture a POI ID or coordinates. An uncertain paid attempt retains its original hold/stop rules. |
| 4 Choose/order | Candidate sets, pace, known time windows, protected fixed/retained items → ordered day items and proposed adjacent pairs | C: extend `cj_feasibility/solver.py` CP-SAT through WP9 | Keep locked items/current version. Missing facts stay unknown. Infeasible hard windows produce a conflict and adjustment suggestion, not a fabricated feasible schedule. |
| 5 Legs | Exact adjacent endpoints plus hotel and airport/station endpoints → mode/distance/duration and original route evidence per pair | L v2 route adapter, C pairing validator | Walking at ≤1.5km, otherwise transit/metro, then taxi; these are code policy. If a permitted route is unavailable, mark that leg unconfirmed. No invented duration or conversion of estimates into future guarantees. |
| 6 Schedule/check | Items and actual legs, source date/zone, arrival/departure overrides, H conditions → structured.4 candidate plus sourced date checks/notices | C WP9 solver, date checks and notice generator; original #860/#861 boundaries | Apply the §3.6 first/last-day rules and explicit user override. Reject known opening/fixed-window conflicts before claiming a verified schedule; do not drop fixed items. |
| 7 Wording | Bounded batches of already chosen items/known reason factors/H facts → one reason sentence and one tip per item; English names with Chinese | L registered model calls, C reason/source projection; pypinyin display helper | Model only rewrites, never adds a notice, booking/price, policy fact or new item. Unsafe/invented reason is removed by code. A failed wording batch leaves safe code-projected names and unconfirmed/absent text, with its failure recorded. |
| 8 Save/present | Strict candidate + held originals/NEEDS/Trip basis, valid source checks and signed confirmation → sole actual commit, new card/version, summary and buttons | C sole publisher; L v4 projection/progress/summary; A consumer | Say saved only from the actual receipt. UNKNOWN queries the same original action, without a new MID/action or supplier replay. Declared tool-data fallback does not waive final AUTH/source/clock/Meter/current-head checks. |

External work runs outside MESSAGE/NEEDS/Trip publication locks. Every returned
async result is checked against its original scope/attempt/profile before use;
publication reacquires real source leases in the existing order. No concurrent
worker or new payment/ledger writer is added.

## Richness and calendar rules

Pace is a typed server choice from the protected profile, with the explicit
moderate default disclosed: relaxed2 sights +2 meals, moderate3+2, packed4+2.
The WP1 “3–4 stops” shorthand is not substituted for §3.9's exact table. WP1's
legacy fixed/retained paths do not prove the full v2 G6 claim.

C applies arrival+2h; departure ends3h before a flight or1.5h before a train.
Without arrival/departure time, day1 begins in the afternoon with one nearby
sight plus dinner, and the final day stays nearby in the morning. Undated plans
use day1/dayN. An explicit first-day-full request is a sourced override, mentioned
in the summary. The first/last-day exceptions are evaluated separately from
ordinary full-day pace counts, never silently treated as dense full days.

Every site has a real retained Gaode ID or is visibly unconfirmed. Route coverage
is measured against all required adjacent pairs, including hotel/airport legs,
not only the pairs successfully queried. At least90% tool-sourced legs is a G6
quality gate, not permission to manufacture the remaining10%. Tool failure may
still yield an honestly unconfirmed saved plan; that run's G6 remains FAIL when
coverage/richness is below the gate. Local correctness does not make it L2 PASS.

One-day combined arrival/departure windows and explicit contradictory times must
be covered by C's deterministic §3.6 tests. Where both constraints have no common
window, preserve the conflict and original itinerary; this document does not
invent a precedence or loosen JT's accepted first/last-day rules.

## Per-itinerary call/output budget

The new host admits a complete plan budget before dispatch and counts actual
supplier attempts, not logical tool labels or successful responses. Cache hits
count zero new external attempts only when the original exact query/result and
read eligibility are retained; they are not new evidence for another date/query.
The existing registered exit, per-RUN/account/global authorization and UNKNOWN
holds remain the spending boundary. WP0's larger approved totals are not a new
secret, actor, lease, accounting period or automatic balance reset.

| Operation | Maximum | Allocation |
| --- | --- | --- |
| Model | 6 | At most1 understanding +1 skeleton +4 wording batches. An already compiled understanding uses fewer calls; no repair/retry allowance is added. |
| Model output | 1536 tokens per call | Native registered `max_tokens` is bounded before send and actual final usage is retained. A character/UTF-8 count is not token evidence. |
| Gaode city/catalog | 1 | Count an actual outbound request if needed; reuse only an eligible exact observation. |
| Gaode search/nearby/detail | 17 | Includes lodging and arrival/departure endpoint lookup; no hidden per-site detail fan-out. |
| Gaode route | 25 | Includes walking/transit/taxi alternatives and hotel/airport legs; unsuccessful attempts also consume this allocation. |
| Gaode weather | 2 | Date-specific query only when meaningful; unknown/undated is not a made-up forecast. |
| Gaode total | 45 | The allocations sum to45; redistribution is permitted only within the same admitted total, before dispatch, with per-attempt custody. |

Long trips cannot multiply model calls by days. Code partitions wording into at
most4 deterministic batches, each with an explicit bounded item set; remaining
text can use safe code projections of the existing skeleton/results. Full day
coverage is still required in structured.4; a supplier length finish or partial
JSON is refused, not trimmed into a valid shorter trip. For long trips, repeated
routes may reuse only exact eligible queries. If25 route attempts cannot prove
90% of all legs, record G6 FAIL rather than hiding the denominator or overspending.
C's long-trip controls must assert both full coverage and the actual ceilings.

## Latency and progress

G5 is measured separately for exploration's first visible segment p95≤6s.
G9 measures generation's first visible text p95≤8s and complete plan p95≤30s.
A code-rendered brief/progress comes from the actual admitted planning state; an
empty SSE event, timer-only skeleton or unrelated cached answer is not first text.

The design budget is: understand/brief0–3s, skeleton3–6s, parallel lookup6–12s,
selection12–13s, bounded parallel routes13–20s, final schedule20–21s,
wording batches21–27s, validation/commit/presentation27–30s. These are allocation
targets, not measured percentiles or independent guarantees; the30s wall budget
includes all stages and concurrent work. Do not sum individual p95 values.

Local scheduler deadlines stop new dispatch without replacing the existing
publication deadline. If a tool branch times out with a known terminal failure,
keep its unconfirmed skeleton. AUTH/source/payment UNKNOWN and final publication
deadline failure retain their existing fail-closed behavior. Saving honestly
unconfirmed tool data is distinct from bypassing an uncertain original action.
C records client-visible first segment, first generation text and completed
receipt timestamps for a preregistered cohort, with all FAIL/UNKNOWN/UNRUN intact.

## WP7/WP9 interface obligations

- `structured.4` adds explicit kind, place, note/tip, reason_refs, adjacent legs,
  daily theme/area and lodging. Frozen structured.1–3 are unchanged. Source claims
  bind real same-attempt provider observations and original input/Trip version.
- Coordinates are raw provider GCJ-02. No coordinate conversion library is added;
  Wikidata supplies only reviewed Chinese/English names and QIDs, never geometry.
  H's entries-v2 conditions retain source/date/expiry and unknown fields.
- Route validation binds exact endpoint IDs/coordinate roles/mode/query. A leg
  referencing nonadjacent items, stale/foreign output or a fabricated route is
  refused. Hotel/arrival endpoints are explicit, not inferred lat/lon guesses.
- Reasons may reference only existing known or memory profile factors. Inferred,
  default, refused or absent factors are not promoted to an “as you said” reason.
  The brief is code-generated from its actual accepted facts/defaults.
- Notices are code-generated, at most2 per round, from dated checks, H conditions,
  chinese-calendar, actual route durations or explicit season rules. The model
  may rephrase only. Unknown dates/holiday data do not become a positive fact.
- Venue opening hours must be machine-readable/confirmed before enforcing a hard
  conflict. An unparsed provider string is unknown. No H entry or model memory
  substitutes for actual date-dependent evidence.
- Public `progress`/exits use WP2's additive LIO-message.4. Backend operation IDs,
  source hashes, tool names and private custody metadata stay out of UI text.

## Evidence and co-sign

This draft has no executable or measured result. L0 must cover budget dispatch
boundaries/invalid or truncated JSON/source/subjects/retained locks. L1 must cover
ZH/EN each3 native signed chains, long trips, unavailable tools, stale/current
source, wrong/expired signatures, UNKNOWN/original recovery and old-Trip isolation.
C independently co-signs the interfaces and deterministic schedule/notice tests.
L2 later uses a B-issued same-source/image actor/window and current budget; local
fixtures do not establish latency, real provider acceptance or physical-device
PASS. JT's G12 remains JT's separate TestFlight decision.
