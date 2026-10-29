# Local MEMORY save/read activation (#226)

The signed local API can opt in with `CJ_LOCAL_MEMORY_POLICY` pointing to a
private, regular, operator-owned JSON file. Missing environment configuration
keeps MEMORY unavailable; an explicitly supplied invalid file fails startup.
There is no policy default, wildcard identity, automatic text classifier, or
production/cloud activation. Existing MEMORY wire fields remain unchanged.

## Explicit configuration

The top-level keys are exactly `version`, `expires_at`, and `profiles`.
`version` is `local-memory-policy.1` (a local configuration format, not a new
MEMORY wire version). The deadline is an explicitly supplied offset-aware ISO
instant; no product duration or retention period is invented. Profiles are keyed
by the authenticated local JWT subject, never a request owner field.

Each profile explicitly supplies `subjects`, `slots`, `extents`, and `context_ids`.
A slot entry supplies `kind` (fact/experience/preference), `collection_allowed`
and `semantic_resolved` booleans. All fields are required. Sets are immutable and
exact, without translation, trimming, case folding or other input normalization.

- The configured subject/slot is a canonical identity selected in an explicit
  structured manual save. Text is preserved verbatim as the user's declaration,
  not certified as an objectively verified fact.
- `collection_allowed` authorizes collection only within that configured slot;
  it is operator policy, not a client/model approval flag. Sensitive or unapproved
  collection must not be enabled by configuration. There is no hidden content
  classifier or claim to detect every sensitive phrase in free text.
- `semantic_resolved` attests the configured subject/slot identity. False remains
  candidate. Inference remains candidate even when this flag is true. Automated
  extraction must not use the manual endpoint as a substitute for source authority.
- Current-context references in this local host are explicitly selected owned,
  active MESSAGE conversations. Merely appearing in the policy set is insufficient:
  the signed host rechecks actual resource ownership during the request lifetime.

The policy is read at startup. Configuration changes require restart and do not
rewrite existing rows, renew old source expiry or reinterpret historical receipts.
Edits/withdrawal and in-flight publication fencing remain #17/#227 responsibilities.
This server slice does not activate App onboarding or automatic conversational
memory writes; #227/#228 retain those acceptance requirements.

## Transactions and authority

The host derives the stable existing local scope from verified issuer/subject.
Only `cj_m1_runtime` executes business SQL. Migration 0015 adds FORCE RLS to the
four existing MEMORY tables using the existing transaction-local message scope.
No applied migration is edited, no owner/superuser role is used for business reads,
and no DELETE, source-approval update or item/receipt rewrite privilege is granted.

Saving needs SELECT/INSERT plus scope epoch UPDATE. Source `SELECT FOR UPDATE`
needs UPDATE privilege on at least one column; scope-only UPDATE, together with
matching RLS USING/WITH CHECK, permits the lock without allowing scope reassignment
or source-content/approval changes. See the [PostgreSQL SELECT documentation](https://www.postgresql.org/docs/16/sql-select.html).

`Repository.transaction_binder` runs after transaction isolation is established
and before domain SQL. The signed host supplies the existing binding hook, which
rejects retained authority and uses SET LOCAL. After commit/rollback, plain SQL on
a surviving physical connection has no scope. The optional unbound path remains
for existing isolated domain drivers; with runtime RLS it fails closed and is not
public activation. Remove that compatibility path only after its consumers migrate.

Fresh request guards retain AUTH checks, source/resource checks, postcommit
withholding and original-operation recovery. Namespace provisioning never updates
an existing scope row, avoiding both reactivation and a self-lock during precommit
checks. The deadline is rechecked for new saves. A byte-identical already committed
operation can return its historical receipt without renewing source authority.
Receipt status is historical, not proof of current effective memory; the existing
current_context/consume_current filters and epoch checks remain authoritative.

## Rollback and verification

Disable local activation before rolling back its migration. The down migration
revokes only the added privileges/policies and retains data. Runtime access fails
rather than switching to initialization identity; reapplying the migration makes
retained rows readable again. Real production migration requires separate approval.

Acceptance is recorded in #226/its PR, with new private PG and signed API tests for
save/replay, commit ACK loss, rollback, postcommit auth denial, restart, canonical
slot conflicts, source expiry without epoch change, tenant isolation and physical
connection reuse. Migration up/down/up and runtime-role data retention are tested.

Run the repository gates:

```sh
uv run --locked python -B scripts/test.py
uv run --locked python -B scripts/pg_suites.py
```
