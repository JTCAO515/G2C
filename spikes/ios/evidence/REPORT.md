# CJ-004 本地选型段交付

最新性能补验见 [post-P2 报告](performance-post-p2/REPORT.md)。

最新定向差额见 [P2-LIFECYCLE.md](resume/P2-LIFECYCLE.md) 与 [恢复补验](resume/SUPPLEMENT.md)；下文保留1dd735e候选的原始结论，不能覆盖新差额。

状态：**LOCAL CANDIDATE / code-ready，保留验收缺口；不关闭 Issue #4**。2026-10-21，北京时间。作者自测，不冒充独立 Review/Testing。

- base：`13905e4587feb8611ebde5e3621024f3338532ae`
- 代码与原始证据固定 head：`0eb447f93041444ce491678f559fbb72041acd29`；后续报告提交只改本文。
- 分支 `cj/004-ios`；remote `https://github.com/JTCAO515/Go2China.git`。
- 工作树 `/Users/jtsm5p/Documents/Codex/2026-10-21/cj-004-ios`，独立 clone；初始目录不存在，原 task-4 仓库只读。全部 delta 位于 `spikes/ios/**`，无共享工程/HANDOFF/原13文档/Issue 改动，无 push/merge/deploy。
- 模型 requested：UNKNOWN（工程文档执行默认偏好 gpt-6.1-sol/medium，不是配置回执）；accepted/effective：UNKNOWN。

## 采用/替换结论

官方 Auth 与 OpenAPI/URLSession 组合可继续作为候选：真实固定包已解析、编译，C0 生成消费者与流中断负例有本地证据。Auth 仅编译 signIn 方法，未构建实际 AuthClient、未保存 Keychain/会话、未登录；URLSessionTransport 仅构造/编译，没有真实 HTTP 请求。不能据此宣称认证/网络链路可用。

Textual **有条件保留为 iOS 18+ 渲染候选**：iOS26.5 已实际呈现中文地点、英文长段、列表、链接样式、图片占位与文本选择菜单。若 CJ-001 选择 iOS16/17，替换此独立渲染层；原生基线当前是可运行纯文本，并非同等 Markdown/链接替代品。不得为了 Textual 提高产品最低系统。本段没有最终采用栈或最低系统决策权。

固定版本/最低系统/工具链/许可及官方链接见 [SOURCES.md](SOURCES.md)，相邻 tagged manifest 与根/工程/消费者锁可核验。组合要求 Swift tools >=6.2；Textual 样例部署18.0，原生对照17.0。最低 manifest 声明不等于对应最低版本已运行。

## 实际环境和执行

Xcode 27.1 / 27A9275；Apple Swift6.4 / swiftlang-6.4.0.34.1；macOS arm64；构建 SDK iPhoneSimulator27.1。仅两个 CJ004 自建独立设备：

| 设备 | UDID | 实际运行系统 / 内容 |
|---|---|---|
| CJ004-iOS26-20261021，iPhone17 Pro | B80AD40D-F779-4FE3-A36D-CFD4C4A19D83 | iOS26.5；Textual + Auth/OpenAPI 编译链接 |
| CJ004-iOS17-20261021，iPhone15 Pro | 067D1D66-39AC-4DF2-960D-7031B4EE5A44 | iOS17.5；相同页面结构，原生纯文本，无第三方依赖 |

没有 iOS18 runtime 实测；未启动/更改其他 owner 设备。MCP 仅新增 `cj004-ios`、`cj004-native17` 自有 profile，原 default 保留。依赖、锁、源码样例、DerivedData/缓存/生成快照均在分配子目录；未安装全局工具。

| 层与场景 | 结果 | 可复核证据与限制 |
|---|---|---|
| 固定包解析、host 构建 | PASS | resolve-isolated.log、build-host.log.gz；首次沙箱默认 module cache 失败保留 resolve.log/test-first.log，之后改用任务内 cache |
| Textual 完整 iOS 工程构建 | PASS | build-simulator-delivery.log.gz |
| 原生 iOS17 工程构建 | PASS | build-native-delivery.log.gz；不证明 SDK 在17的运行 |
| SSE-only 生成消费者 | PASS | tests-sse-final.log，5项：正常终止、EOF、空流、body传输抛错、取消；均为内存 transport |
| 固定 C0 正式消费者 | PASS | C0-CONSUMER.md、c0-source.json、c0-tests-final.log；5 tests，invalid-body含3个参数用例：必填字段缺失、坏JSON、未知枚举；另有正常、unknown/conflict、必填header缺失 |
| 中英长文本/列表/链接样式 | PASS（被测画面） | ios26-final-default.png、ios26-verified-stream-keyboard.png；原生对照 ios17-default.png 显示原始Markdown |
| Textual 文字选择 | PASS（菜单出现） | ios26-selection.png，长按出现 Copy/Share；未执行复制/分享。后续仅焦点时序/裁剪和探针按钮改动，选择组件未变，复用该证据 |
| 局部悬浮/系统安全区 | PASS（被测画面） | 双横线原无效符号已修复；长文本曾进入状态栏，修正后 ios26-verified-stream-keyboard.png 显示系统栏清晰。正文仍能经过局部悬浮区域；首段有足够顶部空间 |
| 增量文本与滚动 | PASS（局部） | ui26-stream-complete.json：3960字符/50更新/5.198340542秒；修正状态栏后 ui26-verified-stream-keyboard.json：5.365518041秒。拖动出现Follow latest。固定同一消息identity，按字符片段只附加一次；6次重复文本是显式fixture，不是重复事件 |
| 帧性能、滚动位置量化、实际网络SSE | UNRUN | 插入耗时包含100ms人工间隔，不能当FPS/布局/网络延迟；未做 Instruments。持续拖动与增量同时发生的精确位置保持仍需独立验证 |
| 大字 | PASS（启动/被测布局）；完整交互UNKNOWN | Textual accessibility3：ios26-verified-large-keyboard.png；原生：ios17-launch-large-keyboard.png。采用本地启动参数和内部toggle，不冒系统设置完整验收 |
| 键盘/焦点 | UNKNOWN（未完整通过） | 最终 ios26-delivery-keyboard.png 可见光标，软件键盘未稳定出现；iOS17启动模式实际弹出系统键盘，但首次滑行输入引导遮住部分输入区，自动Continue回执后画面未变。保留ui17-launch-large-keyboard.json。未改共享键盘偏好。文件名含keyboard仅说明尝试场景，不代表PASS |
| 原生17选择/按钮点击 | UNKNOWN | 长按/切换工具报告成功但画面未改变；ios17-selection.png/ios17-large.png 是尝试记录，不能当选择/大字切换成功 |
| VoiceOver | UNRUN | AX树有控件标签/正文不等于真实读屏、阅读顺序或可用性验收 |
| 网络/脚本/隐私 | 源码边界PASS；动态网络审计UNRUN | 所有openURL均本地notice；覆盖Textual默认远程图片/emoji loader，只返回本地占位；无WebView/脚本执行/预览器；脚本fixture显示字面文本。未实际执行外链，未做抓包 |
| 真实Auth/服务/数据库/真机/CI/发布 | UNRUN | 无真实账号、凭据、旧数据、模型或外部服务调用；无部署或独立验收结论 |

完整构建日志经无损 gzip 保留，原始 SHA-256 与 gzip 路径见 build-log-hashes.json。早期 screenshots / tests.log / tests-final.log 保留诊断历史，不能覆盖最终行的结果；最终临时schema已删除JSON endpoints，只剩SSE。所有截图均模拟器，不是真机。

## C0 消费边界和退出条件

从 CJ-005 **固定** commit `db9c040f262032acaf5375db43d7169b3217e504` 读取 `contracts/api/openapi.json` 与已发布样例，重新生成客户端；不读移动工作树文件。正式schema只提取到忽略 `.cache/c0-consumer`，不在本仓库提交第二份正式来源；脚本记录SHA并检查runtime锁。消费确认只覆盖BASE@1.0 probe/error/request_id，不表示CJ-005独立验收通过。

`Sources/SpikeClient/openapi.yaml` 是仅SSE的临时探针，`[DONE]`仅本地EOF判别用例，不建议作为产品RUN协议。RUN/SSE发布后删除此临时schema和标记，产品只消费正式C0/RUN来源。Auth会话、终态恢复、事件顺序/去重、跨账号late result均不凭临时样例冻结。

## 下一步/停止边界

本段交 Review/Testing 检查固定候选；CJ-001拿manifest与实测矩阵决定最低系统。仍需补：候选最低runtime、VoiceOver、完整键盘/选择/增量拖动组合及必要帧测量。真实Auth/服务/真机仍须相应授权与新环境，不使用旧凭据。无 push/合并/发布，Issue保持未关闭。作者完成本段后等待，不扩大到产品UI/API实现。

跨聊天状态发送被自动审批拒绝，理由是可信用户内容未明确授权向Main聊天发送；没有重试/绕行。Main随后明确会只读本聊天收取结果，因此报告留本聊天与任务目录，不需要为回报额外请求授权。
