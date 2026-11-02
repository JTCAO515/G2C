# Automatic account-basis scheduling V1

Corrective scheduling for the existing explicit IncrementalProducer. JOBS@1 wire,
old per-stream enqueue, original bytes/hash and Memory epoch fences stay unchanged.
No new table, role, permission, metering outlet or automatic retry is introduced.

One account's canonical publication advances its shared Memory epoch. Automatic
intake must therefore plan/prepare at most one original at a time, then inspect
the next source in a later poll after the original completes. Different accounts
remain independent. Ready sources are ranked by their processed cursor, then
conversation ID, rather than permanently preferring a busy lexical first chat.

The new trusted `Service.enqueue_serialized(token, original_jobs1_bytes)` reenters
the same protected source and canonical Memory transaction. Inside that holder,
it refuses another pending/inflight/UNKNOWN original at the current Memory basis
and current consent/source version. This atomic check prevents a concurrent or
repeated poll from preparing a second source before the first commits. A known
pending original resumes its exact original bytes; inflight/UNKNOWN never receives
another begin, attempt or provider call. Failed/cancelled intervals remain blocked
at their original stream. No existing original's Memory basis is rewritten.

Old source versions/disabled grants or a public MESSAGE head proving the original
generation/epoch no longer exists cannot publish and do not permanently block an
independent enabled conversation. Those are negative metadata comparisons only;
they do not grant a source. Actual enqueue/start/model/publication still uses all
normal admission, current source, immutable bytes and original Meter checks.
Lookup uncertainty propagates; it never becomes an inactive/open observation.

The public JOBS@1 HTTP enqueue path retains its original per-stream behavior.
The automatic producer explicitly installs the serialized method. No weaker
factory or per-stream fallback is attempted after a busy/unknown result.

Actual signed API -> original run_once -> BG2 -> unique Meter/Fake regression uses
two same-account conversations and distinct canonical slots. Before the fix, both
jobs had Memory basis 1, the first advanced epoch to 2, and the second became
UNKNOWN without a second model call. Final checks cover one job per poll, repeated
poll and atomic racing enqueue rejection, next-poll fresh basis, both independent
entries retained and zero automatic repeat. The original RED evidence is retained;
real models/fees/cloud/devices remain UNRUN in their normal gates.
