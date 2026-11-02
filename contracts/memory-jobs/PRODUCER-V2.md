# Explicit incremental intake and RUN-BACKGROUND@2 composition

IncrementalProducer is a C-owned, bounded local worker intake. It reads only the
actual current account's C consent/queue/cursor and the public protected MESSAGE
head. It does not scan disabled conversations, infer consent from text/manual
save, open B SQL, use a cleanup role, call a provider or implement another Meter.

The host explicitly installs its submit(token,job_id,attempt_id,query,prepared)
callback. That callback constructs B's actual JobRequest and prepares the original
registered background operation. If current scope is needed, the host must use
the actual committed MESSAGE Travel selection and B's genuine joint source lease;
it cannot derive it from text/manual source, retarget another Travel or silently
turn current information into long-term. Mixed/unsupported current source remains
an explicit failure. No provider call runs in a source or Memory holder.

ProducerHost(producer,tokens_for_run,background).run_once(provider) first polls C
for the actual host's supplied signed tokens, then invokes the original B local
background host. It is passed through the existing run_once background_jobs seam.
There is no new default worker, daemon, environment secret or public dispatch API.
Definitively denied roster tokens are skipped before intake, so a revoked account
does not block another owner. Every admitted call still reenters the canonical
boundary; UNKNOWN is explicit and never becomes a default-off observation.

The host must explicitly inject max_payload_bytes and max_conversations (1–100);
neither has an implicit default. One poll handles at most that configured number
of enabled conversations and one 1–100-message range
per conversation. The source's actual persisted cursor determines after. Job and
attempt IDs are deterministic hashes of the captured scope and exact source
query; enqueue retains the original bytes. Known pending C work can begin once,
including after host reconstruction. Inflight/UNKNOWN/failed/cancelled intervals
never mint a replacement or automatically resubmit. Uncertainty propagates for
original-action reconciliation; no generic success or fabricated empty result.

MemoryCollectionAdapterV2 is the explicit C adapter for B's new writer. It selects
the processing/publication factories from the actual persisted original C job
version, not a parse fallback or model purpose claim. Incremental uses Data2 and
factory3; the segmented end version uses EndingPublicationPolicyV3. Both require
B's before_commit original-budget callback at the actual C commit tail. The old
EndingCollectionAdapter remains a separate historical candidate/compatibility
path; new code uses EndingCollectionAdapterV2 or MemoryCollectionAdapterV2 and
never falls back to factory2 on a deadline denial.

No new storage, role, permissions, retention or cleanup domain is added: original
consent/job/cursor/checkpoint/origin remain in the existing memory-derived hook.
Actual C-only PG checks cover signed consent/head intake, default off including
an existing manual Memory scope, historical text as data, exact pending bytes on
resume, persistent UNKNOWN/disabled zero resubmit and two accounts. Submit is an
observation callback there; actual B worker/Fake/Meter has its separate combined
evidence. Real models, fees, cloud and devices remain UNRUN.
