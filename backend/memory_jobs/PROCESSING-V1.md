# Processing source policy (dispatch/claim preparation)

This C-owned adapter is local runtime only. It implements the same hold protocol
as MESSAGE-SOURCE@1 and @2, but is not a Run/Meter/provider implementation or a
capability to resend an unknown attempt. No storage or cleanup privilege is added.

Inside B's original protected HistoryReadContext, call:

```python
policy = collection.processing_policy(
    context, token, job_id, attempt_id, original_input, input_sha256,
    max_payload_bytes=explicit_bound,
)
```

`context` is the actual outer context, not wire principal/scope fields. C binds its
own canonical repository and fresh checker to that captured identity. Original
input is the exact fully encoded `{system,messages}` from prepare_model_input;
input_sha256 is the original B job/operation's digest. A digest or prepared bytes
alone is data and confers no permission.

B installs policy in its public source reader. In its actual snapshot callback,
enter C's public wrapper before the registered exit callback:

```python
return context.with_enabled_source(query, policy,
    lambda snapshot: policy.with_input(snapshot, registered_step))
```

For SOURCE@2 use with_enabled_source_and_travel and its genuine lease as specified
by B. B retains responsibility for binding that selection to its original job and
actual registered exit; this dispatch adapter does not publish current Memory.

The policy holds C Memory below B's existing MESSAGE/Travel locks. It checks the
original job/attempt, exact source query, original Memory epoch, inflight state and
absence of output/checkpoint. with_input compares the actual protected messages
to the original C batch and renders the current exact model input under C's
server policy. Changed bytes, input digest, source, policy, Memory basis or phase
reject before registered_step. The callback receives the exact original bytes,
returns bounded bytes through B, and must use B's unique Meter/Run/cancellation
gates. C rechecks phase and fresh admission on return. Expired wrapper lifetime
cannot be reused.

Dispatch/claim cannot write a C checkpoint. Publication needs a separate C-owned
adapter that validates the original result and commits checkpoint, canonical
Memory and cursor under the same held transaction; its postcondition must allow
that publication's completed state. B never accesses C's transaction or SQL.

Actual restricted-PG tests cover pending, changed bytes/digest/interval, lifetime,
checkpoint and valid original input. Their callback is a fixed marker, not a model
call. Actual JobRun/Meter integration, Source2 current publication and provider
execution remain UNRUN until the corresponding B interface and producer are wired.
