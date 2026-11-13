# Rich ordinal scheduling (WP9)

Authority: #922 / WP6 design and WP7 contracts. These are new pure scheduling
primitives, not a writer or proof of real feasibility. The old solver Problem,
version, NEEDS/booking requirements and negative cases are unchanged.

`rich_solver.Problem` takes immutable Visit windows, protected fixed starts,
explicit known/unknown directed transfer seconds, and optionally a frozen order.
Clocks are integer seconds relative to explicit day ordinals, so no date or
booking fact is fabricated. Windows may include a declared crossing-midnight
duration; global occupancy is checked. Cross-day route input needs explicit
itinerary representation first and is not silently attached to an unrelated pair.

Without frozen_order a bounded single-worker CP-SAT circuit finds same-day order.
With it, only times may move; old route pairs cannot be reused after a reorder.
Every original visit must appear exactly once. Independent verification checks
the original windows, fixed starts, complete order, occupancy and known travel
amounts. Unknown travel remains in unknown_transfers and real_feasibility is
always UNKNOWN. CONFLICT is only under the explicit supplied constraints; a
resource/horizon/timeout/cancellation does not become an infeasibility proof.

`rich_edges.activity_windows` compiles §3.6 bounds for proposed activities. Actual
fixed facts must separately remain exact and be checked by the source authority;
they are not dropped/moved to fit a default. Arrival+2h and departure flight−3h /
rail−90m can roll over ordinals. Unknown arrival uses the light afternoon recipe;
unknown departure ends at noon nearby. A supplied full-first-day request waives
the soft light-day/padding rule, never known physical arrival, and emits a code
explanation marker. A one-day incompatible first/last window is reported rather
than assigning an invented precedence. Missing departure mode remains uncertain.

`cj_trip.rich_reasons` consumes accepted native profile values formatted by code.
Only known/memory references survive; invalid/inferred/default/absent references
are removed. The code brief separates what the user said, saved preferences and
explicit defaults, plus a requested first-day override. Model prose/public profile
projection must not be used as the protected fact input.

## Dependency license inspection (no production activation)

WP0 PR940 authorized the local chinese-calendar project. Pin:
`chinese-calendar==1.12.1`, import `chinese_calendar`. PyPI's exact distribution
and the official project point to liriansu-opus/chinese-calendar (the former LKI
URL redirects there). No runtime network, new account or paid service is needed.

- [Exact package](https://pypi.org/project/chinese-calendar/1.12.1/), pure Python,
  requires Python≥3.10; installed local data covers 2004–2027.
- Wheel SHA256: `201168423c879a9584b5cd13054f039a2ff34dad9cf5f822dd1133379983a79e`.
- The wheel's `chinese_calendar-1.12.1.dist-info/licenses/LICENSE` was read in full;
  it is MIT, copyright2017 Lirian Su. Original LICENSE SHA256:
  `30666775fe057af3c56b5b9224869de21d27a17ed86eabe87f56b58b5fe02f9f`, identical
  to the [upstream original](https://github.com/liriansu-opus/chinese-calendar/blob/master/LICENSE).
- Retain its copyright/permission notice when distributing substantial copies;
  the dependency carries its original license. No third-party code was copied.

The API's generic is_holiday also returns true for an ordinary weekend. Notice
classification must use actual named holiday/workday data, never promote weekend
or adjusted workday to a statutory exception. Unsupported years remain UNKNOWN.
Calendar observations do not establish actual venue opening or holiday exceptions.

## WP8 assembly interface

`cj_feasibility.rich_assembly.assemble` takes a model candidate plus the separate
protected `RichSource`, accepted native `ProfileFact` values, and host-compiled
`Activity` constraints. The host's source authority qualifies all windows,
hotel proximity and meal periods; model names/city labels are not location proof.
Unknown clocks or nearby status return UNKNOWN. Unknown-arrival day1 requires
exactly one new nearby sight plus dinner; unknown-departure dayN stays nearby in
the morning. Existing protected/fixed/retained items remain complete and byte
exact, including their source/evidence/time fields, outside those soft defaults.

The `order` phase accepts only unconfirmed legs and reconstructs all same-day
adjacent pairs after the CP-SAT order. The `schedule` phase freezes those pairs
and uses the observed route amounts (rounded **up** to integer solver seconds).
Actual quantities and original raw GCJ-02 remain unchanged in content. New
clock starts use a 60-second quantum so HH:MM output never truncates a solver
gap. Candidate/source validation runs before and after projection. Illegal
known/memory reasons are removed before that boundary check; code formats the
separate brief from protected profile values and disclosed defaults.

The return is an intermediate conditional candidate, not publishable authority
or a verification claim. `date_checks_must_be_recomputed` means dated times moved:
the WP8 host must recompute #860 checks on final times, capture the new results,
then validate that final candidate before its native sole commit. Retaining an
old captured check does not prove the moved schedule. Known opening conflicts
return CONFLICT. Source eligibility, exact final protected profile/Memory/Trip
epochs, source windows and actual write/undo remain host responsibilities.

## Deterministic notices

`cj_trip.rich_notices` generates immutable notices from exact captured #860
checks, validated H entries bound by original digest and qualified subject/item/
Gaode identity, actual route amounts, calendar data, and explicit winter/outdoor
classification. There is no model-written notice ingestion path. The host must
retain these code notices; any wording stage cannot replace them with a model's
new facts/IDs/types/sources. `select_notices` deduplicates stable IDs and returns
at most two, prioritizing opening/check conflicts and required booking before
routine advice. Citation dates are not fabricated instants; H checked_on alone
therefore yields observed_at=null. Empty public URLs stay null.

`rich_calendar` separates ordinary weekends, named holiday breaks, makeup work
days and unsupported-year UNKNOWN. A named break alone cannot prove a statutory
venue exception: that closing day stays explicitly uncertain. An ordinary
weekend/makeup working day never clears a weekly closing rule. H `window_max`
and `minimum_lead` have separate templates, including optional booking versus
required reservations. Only actual route duration strictly over 3600 seconds
produces a long-transfer notice. Winter advice uses no guessed weather/date.

These are L0 components for WP8. They do not enable HTTP4, source collection,
new runtime packaging, formal rich saving/undo, Hong Kong deployment, G6/G9/G10
or real-world feasibility. Legacy solver, structured.1–3 and all old checks are
retained; no existing check or test is deleted.
