# FACT-TOOL-HOST@1 — synthetic local worker

New explicit `synthetic-fact-v1` tools profile; CJ_ENV=local, CJ-LOCAL-RUN@2 and
FakeProvider only. It reuses PLACE host's registered model/tool/model loop and the
same OperationStore, RegisteredExit, MeteredExitCore and Meter. No parallel counter,
budget algorithm, network client, source approval, real credential or cost.

Registry is code-owned MappingProxy: existing model.answer, model.tool_turn and
tool.fact. Model turns retain MODEL-TOOL-TURN@1 and contain bounded data only.
FACT-query.1 cannot carry owner/scope/URL/allow/budget/attempt/period. Arguments are
validated before association; the first FACT-tool-input.1 persists the original
query base64, original request_ref and host prepared_at before invocation. Model
keys remain model.tool_turn.<round>, tool keys tool.<round>.<index>, and request_ref
is the original run/logical-position digest. These values are association, not AUTH.

Preparation precedes the final canonical owner/currentness/time guard. Actual
producer.invoke calls existing restricted synthetic acquisition and structured
source parser/evaluator, with zero network IO. Only actual invocation increments
the business counter. Step/tool/output/time limits remain in the one Core; prepared
then revoked/expired requests make zero source invocations while claimed exposure
remains. Cancellation rejects late answers; timeouts keep unknown original exposure
and never redispatch after process reconstruction.

RUN text is JSONL: FACT-output.1 `{data_origin:synthetic,name:fact,operation_key,
result:FACT-result.1}` followed by FACT-answer.1 `{data_origin:synthetic,text_zh,text_en}`.
Cancellation can retain already-published source frames without a later answer.
Original protected RUN reads and cross-owner rejection are unchanged. These new
frames do not broaden frozen PLACE TOOL-output.1/TOOL-answer.1 result semantics.
Without this profile, old model-only/PLACE behavior remains; @1 contexts reject it.

SyntheticFactModel accepts explicit synthetic-city (or 合成城市), weather/天气 or
synthetic rule/合成规则, ISO date(s) and explicit conditions. Missing city/date/kind
produces clarification, not a guessed query. Calendar timezone/category only enter
when explicitly stated. SYNTH_EXPIRED/CONFLICT/UNKNOWN/MISSING/INJECTION/RATE/
MALFORMED/OVERSIZE/TIMEOUT/REDIRECT are code-owned test scenarios; none represents a
real world service or forecast. All input is visibly synthetic and not recorded.

Validation: fact_tool_pg.py uses new private PG, runtime role, signed local API,
formal worker/CLI, positive producer/transport calls, source/period/original ID
inspection, scope isolation and actual Core refusal. Existing FACT suites validate
target/DNS/redirect/body/timeout boundaries. C's typed Memory seam and original
PLACE path remain unchanged; background Memory production #23 stays UNRUN.
