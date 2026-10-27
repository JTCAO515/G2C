# CJ-035 当前需求评估宿主：作者局部证据

> 本文保留 c57e78d 原16场景历史证据。最新 Observation P2 返修见 [OBSERVATION-P2.md](OBSERVATION-P2.md)；客户端独立 P2 仍 HOLD，不能以本宿主修复放行完整 App。

固定源码 `ce7dd19880dffd7bc281ebb415ea71f3b4c8cd57`，base
`b66b0c487a54f519f7b6a7f661171705b634e717`。最终候选 HEAD 是只新增本目录证据的后续提交。
root `<local>/Documents/Codex/2026-10-21/cj-035-feasibility-shell`，
branch `cj/035-feasibility-shell`。Main 的 HANDOFF 和 Issue18/7 已读，只读未改。

## 接线与安全边界

实际源码层级：已有 NEEDS 详情 `NeedsContainerView` → 显式打开评估区
`FeasibilityHostView` → 原包 `FeasibilityView` / `FeasibilityModel`。
打开只捕获已有 `NeedsPresentation.state == .loaded` 的 accepted current snapshot，
以及 canonical NeedsBinding、SessionOperation、Shell generation/container 身份。
捕获 needs_id/version 和原 `content_utf8_base64` 解码 bytes 的 SHA256；从不重编码 fields。
草稿、历史修订、动作回执不是当前评估来源。入口缺来源时禁用并显示双语原因；
当前来源 ID、修订、hash 可见。整体待核实、局部 CONFLICT/UNKNOWN/缺依据说明复用原 View，
不复制 solver、JSON parser 或网络，不产生可行性、写入或保存权限。

**硬关闭**：宿主仅调用原客户端公开 `init(session:currentBinding:)`，没有 endpoint、
credentials、transport、allow flag、内部 FEAS test constructor 或 root factory 变更。
点击原评估按钮仍为 unavailable，不能发送 FEAS 请求。

每次打开分配唯一呈现 UUID；刷新/读取历史版本/有效 query/显式失效撤销评估。
Shell 原有 identity/background hooks 继续进入同一 NeedsContainerHost.invalidate。
current callback、SessionOperation 和 Shell generation 在展示/原客户端回调边界重新核对。
离开 NEEDS 撤销本次评估但保留原需求/编辑；旧 container / evaluation ID 的迟到退出
不清新呈现。重入尝试 epoch 防止旧打开覆盖同步产生的新呈现。
canonical host 仍须在 selection/account/environment/session 变更前同步 invalidate 并生成新 selection，
本任务没有创建第二身份来源；不把 getter 的隐藏行为当远端登出或授权。

## 固定输入与验证图

[inputs.json](inputs.json) 记录 Git 原 blob SHA256、准备图的限定调整及 Harness hash：

- FEAS 客户端 `c607358dc8475a1fdcc90d05ad47ef8450503a04`，测试源0c917f；仅只读导出。
- NEEDS consumer `e03da1b2f1c22a28da5b8c9110166108a44af936`，仅只读导出。
- Shared `9b4852dfad418d124d60366ada8efb380a8ffc1d`；Auth 为产品 base 的固定 blob。
- 唯一 SDK `dc29bb3634e63d8f065c38d39a7a0059f76cfa53`，链接原 shared owner 导出；
  全16文件同时核 shared manifest 和官方 root Git blob，未复制第二 SDK。

`prepare_feasibility_host.py` 只写本证据目录的 inputs.json 与 `.prepare`，不写 peer。
局部 Harness 编译实际三个宿主源文件、固定 NEEDS/FEAS/Shared/Auth。
**ShellFacts.swift 是明确 synthetic 的最小 ShellState/Language/Generation**，用于驱动局部状态，
不是实际完整 ShellState 运行。Harness 自有 NEEDS manifest 仅在 `.prepare` 将旧20aa路径
替换为单dc29；原 NEEDS/peer manifests 完全未改，不能视为已接受正式 cohost pin。
[package-graph.json](package-graph.json) / [graph-check.json](graph-check.json) 证明本局部图只有一个逻辑/物理 SDK。

## 实际结果

- PASS：7 Swift Testing 函数、16展开场景，见 [tests-final.log](tests-final.log)。
  原 bytes/分解Unicode/十进制尾零 hash，缺来源，刷新/历史读取/背景/离场/身份撤销，
  account/environment/selection/session/shell 变更，A→B→同源重开/旧退出/迟到取消，
  current callback 同步重入与刷新，未保存编辑不替代来源；离场不清旧 NEEDS snapshot。
  仅 NEEDS 合成 transport 返回 fixture；FEAS 始终使用公开关闭 Model，FEAS 请求0。
- PASS：普通 import 宿主公开 API typecheck，[PublicAPI.swift](PublicAPI.swift)、[public-api.log](public-api.log)。
  原客户端47场景、公开 API 硬关闭/单构造/内部 seam 隐藏证据复用其固定 candidate，不全重跑。
- PASS：Xcode27.1 / Swift6.4，generic iOS Simulator arm64 与 x86_64 编译，
  iOS17 deployment、CODE_SIGNING_ALLOWED=NO，见 [ios-build.log](ios-build.log)。实际两个 View 均编译。
  这是 synthetic ShellFacts 局部图的静态编译，不是模拟器运行、完整 Shell 或 App build。
- PASS：源码/输入 hash、独占路径和 git diff --check。

首次测试编译因 #expect 中直接嵌套带 callback 的 initializer 触发 Swift 宏诊断失败，
改为显式局部绑定；第二次夹具准备刷新后未 perform 导致 busy，改为执行捕获的原 work。
[tests-first.log](tests-first.log)、[tests.log](tests.log) 保留原失败；没有删产品断言凑绿。

命令（repo root）：

```sh
python3 scripts/prepare_feasibility_host.py
swift test --package-path contracts/ui/evidence/feasibility-host/.prepare/Modules/CJShell --force-resolved-versions --skip-update
swift package --package-path contracts/ui/evidence/feasibility-host/.prepare/Modules/CJShell show-dependencies --format json
xcrun swiftc -swift-version 6 -typecheck -I contracts/ui/evidence/feasibility-host/.prepare/Modules/CJShell/.build/out/Products/Debug contracts/ui/evidence/feasibility-host/PublicAPI.swift
```

从 `.prepare/Modules/CJShell`：

```sh
xcodebuild -scheme CJShell -destination 'generic/platform=iOS Simulator' -derivedDataPath .build/ios -clonedSourcePackagesDirPath .build/ios-packages -disableAutomaticPackageResolution CODE_SIGNING_ALLOWED=NO build
```

## 仍由原 owners/Main 收口

本产品 base 的 Shell/App 原20aa SDK 及旧 isolated-f87图未统一。Shell manifest 只新增 FEAS
包/product 行，正常 sibling FEAS 模块尚须由 Publish 串行纳入；旧 isolated snapshot 也尚无该包。
因此本树未准备的完整图缺 FEAS sibling，且纳入后仍需原 owners 统一 SDK/cohost pin 与兼容。
本任务不修改 peer manifests、不强迁 App SDK、不创建 typealias/第二 SDK，也不宣称原App可构建。

原 CJ019 memory-shell 与 CJ006 fixed 门证据未失效重跑；本次未改 Memory host/ShellState/
Auth/root/peer sources。独立 Review/Testing、正式 cohost 接受、完整 Shell/App graph/实际 root
当前选择与 session callback 组合、真实来源/路线和 Issue18 I 前置仍须完成。
仅之后按原门明确实现/审阅生产 activation；现公开关闭路径继续保留。

UNRUN：真实 HTTP/路线/provider/模型、Keychain、设备/模拟器运行、DB/权限、资源创建、安装、
部署、发布、CI、远端 push/PR/merge、真实双语/VoiceOver 与完整 App E2E；Issue18/7 未关闭。
未发送外部消息，由 Main 官方读取固定报告。
