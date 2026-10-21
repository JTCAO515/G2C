# CJ005 本地 Auth composition 交接（可执行候选）

base：`79f88b6552da1bd3d4b27e22f64a158bddf2853b`，原提交保留供 Publish。
新增 `CJ-AUTH-COMPOSITION@0.1.0-rc.1`（composition.py）与显式 opt-in profile
`CJ-JWT-SUPABASE-ACCESS@0.1.0-rc.1`。均待独立审验/消费者确认，未发布。
原 `CJ-AUTH-SERVER@0.1.0-rc.1` 类型与准入接口不变；没有改共享 OpenAPI 或注册路由。

## 官方形状与本地 profile 差额

2026-10-21 只读核对 [Supabase JWT claims](https://supabase.com/docs/guides/auth/jwt-fields)
与 [JWT overview](https://supabase.com/docs/guides/auth/jwts)。官方将 nbf 列为可选，
aud 支持字符串或字符串数组，并区分用户、匿名与 service-role 用途。官方示例
kid 为可选，签名算法包含 HS256/ES256/RS256。本候选**只覆盖带 kid 的非匿名用户
非对称 access token 子集**，不声称兼容所有 Supabase token 或自定义 hooks。

| 项目 | 保留旧 strict profile | 新显式 Supabase access 候选 |
|---|---|---|
| 选择方式 | `JWTConfiguration` 原默认路径，命名为 CJ-JWT-STRICT@0.1.0 | 显式传 `JWTProfile.SUPABASE_ACCESS_RC1`，不自动识别 token/provider |
| nbf | 必填整数并校验 | 可缺失；出现时仍须整数且通过 nbf 验证，null/float/bool 不接受。缺失时 principal.not_before = 已验证 iat，作为本地有效起点，不伪造 nbf claim |
| audience | 精确匹配单字符串 | 允许字符串/非空不重复字符串数组，必须包含显式配置的目标 audience。principal.audience 为实际匹配的配置 audience，不是原数组 |
| 用户形状 | 原通用 subject/time 约束 | additionally 要求 canonical UUID sub/session_id、role=authenticated、is_anonymous=false、aal1/aal2 与 email/phone 字符串；这些字段不授 CJ 资格 |
| 保留限制 | RS256/ES256、JWT typ、kid、固定公钥、整数时间、签名/issuer/时间检查 | 相同；不加入 HS256、不请求远端用户接口、不自动加载 header URL/JWK、不导入旧 secret |

新 profile 的 profile enum、issuer URL 与 audience 配置均校验；issuer 必须显式
HTTPS 且无 userinfo/query/fragment，audience 不带边缘空白。真实 project URL、
audience、key ID、公钥和容差必须由 CJ005 从获准环境提供，代码没有这些默认值。
本轮 token 全部本地测试 key 签名，仅使用官方字段形状与 synthetic.invalid 地址。
此兼容修正不证明真实签发配置、跨地域网络、会话撤销或 RLS。

## 可直接调用的 composition

模块：`backend/auth/cj_auth/composition.py`。

```python
# Parameters come from a server-owned, approved composition root, never request JSON.
boundary = build_auth(configuration=explicit_configuration,
                      keys=server_key_provider,
                      access=server_cj_access_provider)
result = boundary.authorize(single_authorization_header)
```

以上参数占位不是默认配置或可直接运行的真实服务示例。三参数必须显式传入；传
None 构成安全关闭路径（有效格式 Bearer 的验证/准入为 UNKNOWN），不读取全局
环境/旧项目。配置对象非法时启动构造抛 ValueError，不能 fallback 到旧 profile。

输入只接受一个 `Authorization: Bearer <token>` 值，scheme 不区分大小写，token
须非空、无逗号/空白；拒绝缺值、合并值或不规范格式。host 在调用前必须拒绝多份
Authorization header，不接受 query/cookie/body token、owner、email 或邀请标志。
不要打印 header/token；该 helper 不采集请求、不绑定端口、不生成 request_id。

`BoundaryResult` 返回原 AdmissionDecision、http_status_hint 和 ErrorSemantics。
ALLOWED 仅给内部 principal；没有 HTTP 成功回执，CJ009 等仍须校验资源与原动作。
HTTP hint 是本候选的建议映射，需 CJ005 接受并纳入唯一 wire；不是已经发布的 API。

| 条件 | hint | outcome / recovery | CJ005 处理 |
|---|---|---|---|
| Bearer 缺失/格式错误、签名/issuer/audience/alg/time 明确无效 | 401 | failed / do_not_retry | 当前请求拒绝；不暗示原消息未接收，不泄露 token/异常 |
| 已验证身份但 CJ 成员/邮箱/邀请明确 NO | 403 | failed / do_not_retry | 当前受限操作拒绝；不清除其他会话 |
| 缺配置/密钥、未知 kid、提供者失败、资格缺失/UNKNOWN | 503 | unknown / retry_safe_read | 只可安全验证/查询，不能因此重发注册/模型/原业务写入 |
| 全部必要检查通过 | 无 hint | 无错误 | 继续领域归属/事务与结果边界检查，不能缓存成永久授权 |

ErrorSemantics 仅提供 BASE 已有 outcome/recovery 与安全双语消息。CJ005 必须补充
统一的 code/category、服务端真实 request_id/匹配 X-Request-ID，决定正式 HTTP
状态及需要的认证头，再生成完整 ErrorResponse；不得将本对象当完整 BASE 包发送。
本轮不虚构 provider code、endpoint 或追踪回执。已有写入 ACK 未知仍按原动作
reconcile_original，不能用本次 401/403/503 覆盖该事实。

## host 必须注入/补齐的边界

1. **KeyProvider.resolve(kid)**：只针对显式 issuer/profile 的可信公钥集合。当前
   bundled 实现为 StaticPublicKeys，无网络。真实轮换、新鲜度、错误/超时与可信
   来源须由获准 host 负责；kid 缺失/未知不会触发自动 JWKS 获取。
2. **CJAccessProvider.evaluate(principal)**：服务端同一权威提供 CJ member、
   email_verified、invited 的 YES/NO/UNKNOWN，返回必须绑定同 principal。不从
   token email/role/user_metadata 自授资格，不新建第二权限库。默认没有提供者。
3. **内部存储分区**：由 server composition 从可信环境/profile/身份映射到 CJ009
   仓储，不把 token times/邮箱/客户端 owner 当永久分区。具体数据库映射尚未定义。
4. **撤销/提交**：session_id 这里只检查形状，不导出/伪造实时撤销证明。entry/commit/
   return 再检查只能观察当前 provider 状态；没有与事务联动的权限屏障就不能宣称
   并发撤销安全。提交后拒绝仍保留原动作可能已提交，走原回执恢复。
5. **版本**：CJ005/CJ009 pin 新 commit 并显式确认新 profile 的 effective-not-before/
   matched-audience 语义与 HTTP hints；旧 strict 消费者默认不变。运行基线仍为
   仓库 >=3.12，本包 >=3.12,<3.15，实际 3.14.7，不推断支持 Python 3.10。

## 验证与交付范围

实际源码：新增 composition.py，扩展 JWTConfiguration 的显式 profile 分支，保留
旧默认；依赖锁与接口 types/admission.py 不变。新增 test_composition.py 8 项：
缺 nbf 的新/旧分支、aud 数组、严格时间、服务角色/匿名拒绝、配置无 fallback、
Bearer/BASE 映射、缺成员/伪造 claim 无权、unknown kid 与坏签名不同响应。

修改 JWT 公共解析路径后运行完整受影响包：原 22 + 新 8 = **30/30 PASS**，
`backend/auth/evidence/composition-tests.txt`。没有运行 Swift/数据库/真实服务。
本地 key 临时生成且不落盘，关键组合禁 socket；没有真实 token/provider 请求。
独立 Review/Testing、消费者新 profile/wire 接受、真实权限/撤销/事务仍待完成。


## 对 CJ005 当前最小 wire 提议的 AUTH 确认

以固定 79f88b6 AdmissionChecker 即可接 entry gate，无须等待新 profile 发布。
确认 invalid→401 failed/do_not_retry、其他 DENIED→403 泛化拒绝、entry UNKNOWN→503
unknown/retry_safe_read；**POST entry UNKNOWN 只允许安全验证/查询，不许可重发 POST**。
map_admission 是 entry-only helper，不能用于覆盖 MESSAGE 已可能提交的结果。
return-stage commit_possible 或 repository CommitUnknown 必须由 CJ005 映射 503
unknown/reconcile_original，保留原动作 ID/字节；不能因身份拒绝降格为未接收。

不返回 principal/reason 细节；注册/验证/找回不挂此 gate。可信 issuer/subject/env
到 repository 的映射不接受 caller owner，撤销原子性与 session 缺口仍保留。
POST 原 UTF-8 bytes/octet-stream、回执字段与 GET message_id query 的正式 wire
由 CJ005/CJ009 确认；AUTH 不重序列化正文，不把 receipt=null/not-observed 解释为
权威未接收或重发授权。显式体积上界由 composition 提供，不在 AUTH 猜产品数值。
