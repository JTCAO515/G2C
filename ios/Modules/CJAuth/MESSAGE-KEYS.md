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
