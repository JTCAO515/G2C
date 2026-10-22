# CJ-SDK-SESSION-BRIDGE@0.1.0-rc.1 — 默认关闭的官方 Session 桥接候选

本地 base 43be60d34ceecbefff240cd31a2784a591604a6b，操作前 clean。
只读核 Main `3c52f72daf1d8e2304c0c569b47e68d92a4b323e`：CJShell AccountHost 已有
SessionLifecycle 和 verifyRestored(material, operation) 接缝，但没有官方 SDK Session
编码/再验证实现；原 SupabaseSDKAdapter 丢弃成功 Session，只返回展示事件。
本轮不复制 AccountHost 或 SessionLifecycle、不新增凭据模型，不改 CJShell/后端。

## 固定 SDK 表示与默认边界

复用 Supabase Swift 2.55.4 / fee4bd78997f8b4e919c1c9711e0cfb346fd7a55，
Auth.Session: Codable/Sendable 及 AuthClient.Configuration.jsonEncoder/jsonDecoder。
来源为已核 checkout 的 Sources/Auth/Types.swift、Defaults.swift、AuthClient.swift；
SDK setSession/refreshSession 的实际网络调用本轮**没有启用**。

编码的是官方完整 Session，不自造 access/refresh credentials schema。SDK JSON 只
作为 opaque SessionMaterial 的内存/安全存储 payload，不写普通 JSON 文件、偏好、
日志或截图。未把 token 或其摘要作为消息 AES key；CJMessageKeys 不依赖此桥接。
SessionMaterial 文本/Mirror 脱敏保持；官方 Session 原对象仍只在受信任 SDK/host
闭包内使用，不记录它或原始编码错误。没有持久化/零化的额外承诺。

SupabaseSessionBridge 构造要求原 SessionOperation、同一 SessionLifecycle、可信
host 绑定的 expectedUserID、原 UI generation 检查闭包。verify 闭包默认 nil：返回
unavailable，不启动网络/刷新/自动恢复。expectedUserID 必须来自当前可信 host 账号
scope，不能取缓存/调用者声称的 ID 来自行授予身份或邀请。

## 初始保存、刷新与恢复接缝

- SDK adapter 新增可选 onSessionForSecureStorage(Session, AuthAttempt)，默认 nil。
  仅 email signIn/原生 ID-token 交换实际 SDK 返回 Session 后，在原 attempt 仍有效时
  交给可信 host；回调后再核原 attempt。注册待验证响应不冒登录保存。原 P2 的
  attempt 执行记录继续确保重复/并发/跨 adapter 同 attempt 不重复交接或派发。
- host 在发起 SDK 工作前捕获 SessionLifecycle.beginTrustedSDKSave 与原 UI/Auth
  绑定，回调使用 saveTrustedSDKSession 保存官方编码，不能给迟到结果新建操作。
  存储失败显式返回 storageFailure；SDK 展示事件不代表已经持久化，host 必须消费
  独立保存结果。新增可选参数放在原 material 闭包之前，保留旧 trailing closure。
- revalidate(material, reason) 解码官方 Session，检查基本形状/预期 user ID，再调用
  注入的 SDK/host 验证器。reason 区分 explicitRestore、refresh、backgroundRevalidation；
  reason 本身不启动后台任务，也不绕过 userInitiatedOnly 恢复策略。
- SDKSessionCheck.verified(Session) 只表示该受信任 hook 返回的候选会话，不授 CJ
  principal/成员/邮箱/邀请；identityMismatch、malformedMaterial 不伪装成 authoritative
  invalid，也不删除其他有效会话。generic 网络/依赖/未知必须映射 unknown。
- **两阶段提交**：verified 仅暂存编码并返回 readyToSave，保留原恢复操作有效。
  AccountHost 原 verifyRestored 返回后还检查原 SessionOperation；因此不能在闭包
  内直接生成保存操作。host 完成原 UI/操作核对后才显式 persistVerified，成功后可
  采用 committedOperation。当前 Main host 尚未接这个提交阶段，须 CJ006 后续消费。
- 明确 invalid 先返回 identityInvalid，host 核对后调用 clearAuthoritativelyInvalid。
  清理失败进入 SessionLifecycle blocked，不能恢复/保存。unknown 只调用
  noteNetworkUnknown，保留原存储字节/代次，无删除或自动 retry。
- 相同 bridge 的重复回调共用一次再验证 Task；更换材料或用途冲突。原 SessionOperation
  内仅新增 package-private owner claim，使第二个 bridge 也不能对同一原操作重复刷新。
  记录仅进程内，非持久幂等；unknown 后不得新建 operation/bridge 盲重试已可能消费的
  refresh token，应走 SDK/host 原会话对账方案。
- 每次 await 后检查原 UI 与原 SessionOperation；旧 scope、切号/失效、UI 重入均
  不得保存/清理新身份。检查 UI 闭包后重新核 SessionOperation，避免同步重入导致
  原验证结果绑定到新保存操作。与其他 bridge/host 的共享 UI 单 writer 仍由 host 维护。

## 真实验证与缺口

编译 PASS。定向执行新 bridge **10/10** + 原 SessionStore **9/9** + SDK adapter
**16/16**，共35项 PASS，日志 evidence/session-bridge-tests.txt。
覆盖官方编码 roundtrip、注入刷新/后台 unknown、重复/跨 bridge 原操作保护、明确
invalid 与清理失败、旧 UI/账号晚到、UI 同步重入、错误用户/损坏数据、默认无 hook、
旧 trailing material closure，以及真实 SDK 解码合成200响应→受绑定内存存储只一次。

所有会话/token/password 字符串均明确 SYNTHETIC，SDK fetch 为本地拦截，无真实网络。
存储为注入内存实现，无 Keychain 调用；“SDK 解码成功”不是实际登录/签名验证或平台
生命周期验收。首次测试辅助方法访问级别不符已修正；未降低断言。
SDK 与依赖锁未变；Package.swift 仅增加 CJAuthSupabase 对已存在 CJSession 的依赖。

尚需原 owner 接入：CJ006 的原 UI/operation 验证后保存/清理阶段、初始 SDK Session
回调、真实官方 SDK 错误到 invalid/unknown 的精确映射、原 refresh 未知恢复、实际
受信任 namespace/账号绑定。真实 SDK 刷新/后台唤醒、邮箱/OAuth、Keychain/真机、
服务端准入仍 UNRUN。Keychain 已失败的单次授权保持停机：未 sign/launch/清项。
没有自动启用登录或业务权限，完整 AUTH/Issue8 未完成。

## 保存重入 P2 返修（base 8a201c481dfef116a300c6bd8a4e12840bcd3f86）

旧候选 HOLD：注入保存 A 的同步回调正常 clear 并成功保存 B，随后 A 抛错；旧
SessionLifecycle.save catch 无条件 block，使 B bytes 虽在、B operation 却失效。
新 SessionSaveReentryTests 在旧代码复现：初始 SDK 保存与 persistVerified 两项失败
（4个断言），两个“原操作真实失败仍阻断”控制例通过。日志 session-save-p2-before.txt。

最小修复：save 成功/异常返回后核原 operation/代次；错误已属于旧操作时抛 stale，
不改变新状态。增加 package-private ownsOperation 区分“被新操作替代”与“同一原
操作已因真实失败 blocked”，不放宽公开 isCurrent。bridge 的初始保存与
persistVerified catch 同样核原保存操作，旧错误返回 stale，不向 host 误报 B 存储故障。
revalidate 原 await/UI 后校验保持，原 late/UI 重入反例复验有效。

修复后：新增4/4 + 原 bridge10/10 + SessionStore9/9 = 23项 PASS，输出
session-save-p2-after.txt。确认 B 的原 bytes、saved 状态、operation 均有效；原 A
自身真实失败仍 storageFailure/blocked，保留已有数据，不假报成功。
只改两个原源码文件及定向测试/证据；无新 wrapper、无 CJShell/品牌/Package/后端/
Keychain 操作。SDK adapter 16项既有证据复用。新候选待双审，不自行释放旧 HOLD。

## load/save/clear 同根因完整收口（base 532cb1610f4f4e721d09e062f0197b986832081c）

Testing 指出完整 bridge 仍 HOLD，本轮只修相同生命周期回调家族。
原样复用 Testing 文件 CJ-007-session-save-fix/AdjacentSessionCallbackTests.swift 的
三个固定方法；在旧 532 上重现 **3项 FAIL / 6断言失败**，原输出保留
session-all-callbacks-before.txt。独立发现归属 Testing，不把作者重现冒独立审验。

| 外部回调 | 成功返回后 | 异常返回后 |
|---|---|---|
| persistence.load | 原 operation/current 仍有效才更新状态并返回 material，包括 nil | 原 operation ownership 仍有效才 block，否则 stale |
| persistence.save | 保持 532 的原 operation/current 校验，旧成功也不冒当前保存成功 | 保持 532 的 ownership 校验，旧错误不阻断 B |
| persistence.clearAndBlock | 捕获本次 clearing generation；仍属该代次且无新操作才 unblocks/cleared | 同一代次才 block，否则 stale；不能清/阻断 B 的状态 |

bridge clearAuthoritativelyInvalid 不再无条件回 invalidated：lifecycle 报旧操作则
返回 stale；成功清理后还核 UI、清理后的 generation 与 cleared 状态。真正当前
清理错误仍 storageFailure/blocked，不降断言或假清理成功。revalidate/persistVerified
原操作与 UI 检查保持；新增 package-private generation 只用于当前包收尾核对，
不改变公开 API、自动恢复策略、网络/provider/Keychain 默认关闭状态。

新增/复用 AdjacentSessionCallbackTests 共8项：旧 load material/异常/nil、旧 clear
成功/异常、旧 save 成功、同原 load/clear 真失败阻断与当前 authoritative-invalid
正常清理。另复验 save4 + bridge10 + SessionStore9，总 **31/31 PASS**，日志
session-all-callbacks-after.txt。验证旧私有 material 不返回、新 B bytes/operation/saved
状态保持，当前真实失败继续阻断；不据此宣称任意外部 persistence 实现的物理事务
或真实 Keychain/平台生命周期安全已验。

仅两个原源码文件、定向测试/证据/本说明变更；无新 wrapper/框架，无 Package、
CJShell/品牌、后端或真实资源操作。原 SDK16及其他未改路径证据复用。
新固定候选待独立双审；不自行将旧 8a/532 HOLD 升级为完整验收。
