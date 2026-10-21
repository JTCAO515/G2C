# CJ-AUTH-SERVER@0.1.0-rc.1 — 内部服务端切片接口候选

独立版本用于 backend/auth/cj_auth/interfaces.py 与 AdmissionChecker.check(token)。
未冻结/未发布，需 CJ009 消费确认及 Main 审验路由；不是完整 AUTH@1.0，也不是
新的 API/wire/schema。此前 Swift SDK 29438a6 保全，本轮不改客户端或根工程。

- TrustedPrincipal：验证器从严格验证后的 issuer/subject/audience 与 iat/nbf/exp
  得到的内部身份。不包含 email、owner、invited、user_metadata 或原 token。
- VerificationResult：VALID 必须带 TrustedPrincipal；INVALID/UNKNOWN 不带身份。
  INVALID 表示已确定签名/issuer/audience/alg/time/格式不满足配置；缺配置/密钥
  提供者不可用等无法验证时 UNKNOWN。不是 SDK 当前会话撤销或在线状态证明。
- JWTVerifier.verify(token)：由 server composition 注入；调用者请求不能指定
  issuer、audience、algorithm、key、principal。Python 对象不是密码学能力令牌，
  不可把 JSON 反序列化成 TrustedPrincipal 来绕过 verifier。
- CJAccessProvider.evaluate(principal)：服务端独立提供同 principal 的 CJ 成员、
  邮箱验证、邀请资格（YES/NO/UNKNOWN），每次检查重新调用，不在此缓存/存储名单。
  缺提供者、异常、错误身份绑定、任一 UNKNOWN/错误类型都不授受限权限。任何已知
  NO 也不能通过。JWT 中同名 claim 不作为这些事实的来源；同项目有效旧 VP token
  只有密码学身份，没有 CJ 成员/邀请资格。
- AdmissionChecker.check(token)：先验证 JWT，再取得事实，复核查询期间未过期，
  仅全部 YES 才 ALLOWED 并返回 principal；DENIED/UNKNOWN 不带 principal。
  没有可由请求提供的 owner/invited 参数，没有公开路由或自动挂载入口。

## 消费接缝与错误恢复

CJ009 固定参考消费者 f43ad4d1ee8eec5126efa84a6f372ddcb66c0061：可将本 checker
作为接收/查询/投递前的内部准入入口，ALLOWED 后仍由 MESSAGE 检查每个资源归属。
每次派发/恢复重新 check，不保留旧 ALLOWED 当能力 token；真实事务/async 提交前
复核由消费者承担，本同步切片不承诺跨事务原子性。正式新接口消费确认 PENDING。

仅内部 reason，绝非 HTTP/provider 错误码。将来统一 BASE 映射：本次明确拒绝为
failed/do_not_retry；身份/资格验证无法判断为 unknown/retry_safe_read，仅许可安全
验证/查询，不许可重发业务写入。已有写入 ACK 未知仍 reconcile_original，不能把
本次准入拒绝映射为 not_received。无响应不得伪造 request_id；不暴露原 token/
内部异常/他人资源详情。注册、验证、找回不接此受限业务 gate。

实现指针：`backend/auth/cj_auth/jwt_adapter.py` 使用固定 PyJWT 2.15.1，
本地 RS256/ES256 profile、key provider 与测试边界见 [服务端 README](../../backend/auth/README.md)。
接口首段 head e49ea1a2abcdd82c93a28aeba8b2d6a1248a0f3b，JWT 实现随后交固定差额；
不改变上述接口版本或将它标为已发布。

## 当前排除

无真实 issuer/audience/provider 默认值，无 JWKS 网络默认出口，无邀请库/新权限
来源、RLS 或路由。具体 CJAccessProvider 绑定与在线撤销尚未实现；ALLOW 仅证明
本次配置化验证与提供者事实，不证明实时撤销、数据库隔离、完整生产授权或真实
服务验收。Google/Apple 原生 token 不直接作为 CJ 业务身份，需所选正式服务端
验证 profile 与成员资格；不猜各 provider audience 或 sid claim。

敏感数据：token 仅验证调用期间使用，不写日志/磁盘；测试私钥只在本地测试内存
生成。未来真实存储/密钥分发由 CJ005 统一登记；本切片无新持久状态。修改接口或
事实语义须新版本及 CJ009/其他实际消费者确认，不能静默改变错误/恢复含义。

## P2 修复与 CJ009 消费兼容（3f374214 后差额）

VerificationResult 对非 VALID 的 principal 现在严格要求 `is None`；VALID 必须是
TrustedPrincipal。旧逻辑错误地让字符串、bool、数值、容器等非 TrustedPrincipal
通过非 VALID 构造，虽然 AdmissionChecker 仍拒绝访问，也违反“不带身份”的契约。
这是恢复已声明不变量，不更改接口标识/签名/状态或放宽 gate；非法构造新增 ValueError
是预期修复，不能作为合法兼容用法。原 JWT adapter 的返回构造符合该条件。

只读核对 CJ009 `dc5352f` 的 `backend/message/auth_boundary.py` 与
`tests/auth_consumption.py`：Verifier 只在 VALID 带 TrustedPrincipal，其他状态带
None；Boundary 只消费 ALLOWED 的 principal。本修复与这些固定消费路径源码兼容，
没有改动 CJ009 或重跑其独立验收。集成仍须 pin 新 AUTH commit，版本字符串相同
不能替代精确源码版本。新候选交 Main 定向审验，不冒消费者已接受新 head。

**运行基线明确**：仓库 Python >=3.12；本独立包声明 >=3.12,<3.15，实际验证
Python 3.14.7。Python 3.10+ 仅是部分注解语法所需版本，不是支持矩阵或已验版本。
CJ009 dc5352f 的消费文档所写 3.10+ 应由原 owner 更正；不要求消费者自己猜环境。

## 存储分区、撤销与提交边界的真实限制

- TrustedPrincipal 是本次验证的身份与 token 时间快照，不是已分配数据库分区。
  CJ009 的 resolve_repository(principal) 必须由服务端 composition 使用获准环境/
  验证 profile 与可信 issuer/subject 绑定真实内部存储 scope；不能由请求 body、
  email、user_metadata 或 caller owner 决定，也不能以 token 的 iat/nbf/exp 生成
  每次刷新都会变化的持久分区。实际映射存储、跨环境隔离、权限/RLS 由 CJ005 与
  领域 owner 在真实资源确定后核定；本文件不指定线上字段、表或默认 namespace。
- 当前 Principal 没有权威 session revision/撤销屏障。重新检查能发现过期及当前
  facts provider 报告的成员/邮箱/邀请变化，不能发现未接入的 session 撤销；相同
  principal 或 JWT 签名有效也不能证明会话未被撤销。没有实时撤销或旧 token
  全域失效保证，不用伪造 sid/revision 填补缺口。
- CJ009 当前 entry/transaction/commit/return 检查是可复用的防护边界，但检查后
  到提交仍可能发生权限变化；没有与真实权威存储联动的原子锁/撤销屏障，就不能
  称并发撤销安全已验。慢 provider 的超时/一致性由 host 与 CJ005 在真实集成时
  明确，本同步接口无网络超时、数据库锁或跨进程事务实现。
- 提交后拒绝或身份变化不能假回滚/未接收；保持原消息 ID/字节并查原回执，
  不换身份/ID 重发。模型 dispatch 仍要重新准入，MESSAGE pending 查询不是永久
  授权。本段没有创建任何线上配置或第二权限来源。
