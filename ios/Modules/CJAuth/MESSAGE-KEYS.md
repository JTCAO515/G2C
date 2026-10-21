# CJ-MESSAGE-KEYS@0.1.0-rc.1 — 独立消息密钥接口候选

base b5ef9e57be6d48afaf673bb872c7246552d14c1c 保全；独立 product CJMessageKeys，
不依赖 CJSession/SessionMaterial、JWT 或 SDK token，不改 CJMessageClient。
接口源 Sources/CJMessageKeys/MessageKeyInterfaces.swift，待消费者固定 commit 核对。

namespace 必须由可信 host 显式提供环境 UUID、稳定账号 UUID、用途
localMessageStorageV1。账号 UUID 是域内稳定分区绑定，不可随 token 刷新变化，
也不能由请求任意指定。不同账号、环境、用途不共用 service/account tuple。
Key 对象仅可经 provider 获取，提供 id/namespace 与 CryptoKit SymmetricKey 使用闭包，
无 public raw/session 构造、无 Codable、日志/Mirror 脱敏；不授任何 Auth 业务权限。

所有操作在 MainActor 上绑定原 provider 实例、generation、操作用途与一次消费。
await 前 begin，await 后 isCurrent；不得给旧操作新建 token 重标。invalidate 永久
关闭该 provider；切账号应废弃它并为新 namespace 建新实例，不清其他账号的 key。
clear 另要求 expectedID 与调用者确认密文存储为空，不能作为普通退出的自动动作。

existing 只读取，真正 notFound 才返回 nil；UNKNOWN/存储错误不等于 missing。
create 只允许 confirmedEmpty，先读再仅 add，不覆盖既有 key；随机由平台提供。
创建结果未知保留原候选 ID/bytes，不返回 key、不重新生成；reconcileCreation 只读
确认相同原 key。clear 失败保留原 ID，reconcileClear 只读查询原项；未知期间禁止
新的写入。轮换不支持：没有迁移/重加密与回退证据时，不提供 rotation API。

进程内错误记录不是持久幂等账本；重启后 host 必须先读取原 key/密文引用，不因
missing/unknown 自动创建新 key。创建接口的 confirmedEmpty 是可信消费者证据，
不是本 provider 对消息数据库的检查。保留原 key ID 与密文的绑定是消费者职责。

## 已实现的最小适配

`ScopedMessageKeyProvider` 只依赖独立 `MessageKeyPersistence`；正式 iOS initializer
显式接 namespace/applicationIdentifier/protection，构造 KeychainMessageKeys。
不依赖 SessionMaterial，也没有 token→key 派生入口或 public raw-key 构造函数。
平台 `SecRandomCopyBytes(kSecRandomDefault, 32, ...)` 生成 256-bit key，检查返回码；
错误不写存储。本地 official SDK SecRandom.h 要求检查错误，0 才成功。CryptoKit
SymmetricKey 用于消费者加密闭包，不自造 AES/KDF，不声称内存副本可完全零化。

Keychain 为独立 message-key service 与显式 account/purpose slot，指定本 app group、
synchronizable=false、ThisDeviceOnly 保护级别；不默认查共享组或旧 VP namespace。
记录使用版本化二进制 framing（非加密算法），校验 key ID 与长度；不写 key 到
UserDefaults、JSON、日志或截图。`kSecAttrGeneric` 同时保存非秘密 key ID，删除时
用精确 namespace + expected ID predicate，避免旧 key ID 删除替换项。此 predicate
已做注入查询断言，真实 Apple Keychain 行为仍 UNRUN，不冒充原生事务证明。

创建只有“确认无旧密文 + 明确未发现 key”才生成并仅 add；duplicate/unknown 不
覆盖。未知创建保留原候选，其他 get/create/clear 阻断，只能 reconcileCreation
读取同 ID 与原 bytes；未知清理也只许 reconcileClear 查询原 key。原项仍在时返回
false，不隐式重删；观察到 absent 才完成清理，对方 key 则 mismatch。
失败原因和未确认状态均显式抛出，不降为 missing。没有轮换 API；清空密文后的
显式新 key 创建不是迁移/轮换实现。invalidate 不删除 key，旧 operation 不能
写入/清理新 generation；不同账号应由不同 namespace/provider 接入。

## 分层验证

- 接口先行固定 f1ce075e4b3f26e6c65bfe4b2fa8bcec8291a552，Swift 6 typecheck PASS。
- 新目标编译及 **12/12 注入测试 PASS**：平台随机 key + 合成 AES.GCM roundtrip、
  无业务 grant/脱敏、missing/unknown 不生成、随机失败、未知创建/清理读回、禁止
  有密文时创建/清理、已有 key 不轮换、旧操作/跨实例/失效、expected ID 不删新 key、
  环境/账号/用途隔离、精确 Keychain query 与 duplicate 不覆盖。
  evidence/message-key-tests.txt。测试只用新 key 和合成消息，不打印秘密。
- iOS simulator target 源码（包括准备好的 probe）typecheck PASS，未执行平台存储。
  evidence/message-key-ios-typecheck.txt 记录范围；无 .app 重签或新 SecItem 调用。
- 真实 Keychain **UNRUN**；前轮 -34018 失败保留，不重试、不换身份、不改 entitlement。
  [精确确认提案](Probe/Proposals/KEYCHAIN-APPROVAL.md)列出当前/拟值与独占目标。
  plist 与 probe 阶段只是准备产物，绝非已批准/已运行。
- b5ef9e57 SessionStore 原源码/测试、Swift SDK 与 backend/Auth 固定成果未改；有效证据
  复用，不重跑无关套件。CJ009/CJ006 消费绑定、真实签名/Keychain、进程间恢复与
  消息域持久化仍待相应 owner 验证。独立 key 不是新的权限源，Issue #8 不关闭。
