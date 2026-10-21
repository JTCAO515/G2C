# CJAuthSupabase 本地 adapter 候选

当前含 P2 同 attempt 重入返修，差额 base `d582c14f89e6c279e72eaceded71e51149b858b0`；
该旧 head 不可合入。原编译证据保留，不作为已覆盖重入的证明。

差额 base：`4836dff7f4c1185425b196206639acde44a8d52f`；旧核心候选保留可独立审阅。
新增独立 product/target `CJAuthSupabase`；无 host/CJShell/根工程/API/数据库变更。

## 依赖与来源

复用 CJ004 的官方 Supabase Swift **2.55.4**，revision
`fee4bd78997f8b4e919c1c9711e0cfb346fd7a55`。读取其 `spikes/ios/evidence/SOURCES.md`、
固定 checkout 源码与 LICENSE；MIT 全文在 evidence/SUPABASE-LICENSE.txt。
本包 exact 版本与自有 Package.resolved 共固定 8 个包，逐个核 checkout revision
相等、clean，许可证文件 SHA-256 在 evidence/sdk-provenance.json。包 tools 升至
6.1 以符合 SDK；不代表最低 iOS 或最低工具链已运行验收。

从 CJ004 bare-repository 缓存复制至独立 `/private/tmp/cj007-spm-sdk-cache`，未写其
checkout；先 seed 原锁，SwiftPM 解析后自动收敛成本包所需 8 pins，没有依赖本地
路径或修改全局镜像。实际构建采用本机 Swift 6.4/macOS arm64。未读取 VP 秘密。
官方 API 接缝以这份固定源码为准：AuthClient.Configuration.fetch/localStorage、
signIn(email:password:)、signUp、resetPasswordForEmail、signInWithIdToken。

## 本轮能执行与不能执行的内容

- 通过官方 Auth product 构造邮箱登录/注册/恢复及 Google/Apple 原生 ID-token
  交换请求。native 仅是本轮可编译接缝，不冻结最终原生/网页产品流程。
- adapter 必须显式提供 authURL、publishable key（仅 sb_publishable_；不接受旧 JWT
  key 或 secret key），注册/恢复还需明确 HTTPS redirect，原生 provider 需 clientID。
  不填默认 URL、key、ID、redirect。当前只支持无 query/fragment/userinfo 的 HTTPS
  配置地址；其他 deep-link 类型需正式 host 决策，不能静默 fallback。
- native 材料包含原 attempt、provider、clientID、ID token、nonce 和可选 access token。
  全部来自后续真实平台流程；adapter 核对应关系和非空后才交 SDK，**不自称已验证
  token 签名、nonce 来源或 OAuth state**。材料缺失/不匹配显式 unavailable。
- 关键回写前检查原 attempt；材料获取后、fetch 前、SDK 完成后各重核。每次尝试
  建独立 AuthClient + 仅内存 storage，停用 autoRefresh/logger/持久化，结束清内存。
  SDK 迟到不可能覆盖下一 attempt 的 keychain/session；不存在共享已登录状态出口。
- 所有结果最多到 identityNeedsServerCheck，永不返回 principal/凭据或邀请 grant。
  Google/Apple 身份不等于 JT 受邀资格；当前 canUseRestrictedBusiness 恒 false。
- 邮箱验证和密码更新回调仍为 hostCapabilityRequired：没有可信回调用途/平台
  注册/持久凭据，不调用 session(from:)、exchangeCodeForSession 或 update(user:)。
  邮件发送请求构造不证明邮件送达；不构造成功 OAuth/session fixture。
- **默认 fetch 直接抛本地离线错误，绝不调用 URLSession。** 本次只注入闭合本地
  transport；未来真实 transport/host 启用仍受获准环境及接缝门槛约束。

## 未知结果与 SDK 自动重试

固定 SDK `Sources/Auth/Internal/APIClient.swift` 将 POST 纳入自动重试。
本 adapter 为每个 attempt 增加单次 fetch gate：第一次已交 transport 后，SDK 重试
在本地被拒，不能再次触发注册/邮件/token exchange。重试等待可能仍发生，不能
声称“SDK 无重试”，但 transport 请求次数最多 1；原结果维持 networkUnknown。
SDK 未知错误/解码问题/5xx 不转换为账号无效。4xx 明确拒绝仅针对本次操作，
不清任何其他会话；固定官方 emailNotConfirmed 单独映射 emailVerificationRequired。
新 API 错误 code 需要官方响应版本头才能解码，测试按固定 SDK 规则提供；没有
对任意无版本字符串猜测错误含义。网络未知不是删除凭据命令。

## 核心差额与消费者影响

AuthFlow 只增加 SDKEvent.unavailable(reason)、emailVerificationRequired 及对应状态；
UnavailableReason 新增 missingRuntimeMaterial。已有取消/代次代码不重构。枚举消费
有源码适配影响，正式 host 尚不存在；不能把 4836dff 的旧 exhaustive switch 视为
自动兼容。未改变 AUTH-SEMANTICS@0.1.0-rc.1，未发布完整 AUTH@1.0。
旧核心的“SDK adapter 自己管理安全输入”在新 product 中通过异步材料闭包接缝体现；
秘密只在材料/SDK 请求内瞬时使用，不写日志/磁盘；平台安全输入仍未实现。

## 验证

```sh
env CLANG_MODULE_CACHE_PATH=/private/tmp/cj007-clang-cache \
  SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/cj007-swift-cache \
  swift test --package-path ios/Modules/CJAuth \
  --scratch-path /private/tmp/cj007-sdk-build \
  --cache-path /private/tmp/cj007-spm-sdk-cache \
  --disable-automatic-resolution --disable-sandbox
```

缓存缺失的机器需先按锁取得官方依赖；不得将缺依赖误报代码编译失败。
本轮最终 build PASS，核心 8 + adapter 11 项 PASS，见 evidence/sdk-tests.txt。
新 adapter 测试覆盖 5 类真实 SDK 请求构造（邮箱3、provider2）、缺配置/材料/nonce、
错误 provider/clientID/attempt、验证/重置禁用、取消材料获取与在途结果、未验证邮箱、
默认无网络、未知 POST transport 恰一次。全部使用 `.invalid` 域与显式合成材料，
没有 socket、真实账户、注册、邮件、OAuth、持久凭据或邀请调用。

过程失败保留说明：第一次 resolve 缺 --disable-sandbox，sandbox-exec 失败；修正后
从缓存解析成功。测试先因辅助方法访问级别、嵌套 #require 宏编译失败，已修正；
邮箱未验证例先因缺 SDK 响应版本头失败，读固定 SDK 解码后修正，未降低断言。
最后因新增边界测试/代码变化重跑本包套件；未重复旧 Python 或 UI 验收。

UNRUN：SDK 真实成功会话/安全存储与重启、平台 OAuth/nonce/state/PKCE、回调路由、
iOS host/Apple 能力、邮件/账号/API/数据库/真机。仍需 Main 分共享 host lease；
用户操作、控制台、凭据、环境/费用步骤保持待办，不向离线用户索秘密。


## P2：同 attempt 重入返修

根因：d582c14 的 SingleRequestGate 在每次 perform 内新建，只能抑制一次方法调用
内部的 SDK retry；相同 AuthAttempt 再调用 perform 会重新获取材料并再次出站。
作者在旧源码上新增 5 项反例，全部 FAIL，原输出保留 evidence/p2-before.txt。

最小修复：AuthAttempt 内增加 package-only 的 SDKAttemptExecution 引用，副本和
不同 SupabaseSDKAdapter 收到**同一个原 attempt** 时共享它。该记录仅存运行 Task
和最终 SDKEvent，不存凭据/URL/原请求内容。MainActor 同步登记 Task 后才 await，
因此顺序/并发重入不会启动第二次 performOnce；完成后保存原结果并释放运行 Task。
原 SingleRequestGate 保留，分别处理 SDK 内部 retry 与方法层重入这两个边界。

- 仍是当前 attempt：在途重入等待同一结果；完成重入返回原 SDKEvent，无第二次
  material/fetch。即使换 adapter/config/material，也不能把同一 attempt 重新执行。
- 已取消/切号/失效：isCurrent 先拒绝，返回 userCancelled；原来已发出的副作用
  不声称撤销。在途晚到结果即使被内部记录，也不能写入新的 AuthFlow 状态。
- 原结果 networkUnknown：重入仅读取本地原 unknown，不再次出站。**这不是远端
  对账，也不是重新验证**。必须等未来正式领域提供原操作查询；本实现不创建新
  attempt 来自动重试。host 不能用 begin/run 新建 attempt 绕过未知结果边界。
- 不同显式合法 attempt 各自独立，完成 A 不吞掉 B；一项已知完成操作后用户显式
  发起另一项操作可以派发。此许可不涵盖将未决操作换 ID/attempt 盲重发。
- 作用域是同进程内原 AuthAttempt 的共享记录，包括其值副本与跨 adapter 实例。
  记录随原 attempt 引用存活；不序列化、无全局表/持久存储，不能对重启后重建的
  attempt 或伪造新操作提供幂等保证。没有扩大到跨进程/服务端 exactly-once。

验证：保持原 8+11 测试不改断言，新增 5 项先红后绿：顺序重入、并发重入、
跨 adapter 重入、unknown 后重入、取消拒绝与不同合法 attempt 隔离。
复用原“在途 SDK 响应后切号”反例核晚到。本次完整受影响小包 suite：编译 PASS，
核心 8/8 + adapter 16/16 PASS，见 evidence/p2-after.txt。锁与 SDK 版本无变，
evidence/sdk-tests.txt 保留旧 8+11 原输出；没有真实网络、账号、注册、邮件或 OAuth。
