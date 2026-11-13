# Rich ordinal scheduling (WP9, in progress)

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
Reminder generation, full assembly/consumer integration, full tests/CI and any
actual rich/native/provider result are not established by these initial primitives.
