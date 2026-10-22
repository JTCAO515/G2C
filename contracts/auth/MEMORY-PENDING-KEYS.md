# Memory pending 独立密钥用途 — 最小增量候选

base `1e63217e2d206c368716d42cde459e34a93a3a73`；模块仍为 CJMessageKeys。
新增 `MessageKeyPurpose.localMemoryPendingV1`，raw value 固定
`local-memory-pending-v1`。原 localMessageStorageV1/raw value、service、slot 拼接
及记录编码完全不变，无旧 key 迁移/复制/轮换，无 public raw-key 构造器。

同环境/账号的精确位置：
- service 仍为 `G2C.CJAuth.message-key.<environment UUID>`，保留既有前缀。
- Message slot：`<account UUID>.local-message-storage-v1`。
- Memory pending slot：`<account UUID>.local-memory-pending-v1`。

slot 不同意味着 Keychain item 和平台随机 key 独立，不是给同一 key 换标签。
账号/环境仍由可信 host 显式绑定；不从 session token、文件自报 owner 或旧 VP 配置
派生 namespace。Memory 消费方须先确认 provider.namespace 与可信环境/账号及
localMemoryPendingV1 完全相等，再获取 key；取回后核 key.namespace 与持久化原
expected key ID。文件头/密文 metadata 只能比较，不能用于选择另一账号/用途仓储。
不得用 Message key 或 session token 作为 fallback。

复用 existing/create/reconcileCreation/clear/reconcileClear/invalidate，不新增 provider
或第二权限源。已有其他 scope key 的 expected ID 不匹配返回 keyMismatch，跨实例
operation 返回 staleOperation；目标 scope 真正不存在仍按原协议返回 nil，不自动
创建。创建必须确认没有旧密文；unknown/缺 key 不能擅自重置 key。清理先由 Memory
owner 完成其密文清理证明，再用本 scope 原 key ID；轮换仍不支持。

public enum 增加 case，旧 exhaustive switch 消费方须检查；协议方法和已有 namespace
字节不变，不宣称仅凭旧 RC 字符串即支持新 case。新消费者必须 pin 本次固定 commit。
本候选未改变原 SessionBridge/SDK/后端、签名、权限或 access group。

验证：原 MessageKeyTests12 + 新3 = **15/15 PASS**，证据
[evidence/memory-key-purpose-tests.txt](evidence/memory-key-purpose-tests.txt)。
新例通过同一注入 Keychain 字典及真实 CryptoKit 合成加密验证：四个 scope 独立 key、
错用途/账号/环境不能解密 Memory 密文，错 expected ID/operation 不能查取或删除，
清 Memory key 不影响原 Message key；unknown 创建读回原 key 且只有一次 add。
没有真实 SecItem/Keychain 调用、重签/launch、外部网络或真实凭据，原 probe 停机。
Memory pending 文件 store 自身、持久化/重启/删除与真实平台层仍由原 owner 验证。
