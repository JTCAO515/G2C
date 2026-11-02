# Explicit publication commit-tail check V3

Additive trusted-producer method; old processing/publication factories and frozen
wire formats stay unchanged. Data2, output2, MEMORY-PUBLICATION-result@2 and
original result queries are still the same grammar. This adds no store or role.

```python
policy = collection.publication_policy_v3(context, token, job_id, attempt_id,
    original_prepared_input, prepared_input_sha256,
    original_model_output, model_output_sha256,
    max_payload_bytes=explicit_bound, before_commit=check_original_budget)
```

before_commit is a required trusted synchronous, bounded callback, never a client
field. It checks the original registered Run/Meter deadline/limits and returns
normally only while that original publication is still allowed. It cannot call a
provider, await, open another C holder, mutate C state, perform cleanup or authorize
any dispatch/resend. It must be read only; no new Meter reserve or claim happens.
Missing callback is rejected; there is no fallback to factory2 after a denial.

C first performs the real filtered rendering, local original-result publication,
the second/final filtered rendering, exact original-result verification, current
source/consent recheck and canonical admission guard. Then it calls before_commit,
immediately before the repository attempts the MEMORY commit. No C render, query,
guard or encoding follows that callback before the commit. Its exception aborts
the entire C transaction: canonical source/item/operation, origin, model checkpoint,
publication receipt and cursor all roll back together. The exception's semantic
type is preserved for B to record the original outcome. B still records published
only after both C and outer MESSAGE commits are known.

Earlier B checks remain necessary, including actual model step/tool/output/time
limits and current admission, cancellation and source checks. This callback does
not reverse real provider work or settled fees. A deadline failure keeps the
original claimed/settled/UNKNOWN Meter evidence; absence of a C receipt is not an
automatic resend grant. COMMIT ACK uncertainty still uses the original query.

Positive/negative C private-PG evidence runs the real final rendering and advances
a synthetic clock to the limit only after it finishes. It checks actual canonical,
source, operation, origin, checkpoint, receipt and cursor rows. B's actual worker /
unique Meter consumer separately verifies that its settled financial state remains
truthful after this rollback. L2 real model, fees, cloud and device remain UNRUN.
