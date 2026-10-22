# NEEDS pending 独立密钥用途 — 4718 后置增量

实际 parent：4718db705d97cceaff5a7954bfc1dd9f4b562c6f，首写前 clean。
仅新增 `MessageKeyPurpose.localNeedsPendingV1 = "local-needs-pending-v1"`。
模块仍为 CJMessageKeys；与 typed clear 候选分开提交，未改变其源码/行为。

- service 保持 `G2C.CJAuth.message-key.<environment UUID>`。
- 新 slot：`<account UUID>.local-needs-pending-v1`。
- Message/Memory/Trip 原 raw value、service/slot 拼接和记录编码全部不变。

NEEDS 客户端必须由可信 host 绑定环境/账号并明确选择新 purpose，获取后验证
key.namespace 与原 expected key ID；pending 文件 metadata 只能比较，不可用于
选择另一 scope。不能复用 Trip/Memory/Message key 或 session token，不新增 provider、
权限或 raw-key 公共构造器。用途仅保护原 action 精确 bytes，不授业务写入或确认。

继续复用原 existing/create/reconcileCreation/clear/reconcileClear：unknown 不当
missing，不自动创建/换 key；创建仅在确认无旧密文后显式进行。原 key 创建/清理
未知仅按原 ID 只读对账，不换 namespace；清理前由消费方确认原 pending 密文处理
已完成，不能用清 key 跳过原 query/revision 的业务确认。轮换/迁移仍未支持。

定向验证 **9/9 PASS**：新 NEEDS3 + 相邻 Trip3/Memory3，日志
[evidence/needs-key-purpose-tests.txt](evidence/needs-key-purpose-tests.txt)。
覆盖所有旧命名字节、四用途/另一账号/另一环境六独立 key，错 key 解密/expected ID/
operation 拒绝，各旧用途清理不影响 NEEDS、NEEDS 清理不影响其他 scope；unknown
创建与清理只对账原 key，各一次实际注入 add/delete，无自动重做。

未变完整生命周期/typed clear 证据复用，不重跑真实 Keychain。仅源码、注入
persistence、平台随机与 CryptoKit 合成数据；无 SecItem、probe/签名/权限/网络动作，
不改新客户端、Package/root/backend。新 enum case 的 exhaustive switch 消费方须
核对并 pin 新 commit；客户端文件持久化/原动作恢复及真实平台验收仍属原 owner。
