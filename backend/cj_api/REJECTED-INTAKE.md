# Private rejected intake capture

Only the actual `model.lio_intake.9` / `model.lio_intake.0` complete producer can
register raw output. A definite original Meter settlement must acknowledge that
same operation before rejection can persist it. No input/request/header copy,
extra provider invocation, replay, static success or public endpoint is added.

The L consumer encloses its original stream and parser:

```python
with capture_rejected_intake(binding, check_running=lambda: worker._running(binding)) as capture:
    raw = ''.join(the_original_registered_stream)
    try:
        parsed = the_original_parser(raw)
    except actual_validation_errors as error:
        receipt = capture.reject(diagnostic_code(error), raw.encode('utf-8'))
        # Preserve the existing none-authority barrier and guarded fallback.
```

Normal parse, normal date/booking clarification and transport/settlement UNKNOWN
exit without a file. `finally` drops buffered references; it does not remove a
previously confirmed private reference or change fees. CAPTURED/NOT_CAPTURED and
exceptions remain distinct; a ref is not proof of product quality or live usage.
The operator must read through the current original source/Memory/AUTH/erasure
boundary, never use a ref to resurrect an erased payload.

Files require an owned 0700 directory and 0600 mode, exact native binding and
receipt, source lifetime checks before/after filesystem work, and seven-day TTL.
Only output bytes plus minimal original IDs/hashes/public receipt metadata are
stored. A failed new write/lifetime close removes only its unconfirmed file.

HK wiring is B-owned: provision `/srv/g2c-beta/rejected-intakes` as UID 10001 and
0700, mount it only in the worker at `/rejected-intakes`, and verify actual source
and permissions in the deployment window. The default worker requires this
store and periodically prunes it. Before activation, exclude it from external
file backups; the existing checkpoint/OSS backup container has no such mount.
Install the supplied independent minute timer with a root-owned 0600
`rejected-intake-gc.env` pinning `REJECTION_GC_IMAGE` to the exact reviewed capture
image ID. It has no network, credentials or budget mount and remains pinned when
an application rollback removes worker-side pruning. Retain that image while
any capture can remain. Verify the timer and an expired fixture before enabling
capture. Reverting the app must not restore diagnostic files or disable TTL.

Implementation/tests are not HK activation. B must separately verify the store,
backup exclusion, immutable GC image/timer, source/image and actual lifecycle.
