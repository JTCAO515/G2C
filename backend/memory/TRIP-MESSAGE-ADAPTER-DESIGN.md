# 正式 Trip 消息的记忆适配设计（草案，未冻结）

Owner C；#25 子票 #344；上游为 B #330 / PR342 及追加接口 #343。
本文只交独立设计与负例矩阵，不假定 B 草案字段、运行许可或实际接线已通过。

## 实时停点

PR342 的 message-trip.1 仅讨论：creation_intent=none；升级后拒绝新 send.2；
已有 MEMORY scope/config 也明确拒绝。不能用它给 #25 生成修改候选，不能静默关闭记忆。
B #343 先冻结追加的修改/profile/来源接口；C 再冻结本适配版本并验证实际组合。
旧版本和旧拒绝负例保持，不需要等待 JT 重复批准。

## C 消费边界

- 必须消费 canonical producer 实际签发的 owner/message/run、精确正式 Trip/version/
  content hash/选区与当前性 lease。DTO、hash、版本相等、caller owner 或本地 READY
  都不是许可；只接受可信组合注入的必需依赖，不反射探测可选能力或自动降级。
- 复用 current_context、require_current、typed eligibility/policy、编辑/启停/撤回 epoch
  fence，不另写资格、版本或范围引擎。来源数据不是最终发布许可。
- 正式 Trip 与 travel 身份保持独立。临时约束需要 canonical 来源提供实际 namespace/
  当前性证明；关联未知就 withhold，不从 TripID 推 travelID，不伪造空 Context，
  不静默只用部分记忆。producer 的明确无 namespace 也需冻结语义，不能自行解释 wire null。
- 配置/profile/consumer ABI 只追加。旧显式配置继续旧行为，缺 C 支持或来源证明时拒绝；
  不改旧 activation 脚本，不通过另一 writer 或 SQL 绕过原 gate。

## 运行与提交

1. 模型前捕获真实当前来源，只把有资格且有界的原 bytes 经原注册出口/Meter送入模型。
   不持 SQL lease 跨模型 IO，不伪称模型/费用或实际来源质量已核验。
2. 最终发布重取并检查同一捕获；B 冻结可组合锁序/写接口。不能在另一连接持 Trip SHARE
   时等待 C 唯一 Trip 事务 FOR UPDATE，形成自锁，也不能另起版本引擎绕开。
3. C 仍用原 Proposal/ConfirmationSigner/act。来源、当前记忆、Trip/选区检查在原最终
   deadline之前完成；不在 deadline 之后追加 SQL，不增加第二正式写路径。
4. 编码/返回前重复 canonical admission/currentness。账号/Trip/选区 ABA、版本变化、
   停止使用或依赖 UNKNOWN 都拒绝旧输出；保留原 action/bytes/receipt/UNKNOWN 对账。
   偏好改变不自动重写已正式接受的旧 Trip。

## Owner 与追加式交付

B 拥有新 MESSAGE/profile/capability producer 及激活；C 拥有本 adapter 和原记忆实现；
App #337 归 A。旧 send/profile 拒绝和冻结 wire不改，不增加新角色/DELETE/TRUNCATE/
BYPASSRLS/SECURITY DEFINER。若实际需要持久化，只按最新 manifest 追加本地迁移，
空库 up/down、非空 down 拒绝及跨 owner 负例通过后交付。

## 最小实际矩阵

- 签名来源/受限 PG：真实 Trip/source、长期与有明确 namespace 的临时记忆；缺失关联、
  错 owner、编码后撤权、旧 profile 兼容负例，不把 data-only fixture 当 lease。
- 编辑/暂停/恢复/停止使用发生在模型 IO 前后；Trip/选区 ABA、writer-first 与
  publication-first、限额/取消/UNKNOWN/原动作恢复；真实 worker/FakeProvider。
- Scope/owner/来源/字节/版本对不上必须零新正式效果，旧草稿与原回执继续可对账。

当前仅设计：C 契约冻结、来源绑定、激活、记忆/模型消费、发布、迁移及 App 全部 UNRUN。
未执行真实服务/模型、费用、云/生产、账号/密钥操作或物理删除。
上游实际接口和文件锁就绪后自行继续；停点期间推进其他独立 C 工作。
