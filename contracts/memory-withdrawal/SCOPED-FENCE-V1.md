# MEMORY-SCOPED-HISTORY-FENCE@1

Added explicit public passthrough on C `cj_memory.scoped_capture.TrackedMemory`:

```python
run = tracked_memory.capture_history(
    original_binding, all_original_message_refs,
    decision_source_sha256s=all_original_decision_digests,
)
```

It calls the original RuntimeMemory.capture_history and puts **that exact same
Fence1 run** in the existing ScopedMemoryConfiguration.registry before returning.
The scoped publisher's existing `registry.captured(original_binding)` therefore
receives the actual held-fence capture, without unwrapping C private state or
constructing another RuntimeRun. Old capture() semantics are unchanged. Missing
or invalid evidence throws before publishing a new registry value. Actual
restricted-PG capture tests assert object identity and both stale/new original
history denial after erasure. No new storage, authority, scope or Meter is added.
