# MODEL-TOOL-TURN-STREAM@1

An optional internal transport for the existing registered M4 Beijing model
operation. Hong Kong beta may select one explicitly invited synthetic subject
through the worker's private environment file. Unselected operations retain
`model-tool-turn-function.2` and its existing bilingual envelope. Neither the
public RUN SSE wire nor the original MESSAGE/Meter binding changes.

Each original model turn sends one request and pins this profile in its Meter
input. It returns one of two shapes:

- **Answer:** nonblank UTF-8 assistant text in the language of the request;
  no tool deltas and a `stop` finish. The worker can publish guarded, bounded
  partial text on the original RUN before the final provider receipt. After the
  first fragment, it groups more text to limit database writes.
- **Tools:** up to four complete native calls, with contiguous indexes and
  distinct supplier IDs; no assistant text and a `tool_calls` finish. Registered
  tool parameters, identity, and original model/Meter receipts must pass before
  any tool dispatch. Each result refers to its original supplier call ID. The
  worker still executes tools through the original ordered registry and limits.

Terminal success requires one stable model response identity, terminal token
usage, `[DONE]`, and original settlement. Mixed text and tools, invalid
identity or arguments, and interrupted or incomplete receipts never start a
tool from that turn. Previously committed guarded partial text remains on the
original RUN; uncertainty remains `UNKNOWN` and is never retried as a new
operation. Owner, cancellation, Memory, budget, expiry and credential echo
checks continue to apply. The last allowed model round disables tools.

Supplier shapes are described in [Model Studio Chat Completions](https://docs.modelstudio.console.alibabacloud.com/en/model-studio/qwen-api-via-openai-chat-completions).
