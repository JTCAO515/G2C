# Trip pending 独立密钥用途 — 最小增量候选

base ab37bae6f91796f9156e29a18213eb250f3fda0c，原分支 clean 后首写。
新增公开枚举 `MessageKeyPurpose.localTripPendingV1`，稳定 raw value：
`local-trip-pending-v1`。模块仍为 CJMessageKeys，原协议/provider/记录编码不变。

- service 仍为 `G2C.CJAuth.message-key.<environment UUID>`。
- Trip slot 为 `<account UUID>.local-trip-pending-v1`。
- Message 的 local-message-storage-v1、Memory 的 local-memory-pending-v1 及所有
  原 service/slot 拼接字节不变；三用途独立 item、独立平台随机 key，不共享 session token。

Trip consumer 只在可信 host 的环境/账号绑定下选择该 purpose；先核 provider.namespace，
获取后核 key.namespace 与原 expected key ID。pending 文件 metadata 仅比较，不能
据它改选其他环境/账号/purpose。继续使用原动作精确 bytes；本用途不生成新动作、
不赋予 Trip 接受/写入/账户权限，也不新建原始 key 公共构造器。

复用 existing/create/reconcileCreation/clear/reconcileClear：真正 absent 才返回 nil，
unknown 不当缺失/不新建 key；create 仍须确认无旧密文，未知创建只读对账原 key。
清理先由 Trip pending 文件 owner 完成其密文清理证明，再传原 key ID；不删除其他
用途或账号的 item。旋转/迁移、默认创建依旧不支持，无新的 Keychain provider。

定向验证 6/6 PASS（新 Trip3 + 原 Memory3），输出
[evidence/trip-key-purpose-tests.txt](evidence/trip-key-purpose-tests.txt)。
覆盖旧命名字节、Trip/Memory/Message/另一账号/另一环境五个独立 key、跨 key 解密
失败、错 expected ID/operation 拒绝、Memory 清理后 Trip 保留、Trip 清理后新 Memory/
原 Message/其他 scope 保留，以及 unknown 创建只写一次并恢复原 key。
其余原完整 key 生命周期/SessionBridge 证据复用；没有重跑真实 Keychain probe。

新增 enum case 的 exhaustive switch 消费方须检查并 pin 新 commit；不能仅用旧 RC
字符串判断已支持该用途。仅源码/注入 persistence 与 CryptoKit 合成数据，未改
CJTripClient/其他客户端、Package、根工程、backend、签名/权限/access group；无真实
SecItem、网络或账号动作。pending 文件持久化/恢复、完整 Trip 及真实平台仍待原 owner。
