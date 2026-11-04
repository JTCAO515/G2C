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
上述业务断言与设备无关。总矩阵 `check_m4_app.py` 仍是模拟器入口，**不能直接把
`--simulator` 换成设备 ID**；已接通的领域设备入口分别记录如下，不冒称整个矩阵已就绪。

普通业务宿主继续只在 DEBUG Simulator 编译。M4 条目 1、2 已批准指定 iPhone 的
开发签名、高德只读展示与合成账号测试；显式本地设备配置可用
`G2C_M4_DEVICE_ACCEPTANCE` 编译业务宿主，再以 `G2C_M4_LOCAL_HOST` 指定一个
RFC1918/link-local IPv4 开发机地址及显式端口。现有签名 API、身份隔离、原动作和
路由限制不变。Release/Production 不编译该接线，也不含本地网络 ATS 放行。
具体 SDK、Bundle ID、Key 与网络步骤见 [M4-AMAP-LOCAL](M4-AMAP-LOCAL.md)。
JT 通知连接设备后才执行签名、安装和验收；编译、手工步骤和模拟器 PASS 均不计
真机 PASS。真机自动化及 VoiceOver 保持 #29 UNRUN，TestFlight 保持 #33 UNRUN。

### 登录领域的指定真机入口

`check_development_accounts.py` 支持指定设备及本轮获准的本机 TLS profile：

```sh
CJ_PG_BINDIR='<PostgreSQL-17-bin>' uv run --locked python -B \
  ios/App/Acceptance/check_development_accounts.py --device '<approved-iPhone-UDID>' \
  --local-tls '<approved-external-profile/operator.json>' \
  --output '<new-external-directory>' --build-dir '<external-build-cache>'
```

`--prepare-only` 只做 Debug/Release 的 `build-for-testing`，不安装或启动设备；结果为
`PREPARED_EXECUTION_UNRUN`，全部原生用例仍为 UNRUN，总矩阵不得接受它为 PASS。
实际执行保留中英登录、拒绝/过期/离线、退出、显式恢复和迟到账号隔离的六个
Debug 用例，以及原 Release 不接业务后端的独立用例，不删除或放宽断言。

设备测试控制进程使用固定叶证书的 HTTPS 和每轮控制令牌；未认证请求先拒绝，
包括每次 App 重启前的一次性输入暂存。测试账号不放入设备 XCTest 启动环境；
Mac 临时源用后删除，App 读自身 Caches 固定文件后立即删除，失败仍核对并清理
精确输入。Release 产品不含本地公钥或 ATS 放行，也不编译业务接线；独立测试
控制进程仍使用自己的本地调试连接。Release 忽略输入的检查结束后，用同轮已签名
Debug 包的专用丢弃入口回收这一个输入，再扫描 App 文件，不清业务日志或其他数据。

构建与测试原包在私有隔离目录，不可直接分享；只导出通过凭据扫描的限定文本。
凭据清理、服务/私有 PG 停止及源码/head 核对完成后才写终态。指定设备离线时可先
构建，设备实际执行、系统最大字号和 VoiceOver 仍须分别记录，不能由构建替代。

### 需求领域的指定真机入口

`check_needs.py` 同样支持 `--device`、`--local-tls` 和 `--prepare-only`，继续要求
显式 `--run-context`。可按原 `--case` 选择中英、原动作恢复、账号迟到、进程时区或
Release 关闭用例；不改变原签名 API、受限 PG、正式 NEEDS worker 和后端证明。
一次性凭据只允许为已 prepare 的当前 case 暂存；不能把其他 case 的输入注入 App。

```sh
CJ_PG_BINDIR='<PostgreSQL-17-bin>' uv run --locked python -B \
  ios/App/Acceptance/check_needs.py --device '<approved-iPhone-UDID>' \
  --local-tls '<approved-external-profile/operator.json>' \
  --run-context '<explicit-context.json>' --case testEnglish \
  --output '<new-external-directory>' --build-dir '<external-build-cache>'
```

设备 `testChineseLarge` 不设置字号启动覆盖，先核对 Runner 的有效字号为最大
无障碍字号；实际系统设置与 App 显示的记录仍需填 DEVICE-RECORD，单个 Runner
读数不单独证明产品最大字号已验收。模拟器保留原字号参数与完整 AX 断言。
`testDeviceTimezones` 仍核对 App 进程 TZ 与中国当地字段，不冒称已切换 iPhone 的
系统时区；真实系统语言/时区切换和 VoiceOver 继续在 #29 独立记录。

### 规划采用与手动修改的指定真机入口

`check_manual_trips.py` 支持同一显式设备/TLS 与 `--prepare-only`，继续要求
`--backend-root`、精确 `--backend-head` 和 `--run-context`。原始来源创建、
正式规划/采用、diff/save、原动作恢复及原后端证明保持不变，不直接写入 Trip。
设备控制的 prepare 只向本轮已安装的 App 暂存当前用例的合成账号；恢复不再次注入。

```sh
CJ_PG_BINDIR='<PostgreSQL-17-bin>' uv run --locked python -B \
  ios/App/Acceptance/check_manual_trips.py --device '<approved-iPhone-UDID>' \
  --local-tls '<approved-external-profile/operator.json>' \
  --backend-root '<pinned-checkout>' --backend-head '<full-SHA>' \
  --run-context '<explicit-context.json>' --case testNeedsPlanningAccept \
  --largest-recovery --output '<new-external-directory>' --build-dir '<external-build-cache>'
```

设备的大字号分支核对 Runner 的最大有效字号，App 不再用启动参数覆盖字号；
实际系统设置/App 显示仍需 DEVICE-RECORD，VoiceOver 不由 AX 或预编译代替。
`--prepare-only` 不取得业务运行证明，结果仍为 `PREPARED_EXECUTION_UNRUN`。
规划和停止客户端沿已有 CJMessageHTTP 依赖复用同一调试 TLS 委托；各自原有的
精确路由、身份/lease 与禁止重定向检查保留。其他领域的多端口设备接线仍待补齐，
不把本节的预编译结果当作全流程设备 PASS。

### Typed 记忆领域的指定真机入口

`check_typed_memory.py` 支持相同的设备、TLS profile 与预编译参数，保留显式
`--run-context`、原用例和真实签名生产者/受限 PG/正式 worker 证明。
主 API 与 typed 记忆 API 使用同一批准开发 Mac 的两个明确端口；App 只信任
配置列出的端口与同一叶证书，不扩大主机或系统根信任。配置缺失、重复、超范围
或未列端口不接受。设备 XCTest 环境不含账号 token，恢复不再注入输入。

```sh
CJ_PG_BINDIR='<PostgreSQL-17-bin>' uv run --locked python -B \
  ios/App/Acceptance/check_typed_memory.py --device '<approved-iPhone-UDID>' \
  --local-tls '<approved-external-profile/operator.json>' \
  --run-context '<explicit-context.json>' --case testEnglishSaveReadAndOwnedTravel \
  --output '<new-external-directory>' --build-dir '<external-build-cache>'
```

设备的并发暂停夹具使用同一 observed ASGI 签名生产者和真实 PG，App 请求仍走
实际 HTTPS；原回执/版本/跨账号检查不变。预编译不执行这些业务证明，实际真机、
系统设置记录和 VoiceOver 必须分别验收。

### 记忆管理领域的指定真机入口

`check_memory_lifecycle.py` 也支持设备/TLS profile/预编译参数及原 `--case`。
主读取与管理 API 仍使用各自正式 ASGI 生产者和签名账号，共用批准的本机证书；
App 只列出这两个明确端口。夹具预备的原始记忆仍经原签名 API 写入，设备用例
修改/暂停/恢复/停止使用及原动作、来源不变/跨账号证明不删改。

```sh
CJ_PG_BINDIR='<PostgreSQL-17-bin>' uv run --locked python -B \
  ios/App/Acceptance/check_memory_lifecycle.py --device '<approved-iPhone-UDID>' \
  --local-tls '<approved-external-profile/operator.json>' \
  --run-context '<explicit-context.json>' --case testEnglish \
  --output '<new-external-directory>' --build-dir '<external-build-cache>'
```

一次性账号输入与当前已 prepare 的 case 绑定；预编译可预备合成数据和签名包，
设备交互/文件扫描仍为 UNRUN。实际测试结束后才核 App 文件、导出凭据和服务/PG
收尾，再写终态，不能用预编译或 AX 代替完整领域、系统设置或 VoiceOver 验收。

### 候选确认领域的指定真机入口

`check_memory_candidate.py` 支持显式设备/TLS 与原后端精确 pin，仍要求预算2的
独立 `--run-context`。模拟器原有准备、标准→最大字号切换及业务断言保持原路径；
设备预编译会生成签名包，实际交互仍为 UNRUN。

设备用例全程要求实际系统最大字号；两个字号检查点均核对有效字号，不用启动
覆盖或假装切换系统设置。它证明最大字号下完整候选流程，不证明编辑过程中
切换系统字号。真实系统设置与 App 显示另记 DEVICE-RECORD。
原候选来源、单次确认/拒绝、原动作重开、原文字节和另一账号不变的证明均保留。
设备文件证明使用每次独立的私有 App 容器副本，删除后不会读到旧副本的残留文件。

### 删除领域的指定真机入口

`check_memory_erasure.py` 支持相同设备/TLS 与精确后端 pin，使用预算4的独立
`--run-context`。设备用例全程要求实际系统最大字号，模拟器标准→最大切换
继续保留；不声称设备编辑过程中已切换系统字号。
单次删除原动作、原回执、目标文件消失、其他记忆/另一账号保留，以及未知结果
重开后只核对原动作的断言不删改。设备文件证明使用每次新的私有容器副本；
预编译、模板和文件准备都不是实际删除交互 PASS。

### 反馈领域的指定真机入口

`check_feedback.py` 支持设备/TLS、精确后端 pin 与预编译参数。设备用例全程
核对实际系统最大字号，原模拟器字号切换路径保留；实际系统设置仍另记。
回答关联默认关闭、自愿填写、general refs=[]、原回执哈希、跨账号拒绝、最小
内容和真实定位符证明不删改。预编译不计业务 PASS，账号 token 不进设备启动环境；
输入清理、导出扫描、服务/PG停止及源码 pin 核对完成后才写终态。

### 离线缓存领域的指定真机入口

`check_offline_trips.py` 支持显式设备/TLS 和 `--prepare-only`，原 `--seed-only`
仍仅诊断正式来源创建。设备用例使用原签名 MESSAGE/worker/采用链和缓存读取，
不提供伪造 Trip 或缓存字节。设备文件观察经每次新的私有容器副本，不复用旧文件。

原 `/offline` 停止的是本机 API，设备版明确只证明服务不可达时的缓存路径，
不当作 Wi-Fi/飞行模式物理断网。受控时钟不当作真实经过14天，容器副本权限
不当作锁屏文件保护。实际物理断网、系统锁态、真实期限和 VoiceOver 继续在#29
记录；字体全程要求实际系统最大字号，模拟器原字号变化保留。

### 注销与结构/AX 的指定真机入口

`check_account_cleanup_component.py --device` 限定为 `--native-device --all-provided`
的 CJProbeApp 31个已提供域路径，仍要求预算4及精确后端 pin。原组件/完整阻塞
清单用例保留模拟器入口，外部处理不计完成。设备前后文件证明使用每次新的
私有容器副本，保持另一账号哈希、21个设备目标和原调用/回执检查。

`check_shell_structure.py --device` 支持 structure/accessibility/account-deletion：
普通 App 与标明合成、只读的 ShellFixtureApp 分开记录；只读夹具不冒签名业务。
夹具与控制使用批准的本机 HTTPS，控制 audit/release 要求本轮令牌；原只读接口
仍只接受标明SYNTHETIC的读取身份。设备全程要求系统最大字号，不使用夹具字号
覆盖；模拟器原路径保留。所有用例、完整.all AX及原失败断言均保留。
这些入口的 `--prepare-only` 仍全部记为 `PREPARED_EXECUTION_UNRUN`。

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
