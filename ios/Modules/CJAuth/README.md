# CJAuth — local flow candidate

CJ007 独占独立包，base `d27c23c009b308c6083a93c0d0096b1162900233`。
这是邮箱/Google/Apple 的协议无关流程核心，不是已接通的登录 UI 或 SDK。
包内无外部依赖，因此没有 Package.resolved；Swift tools 6.0，本机 Swift 6.4 编译。
iOS 17/macOS 14 只是本地编译目标，不定产品最低版本。

## 可用接口与边界

- AuthAction：邮箱登录/注册/验证/请求恢复/重置密码，以及 Google/Apple 登录。
- AuthSDKAdapter：未来官方 SDK 实现的边界。adapter 自己管理安全输入、平台 UI、
  秘密、回调合法性、nonce/state/PKCE、凭据存储及脱敏错误；本包不接收密码/token/URL。
- 唯一随库提供的 UnconfiguredSDKAdapter 对所有入口返回 missingConfiguration，
  run 不调用 perform。没有可设置为“已配置”的默认开关或生产假登录出口。
- AuthFlow：MainActor 上捕获 per-instance/per-generation/per-operation attempt，
  await 后复核；取消/替换/失效后的回调与重复回调无效。purpose 不匹配显式失败，
  恢复结果不能当登录结果。identityNeedsServerCheck 只是待服务端验证，所有状态下
  canUseRestrictedBusiness 恒 false；Google/Apple 返回身份不等于受邀。
- begin/accept 提供受控 SDK callback 接缝，不是 URL parser。adapter 必须保存原
  attempt，验证原 provider/purpose 后提交，禁止用当前 attempt 给旧 URL 贴标。
  本地 UUID 是关联标识，绝非 OAuth state、nonce、业务 ID 或凭据。
- cancel(attempt) 是本地取消；host 要在关闭流程时显式调用，不能只取消 Swift Task。
  invalidateIdentity 用于退出/切号/新身份生命周期/明确失效。它不持有也不删除
  会话、缓存或 UI；未来 host 必须同步执行 AUTH/UI 双重屏障。语言不属于身份输入。
- 网络未知不变成明确拒绝或远端撤销。本包不持有凭据，因此不可能把网络未知当作
  删除凭据的指令；仍需真实 SDK adapter 证明此行为。

未来官方 adapter 接入时，新增包依赖须固定版本与锁，并重验实际 SDK 事件/错误。
本次固定基线 ios/Package.swift/Package.resolved 未发现 Supabase；未继承其他工作树
SDK 版本，未安装或宣称验证任何 Supabase Swift 版本。

## 复现与证据

```sh
env CLANG_MODULE_CACHE_PATH=/private/tmp/cj007-clang-cache \
  SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/cj007-swift-cache \
  swift test --package-path ios/Modules/CJAuth \
  --scratch-path /private/tmp/cj007-auth-swift-build --disable-sandbox
```

2026-10-21，本机 macOS/arm64，Swift 6.4：build PASS，Swift Testing 8/8 PASS。
输出见 evidence/swift-test.txt；XCTest 的 0 tests 是另一 runner，实际 Swift Testing
输出为 8 项。首次默认缓存因 sandbox 不可写失败，随后指定可写临时缓存修复；
只读全局 SwiftPM 缓存警告保留。未更改全局配置。
测试 adapter 仅存在测试 target，无网络、账号、SDK；覆盖缺配置零调用、取消/重复、
回调用途、跨 provider 替换、跨实例、身份失效、独立邮箱结果及真实 async 挂起晚到。
既有 Python 契约未改，证据复用。

UNRUN：iOS simulator/device、实际页面/host 注册、SDK 编译与行为、浏览器 OAuth、
Apple 能力、nonce/state/PKCE 校验、邮件、真实注册/恢复、服务端邀请、数据库隔离。
没有发布完整 AUTH@1.0 或 AUTH-SEMANTICS 子版本；Issue #8 未关闭。
