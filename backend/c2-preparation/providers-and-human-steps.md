# 邮箱 + Google + Apple：最新登录范围与人工步骤

本增补覆盖初稿仅邮箱与“新建优先”的旧描述：现在先评估 VP-V4，次选收费新项目。Google/Apple 已纳入需求，不等于任何控制台修改、secret生成、付费或签名能力已获执行授权。资源审批未完成、用户不在电脑，需要其亲自操作的步骤先跳过；本lease仍只写本准备目录。

## 登录资源与回调矩阵

| 入口 | 拟实现与资源依赖 | 回调/域及平台限制 | 待人/待配置，不执行 |
|---|---|---|---|
| 邮箱密码 | 官方Supabase Swift注册/登录，验证/找回不需邀请；受限业务另核JT名单；独立SMTP | 精确App callback URI + project Site URL/allowlist；发信域/From/DNS，不能用默认SMTP覆盖游客 | 供应商/域/费用、真收件人；注册/确认与找回实际未验 |
| Google原生（iOS候选） | 官方GoogleSignIn + Supabase ID-token入口；绑定真实CJ bundle的iOS OAuth client、用于backend audience的Web/server client | App注册reversed iOS client ID scheme；GoogleSDK回跳到App，取得provider ID token后交Supabase换会话。Google账户不是CJ资格；API只信所选Supabase会话 | Google Auth Platform项目/audience/branding/scopes，iOS与Web client ID；SDK版本/许可证与签名Keychain条件须再核，不在当前锁里偷加依赖 |
| Google浏览器OAuth（备选，非默认新增第二实现） | Supabase发起provider OAuth；Web client ID与server-side secret | Google授权回调必须为**所选Supabase项目** `/auth/v1/callback`，不是CJ API地址；随后Supabase回跳精确App URI；Google branding/域验证/测试用户范围按控制台实际要求 | 只在选择此流程后登记client secret于Supabase；不把secret放App/CJ API、不扩scope |
| Apple原生（SwiftUI优先候选） | AuthenticationServices + Supabase ID-token入口，随机nonce及校验；真实Team/App ID、Sign in with Apple capability、有效签名 | 原生系统授权不要求先为浏览器OAuth建Services ID/网站回调；Supabase允许的native token audience要对应真实App ID，不能用其他App ID；取消不是成功 | Apple Developer账号权限/会员状态、App ID能力和签名；本机C1 unsigned build不能证明Apple登录可用 |
| Apple浏览器OAuth（仅确需时） | Apple Services ID关联支持Sign in with Apple的App ID；Team/Key ID、签名.p8、生成client secret | Apple website domain为所选Supabase Auth host，return URL为其 `/auth/v1/callback`；App最终callback另外登记。OAuth secret需定期更新，native-only不因此需要同样secret轮换 | 不因为“加Apple”先生成.p8/复制旧key；有browserOAuth需求才申请具体资源与轮换owner |

Google原生的两类client ID、reversed scheme和Keychain签名要求据[Google iOS官方集成说明](https://developers.google.com/identity/sign-in/ios/start-integrating)。Supabase provider支持web/native、基础openid/email/profile scope与多client设置见[Google provider文档](https://supabase.com/docs/guides/auth/social-login/auth-google)。本方案不要求额外Drive/Calendar权限；具体client/audience配置须和选定SDK实测，不照抄其他平台示例。

Apple原生与web路径、仅OAuth设置需要六个月secret轮换、不同client audience顺序见[Supabase Apple文档](https://supabase.com/docs/guides/auth/social-login/auth-apple)。Apple web环境资源依赖见[Apple环境配置](https://developer.apple.com/documentation/signinwithapple/configuring-your-environment-for-sign-in-with-apple)。没有现成CJ Team/App/Services ID、域或secret可在本目录填入；不复用旧App身份来绕授权。

## 名单、身份绑定与私密邮箱

Google/Apple成功证明provider→所选Supabase的认证完成；认证成功及账号注册/验证/找回不因缺少邀请而失败。受限业务访问及MESSAGE/模型派发前才由服务端核当前JT名单/主体绑定/资格撤销代次。共享项目旧VP账号不自动获得CJ受限业务或旧数据权限。Apple Hide My Email可能给与邀请邮箱不同的relay地址；不能根据设备姓名、昵称、客户端声明或“看似同一个人”自动关联资格。账号认证可完成，进入受限功能时才显示需批准绑定/无资格，提供由AUTH owner固定的安全资格绑定流程；JT须决定名单是否登记特定provider subject/relay邮箱，不把这项未知悄悄填成放行。跨provider同邮箱、已有Supabase身份自动关联/手动绑定的现行行为需要独立反例验证，不在这里许诺迁移或合并账号。

如要向Apple私密邮箱发事务邮件，需登记实际出站email source域/地址与SPF，并实测relay投递；这不是默认SMTP解禁，也不是Google/Apple登录替代邮箱找回。依据[Apple private email relay](https://developer.apple.com/help/account/capabilities/configure-private-email-relay-service/)。不要求用户公开真实个人邮箱，不在Git存名单/relay地址。

撤销分层：CJ邀请/绑定资格在受限API访问/派发前核当前状态；撤邀不自动退出账号或阻断注册/验证/找回；Supabase session按既定会话撤销；provider用户可撤销授权，其凭证状态需SDK/服务端处理。不能为撤销单个CJ用户删除整个旧项目provider/key、全体会话或修改全局JWT。注销/Apple相关token撤销若需要额外provider secret，由AUTH/CLEANUP票列清并获准后实现，不声称native登录演示已完成全注销。

## 用户回来后必须亲自确认/操作的最小清单（现在 SKIP-pending-human）

1. **资源/费用决策**：先看支持线程VP-V4官方盘点、依赖和恢复证据，决定是否可共享。不可接受共享风险时，再审新项目组织/region/约USD10/月假设报价的原回执及额外项；尚未confirm_cost，不创建。
2. **账号控制台身份**：如官方流程要求重新登录/2FA/Owner或Account Holder同意，由JT在官方窗口完成；不在聊天交密码/验证码/key。可用既有安全授权的只读准备先完成，不能把“不在电脑”当批准新增权限。
3. **Google**：决定/确认CJ项目、品牌/audience/test users、真实bundle/client IDs、允许Auth回调。若需域归属/品牌验证由域owner处理；安全填server-side secret，不复制到本材料。
4. **Apple**：选择真实CJ Team/App ID与能力/签名；只有webOAuth确需时再建/批准Services ID/key与回调、安排secret轮换；发往relay时批准登记发信域。需要会员费用/条款或新增付费，不代批准。
5. **邮件/域/手机**：选SMTP与预算、批准精确DNS/From/试发名单；A安装信任仅指定实验CA，或B批准具体托管与平台入口策略；设备签名/安装、登录/邮件点击需要操作者时预约，不伪造验收。

成功标志均是实际资源/非秘密配置读回与真实指定设备的动作结果；人工步骤未完成只阻依赖的真实验证，不阻纯本地代码。涉及资源/发信/权限的动作仍需对应范围授权，不能把本清单当批量同意。

## 无需等控制台、可先交 Main 的代码切片

当前只准备方案，不越过本目录lease改根API/iOS或冻结AUTH业务schema。Main可沿各自owner派以下实现，不要求JT先回电脑：

- AUTH owner：邮箱/Google/Apple统一的认证事务状态、配置缺失/取消/错误与账号代次；受限业务的待资格/资格撤销状态独立于认证成功，不能遮蔽账号入口；原生SDK/nonce与回调匹配的最小可编译实现，凭据/ID缺失必须blocked，不能假登录成功。
- iOS owner：准确按钮与官方系统授权呈现、Keychain/账号切换清理、迟到回调fence；Google原生SDK依赖由独占锁writer核版本后集成，Apple用系统AuthenticationServices，不额外引浏览器框架。
- API owner：所选issuer/audience/JWKS固定、JWT过期/错项目与资源归属检查；受限访问/派发另核资格并fail closed，不能用邀请依赖阻断账号流程。用明确synthetic fixture验证边界，不误称实际Google/Apple/Auth联通。
- DB/AUTH owner：先制定邀请/subject绑定与非暴露schema策略和迁移计划；支持盘点/旧服务冲突未核前不应用到VP。数据授权、恢复和清理hook按已接受规则，不新增绕RLS入口。

登录UI/本地契约/配置校验可以先做；真实Google/Apple账号、provider设置、SMTP发信、持久隔离、设备TLS和注销联调仍UNRUN。不要等待人工步骤时扩大为旧VP开发、创建收费环境或关闭C2。
