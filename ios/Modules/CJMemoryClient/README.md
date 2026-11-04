# #271 本地 App 编辑与生命周期消费

显式 DEBUG 模拟器入口可配置独立的 `G2C_DEV_MEMORY_MANAGEMENT_URL`，仅接受带端口的 HTTP 127.0.0.1 根地址。主 API 使用既有手动保存/读取 host；管理 API 使用正式 `create_local_memory_management_app`，由本地 operator 配置同一私有 PG、签名身份及收集策略。缺少管理地址时保持原手动保存行为；无效地址 fail-closed。公开 live 客户端、Release 和真机不获得该能力。

管理动作消费冻结的 pause/resume、MEMORY-MANAGEMENT-EDIT@1 与 MEMORY-STOP-USE@1。选择只来自实际读取的条目/来源/版本；编辑不改范围或提升候选，已停用条目编辑后仍停用。停止使用保留原记录、完整来源历史与操作字节，不表示物理删除或账号清理。

每个原 action 的字节与哈希先进入独立加密日志。明确 POST failed 追加独立加密失败记录，原输入保留，只有重新读取/审阅后才可发新 action。未知、缺少回执及回执 GET 拒绝均不释放原操作、不自动重发。页面退出仍失效读取和调度代际；已确认的精确 ID+字节哈希只保留历史终态。新客户端重开通过“此前的记忆操作”查询原 ID，并显示保留的编辑原文。

当前入口明确使用 `local-memory-run.1` 与 legacy MESSAGE。MEMORY@2/MESSAGE@2 的 Swift 生成物已同步，typed producer 的成组激活与消费由 #228 框4承担；不把 travel 当 conversation，也不在版本拒绝后回退。

实际 App/签名 API/受限 PG/正式 run_once/FakeProvider 的复现入口为 `ios/App/Acceptance/check_memory_lifecycle.py`；必须传显式 `--run-context` 与仓库外证据目录。每轮 PASS/FAIL、实际固定 head、未运行层级在 #271/PR 中记录，历史失败保留。真实账号/模型/云/费用、真机分别留 L2 #32 / L3 #29。

以下为原阶段记录，原固定 pin 和限制保留。

# #228 local App candidate (L1 pending)

The explicit DEBUG iOS Simulator `localEndpoint` initializer uses only loopback,
`NoRedirectTransport`, the existing signed #226 API and the existing encrypted
manual journal. It enables manual save only; lifecycle management and ordinary
public/Release clients retain their previous gates. The host must use the same
account lifetime and explicitly selected server policy choices. No production
factory, automatic recall, lifecycle writes or real-account permission is added.
The historical read-only candidate and its earlier limitations below remain as
provenance; new local acceptance is recorded in #228, never inferred from them.

# Independent lifecycle candidate

Current follow-up adds gated pause/resume/original-action recovery on SDK20aa. See
[MEMORY-MANAGEMENT.md](MEMORY-MANAGEMENT.md) for exact pins, host limits and checks.
The accepted f87 candidate `1734971` and earlier documents below remain preserved.

# CJMemoryClient — CJ011 iOS consumer

Independent domain package for Issue #12. Own source is only this directory. The
CJShell Memory tab/account/language container remains CJ006's responsibility.

## Fixed inputs and integration

- main base: `23e12f28435ab0ddc685d544670564e3fa79db41`.
- Official API: `57336d501e5691302a3d5e9770f07666d1c57d4a`, producer
  `426d337b0647d7770f1716fad83f2e5e724d28e4`.
- CJ009 prerequisite: `d0f396ceaff5a7d51ddc3a623b35e3eef9191412`, imported unchanged
  as `bf8bf5c`. It exports the single shared CJFoundation/CJAPI package, including
  `MemoryClientConfiguration.swift`. This package points to precisely the same
  `../CJMessageClient/.generated/57336d501e5691302a3d5e9770f07666d1c57d4a/CJFoundation`
  path; no second copy or package identity.
- CJ007 prerequisite: `b24cc77c307bbb1dd9c552aeb92a148213534541`, imported unchanged
  as `d7cc48c612326ccd74a5d0fed79cab65a065ee1a`. It adds
  `MessageKeyPurpose.localMemoryPendingV1`. No Message key or token fallback.
- Review own diff from `d7cc48c612326ccd74a5d0fed79cab65a065ee1a`. Prerequisite
  commits belong to their original owners and are not this task's implementation.
  Publish must integrate their accepted equivalents before this package.

In the consumer clone, run the **CJ009-owned** fixed exporter with a repository
containing API commit 57336d5:

```sh
python3 ios/Modules/CJMessageClient/scripts/prepare_generated.py /path/to/fixed-api-repository
swift test --package-path ios/Modules/CJMemoryClient
```

No generated code is edited. `.memory` is used for every official `Client` and
accepts whole/fractional RFC3339 dates. Generated schema types supply the manual
command, receipts, groups, items and response unions. Invalid non-null fallback,
duplicate JSON keys, mismatched trace, malformed item/version/cursor and HTTP
errors are errors, never empty or successful results.

## Host composition

1. Supply a validated `MemoryEndpoint` with explicit request/response byte limits,
   a trusted async credential callback, and a synchronous `currentBinding`
   callback. The binding contains environment/account plus session generation
   and selection generation. These are **local fencing data, not server owner
   authority**. Create a new client per account/store. Call `invalidate()` and
   clear displayed read results on session/selection changes.
2. For pending storage supply an existing private directory (0700, owned by the
   process, canonical non-symlink path), explicit per-record byte/count limits,
   original expected key ID, and official `MessageEncryptionKeyProvider` with
   the exact environment/account and `localMemoryPendingV1` namespace. The store
   only performs provider lookup. It does not create, reset, rotate or clear keys.
   Missing/unknown/mismatched keys and corrupted records fail closed. Host key
   creation/reconciliation follows the existing CJ007 lifecycle and its grants.
3. The public initializer accepts only `NoRedirectTransport` for live **GET**.
   No endpoint, credential, store, storage directory, field policy, key or live
   write permission is defaulted. `save` rejects live composition before storage
   or credential access. The POST capability exists only in a package-internal
   initializer, used by `@testable` in-process transport tests. No public Boolean
   or generic transport can open it.
4. `groups`, `list(limit:after:)`, and `detail` are official GET operations.
   Listing is live item-ID keyset pagination, not a snapshot; every nonempty page
   has the final item ID as its continuation, including the last nonempty page.
   Continue until an empty/null page. Cursors are bound to this client and the
   original binding. Group selection filters loaded items by exact UTF-8 subject
   and status; a partial page is not proof of an empty group or complete count.
5. `pending(binding:)` enumerates durable originals after reopen. Present each
   original operation and call `query(operationID:binding:)`. Receipt null means
   *not observed*, not noncommit and not resend permission. There is no resend,
   body-reconstruction, pending-delete or replacement-ID recovery API.
6. `MemoryGroupsView`, `MemoryItemsView`, `MemoryDetailView` and
   `MemorySaveStatusView` are embeddable sections with explicit unconfigured,
   loading, loaded/empty and failure states. Host owns navigation, pagination,
   current account/language settings, and clearing old account snapshots.
   `MemoryManualForm` owns one form action and is keyed by the supplied binding;
   it also checks current binding/request generation before/after async work.
   Supply permitted `MemoryManualOption` combinations and their understandable
   save-scope disclosures. Empty options remain unconfigured. No personal
   preferences, policies, occurrence times or server authority are invented. Time
   is required explicit display text; blank/whitespace is rejected before staging.
   Form submission is one-use; the original-query button preserves its original
   operation ID. Unknown results must not be presented as a fresh form retry.

## Original operation and storage contract

The manual command is encoded once using the official nine-key type. Its exact
UTF-8 bytes, original operation ID, item ID, inference classification and
SHA256 are persisted **before** async credential acquisition/network dispatch.
Sorted JSON keys do not normalize text; NFD bytes remain NFD. The official binary
POST sends the persisted bytes unchanged. A response can settle only the original
operation/item/hash, version 1, authoritative candidate/active status (inference cannot become active), and
current binding/request generation. Cancellation and errors retain the original.
Reopening never restores one-use write authority; all originals are queried again.

Each `<SHA256 of exact operation-ID UTF8>.memory` file contains a CryptoKit AES-256-GCM combined box
(nonce/ciphertext/tag), with a JSON `MemoryPending` plaintext. Associated data is
UTF-8 `CJMemoryPending|1|<environment UUID>|<account UUID>|local-memory-pending-v1|<key UUID>`.
Expected namespace/key ID come from trusted host configuration, not file metadata.
Legacy UUID-named files remain readable without rewriting; new opaque operation IDs
use a byte-exact hash filename, including distinct NFC/NFD or case variants.
Files are immutable 0600, created with `openat/O_EXCL/O_NOFOLLOW`, synced before
network use; the private directory is held by descriptor. Canonical directory
identity is checked after key and binding callbacks, after write/fsync, and with
the original encrypted record at the transport validation boundary. Displacement
fails without deleting or migrating the original ciphertext. These checks do not
claim protection against arbitrary concurrent same-UID filesystem attacks. Replacement directories,
unknown files, symlinks/hardlinks, oversized records, partial/corrupted ciphertext
and authentication failures do not become empty ledgers. No UserDefaults or
plaintext production fallback exists. The bounded record store intentionally has
no automatic pruning; reaching its explicit bound fails closed pending a separately
specified cleanup policy.

These local files **cannot prove freshness against deletion or restoration of an
older filesystem snapshot**. A missing/rolled-back ledger cannot authorize live
POST. Live write remains closed until an independently authoritative freshness
mechanism and actual write authorization are integrated by the relevant owners.
No local confirmed set, GET permission or receipt-null response removes that gate.

A saved receipt is historical. Its `active` status does not prove current effective
eligibility or that the next answer uses it; current service effective/fence logic
owns that decision. Inference is shown as candidate, never as confirmed fact.
No new wire field or local eligibility inference is introduced.

## Evidence and remaining gates

Latest row identity repair: [validation](https://github.com/JTCAO515/G2C/blob/evidence-archive-2026-10-27/ios/Modules/CJMemoryClient/evidence/ROW-IDENTITY.md).
Prior four-finding repair: [repair validation](https://github.com/JTCAO515/G2C/blob/evidence-archive-2026-10-27/ios/Modules/CJMemoryClient/evidence/REPAIR-623.md).
Historical 623 author checks: [validation](https://github.com/JTCAO515/G2C/blob/evidence-archive-2026-10-27/ios/Modules/CJMemoryClient/evidence/VALIDATION.md), [tests](https://github.com/JTCAO515/G2C/blob/evidence-archive-2026-10-27/ios/Modules/CJMemoryClient/evidence/tests.txt).
The old 20 PASS did not override the independent four failing cases.
The package's SwiftUI views compile on macOS and the generic iOS Simulator SDK.
Tests use only in-process interceptors, synthetic values and isolated temporary
private files; the official key provider uses test-only injected persistence.
There are no real account/provider calls, Keychain probes, app launches, signing
changes, backend edits, root schema/lock edits, pushes or merges.

Real HTTPS reads, actual private-platform storage lifecycle, CJShell integration,
visual/VoiceOver runtime validation, real manual save, next-answer context,
new-session/device travel use, and independent Review/Testing are **UNRUN** here.
Issue #12 remains open and is not closeable from this package evidence.

Definitive manual-save failures are retained separately in an encrypted
`CJMemoryRejections` adjacent journal using the same account/key namespace and
a distinct authenticated domain. Existing manual ciphertext/files are unchanged.
Receipt null alone remains unknown; only the matched direct server failure allows
a distinct new action. Reopening never resends the failed original.

## MEMORY-HISTORY@1 App consumer (#434)

`MemoryHistoryClient` and `MemoryHistoryView` consume the additive published
`contracts/memory-jobs/PG-V1.md` without changing older Memory wires or SDK pins.
The explicit local development factory requires canonical SessionLifecycle/op,
current account binding, actual selected MESSAGE conversation and the existing
Memory key namespace. Its dedicated NoRedirect capability admits only the one
consent POST and two exact private GET routes; it cannot dispatch organizer jobs
or candidate actions. Default/Release/non-loopback activation remains closed.

Settings are current effective state. A receipt is immutable historical data,
never authority for the current switch. Epoch0 is valid; strict token-preserving
JSON rejects bool/float/exponent/overflow counters, duplicate/extra keys and invalid
Unicode. Original seven-key bytes persist before credentials/network. UNKNOWN/null
only reconcile the original ID. A new action needs a fresh settings read and all
unresolved originals for that conversation reconciled; definite failed POST evidence
is separately durable, and a failed receipt/settings GET never supplies it.

History uses `G2CDevelopmentMemory/<env>/<account>.history-v1` with AD
`CJMemoryHistoryPendingV1`, plus optional adjacent `CJMemoryHistoryRejectionsV1`,
and existing `localMemoryPendingV1`. Legacy/manual/typed/lifecycle data is neither
reinterpreted nor removed. Namespace emptiness checks include all account-owned
siblings before a missing key is created. New additive ciphertext/inventory proof
methods leave older journal formats/consumers unchanged; the final callback-free
proof follows every source/key callback at each live exit.

Presentation scope uses private atomic slots and a coalesced Observation signal.
Reentrant account/conversation replacement owns its new slot; old work cannot
publish into or clear it. UI only allows this selected conversation and explains
that one save is not all-history consent, stopping is not data deletion, and
inference candidates still need confirmation. Candidate review requires C's actual
job/attempt discovery source; this consumer does not manufacture those IDs.
Device physical cleanup of the provided journal family remains part of #27's
original authenticated device-call bridge. Native/real-provider/device evidence
and retained failures are recorded in #434/PR437; local tests alone are not release.


## M3 local account-cleanup primitive (#439)

`clearLocalFiles()` retires the original store and physically erases only its
manual, lifecycle, typed (including management and rejection records), and history journal family. Memory's four public store types each own
their separately constructed root; callers must retain and invoke all provided
stores. Feedback Answer and General are separate roots and both require cleanup.
The method never queries/decrypts a record or accesses/creates/deletes a key.
Existing ciphertext, action IDs, raw UTF-8, receipt/query and unknown-write rules
are unchanged before explicit cleanup.

Known adjacent directories are captured with retained descriptors at construction,
or registered only when that store creates them. Renamed/replaced/missing captured
directories, independently appearing sidecars, unknown filenames, subdirectories,
symlinks and hardlinks refuse cleanup. Complete metadata preflight precedes the
first unlink; failure retains a retired store and retry uses the same original
targets. Regular account-owned ciphertext may be erased even when its content or
read protection is unusable, as in #421; this does not make it readable.
No recursive or sibling-prefix deletion exists. A successful retry verifies empty
original directories and fsyncs them; it never reports server/backup/device-wide
completion.

The host still must fence every old client/SessionLifecycle before cleanup,
prevent constructing replacement writers, then clear the exact key only after
all its provided stores are verified empty. Other independent instances are not
a global revocation mechanism. Original account operation/device-call/receipt,
Keychain clearing, signed API/PG/native composition and physical-device behavior
are separate #27 acceptance. In particular the history roots introduced by #437
require B's additive device target version; DEVICE@2's frozen targets are not
expanded by this local API. This primitive alone does not open an App factory or
mark #24's original-account-operation box complete.

## M3 candidate review consumer (#460, parent #23)

Current App constructors explicitly select `.canonicalProjectionV2` and read
`GET /v6/memory-candidates` / `MEMORY-CANDIDATE-projection@2`. This supplies the
current canonical candidate, Memory epoch and original review job/attempt without
recovering an erased job payload. Only this client's protected current read can
prepare a review. The older producerJobsV1/V5/V3 consumer remains for its existing
callers; current App activation does not fall back to it.
The canonical SessionLifecycle, account binding and actual selected MESSAGE
conversation are checked before and after credentials, HTTP and body collection.
The explicit DEBUG Simulator loopback factory enables the canonical projection
and original review/receipt routes through NoRedirectTransport; Release and ordinary write factories stay
closed. Query encoding preserves literal plus signs and original Unicode bytes.

Confirm/reject originals are encrypted and read back before their one POST.
The separate CJMemoryCandidatePendingV1/CJMemoryCandidateRejectionsV1 domains use
the canonical localMemoryPendingV1 key. Lost ACK, reopen and null receipt preserve
the same original action and permit only receipt GET, never resend. A recorded
result remains historical; a fresh protected candidate read separately establishes
current status. Exact keyless file cleanup reuses the existing journal primitive.

The bilingual review view captures an immutable editor entry. A newer read or
account/conversation replacement retires that entry; editing cannot silently
retarget another candidate. Inference requires an explicit fact/experience/
preference choice. Text/time may be edited; original extent and Travel identity
are retained and the server still verifies current Travel/version/source scope.
No suggestion, history consent or historical receipt itself activates a memory.

The Shell entry/host, source-bound conversation bubble and exact App constructor
are provided, but ordinary Root activation and native acceptance remain pending.
The constructor owns exact roots M.candidate-v1 and
M.candidate-v1.CJMemoryCandidateRejectionsV1. Before either is provisioned, B must
provide an additive device version and include both in the shared Memory-key
empty-set rule. Frozen DEVICE@3 is not expanded and no WIP App root is registered
by this module. This slice does not close #460 or the parent App frame; signed local
API/private PG/FakeProvider/native maximum-type/all-AX proof belongs to Part 2.
