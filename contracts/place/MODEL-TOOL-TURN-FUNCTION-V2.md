# MODEL-TOOL-TURN-FUNCTION@2

This provider transport is pinned by `native_turn_profile=model-tool-turn-function.2` in the original registered model input. Its only supplier wrapper is `m4_tool_turn_v2`. It succeeds `model-tool-turn-function.1` for new formal real-tool dispatches. The original profile and its four-field envelope remain available for their original consumers and evidence.

The function arguments are bounded UTF-8 JSON with no duplicate keys. The root is an object with exactly one of the following fields.

- `answer` contains exactly the two non-blank strings `zh` and `en`.
- `calls` contains one to four ordered entries. Each entry contains exactly `name` from the registered tool set and an object `arguments`. The final round accepts only `answer`.

The adapter projects an accepted root to the existing internal `MODEL-tool-turn.1` form and validates it with its frozen parser and tool bounds. The answer branch gets the host-defined version, answer kind and empty calls. The calls branch gets the same version, tool kind and null answer. The model authors neither the internal discriminator nor those constants. Both fields, additional fields, malformed content and old wrapper identities fail closed under v2.

The original supplier function name, ID and argument string remain intact in assistant history. The next tool message binds the original wrapper ID and retains all original ordered results. The registered model input and supplier wire digest still identify the same attempt. DONE, complete usage, supplier identity, strict parse and final authority must pass before the original receipt is settled. An invalid or uncertain response stays attached to its original INTENT. The transport never retries or falls back to the other profile.

The triggering live evidence is the c337 English weather continuation in #523. Its retained presence mask was 4 with zero extra fields after HTTP 200, DONE and usage. The exact nested answer remains UNKNOWN. The v2 shape accepts an answer-only root only if the existing bilingual boundary accepts its content.
