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

## 当前排除

无真实 issuer/audience/provider 默认值，无 JWKS 网络默认出口，无邀请库/新权限
来源、RLS 或路由。具体 CJAccessProvider 绑定与在线撤销尚未实现；ALLOW 仅证明
本次配置化验证与提供者事实，不证明实时撤销、数据库隔离、完整生产授权或真实
服务验收。Google/Apple 原生 token 不直接作为 CJ 业务身份，需所选正式服务端
验证 profile 与成员资格；不猜各 provider audience 或 sid claim。

敏感数据：token 仅验证调用期间使用，不写日志/磁盘；测试私钥只在本地测试内存
生成。未来真实存储/密钥分发由 CJ005 统一登记；本切片无新持久状态。修改接口或
事实语义须新版本及 CJ009/其他实际消费者确认，不能静默改变错误/恢复含义。
