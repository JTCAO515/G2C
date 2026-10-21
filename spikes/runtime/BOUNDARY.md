# CJ-002 local spike boundary v0.1

This is a local test interface, not BASE/RUN/USAGE or a product API.
Only `spikes/runtime/**` is owned by this candidate. The original 13 docs
and shared API/engineering files remain unchanged.

- Workflow ID identifies one DBOS execution and its completed steps.
- Attempt ID identifies one model dispatch, independently of workflow replay.
  Persist intent before dispatch; a crash after intent and before a durable
  response is UNKNOWN, including a crash before the actual send. Replay must
  not dispatch again, even under a new workflow ID.
- Business action key is scoped to principal + operation + stable action ID;
  same key with changed input conflicts. A workflow ID or attempt ID is not a
  business transaction receipt.
- Model/side-effect steps use no automatic retry. A completed external response
  must be persisted before publication. Workflow success is distinct from model
  outcome and business commit outcome.
- Cancellation prevents later steps; an in-flight external action can finish.
  Committed effects stay queryable; a cancelled run cannot publish a new result.
- All examples use fresh synthetic principals/data. No provider credentials or
  network model requests are read or issued. Real model/stream/tool/usage/cost
  validation is UNRUN. SQLite only proves local process restart semantics.

Target packages: AgentScope 2.0.10, DBOS 3.3.0, Python 3.12.14; official metadata
is in `evidence/package-metadata.json`. Local executable checks are recorded
in `REPORT.md`; real-provider validation remains UNRUN. No fallback framework is selected merely for lack of
paid model access.
