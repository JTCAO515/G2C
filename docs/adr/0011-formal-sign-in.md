# ADR-0011：正式登录（Apple、Google、邮箱）与账号池

- 状态：**accepted**（以统筹审定合并为准；合并前是待批草稿。Claude 起草。路线和第 13 节九项由 58/59 统筹线程 2026-11-26 按 JT 预授权决定，见「决定来源」）
- 日期：2026-11-26
- Issue：[#1883](https://github.com/JTCAO515/G2C/issues/1883)（总票 [#1715](https://github.com/JTCAO515/G2C/issues/1715)）
- 关联：[ADR-0002](0002-runtime-candidates.md)（客户端/认证候选「Supabase Auth 官方 Swift SDK」，本 ADR 不采用）、[ADR-0004](0004-delivery-flow-and-repo-hygiene.md)「JT 决定」第 3 条（主登录邮箱 OTP，本 ADR 扩为三种方式）、[ADR-0007](0007-issue-closure-workflow.md) 第 2 条（迁移预授权边界，见本 ADR 第 2 条的例外申请）与第 3 条（红线审查）、[W4-10 #1754](https://github.com/JTCAO515/G2C/issues/1754)（缩为大陆网络可达性抽测）

## 背景

JT 2026-11-26 要求 App 支持 Apple、Google、邮箱三种正式登录，邀请码登录保留、用邀请码仍可跳过这三种。

**仓库现状**（`origin/main` `ac9fbf6f`）：

- 唯一登录是邀请码：`POST /v2/demo-invite-sessions` 返回四字段 grant（`version` / `access_token` / `subject` / `expires_at`），7 天滚动；App 在到期前 24 小时内调用 `POST /v2/demo-session-renewals` 续期（窗口只在 App 端判断，服务端不检查）（`ios/App/DemoBetaConfiguration.swift`、`deploy/hk/demo_login.py`）。
- 签发：API 进程只校验请求形状，经私有 Unix socket 交给 worker；worker 持 RS256 私钥（进程内存，不落盘），核对 `cj_message_scope` 中的邀请码摘要后签 JWT。
- 账号是**静态名单**：`CJ_BETA_SUBJECTS_JSON` 与 demo 名单（`m4-synthetic-demo-<12>`）由运维逐个预开户，demo 名单当前上限 206；业务准入看 subject 是否在名单内，数据按 `scope_for(ISSUER, subject)` 隔离（`deploy/hk/configuration.py`、`deploy/hk/demo_accounts.py`）。
- App 把会话字节存 Keychain，账号目录按环境 + 账号分开；App 内已有「注销账号」多步清理（`ios/App/DevelopmentTripHost.swift`、`ios/App/DemoBetaApp.swift`）。
- `backend/auth/cj_auth` 有固定算法的 PyJWT 验证与显式 JWKS 拉取组件（默认不联网）；`ios/Modules/CJAuth` 有从未接通的 Supabase Swift SDK 候选。

## 决定

1. **香港自建，不引入 Supabase Auth。** 香港服务端验证 Apple / Google 的 ID token 和邮箱验证码，验证通过后由现有 worker、用现有签名密钥和 iss/aud 签发会话。grant 仍是四个字段，`version` 为 `ACCOUNT-session.1`，与 `DEMO-invite-session.2` 同为 7 天上限，并且和邀请码会话一样不超过 `hk_demo` 授权截止日。理由：不新增境外身份处理方；不用两套签发方和续期语义；App 只连香港和 Apple/Google 自身；业务接口不用改。`ios/Modules/CJAuth` 的 Supabase 依赖另开清理票。

2. **账号池加身份绑定，不按需开户。**
   - 运维按现有预开户流程开一批**未绑定**账号（新模式 `bootstrap-pool`，不写邀请码摘要），首批 50 个，计入 demo 名单。名单上限按 #1749 定为 256，即现有 206 加池 50，额度沿用 Demo。池名单变量只能在发布切换之后写入。
   - 正式身份首次登录且准入通过时，worker 在**同一个事务**里写入身份并用 `FOR UPDATE SKIP LOCKED` 取一个未绑定账号。同一身份并发首次登录撞上唯一约束时，事务回滚（取号随之撤销），然后重读已有绑定，不另占池号。
   - 池号用完返回 503 并告警，不会把用户放进已绑定的账号。注销后该账号退役，不复用。
   - **跨 scope 访问不在 ADR-0007 第 2 条迁移预授权内。** 登录前还不知道 scope，身份查找、取号和绑定都要跨 scope；而预授权禁止 `SECURITY DEFINER`、新角色和 `DELETE`。另外，API 和 worker 现在用同一个 runtime 角色连库，所以只靠函数并不能把调用限制在 worker。
   - 因此迁移 PR 必须在下面两种做法里选一种，并由统筹按 JT 预授权**单独批准这个例外**：
     - **（推荐）worker 专用签名角色**：只对身份、池、验证码三张表有 `SELECT`、`INSERT` 和必要列的 `UPDATE`，不能读业务表，也不能 `DELETE`。连接串只交给 worker，API 的 runtime 角色对这三张表没有任何权限。
     - **`SECURITY DEFINER` 函数**：固定 `search_path`，`REVOKE ALL FROM PUBLIC`，owner 不是超级用户；只接收摘要、只返回 subject。这种做法要写明它的边界：API 进程能调用函数，但没有 HMAC 密钥，算不出某个身份的摘要；不过仍可能用随机摘要耗尽号池，所以还必须在函数内对取号限速。
   - 身份 HMAC 密钥和验证码 HMAC 密钥只放在 worker。

3. **身份存储。**
   - 身份键是 `(provider, HMAC(服务端密钥, provider ‖ sub))`，不存原始 sub。一个账号每种方式最多绑一个身份。
   - 邮箱的规范化：去首尾空白、NFKC、小写，不归并 Gmail 点号。
   - 「已验证」只有三种来源：
     - 验证码；
     - Apple 标记为已验证（`email_verified` 可能是字符串 `"true"`）的非中转邮箱；
     - Google 标记 `email_verified` 为真，并且邮箱是 `gmail.com` 或 token 带 `hd` 声明（Google 说明非 Google 域的验证状态可能过时）。
   - 其他邮箱只存为未验证。**未验证邮箱不参与任何匹配或合并**，也不作为发信地址。
   - 验证码：6 位数字，只存 HMAC，常量时间比较，10 分钟过期，单次最多尝试 5 次。
   - 链接验证码绑定发起关联的那个身份摘要，只能把该身份关联到目标账号。
   - 过期的验证码、nonce 记录由现有定时清理机制（参照 rejected-intakes 清理）在 24 小时后删除；签名角色本身没有 `DELETE`。三张表都接入现有账号清理，并登记进 `backend/storage-registry.json`。
   - 续期沿用原路径，按账号类型判断资格并返回对应 version：
     - 邀请码账号：邀请码有效，返回 `DEMO-invite-session.2`；
     - 正式账号：身份绑定有效且 `iat ≥ session_floor`，返回 `ACCOUNT-session.1`。

4. **三种登录。** 都先向服务端申请一次性 nonce：`ACCOUNT-signin-nonce.1` 返回随机 nonce，10 分钟有效，用一次即作废。服务端核对 token 里的 nonce 后把它标为已用，同一个 ID token 不能重放。
   - **Apple**：
     - App 用系统原生授权，只请求 `email` 范围，`request.nonce` 取服务端 nonce 的 SHA-256。
     - 服务端按 Apple JWKS 验 RS256，检查 `iss = https://appleid.apple.com`、`aud = space.go2china.app`、时间声明和 nonce 哈希。
     - header 只有 `kid`、`alg`。payload 里还有 `nonce_supported`、`real_user_status`、`is_private_email` 等声明，固定声明集只核对需要的字段，其余忽略。
     - 中转邮箱（`privaterelay.appleid.com`）只用于显示，不参与匹配，我们也不向它发信。
   - **Google**：
     - 不用 GoogleSignIn SDK。App 用 `ASWebAuthenticationSession` 走授权码 + PKCE（S256）+ `state` + 服务端 nonce，只请求 `openid email`，在设备上换取 `id_token`。
     - 服务端按 Google JWKS 验签，检查 `iss`、`aud`（iOS client ID）、`azp`（存在时必须等于 iOS client ID）、nonce 和邮箱验证状态（见第 3 条）。
     - 服务端不向 Google 发送用户数据，只拉公钥。
     - 大陆网络打不开 Google 时，App 提示改用 Apple 或邮箱，不当作账号问题处理。
   - **邮箱**：
     - 发码接口不论邮箱能否登录都返回 202 和 challenge id，不暴露账号是否存在；不在准入名单里的邮箱不实际发信。
     - 限速：每邮箱每小时 5 次、每天 10 次；每 IP 沿用现有登录限速。
   - Apple 与 Google 的 token 都缺 `typ`，Apple 还缺 `nbf`。因此按提供方各加一份固定声明集的验证 profile，原 strict 验证路径不放宽。

5. **账号合并。** 身份已存在时进入它绑定的账号。身份不存在、且带**已验证**邮箱 E（按第 3 条判断；未验证邮箱一律按无邮箱处理，直接开新账号）时：
   - 没有账号持有**已验证**的 E：准入通过就从池中开户。
   - 已有账号持有**已验证**的 E，用邮箱验证码登录：验证码证明邮箱归属，直接关联到该账号。
   - 已有账号持有**已验证**的 E，用 Apple 或 Google 登录：**不自动合并**，返回 `409 ACCOUNT_LINK_REQUIRED` 并向 E 发验证码，用户确认后才关联。

   59 不做身份解绑，也不做 App 内绑定其他登录方式。

6. **与邀请码共存。**
   - 邀请码的请求、签发、续期、清理都不改。登录页加「我有邀请码」入口，进入原邀请码页面。
   - 邀请码账号与正式账号不合并。「邀请码账号绑定正式登录」59 不做，另开后续票。
   - 正式开户的准入由 `CJ_FORMAL_SIGNIN_ADMISSION = closed | allowlist | open` 控制，默认 `closed`。外测用 `allowlist`，由运维登记邮箱摘要，与 #33 名单对应。外测第一次对外开放要 JT 本人确认，并先取得 #33 第 5.8 项的补充法律意见。

7. **注销。**
   - 沿用 App 内现有注销流程，服务端清理时删除该账号的全部身份与验证码记录，账号池记录标为退役。
   - Apple 令牌撤销：注销确认时重新做一次 Apple 授权，服务端用 Sign in with Apple Key 生成的 client secret 把新 code 换成令牌，再立即调用 `appleid.apple.com/auth/revoke`。平时不保存 Apple refresh token。撤销失败不阻断注销。换到的令牌用 worker 密钥加密后暂存，最多保留 7 天用于重试；撤销成功或到期即删除。这份暂存登记进 `backend/storage-registry.json`。授权码约 5 分钟失效，不暂存授权码。
   - Google 令牌不由我们持有，无需撤销。

8. **开关默认全关。**
   - 服务端：`CJ_FORMAL_SIGNIN_METHODS` 默认为空，此时新路由返回 404；准入默认 `closed`。
   - App：编译开关 `G2C_FORMAL_SIGNIN` 在 Beta 默认不定义；开启后也只显示 `GET /v2/account-signin-options` 返回的方式。
   - App Store 4.8：凡是给外部测试者或送审的构建，只要启用 `google`，就必须同时启用 `apple`（邮箱验证码不能替代）。Apple 在 Key 到位之前不能启用，所以 Google 也一起保持关闭。
   - 登录界面由 #1891（登录页 UI 线）先做占位按钮，放在同一开关后面；59 的实现直接接到这些按钮上。
   - 改默认值属停点，由统筹决定。
   - `com.apple.developer.applesignin` entitlement 等 JT 在 Apple Developer 开通能力后，单独一个 PR 加入。

9. **隐私。** 新增收集：邮箱、登录方式、提供方标识的 HMAC 摘要、登录时间。新增接收方：Apple、Google、邮件发送商（阿里云邮件推送；地域和费用由 JT 开通时定）。上线前，合规文档线把它们写进隐私政策、出站数据流登记表和 `backend/storage-registry.json`，并按需取得同意；App Store 隐私标签同步更新。

10. **命名债。** 池账号沿用 `m4-synthetic-demo-*` 前缀，以便继续使用现有名单校验与准入；实际上外测用户本来就是真人。本 ADR 不改这个前缀；外测开放前另开票处理命名和 `CJ_M4_SYNTHETIC_ONLY` 的口径。

## 决定来源

- JT 2026-11-26（A 线会话，原话由统筹转记在 #1883）：「我需要添加一个 Google 账号的登录和呃 Apple 账号的登录，在这个 App 上面，还有邮箱登录。现在用邀请码可以跳过，但是这三点要做好。」
- 58/59 统筹线程 2026-11-26 按 JT 预授权审定 #1883 方案：上面第 1 至第 10 条，以及 W4-10 缩为可达性抽测、池首批 50、发信商为阿里云邮件推送、热点名额在 59 内迁移编号、contracts、storage-registry 各给一次（具体位置届时申请）。

## 不做

- 不引入 Supabase Auth，也不在本 ADR 删除现有 Supabase 代码。
- 不按需动态开户，不改业务准入模型。
- 不做网页登录（因此不需要 Apple Service ID）、Apple 服务端通知、身份解绑、邀请码账号迁移。

## 必须 JT 本人做

- Apple Developer：开通 Sign in with Apple 能力，创建 Key，由 JT 本人录入密钥。
- Google Cloud：配置 OAuth 同意屏幕，创建 iOS 客户端。
- 开通邮件推送，并定地域与费用。
- 配置 DNS（SPF / DKIM / DMARC，Google 域名验证）。
- 首次外部 TestFlight 开放，App Store 隐私标签。
- 用本人账号做真机与真实账号验证。

## 后果与验证

- 业务接口、邀请码路径不变。新增一条迁移（三张表加解析函数）、一组 `ACCOUNT-*` 契约、部署变量和 App 登录界面，均为红线，按 ADR-0007 第 3 条独立审查。第 2 条的跨 scope 例外须在迁移 PR 合并前由统筹单独批准。
- L0：篡改、过期、错 key、错 aud/iss/azp、nonce 不符或重放；验证码错码、超次、重放、链接码换身份；未验证邮箱不参与合并；合并各分支；跨账号隔离；池并发取号与同一身份并发首登；撤销后续期被拒；API 角色读不到身份表（若选专用角色）。
- L1：本地测试身份提供方（仅 `CJ_ENV=local`，香港配置加载时拒绝）在模拟器走通三种方式的登录、退出、注销。
- L3 → #29：真机 Apple 登录。

## 回滚

本 PR 只涉及文档，revert 即可。后续实现在开关关闭时行为与现状一致。
