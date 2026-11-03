# CLEANUP-CONTROL-RECORDS@1

Explicit client reconciliation records for #27/#24, separate from server cleanup
metadata and DEVICE@3's nineteen content targets. This version grants no ordinary
access, broad Keychain deletion, new HTTP credential or real-device acceptance.

## Provided inventory

PR453's actual App Root at f254fab6 provides these five slots. Each uses service
`G2C.CJAuth.session.<verified-backend-uuid>`, the current applicationIdentifier /
accessGroup, WhenUnlockedThisDeviceOnly and no synchronization.

| Registry ID | Exact slot template |
| --- | --- |
| cleanup-control/selected | M3.Cleanup.Selected |
| cleanup-control/manifest | M3.Cleanup.Manifest.<verified-account-uuid> |
| cleanup-control/execution | M3.Cleanup.Execution.<verified-account-uuid> |
| cleanup-control/device | M3.Cleanup.Device.<verified-account-uuid> |
| cleanup-control/account | M3.Cleanup.Account.<verified-account-uuid> |

Selected routes to an original account/environment and is not a server operation
ID. Other records contain native manifests, original requests/replies, finite
purpose-bound device/progress/receipt capabilities and execution intents. These
are private cleanup reconciliation evidence. They are not ordinary SDK session
credentials, message keys, offline anchors, a90-day diagnostic category, or proof
that private content has disappeared.

## Retention and finalization

While an original action is pending, uncertain or needs restricted recovery,
retain its exact secure bytes. A timeout,503, network loss, token expiry, SDK
logout, process restart or unknown native persistence result is never permission
to report completion, replace the operation, mint a new identity or erase the
only original recovery evidence. Credentials stay in the protected native store,
never files, logs, diagnostics or a server registry value.

For account deletion, A may finalize these original records only after observing
both the original server online content result (`API@1.online_status=complete`,
not the overall unverified-obligation status) and the original device's
acknowledged confirmed receipt. A remote device can use the bounded original-call
representation in DEVICE-COMPLETION-V1.md; a device receipt alone is insufficient.
A must first retire all old writers and
capture the exact original namespace, generation, operation/invocation/request
bindings and expected record bytes. Physically remove the secret-bearing control
records using the owner's proven exact-record primitive, then read back and
verify absence. A changed/replaced record, unsupported comparison primitive,
locked Keychain, uncertain write/clear or another account remains unconfirmed.
No prefix/sibling sweep or cleanup of a newly selected account is permitted.

Selected is cleared only when it still routes to that finalized original scope.
Optional terminal recovery metadata contains only bounded nonsecret hashes and
the actual terminal outcome; no token, original request/reply, path, SDK hash,
key UUID or plaintext account identity. It cannot reopen ordinary access or
recreate finalized native work. Record finalization is its own native evidence;
an invalidated in-memory object or a server result alone does not prove it.

For standalone session invalidation/offline expiration, finalization is confined
to the exact original device action and records exclusively owned by that action.
It does not authorize clearing all account controls, a pending account operation,
another live shared manifest, another account, or a newer generation. Retain
shared/unresolved records until their own dependencies are known.

## Explicit registry/host profile

`CJ-LOCAL-CLEANUP@3` preserves V2's same five configuration keys and account hook
factory, and explicitly uses `freeze_controls`. This freezes the full registry
bytes and the independent online content inventory, plus a distinct immutable
`retained_controls` catalog of the exact five IDs and entry digests. The persisted
profile includes this protocol in addition to CLEANUP@1.0/1.1. Missing, duplicate,
unknown or wrongly categorized control slots fail closed; no arbitrary entry is
allowed to escape the online inventory by claiming to be reconciliation.

Old host1/2 and ordinary `freeze` do not reinterpret this catalog: the additional
leaves remain gaps. They need explicit profile3 activation for a registry that
contains the provided controls. Component registries with no App control store
may still use the original profiles and original inventory. Legacy operation
bytes, receipts, registry drift and unavailable external storage keep their rules.

Online content status has its existing API@1 meaning: every applicable frozen
content target requires its real original receipt. The separate retained-control
catalog is not an execute/reconcile target and cannot return a synthetic
CLEANUP@1.1 confirmed receipt. DEVICE@3 and its original call/receipt bytes remain
unchanged. Server online complete does not attest finalization of these native
control records. App-wide completion additionally requires A's actual exact-record
finalization result; retained/unknown control state must remain visible as such.

## Positive and negative examples

- Positive: unknown device-call ACK retains its exact journal/capabilities; the
  original action/hash GET recovers it without a new call. No finalization occurs.
- Positive: original account content complete + original native/device receipt
  acknowledged, old writers retired, exact five owned records cleared and absence
  verified; Selected still matches that scope. A may report native finalization.
- Negative: content complete with a native clear UNKNOWN, or device confirmed
  while the account operation is blocked, never yields App-wide complete.
- Negative: changing Selected to Bob, replacing a same-account generation/record,
  presenting an SDK slot or adding an undeclared control slot grants no purge.

B's registry/host acceptance proves classification and original operation
freezing only. Actual post-terminal native clear, devices and backups remain A /
#29/#30 evidence. Nothing here claims those unimplemented native results PASS.
