# Explicit dialogue Trip adoption

A `DEMO-dialogue-action.1` with `operation:"accept_trip"` names the exact
original `trip_candidate` card and its version. The service checks the current
conversation and protected planning source, records the explicit action intent,
and invokes C's canonical Trip acceptance once. A candidate can only write
a formal Trip through that original operation.

The original dialogue action receipt has `operation:"accept_trip"`, the
original action digest, `trip_id`, and `committed_version`. The
`message_id`, `run_id` and `card` response fields are null for adoption.
`GET /v1/demo-dialogue/actions?action_id=…` recovers the same result
from the canonical receipt. If the intent exists but the original result is
unknown, the service withholds a success receipt and never submits the action
again. Changed input with the same action ID conflicts.

The terminal cursor still resumes an empty completed stream after adoption.
The previously emitted candidate remains tied to its original planning RUN.
