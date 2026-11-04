# M4 App 中英验收（#498，承接 #4 模拟器部分）

`check_m4_app.py` 复用已有领域验收 seam，把登录→规划→接受→修改→记忆管理→
反馈→注销及离线、语言、时区、最大字号与完整 AX 汇成一个必过矩阵。
各切片独立建私有 PG、签名本地 API、受限 `cj_m1_runtime` 和 FakeProvider；
切片的测试账号不同，不将其描述为同一账号的一次连续端到端运行。

从已提交且干净的候选运行，使用显式 `CJ-LOCAL-RUN@2` 配置，当前周期覆盖
执行时间，budget16、max_steps8、max_tools1、max_output16000、max_seconds600、
output_limits 的 model/tool/memory 各4000。候选与删除验收分别要求预算2和4；
驱动只在新空库初始化对应 profile，不重置旧账本。不用真实模型、OTP 或云。

```sh
CJ_PG_BINDIR='<PostgreSQL-17-bin>' uv run --locked python -B \
  ios/App/Acceptance/check_m4_app.py --simulator '<iOS-17.5-UDID>' \
  --run-context '<explicit-context.json>' --output '<new-external-directory>' \
  --build-dir '<external-build-cache>'
```

20 项均完成才可记本矩阵 PASS。每个原生 case 保留原脚本的全套断言、
`.all` AX 审计、native summary 零失败/零跳过、服务端与受限 PG 证明。
`--step` 仅用于诊断，成功仍为 PARTIAL_PASS；未执行项仍是 UNRUN。
子脚本对其未覆盖旧矩阵的 PARTIAL_PASS 原样保存，不将其改称原领域全量通过。
OS_ACTIVITY_MODE 始终为 disable；继续复用按 identifier 和控件类型定位的测试。
历史 FAIL、日志和 xcresult 不覆盖；证据在仓库外，以 report 的 head 为准。

| 顺序 / 路径 | 本机原生用例 | 真机按同一路径执行的关键动作 |
|---|---|---|
| 登录 | accounts | 记忆→账号→明确登录/恢复；换号、退出与迟到响应隔离 |
| 需求与时区 | needs-en/zh、timezones | 助手→需求→手工核对；切语言/时区后原日期、币种和数值不变 |
| 规划接受 | plan-accept | 明确旅行与需求→发送规划→读取候选→审阅→明确采用→原回执和正式 v1 |
| 修改 | manual-edit | 行程→正式详情→选标题→编辑→准备 diff→保存→正式 v2；重启核原动作 |
| 记忆 | typed-en/zh、manage-en/zh | 记忆→新增/已读页→条目→编辑、暂停/恢复和停止使用；对象/范围明确 |
| 候选与删除 | candidate-en/zh、erase-en/zh | 默认关闭→逐会话开启→编辑确认候选；停止使用与物理清理分别观察 |
| 反馈 | feedback-en/zh | 回答→反馈，关联默认关闭；记忆根页 general refs=[]；核原回执 |
| 离线 | offline | 成功正式同步→离线只读出示→语言切换/重启；保留中国当地时间 |
| 注销 | account-cleanup | 记忆→账号→注销说明→明确确认→原进度/设备完成；另一账号不变 |
| 结构与 AX | structure、accessibility | 四 Tab、占位插件、帮助/隐私、长正文/选择/键盘、最大字号、安全区 |

## 构建身份与签名

- `CJProbeApp` 的 Debug/Release 保持 `space.go2china.foundation.local`，现有外部验收
  工程仍使用各自 `*.acceptance` ID 与 Keychain 域。Release 是历史开发隔离变体。
- `G2CProduction` scheme 的 Production 配置使用 `space.go2china.app`，不定义 DEBUG，
  不含开发 entitlement；默认禁止签名。它只是可编译的正式身份配置，不表示
  App 已接真实后端、可内测、已签名或可发布。
- `Signing.xcconfig.example` 只列占位字段；#495 提供批准的团队、证书/profile 与设备后，
  在忽略的本地目录配置。不把证书、profile 或秘密写进 Git/PR。

## 真机执行准备与明确的剩余依赖

[DEVICE-RECORD](DEVICE-RECORD.md) 可直接复制执行两种语言和两种字号的手工路径，
记录机型、系统、网络、VoiceOver、失败与回归。XCTest 的语义动作/定位符和
上述业务断言与设备无关；当前 Python fixture 驱动仍是模拟器驱动，**不能直接把
`--simulator` 换成设备 ID**。

普通业务宿主继续只在 DEBUG Simulator 编译。M4 条目 1、2 已批准指定 iPhone 的
开发签名、高德只读展示与合成账号测试；显式本地设备配置可用
`G2C_M4_DEVICE_ACCEPTANCE` 编译业务宿主，再以 `G2C_M4_LOCAL_HOST` 指定一个
RFC1918/link-local IPv4 开发机地址及显式端口。现有签名 API、身份隔离、原动作和
路由限制不变。Release/Production 不编译该接线，也不含本地网络 ATS 放行。
具体 SDK、Bundle ID、Key 与网络步骤见 [M4-AMAP-LOCAL](M4-AMAP-LOCAL.md)。
JT 通知连接设备后才执行签名、安装和验收；编译、手工步骤和模拟器 PASS 均不计
真机 PASS。真机自动化及 VoiceOver 保持 #29 UNRUN，TestFlight 保持 #33 UNRUN。

## #4 的候选矩阵

包版本以当前锁文件为准；Swift OpenAPI Generator 的真实生成与结构化错误/流式
消费使用既有生成检查及领域用例。当前产品用原生 RunReadableText/RunSelectableText，
不引入 Textual；历史 Textual 原型不等于产品依赖。中英长文、链接、选择、滚动、
最大字号和无脚本执行分别由 structure/accessibility 与领域实际页面验证。
最低 iOS17 和当前安装 runtime 分开记录；iOS17.5 不冒称 iOS17.0 或真机已验证。
远程图像/未许可链接遵守现有呈现与显式 Link 行为，不新增自动抓取/预览服务。

2026-11-04 本机补验原 CJ004 Textual0.5.0 原型：Xcode27.2/iOS18.0 首次启动
FAIL，dyld 缺少 `libswiftCompatibilitySpan.dylib`。使用以下本地构建参数后实际
启动、中英混排/列表、长按中文选择菜单和原 `--large-type` 样例可见：

```sh
xcodebuild -project spikes/ios/CJIOSSpike.xcodeproj -scheme CJIOSSpike \
  -destination 'platform=iOS Simulator,id=<iOS18-UDID>' \
  -derivedDataPath '<external-directory>' CODE_SIGNING_ALLOWED=NO \
  ALWAYS_EMBED_SWIFT_STANDARD_LIBRARIES=YES \
  'LD_RUNPATH_SEARCH_PATHS=$(inherited) @executable_path/Frameworks' build
```

这是本地工具链接线，未修改 `spikes/**` 或换依赖；原崩溃记录保留。该观察不含
新 FPS/性能结论、全交互或 VoiceOver 证明，产品仍采用原生文本组件。
