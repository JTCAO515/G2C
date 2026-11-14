# MODEL-TOOL-TURN-STREAM@2

Hong Kong Demo and its existing synthetic assembly pair may select this internal
transport in place of [STREAM@1](MODEL-TOOL-TURN-STREAM-V1.md). The original
registered Meter input pins the selected profile. The public MESSAGE and RUN
event contracts stay the same.

A turn that permits tools buffers assistant text until the original response
has passed its identity, terminal usage, finish and `[DONE]` checks and the
original Meter receipt has settled. A text-only turn with a `stop` finish then
releases its answer. When a `tool_calls` turn contains both text and valid
native calls, the worker discards the text and continues with the validated
calls and their original supplier IDs. The discarded text enters neither the
RUN display nor the next model input. Tool dispatch still uses the original
registry, ownership, cancellation and budget checks.

The final tools-disabled round can publish guarded partial text as in STREAM@1.
A tool delta in that round, a finish that disagrees with the response shape,
invalid calls, or incomplete receipts still reject the original turn. Any
uncertainty remains with that original request. Recovery never issues a second
provider request for the same turn.
