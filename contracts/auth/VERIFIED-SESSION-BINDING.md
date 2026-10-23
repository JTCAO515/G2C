# CJ-AUTH-SESSION-BINDING@0.1.0-rc.1 — 可信具体 session 绑定候选

实际 parent 8b6abb236cf10c1865a9cc8c6155bd8ac732c07e，首写前 clean。
为 CJ005 C2 后续受批准目标提供 source 接点；真实目标/权限/资源申请不在本轮修改。
没有 Supabase/JWKS/账号/数据库或撤销请求，无 secrets/Token 日志/Keychain 操作。

## 缺口与窄增量

原 Supabase access profile 已校验 session_id UUID，但返回的 TrustedPrincipal
有意只有 issuer/subject/audience 与时间，没有具体 session；旧 CJAccessProvider
仅凭 principal 不能证明某个 session 仍有效。本增量不往旧 principal 偷加字段，
也不把新 binding 类型当作授权。

```python
# Existing PyJWTVerifier; explicit SUPABASE_ACCESS_RC1 only.
verifier.verify_session(token) -> SessionVerificationResult
# VALID binding = VerifiedSessionBinding(principal: TrustedPrincipal, session_id: UUID)

# One host-owned authoritative session + original CJ facts query.
SessionAccessProvider.evaluate_session(binding) -> SessionAccessFacts
# SessionAccessFacts(binding, access: CJAccessFacts, session_active: Fact)

checker = SessionAdmissionChecker(verifier, approved_session_access_provider)
checker.check(token) -> AdmissionDecision             # old result shape
checker.check_session(token) -> SessionAdmissionResult # decision + binding only if ALLOWED
```

公开类型在 backend/auth/cj_auth/session_binding.py，checker 在 session_admission.py。
与其它 Python 内部身份对象一样，dataclass 不构成不可伪造 capability；不得接受
caller JSON 构造 binding/facts 或直接授予访问。真实 root 必须从此 canonical verifier
的返回取得 binding，不能由 caller 另传 session_id、owner/email/邀请状态补可信。

## JWT 原来源与兼容

verify_session 复用原 PyJWTVerifier 的同一次完整验签/issuer/audience/algorithm/
时间/profile 流程，**仅从 jwt.decode 成功后的 claims['session_id']** 建立 UUID binding，
不是解码未验证 payload 后拼接到旧结果，也没有第二次取 key/第二个 JWT 引擎。
原 Session ID 不能由 host 参数替换。错误 claim/坏签名/错误 audience => INVALID、
无 binding；缺配置/公钥 UNKNOWN。STRICT 不提供 session 语义：新方法 UNKNOWN，
但原 STRICT verify、原必填声明与输出行为仍保持。

旧 verify 的返回仍是原 VerificationResult/TrustedPrincipal，所有字段、签名与
原 profile 默认保持。为共享一次验证流程，原函数主体移动至私有 _verify；原
AdmissionChecker 的 post-provider 时间/归属/member/email/invite 逻辑提取为私有
_decide_verified_access，旧 check 的调用顺序/结果保持。interfaces.py、read_context.py
与 composition 的旧 public 行为未改，无默认切换到新 checker。

## 具体 session 准入与当前性

每次 check_session 都重新 verify_session，再调用原绑定的 SessionAccessProvider；
没有 session facts 缓存、TTL fallback 或默认 YES。provider 缺失/异常/UNKNOWN、
错误类型、binding/principal 不匹配都不放行。session_active=NO 是对**本原 session**
的明确拒绝，返回 DENIED/IDENTITY_INVALID；UNKNOWN 为 UNKNOWN/FACTS_UNKNOWN。
只有当前 session YES 后才继续原 CJAccessFacts 的 member/email_verified/invited
与有效时间检查，仍必须全部 YES。签名有效或 session 存在都不是 CJ 受邀资格。

provider 是**同一已接受权威的具体 session 接点**，不是第二成员/邀请库：真实 host
须在获准目标证明该 issuer/subject/session_id 的当前活动/撤销状态，并提供原 CJ
成员/邮箱/邀请 facts。不能把 JWT 同名字段、getUser 仅返回用户、刚发过新 token、
仅 subject 存在或旧 principal-only provider 当具体 session 存活证明。
实际查询方法/角色/endpoint/权限由 CJ005 与 AUTH 按获准目标另定，本轮不猜线上配置。

ALLOWED 才由 SessionAdmissionResult 带出原 binding；DENIED/UNKNOWN 均无 binding。
check 保持旧形状，且 class 继承 AdmissionChecker，现 ProtectedReadBoundary 可以
原样消费它并在每次 guard/finalguard 重新查原 token 所对应的 session。旧 read
context 失效后不因 provider 恢复而复活；新的 read context 仍需重新准入。

同 subject 的 A/B session 可独立有效：撤销 A 不隐式撤销 B，也不能把 A 的拒绝回调
当作清 B 的客户端指令。刷新保持 session_id 时新的 token 时间快照可改变，但
**不以 iat/exp/session_id 创建新用户/预算/存储分区**；持久 scope 仍由可信环境与
issuer/subject/audience 绑定，原域各自检查资源归属和操作版本。

## 时序与未验证范围

每个 lookup 必须返回与传入 binding 全值一致的 facts；另一个 session、subject、
audience 或刷新快照的迟到结果拒绝，不能重标回原调用。查询后仍复用原有效时间
检查；坏 host 时钟不授权。这不是声明任意 provider 返回的陈旧事实可被本地代码
自动识别：当前性必须由真实 authority 提供，撤销发生在查询后到提交间仍有窗口。
没有 session revision/原子数据库 fence、跨worker派发安全或实时撤销验收。

旧 CJAccessProvider/AdmissionChecker 仍只证明其原语义；C2 要求具体 session 时，
必须显式选择新 checker/provider，不能继续使用旧 build_auth 默认然后声称已补撤销。
入口拒绝/UNKNOWN沿 BASE 原泛化规则；若业务可能已提交，仍保持原动作
reconcile_original，不能用本次 session 拒绝覆盖提交事实。没有新 wire/HTTP 路由。

## 实际本地证据

13项新测试全部 PASS：已签 claims 来源/篡改拒绝、同 subject 不同 session、刷新、
撤销/UNKNOWN/缺 provider、原资格不绕过、错误 audience/profile/缺 session claim、
类型不变量、迟到错绑定、无缓存重核、原 read context 终止、新 context、查询中
过期与坏时钟；私钥仅本地内存生成，token 不打印。
另从实际 parent Git blobs 加载旧 verifier/checker，与新 verify/check 结果直接比较。
原相关 JWT12 + Admission6 + composition8 + read context13 同跑，共52/52 PASS，
日志 backend/auth/evidence/session-binding-compatible-tests.txt；新13日志
session-binding-tests.txt。首个组合 runner 未设置 unittest module=None，加载失败未
执行用例；已修正且保留 session-binding-runner-initial.txt，不把初始输出冒 PASS。
Python3.14.7，独立锁/依赖未变；未重复 Swift/JWKS/HTTPS/真实平台大套。

真实 Supabase 会话/公钥目标、真实 provider 与撤销操作、RLS/部署、C2 正式闭环
均 UNRUN。仅 source 候选待 Main 原双审/CJ005 后续明确批准目标消费，不解除资源门禁。
