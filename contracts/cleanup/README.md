# CJ-CLEANUP-INTERNAL@0.1.0-rc.1

内部候选，固定 base `8deb696f8149b4f5aa70c767be6c3a263b036227`，Issue #27。
不是 CLEANUP@1.0、第二 AUTH、HTTP API 或公开注销后凭证。后续唯一 wire owner CJ005。

## 最小签名与信任边界

- `Scope.from_principal(environment, TrustedPrincipal)`：仅可信 host 从现有 AUTH 已验证身份及显式环境构造；不从请求反序列化。scope 包含 issuer/subject/audience/environment，重新登录同主体可恢复原操作，不依赖旧 token 有效期。
- `freeze_registry(raw: bytes, expected_ids: tuple[str,...]) -> Manifest`：冻结原 registry bytes SHA256、版本、各层 store/object ID 与内容 hash。`expected_ids` 必须来自 host 独立完整数据清单；不能取空记忆列表或从 registry 自身导出并声称清单完整。未知新数据未进入任一清单无法由本库发现，激活前 owner 必须登记。
- `request(scope, operation_id, confirmation_digest, manifest, capabilities=()) -> Operation`：可信 host 已核明确确认，digest 是其**原始确认输入 bytes**的 SHA256；库不接正文、不把摘要当确认凭证。host 必须绑定展示给用户的操作范围/确认内容，不能用普通登录替代确认。operation ID 同 scope 不可换 ID 重新执行。
- `Repository.create / query(scope, operation_id)`：内部同 scope 安全查询；缺失与他人操作统一 unavailable。scope 对象不是授权能力；只可 trusted host 持有。不公开 query，不授回普通业务权限。
- `Repository.intent(scope, operation_id, expected_revision, target, invocation)`：CAS 记录原调用意图；**不执行或调度**。只有 host 已登记能力且 registry 明确 `cleanup_protocol` 同版才允许 store intent。默认全部缺失。
- `Repository.receipt(scope, operation_id, expected_revision, target, raw: bytes)`：仅可信原结果 importer 调用。没有签名验证能力，不接受客户端/provider 任意 JSON 作为权威结果。
- `Repository.audit(..., current_manifest)`：任意 registry/version/内容变动锁存缺口；不可悄悄扩大原确认范围，不能改回旧 manifest 消除缺口。host 每次报告限定完成之前必须与当前获准 registry/独立 inventory 复核。
- `Repository.journal() -> bytes / Repository.rebuild(bytes, recover_inflight=True)`：私有 metadata 的原序列化 journal，逐事件重放；原 receipt bytes 以 hex 原样保留。scope/operation IDs 仍是私有元数据，不进日志或公开错误。原 journal 的完整性、原子持久化、隔离、留存与清理必须由 host 存储适配负责。

Python dataclass/对象与 `capabilities` 只是 trusted host 组合输入；不是安全边界、不是新权限来源，不能根据可构造性自授撤销/删除权限。这里只消费 `cj_auth.interfaces.TrustedPrincipal`，不写 access provider。现有 AUTH 没有真实撤销能力；当前默认 blocked。

## Trusted hook 候选协议

输入由原操作生成：同 Scope、operation_id、confirmation_digest、冻结 registry_digest、target、version、唯一 invocation。target 仅内部登记 ID；不消费 registry 路径、不动态 import、不执行 SQL。必须先 journal intent，再由未来获准 host 调用其**显式注入**原域 hook；本模块无调用代码。

回执 exact UTF8 JSON（严格 UTF-8 decode，不接受 BOM/UTF-16/UTF-32；所有对象层级拒绝重复 key；仅下列字段，最大4096bytes，无正文/异常/provider payload）：

```json
{"protocol":"CJ-CLEANUP-INTERNAL@0.1.0-rc.1","scope_digest":"<sha256(canonical internal Scope)>","operation_id":"original-operation","target":"auth_revocation","version":"CJ-CLEANUP-INTERNAL@0.1.0-rc.1","invocation":"original-call","outcome":"confirmed"}
```

无效回执在修改操作或 journal 前拒绝；rebuild 重新校验每份原 receipt bytes，旧无效记录也拒绝恢复，不能通过 canonicalize 掩盖冲突。

store target 为 `store:<registry path ID>`，version 为冻结 Entry.version；barrier version 为本协议版本。`outcome` 仅 confirmed/unknown/failed。`confirmed` 必须是该原域已验证的实际原结果，不能把 accepted/排队/空数组/零条/停止检索/SDK clear/过期/未上线/外部仍留存映射 confirmed。importer 必须校验原域结果再生成 metadata；本候选不定义各域事实查询接口，也不猜原回执形状。

前置：auth_revocation 确认前不能启动其他步骤；tasks_stopped 确认前不能开始 store 步骤。其余强制屏障为 restore_fence、backup_retention、offline_devices、external_retention，绝不默认零或不适用。若需适用性豁免须后续明确 owner 契约，本版不支持。备份/离线/外部仍有未解决留存即不得 confirmed。

## 状态与恢复

优先级：coverage gap → blocked；任一 unknown → unknown；任一 failed → failed；全部 confirmed → complete；缺能力 → blocked；撤销未确认 → awaiting_revocation；其余 in_progress。可单独查询每个 step/gap，汇总不会隐藏另一失败。

complete 只表示**该冻结清单全部已证实**，不是现实全域或无限未来保证。原 manifest/回执终态不可变；registry 漂移可使该操作重新 blocked，不能声称覆盖新增域。

同 ID 同输入返回原进度，异确认 digest/manifest 冲突。相同 receipt bytes 幂等，不同 bytes 与终态冲突；错 scope/operation/version/invocation 拒绝。unknown 仅能接受**原 invocation**核实结果，不自动重试或换 ID。failed 本版不重试，等待 owner 提供明确 safe-idempotent 契约。rebuild 后未有结果的 in_progress 转 unknown，不调 hook、不重写已确认结果、不复活业务数据。

`execute_destructive_action()` 与 `public_query()` 始终拒绝。没有 HTTP router/token/验证码/账号删除/权限变更/业务数据读取或写入。

## 原 owner prep（不得冒已实现）

CJ007：真实普通访问撤销/旧 token 和在途边界、原操作结果；CJ010：任务停止和 checkpoint；各 storage-registry 域：原 scope + frozen version 的实际物理清理和防晚到重建原结果；CJ021/022：记忆/设备与离线界限；CJ027：备份恢复先重放 fence；provider owner：外部留存。CJ005：唯一 API 外壳及注销后受限查询凭证方案。以上必须先固定原 public 能力，本模块不代建。

真正删除、真实撤销、全域 hook、备份重放、设备、真实账号及 Issue I 验收全部 UNRUN。本候选不关闭 Issue27，不降低原 I 要求。

## 后置 PostgreSQL repository 候选

`cj_cleanup.postgres.Repository(connect, scope, guard)` 不改变本契约或另立状态机。内部签名与原内存版等价，但 scope 由构造固定，后续方法不接 scope；只持久化 Cleanup 原操作的元数据。行锁/CAS + 原journal/state/revision 原子事务；重放使用原 reducer 的 `recover_inflight=False` 保留数据库原状态，显式 `recover(operation_id, expected_revision)` 才提交失去writer后的 unknown。默认 `rebuild` 旧行为不变。所有 receipt 仍经同一 strictUTF8/拒重复key入口。

写入的 COMMIT/返回/close 结果不明确抛 `CommitUnknown`；只能用原 ID 只读 query/journal 核对，不自动调用、重试或换 ID。已落盘 intent 未有原结果时不能推 confirmed；显式恢复也不会把 unknown 变 complete。query 不授予普通业务权限，没有公开注销后路由。

表候选 `cj_cleanup_journal_candidate` 自身是新增私有元数据存储，尚未被正式 registry 接纳，也未有留存/物理清理/备份防复活正式接口；生产激活必须经原owner登记与验证，原冻清单不能忽略它而宣称全域完成。此段仅在全新私有空cluster用合成身份验证，不触碰其他域表/权限/真实账号。生产 durable 服务、权限策略、I验收仍未完成。
