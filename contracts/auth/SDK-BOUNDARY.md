# 邮箱 / Google / Apple 本地接入准备

用户新增范围由 Main 转交，来源 `Sentinel_071cce814e488191a43ec291abbcc680`：
可新建 Supabase 或使用 VP-V4，最好加入 Google/Apple；用户不在电脑，需要其操作
的步骤先跳过。本轮优先新独立环境，不采用旧凭据/用户/安全设置，不创建收费资源。
原 d27c23c 的规范子候选完整保留；新增入口不把 Google/Apple 身份当作邀请资格。

本轮实现：[CJAuth](../../ios/Modules/CJAuth/README.md)，独立 Swift 包，
仅流程/回调相关性与明确不可用的 SDK 边界；没有 UI 按钮或实际 SDK adapter。
这不是正式 wire，也不改变唯一 OpenAPI、CJShell、根 iOS 工程、backend 或 RLS。

## 官方 SDK 边界核对（2026-10-21）

官方 [Swift 邮箱密码登录](https://supabase.com/docs/reference/swift/auth-signinwithpassword)
使用 SDK auth 登录入口。官方 [Swift 原生 ID token 登录](https://supabase.com/docs/reference/swift/auth-signinwithidtoken)
展示 Apple ID token 与 nonce 的交换，说明真实 token/nonce 必须由实际流程提供，
不能从本包 attempt UUID 推导。官方 [Apple 登录指南](https://supabase.com/docs/guides/auth/social-login/auth-apple)
作为后续能力与配置核对入口；本轮不配置控制台，也不复制示例凭据。
Google 原生/网页流程及回调方式尚未选定，本包仅区分 provider 和用途，不猜 SDK 签名。

[官方 changelog](https://supabase.com/changelog)已只读扫描；changelog.md 被工具以
content-type 拒绝，改读 HTML。OAuth Swift 页面首次超时、Markdown 路径不可访问，
没有借此猜 SDK API。未安装 SDK，无特定版本兼容结论；实际 adapter 前必须核
固定 SDK 版本与相关 breaking changes、邮件/回调限制。本地流程代码无 SDK 调用。

## adapter/host 后续义务

- 安全输入和官方 SDK 拥有密码、token、会话存储；host 不把完整回调 URL 送日志。
  secret/service-role 不能进 App；用户可编辑 metadata 不作为邀请依据。
- 回调必须由官方 SDK 验证环境/目标、原 provider/用途与 state/nonce/PKCE 等适用
  校验，再关联原 attempt；本包只拒绝不属于当前 attempt 的事件，不验证 OAuth。
- 邮箱注册受理不代表邮件送达；Google/Apple 身份可用仍停留待服务端验证。
  当前有效 principal、邮箱/邀请判断和资源权限仍属于服务端 AUTH 未完成接缝。
- 用户取消必须调用 cancel(originalAttempt)；后台 task 终止不证明远端撤销。
  logout/switch/新身份生命周期由 host 先失效旧 AUTH 与 UI generation 再开始新工作。
  需要 Main 另分共享 host lease 后接入，不抢写 CJShell 或根工程。
- 流程核心不会保存身份/私有正文；完整凭据清理、外部缓存、UI、远端撤销、
  邮件重试与密码恢复仍由未来实现提供分层证据，不能被本地测试代替。

## 用户不在电脑期间已跳过并登记

| 待办 | 所需信息/操作与 owner | 本轮结果 |
|---|---|---|
| 新独立 Supabase 目标 | JT/CJ005 明确组织、地域、项目、套餐与预算；涉及费用不创建 | SKIP，未创建/改旧项目 |
| 邮箱发信/验证恢复 | JT/CJ005/CJ007 的发信身份、服务、语言、回调与真实送达 | SKIP，无邮件发送/秘密 |
| Google 配置 | JT 的官方控制台授权、具体 client IDs/允许回调与所选 native/web 方式 | SKIP，入口不可用 |
| Apple 配置 | JT 的 Apple 能力/应用身份、控制台授权与所选流程所需配置 | SKIP，入口不可用 |
| iOS host 注册 | Main 分共享工程 lease；应用标识、URL/universal link、能力与 SDK UI 生命周期 | PENDING，仅独立包 |
| SDK 版本与真实 adapter | CJ007 按实际环境固定官方版本/锁并实现安全回调 | PENDING，未安装依赖 |
| 服务端邀请/身份 | CJ007/CJ005 定验证、绑定、撤销与正式 API，消费确认后接入 | PENDING，无正式权限出口 |

无需现在让用户操作或粘贴秘密。可编译本地流程候选先独立审验，真实步骤留后续
授权与人在场时完成；环境许可不自动表示已选中 VP-V4 或批准更改旧安全设置。
