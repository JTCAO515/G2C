# Retained exact classification of one original use

`FixtureScanJournal` connects the existing B fixture reservation, original
consumer claims and native exact scanner. It reads an already reserved use; it
does not reserve a new use. The full canonical claim bytes must hash to that
use's original request and match its binding, pins, attempt and step. The native
MESSAGE ID is that original step, not an independently supplied target.

An owner-only retained directory contains an exclusive, fsynced intent before
classification. Its identity includes the actual reservation/request digests and
frozen C state and private marker-set digests. Concurrent or reconstructed callers
with an existing intent can only query its original result. They never classify
again, even if the first caller failed or lost its acknowledgement before writing
a result. An incomplete/partial result is not repaired or replaced. These files
must survive application releases alongside the existing canonical claims and
reservations; an experiment directory is not an acceptable location.

The private result contains only the scanner's metadata report, not raw private
markers or consumer bytes. On every query the original request/reservation and
current qualifications are read again, the actual E surfaces must still have the
original report's digest, and the native C source must still match its qualified
immutable state. E reads precede C holders, with a final E recheck; no E MESSAGE
lock is acquired inside a C projection. Re-querying evidence is not a second
classification and does not dispatch or charge anything.

This is an at-most-once private scan journal, not the final X09 publisher or
late-write closure. A written result is not proof that the source callback or
the later publication succeeded. Query can still withhold that result. PASS
retains the scanner's explicitly limited coverage and semantic UNRUN; no route
exposes the body to E or activates a paid task. A future final host must include
all task surfaces, native dispatch/post/publication qualification and independent
definition/cost/probe sources before full X01–X12 can pass.

Unit controls exercise the real reservation implementation with controlled
claim/scanner inputs: process reconstruction, concurrent reentry, failed scan,
intent/result ACK loss, changed request, source/consumer withdrawal and late E
surface change. They do not establish native full-task or Hong Kong eligibility.
