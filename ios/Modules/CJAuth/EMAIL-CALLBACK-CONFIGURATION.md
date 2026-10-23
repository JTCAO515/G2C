# Native email callback 配置分离 — 最小 C2 接口候选

parent a82e7fe0b22e990cba697b1ab8c668b85c502d53，首写前 clean。
本轮按 Main 新 #8/C2 技术差额授权实现；不涉及恢复被拦审验轮或外部资源授权。
先读 write-swift SKILL.md 与值类型/错误分支参考；只读 CJ005 的
backend/c2-preparation/C2-CLOSURE-PLAN.md，确认工程缺口是 endpoint/回调混用。

## 新公开配置与原兼容

`HostEmailCallback(exactDestination: URL, kind: EmailCallbackKind, purpose: EmailCallbackPurpose)`
是 immutable host 配置描述。kind 仅 https/customScheme，purpose 仅 verifyEmail/
resetPassword；构造失败抛 EmailCallbackConfigurationFailure.invalidDestination。
没有预填或自动批准任何实际 C2 scheme，包括计划候选 space.go2china.c2.dev。

SupabaseAdapterConfiguration 新增两个默认 nil 字段：
- emailVerificationCallback：用于 emailRegister 发出的验证邮件 redirect。
- passwordRecoveryCallback：用于 emailRecovery 发出的恢复邮件 redirect。

服务 authURL 仍用原 HTTPS-only endpoint validator，未放宽 TLS。显式 callback
不再复用服务 validator，可使用 host 明确选择的 custom scheme，但只接受带 host
的精确层级目的地，不通配、不接受 userinfo/query/fragment/空白。custom scheme
还拒绝 reserved http/https/file/data/javascript 等、port、编码/点段路由歧义。
HTTPS descriptor 保留合法编码路径的字节，不把编码路径归一成另一配置。

旧 emailRedirect 参数保留 HTTPS-only/共享 email 路由语义，默认配置仍缺失关闭。
同一配置不能同时给 legacy emailRedirect 与任何新 descriptor；冲突/错 purpose
安全返回 missingConfiguration，不默选一个来源，也不把验证路由 fallback 为恢复
路由。唯一 scheme/URL 信任来自 host 显式配置，不是 incoming URL、token 或 caller。
配置的语法合法也不证明平台注册、项目 allowlist 或资源审批已完成。

## 目的与原 request lifetime 接点

```swift
// SupabaseSDKAdapter，@MainActor
public func emailCallbackContext(for attempt: AuthAttempt,
                                purpose: EmailCallbackPurpose) -> AuthEmailCallbackContext?
public func isEmailCallbackContextCurrent(_ context: AuthEmailCallbackContext) -> Bool
```

context 含只读 callback + 原 AuthAttempt，构造非 public；还绑定原 adapter 实例。
仅当前且配置可用的 emailRegister/verifyEmail 或 emailRecovery/resetPassword 配对
能取得 context。错误目的、其他 adapter、旧 attempt/失效代次/请求已结束均不能使用。
没有接收 incoming URL 的授权函数，也不解析 code/nonce/state，不能拿其 true 当
OAuth/PKCE/会话/邀请证明。host 如跨 await 使用，还须原 SessionOperation/UI 绑定，
继续复用 SessionBridge；本增量未改其源码或存储语义。

此 context **仅属于原 outbound email request**。flow 接受 verificationPending 等
结果后原 attempt 退休，context 不再有效；不是跨进程/长期确认邮件 callback lifetime。
真正长期 callback 的 original-operation/一次消费/当前账号协议尚未批准，不能新建
attempt 给旧 URL 重标、从回调 URL 反向建立信任或伪造 nonce。

## 实际 SDK 与本轮停止点

复用实际 Supabase Swift 2.55.4 / fee4bd78997f8b4e919c1c9711e0cfb346fd7a55。
只读固定 AuthClient.signUp/resetPasswordForEmail 源码：二者把显式 redirectTo 放进
redirect_to query，并调用 prepareForPKCE。本 adapter 仅按目的把配置交给这两个
既有 SDK 调用，服务请求仍发 HTTPS endpoint。

原 AttemptStorage 在请求结束清空，没有 host 已批准的跨回调 PKCE verifier 生命周期。
因此 **emailVerify/emailReset 仍返回 hostCapabilityRequired**，没有真实 code exchange、
session(from:)、setSession 或持久化启用，没有 incoming URL 注册/校验/重放防线的
完整实现声明。Google/Apple native 材料、SessionBridge、原 SDK dispatch/retry gate
与业务 canUseRestrictedBusiness 行为不变。

## 证据与消费前剩余输入

编译与24项测试 PASS：新 HostEmailCallbackTests8 + 原 SupabaseSDKAdapterTests16，
输出 evidence/email-callback-configuration-tests.txt。覆盖显式 native/HTTPS、旧 HTTPS/
编码路径/default-off、错目的/来源冲突、native 不能当服务 endpoint、非法/通配/
编码/保留scheme拒绝、原attempt/其他adapter/失效/请求结束，以及 verify/reset保持关。
正常请求构造仅注入 capture transport，不连接服务器、发邮件或使用真实凭据。

普通 import 的 ExternalEmailCallbackConsumer.swift 用不同 package-name 单独
swiftc typecheck exit0；工具打印两条 sandbox-exec plugin warning，未误报无诊断，
见 evidence/email-callback-external.txt。不运行 consumer、不修改平台安全设置。

未改 Package/锁/根工程、CJShell、backend/Auth 或其他 domain；无 Keychain、sign/
launch/设备、网络、数据库、账号/密钥/邮件/资源操作。旧 Session/平台失败证据复用。
C2 还需获准 host 的精确 native registration/实际项目 allowlist、一致的 callback
用途和 code/PKCE 原操作协议、受信当前账号与安全存储生命周期；缺失时保持不可用。
本候选供 Main 正常新任务双审，不宣称首发免费授任何外部权限或完整 C2/Auth 已通。
