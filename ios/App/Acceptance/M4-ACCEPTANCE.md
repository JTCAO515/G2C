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

当前业务宿主依仓库既定边界只在 DEBUG Simulator 编译，且仅接受显式 IPv4 loopback。
#495 的 Apple Developer/设备/分发授权之外，实际全流程真机还需批准设备可达的
测试服务与 App 身份/鉴权接线；在该授权和接线完成前，正式配置只显示未配置 shell，
不能把编译、手工步骤或模拟器 PASS 当作可用真机业务包。此处不放宽这些边界。
真机自动化执行和 VoiceOver 保持 #29 UNRUN，TestFlight 保持 #33 UNRUN。

## #4 的候选矩阵

包版本以当前锁文件为准；Swift OpenAPI Generator 的真实生成与结构化错误/流式
消费使用既有生成检查及领域用例。当前产品用原生 RunReadableText/RunSelectableText，
不引入 Textual；历史 Textual 原型不等于产品依赖。中英长文、链接、选择、滚动、
最大字号和无脚本执行分别由 structure/accessibility 与领域实际页面验证。
最低 iOS17 和当前安装 runtime 分开记录；iOS17.5 不冒称 iOS17.0 或真机已验证。
远程图像/未许可链接遵守现有呈现与显式 Link 行为，不新增自动抓取/预览服务。
