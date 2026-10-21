# CJ007 对 UI@1.0 候选的历史消费确认

当前 UI@1.1 差额结论见 [UI-1.1-CONSUMPTION](UI-1.1-CONSUMPTION.md)。
下文只对应 e722bef，不将其源码事实或缺口原样套用于新版本。

只读源：`cj-006-ui`，固定 commit
`e722befc9adf53e07dfb508198ff49710ab91b01`，不使用移动 HEAD。
AUTH 对照：`c9f99bab68b254fb5fd574ec2e05766a6279cedc` 的 AUTH-draft.1。
这是 CJ007 消费方的契约兼容核对，不代替独立 Review/Testing，也不冻结 UI/AUTH。

核对来源均取自固定 commit：`contracts/ui/README.md`、`examples.json`、
`ios/Modules/CJShell/Sources/CJShell/{ShellState,MemoryShell,ShellView}.swift`、
`ios/Modules/CJShell/Tests/CJShellTests/ShellStateTests.swift`。

| 接缝 | 固定源码事实 | CJ007 结论 |
|---|---|---|
| 记忆内账号入口 | 四 Tab 不含 account；MemoryRoute.account 经 MemoryShell 的记忆导航进入；内容明确尚未接入 | PASS，接受此入口位置；不把占位文案当登录状态 |
| 语言不改变会话 | selectLanguage 只更新本地语言偏好及警告；ShellView 以 locale 更新显示，无 language-based id；已有语言保留导航/草稿/引用测试源码 | PASS，语义兼容；未来 host 必须保留同一身份生命周期，实际 Auth 联动 UNRUN |
| 代次失效清理 | ShellState 无身份/代次与清理 hook；draft、context、memoryPath、页面状态须由 host 处理；assistantBody 是 ShellView 外部传入值 | GAP，正式消费前必须由 host adapter 清理并核绑定；当前 UI 明确未声称已实现，无需本轮越界修改 UI |
| 网络 unknown | ShellPageState 为展示枚举，unknown/offline/failed 都不验证身份；账号仍为 not connected；无 Auth adapter | PASS，语义不冲突；映射实现 PENDING，不能据页面 failed/unknown 登出或删除凭据 |

## 最小 AUTH 草案补充

- 语言变更只改变 UI 文案，不启动登录/退出/刷新、不轮换 client generation，
  不重建身份 host。语言保留私有状态的规则仅适用于**同一身份代次**，不能用于
  退出/切号时保留旧草稿或旧上下文。
- 身份代次失效时，host 在同一 MainActor 更新段中先关闭旧绑定的渲染与回写，
  清空 ShellState.draft、context 的两个引用、memoryPath，以及外部 assistantBody；
  assistant/trips/memory 页面重置为 notConnected。保留语言偏好；selectedTab 可保留，
  但不得保留旧私有路由/正文。清理不意味着远端任务已取消或数据已删除。
- 先失效旧绑定，再清理展示，然后允许新身份验证；每次 await 后重新检查
  instance/generation/principal/session revision。主线程隔离本身不保证晚到安全。
- ShellPageState 不与 AUTH 状态一一对应。网络/依赖未知不得生成权威 invalid，
  不得删除有效凭据或凭展示状态授予业务权限。账号状态由未来域 adapter 提供。
- AUTH 模型的 visible 列表只证明抽象显示屏障；它未覆盖真实 ShellState 和
  assistantBody 清理。新增合成反例明确检出这些清理遗漏，不能据此称 UI 已修复。

责任接缝：CJ006 确认上述 host 展示清理与入口；CJ007 提供绑定/失效语义及
未来正式验证结果；CJ005 确认统一来源与 C2；实际集成 host 的文件写权由 Main
分配后实施。当前不添加 Swift adapter、API 或正式错误枚举。

## 兼容检查与剩余门槛

`python3 -B contracts/auth/check_ui.py`：4 项离线合成测试，覆盖正确/错误入口、
语言导致会话/导航变化、五类私有展示清理遗漏、晚到，以及网络未知不能伪装失效。
检查是对**所需接缝规则**的正负样例，不执行 Swift，也不自动读取或验证 UI 源码。
UI 固定源码事实由上述只读核对取得；未复跑 CJ006 Swift 测试/构建。

本次运行 Python 3.9.6：4/4 PASS。原 AUTH 模型未改，原 12 项证据复用。

CJ007 确认 UI 候选的入口/语言/展示非授权语义可供草案设计消费；不作完整
UI@1.0/AUTH@1.0 冻结确认。身份清理 adapter、双方最终映射确认仍 PENDING。
正式登录方式、受邀政策、C2 环境未定；真实登录/API/数据库隔离、SDK 生命周期、
真机、部署 UNRUN。Issue #8 不关闭。
