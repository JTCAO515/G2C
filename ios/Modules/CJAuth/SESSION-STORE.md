# CJ-SESSION-STORE@0.1.0-rc.1 — host 生命周期接口候选

base f3c8e5074eb27de0de6fef6dd7558763cbcf4291，独立 product CJSession。
本轮只改 CJAuth 包；后端/JWT 固定成果不动。接口尚待 CJ006/CJ009 消费确认。

SessionNamespace(environment: UUID, slot: String) 必须由 host 为新 G2C 环境分配，
没有旧 VP/service/access-group fallback。SessionMaterial 只接可信 SDK host 给出的
opaque session bytes，不收密码，不 Codable、不进偏好/日志，文本/Mirror 脱敏。

SessionLifecycle(persistence:, restorePolicy: .userInitiatedOnly) 提供：
- beginTrustedSDKSave → save(material, for: 原操作)；beginUserRestore → load(for: 原操作)。
- 操作绑定实例、身份代次和原操作/用途，仅一次可消费；host await 后必须 isCurrent
  再使用恢复结果/写 UI，不用当前新操作给旧 SDK 回调重标。
- clear 先使旧操作失效，再清凭据；load/save/clear 异常均显式返回并阻本生命周期
  继续恢复/保存。clear 重试成功才解除本地阻断，旧代次永不恢复。
- noteNetworkUnknown 不碰存储或身份代次。读取成功只是 loadedNeedsVerification，
  不是已登录/已受邀；canUseRestrictedBusiness 恒 false。
- 自动恢复接口始终不可用；这是本候选的显式有限能力，不是已接受的最终 UX。
  重启后也不会自动读取凭据。真正自动恢复策略及 SDK/host 接线仍需后续确认。

一个 namespace 只允许一个 host 生命周期 writer；本包不声称多进程/多 coordinator
原子性。首次进入新账号流程前 host 必须 clear，并同步清 CJShell 私有内容。真实 SDK
会话刷新/账号识别、安全输入、服务端验证和邀请资格均独立，不能由本地 store 授权。

## Keychain adapter 与显式平台配置

`KeychainSessionStore` 使用 Apple Security SecItemCopyMatching/Update/Add，iOS 才提供
live initializer；macOS 测试仅能使用内部注入 operations，未运行主机 Keychain API。
`KeychainSessionScope` 必须显式传 namespace 与本 App 的 application-identifier，
每个查询均带 kSecClassGenericPassword/service/account/accessGroup/synchronizable=false。
无 access-group 默认搜索/共享组参数/旧 VP 迁移；host 必须从自己的可信 entitlement
取得并核对 application-identifier，格式校验不能替代 entitlement 归属证明。

保护级别必须显式选择 whenUnlockedThisDeviceOnly 或 afterFirstUnlockThisDeviceOnly，
无产品默认值。依据本机官方 iPhoneSimulator SDK 的 Security.framework/Headers/SecItem.h
（kSecAttrAccessible 值说明）：前者用于解锁时访问，后者用于重启后首次解锁之后
访问，二者不会随备份迁移到新设备。官方入口：
[WhenUnlockedThisDeviceOnly](https://developer.apple.com/documentation/security/ksecattraccessiblewhenunlockedthisdeviceonly)、
[AfterFirstUnlockThisDeviceOnly](https://developer.apple.com/documentation/security/ksecattraccessibleafterfirstunlockthisdeviceonly)。
网页正文需要 JS，Markdown 获取被工具拒绝，因此以已安装官方 SDK 注释核对，不猜默认。
本轮 probe 显式选择 whenUnlockedThisDeviceOnly，仅为测试选择，不定产品后台策略。

记录是带版本的二进制 envelope，真实 secret 数据只写 Keychain；不自造加密、不写
UserDefaults/普通文件/日志。clearAndBlock 覆盖完整 valueData 为不含凭据的 tombstone，
不进行宽泛删除。load 看到 tombstone 返回 restorationBlocked，损坏记录返回
malformedRecord，只有 errSecItemNotFound 才是 missing。所有 OSStatus 错误显式返回。
update 仅在明确 notFound 时 add；失败/duplicate 不换 key、不 blind retry。

clear 写入失败时旧字节可能仍存在，不能宣称已删。当前生命周期进入 blocked；
新进程也没有自动恢复入口。若阻断标记尚未成功持久化，则**不承诺失败意图跨进程
持久化**；未来 host 必须在允许新的显式恢复前处理已知清理失败，不能擅自启用自动
恢复。成功标记的跨 adapter 持续阻断已注入验证，真实跨进程层见下方未验状态。
不增加另一份凭据或全局状态库来掩盖该限制。

## CJ006 / CJ009 host 消费须知

1. 原 AUTH attempt 与 SessionOperation 都在发起 SDK/恢复异步工作前捕获；await 后
   同时检查原绑定，不能在旧结果返回时新建 SessionOperation 给它重标。
2. 退出/切号/明确失效时先关闭 UI/域旧结果回写并调用 clear；清理失败保持 blocked。
   本模块不代替 CJShell.invalidateIdentity 或清理 MESSAGE 草稿/正文/外部缓存。
3. 恢复字节仅交可信 SDK 重新验证，不能直接渲染私有内容/认定 principal 或邀请。
   网络 unknown 不调用 clear；仍须按 AUTH/MESSAGE 的未知操作恢复规则处理。
4. 当前 Supabase adapter 仍是临时内存隔离候选，尚未把成功 Session 接进此 store；
   需要真实 host lease、SDK 安全编码/验证及应用能力证据后再接，不假称自动登录完成。
5. 单 namespace 单 writer、不跨进程锁、不声明物理设备 Keychain 完整性或零化保证。

## 本轮分层证据

- 接口固定 ef2c7da41cce9bc994fa7859c29dddd5f915a978，Swift 6 源码 typecheck PASS。
- 当前包 CJSession 编译与 **9/9 注入测试 PASS**，evidence/session-tests.txt；覆盖
  namespace/query、加载/保存/清理失败、tombstone、网络未知、迟到/重复/用途/跨实例、
  禁自动恢复及脱敏。全部材料为合成字符串，不打印或持久记录真实凭据。
- simulator harness 编译 PASS：Probe/build.sh 直接编译包内同一 Session 源码，不复制
  adapter；不生成/修改根工程或 entitlement。编译器出现 sysroot warning，vtool
  核产物 platform=IOSSIMULATOR、minos=17.0；已实际安装/启动，非仅 build 假运行。
- 唯一设备 CJ007-Session-20261021 / EAF9183B-2B0B-4D9C-BCB5-A9AA71C7BB01，iOS 17.5。
  Bundle local.g2c.cj007.sessionprobe。Probe 每次 prepare 分配全新 environment UUID，
  service 使用 G2C.CJAuth.session.<UUID>，account=synthetic-session-probe；只有成功
  创建的项才可进入后续读/写/清理。元数据文件不含会话字节。
- **真实 Keychain 层 FAIL/BLOCKED**：首次 SecItemAdd 返回 -34018；官方 SDK
  SecBase.h 定义为 errSecMissingEntitlement。原日志 evidence/session-keychain-runtime.txt。
  未成功创建测试项，未进入读取/保存/删除；不修改 entitlement、不借其他 app/group。
  因失败发生在创建前，该次随机 UUID 未进入成功 metadata receipt，不伪造具体值。
- restore-clear / blocked-clean 两个后续独立进程阶段 **UNRUN**；未宣称真实凭据
  持久化/重启恢复/tombstone/清理通过。Probe 代码只为未来获准 host 能力准备，未跑
  的测试计划不是证据。设备已 shutdown，应用已停止，未操作其他 owner 模拟器。
- 注入测试首次因 throwing #require 写法编译失败，拆开结果后通过；初始 SwiftUI
  harness 的宏编译失败，改为无宏 UIKit harness 后编译/启动通过。未降低断言。

原 AUTH/SDK/JWT 测试证据复用，本轮没有修改那些源码/后端或重跑无关套件。
剩余：正式恢复策略、host entitlement/应用私有组验证、SDK 接线、真机锁屏/备份/
真实账号/资格。没有业务权限 grant、外部账户/云操作或完整 Issue #8 验收声明。
