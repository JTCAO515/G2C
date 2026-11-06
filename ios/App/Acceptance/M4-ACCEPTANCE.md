# M4 App 中英验收（#498，承接 #4 模拟器部分）

`check_m4_app.py` 复用已有领域验收 seam，把登录→规划→接受→修改→记忆管理→
反馈→注销及离线、语言、时区、系统默认字号与完整 AX 汇成一个必过矩阵。
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
| 结构与 AX | structure、accessibility | 四 Tab、占位插件、帮助/隐私、长正文/选择/键盘、默认字号、安全区 |

## 构建身份与签名

- `CJProbeApp` 的 Debug/Release 保持 `space.go2china.foundation.local`，现有外部验收
  工程仍使用各自 `*.acceptance` ID 与 Keychain 域。Release 是历史开发隔离变体。
- `G2CProduction` scheme 的 Production 配置使用 `space.go2china.app`，不定义 DEBUG，
  不含开发 entitlement；默认禁止签名。它只是可编译的正式身份配置，不表示
  App 已接真实后端、可内测、已签名或可发布。
- `Signing.xcconfig.example` 只列占位字段；#495 提供批准的团队、证书/profile 与设备后，
  在忽略的本地目录配置。不把证书、profile 或秘密写进 Git/PR。

## 真机执行准备与明确的剩余依赖

[DEVICE-RECORD](DEVICE-RECORD.md) 可直接复制执行两种语言、系统默认字号的手工路径，
记录机型、系统、网络、普通交互、完整 AX、失败与回归。XCTest 的语义动作/定位符和
总矩阵 `check_m4_app.py` 具有相互独立的 `--simulator` / `--device` 入口；设备入口
必须提供本轮批准的 `--local-tls`，不会把模拟器 ID 当设备使用。各领域的来源与
实际层级分别记录，支持设备参数或预编译并不表示整套真机已通过。

```sh
CJ_PG_BINDIR='<PostgreSQL-17-bin>' uv run --locked python -B \
  ios/App/Acceptance/check_m4_app.py --device '<approved-iPhone-UDID>' \
  --local-tls '<approved-external-profile/operator.json>' \
  --run-context '<explicit-context.json>' --output '<new-external-directory>' \
  --build-dir '<external-build-cache>'
```

JT 2026-11-05 取消最大／大字号验收。本轮使用系统默认字号，不设置启动参数、
夹具字号或 simctl 字号覆盖，也无最大字号前置检查。`--prepare-only`
只证明签名构建准备，所有步骤仍是 UNRUN，另记 preparation PASS；总状态为
`PREPARED_EXECUTION_UNRUN`。`--step` 实际执行子集仍只能 PARTIAL_PASS。

普通业务宿主继续只在 DEBUG Simulator 编译。M4 条目 1、2 已批准指定 iPhone 的
开发签名、高德只读展示与合成账号测试；显式本地设备配置可用
`G2C_M4_DEVICE_ACCEPTANCE` 编译业务宿主，再以 `G2C_M4_LOCAL_HOST` 指定一个
RFC1918/link-local IPv4 开发机地址及显式端口。现有签名 API、身份隔离、原动作和
路由限制不变。Release/Production 不编译该接线，也不含本地网络 ATS 放行。
具体 SDK、Bundle ID、Key 与网络步骤见 [M4-AMAP-LOCAL](M4-AMAP-LOCAL.md)。
JT 通知连接设备后才执行签名、安装和验收；编译、手工步骤和模拟器 PASS 均不计
真机 PASS。真机业务按 #29 的实际范围记录，TestFlight 保持 #33 UNRUN。

### 已交付测试域名的 Debug 接线

B 在 #30 正式发布 READY 后，指定设备的 `DEBUG + G2C_M4_DEVICE_ACCEPTANCE`
构建可显式选择 `G2C_M4_BETA_API=1` 和
`G2C_DEV_API_BASE_URL=https://api-beta.go2china.space`。只接受这个主机和默认443，
不接受别名、其他端口、路径、用户信息、query 或 fragment；不能同时设置
`G2C_M4_LOCAL_HOST`。Public HTTPS 使用系统 CA、主机名和有效期验证，不使用本机叶证书
替换公域信任。原无重定向、路由、会话和原动作门禁继续执行。Release/Production
不获得开发激活能力，也不增加 ATS 放行。

真机定向诊断确认原 v6 回答读取在短请求出口发生 URLError.timedOut（-1001）。
公域 v6 读取复用现有 Run 只读 session（请求30秒、资源150秒），保留同一来源/会话/
身份/响应上限校验；普通消息写入仍走原10/20秒出口。没有自动重发，失败仍显式呈现。

沿用一次性 `G2CM4DeviceAccounts.json` 输入，B 在包和驱动就绪时交付15分钟的既有
合成主体 token。Bearer 不进启动环境、聊天或报告。App 消费后删除输入，原材料只按
既有 Keychain 作用域保存；重开仍核服务端身份，不能以本地 claims 当授权。

当前 B 已交付 plain 消息、原 RUN/SSE，未配置公域 Needs/typed Memory/cleanup，
无预置 Trip/Memory。分别记录实测范围，未交组合保持 UNRUN；禁止向 beta 主体派发
未经授权的删除。客户端接线通过不等于云端/目标网络验收 PASS，也不启动真实用户分发。

公域已保存回答的 V6 只读请求使用独立的 30 秒请求／150 秒资源上限；普通消息
写入仍走原 10／20 秒出口。该只读出口继续校验原记录、当前会话及 owner，不能授权
发送或恢复原消息。Debug 的可选诊断只在本机 Caches 留固定两条路由的状态和错误码，
不记录请求参数、头、正文或凭据，不能作为业务成功证据。

`check_beta_device.py` 先 `--prepare-only` 固定 head、工程和产物哈希，再用
`--prepared` 执行；`--case english-diagnostic` 和 `--case chinese-recovery` 可分别
补英文读取及中文恢复／身份隔离。每个选定方法保留完整字节、来源和 `.all` AX 断言；
英文通过不能代替中文方法通过。设备断开时保存原 FAIL／UNRUN、清理精确一次性输入，
等 JT 通知重连后再执行，不自动重启原批次。

B 在 #30 正式交付手动 Needs 和 Feedback 后，可分别准备 `--case manual-needs`
与 `--case general-feedback`：两者都执行中英主动填写、一次明确提交、换语言重启只查
原动作，以及另一账号的隔离呈现；保留完整 UTF8、版本/来源和 `.all` AX。
Needs 只新建本轮 `m4-a-needs-*` 合成记录，不改 B 的 smoke 原记录；Feedback 只用
一般反馈、关联为空。两项都不发送消息、模型、工具、重放或删除。
App 生成的原 action ID 以非秘密定位符导出，供 B 对照原 DB 字节/计数和跨 owner 负例；
设备方法与服务端证明分别记录，UI 通过不能补写未知的服务端计量或正式规划/Memory/注销。
这些是新增公域覆盖，未替换原本机业务用例；构建准备仍不计设备 PASS。

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

生成的设备工程、控制引导输入、DerivedData、原生结果和 App 容器从创建起就放在
导出目录之外的 0700 私有目录；复制中断或扫描失败也不会把原始文件留在导出区。
总矩阵先检查整个导出根，子驱动再检查本轮根；显式 `--build-dir` 不得位于导出
目录内或包含导出目录。实际创建的临时目录也检查，TMPDIR 指向导出树时拒绝运行；
省略构建目录时使用已核对的私有目录。
只导出通过扫描的限定文本、容器扫描结果与内容哈希，原包不可直接分享。
设备验收工程只有 Debug 或 Debug/Release，不保留 Production；正式工程不受影响。
App 自己消费一次性输入与驱动事后清理分别记录，Release 忽略输入仍单独验证。
收尾先关闭凭据暂存入口，再等待已开始的复制完成并清理；收尾后迟到请求被拒绝，
下一个原生阶段由驱动显式重开入口。多用例执行对象固定自己的 case 与账号快照，
不能把上一用例的迟到请求注入下一用例。
凭据清理、服务/私有 PG 停止及源码/head 核对完成后才写终态。指定设备离线时可先
构建；默认字号下的设备实际执行和完整 AX 仍须分别记录，不能由构建替代。

### 需求领域的指定真机入口

`check_needs.py` 同样支持 `--device`、`--local-tls` 和 `--prepare-only`，继续要求
显式 `--run-context`。可按原 `--case` 选择中英、原动作恢复、账号迟到、进程时区或
Release 关闭用例；不改变原签名 API、受限 PG、正式 NEEDS worker 和后端证明。
驱动循环绑定当前执行 case；控制请求不能通过另一次 prepare/fixture 改选 case。
所有带 case 的控制请求及一次性输入暂存均先核对该绑定，拒绝不匹配或重复参数。

```sh
CJ_PG_BINDIR='<PostgreSQL-17-bin>' uv run --locked python -B \
  ios/App/Acceptance/check_needs.py --device '<approved-iPhone-UDID>' \
  --local-tls '<approved-external-profile/operator.json>' \
  --run-context '<explicit-context.json>' --case testEnglish \
  --output '<new-external-directory>' --build-dir '<external-build-cache>'
```

保留 `testChineseLarge` 等历史 case ID 以对应原报告，其中文业务路径改用系统
默认字号；名字中的 Large/Largest 不再表示字号覆盖或验收门槛。所有业务、字节、
隔离、安全及完整 `.all` AX 断言保留。
`testDeviceTimezones` 仍核对 App 进程 TZ 与中国当地字段，不冒称已切换 iPhone 的
系统时区；真实系统语言/时区切换继续在 #29 独立记录。

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
  --chinese-recovery --output '<new-external-directory>' --build-dir '<external-build-cache>'
```

`--chinese-recovery` 保留中文重启与原回执查询路径；旧 `--largest-recovery` 只作
同一业务路径的兼容别名，均不改变字号。实际系统设置/App 显示仍记 DEVICE-RECORD，
普通触控、键盘与完整 AX 不由预编译代替。
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
系统设置记录、普通触控/键盘和完整 AX 必须分别验收。

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
收尾，再写终态，不能用预编译或 AX 代替完整领域、系统设置或普通交互验收。

### 候选确认领域的指定真机入口

`check_memory_candidate.py` 支持显式设备/TLS 与原后端精确 pin，仍要求预算2的
独立 `--run-context`。中英业务用例与原业务断言保留，均使用系统默认字号；
设备预编译会生成签名包，实际交互仍为 UNRUN。

设备和模拟器均不强制字号。原 `/size` 诊断握手兼容保留，仅校验原输入，
明确返回默认字号范围，不执行系统设置或把握手当作字号变更证明。
实际系统设置与 App 显示另记 DEVICE-RECORD。
原候选来源、单次确认/拒绝、原动作重开、原文字节和另一账号不变的证明均保留。
设备文件证明使用每次独立的私有 App 容器副本，删除后不会读到旧副本的残留文件。

### 删除领域的指定真机入口

`check_memory_erasure.py` 支持相同设备/TLS 与精确后端 pin，使用预算4的独立
`--run-context`。设备与模拟器均使用系统默认字号，不执行标准→最大切换。
单次删除原动作、原回执、目标文件消失、其他记忆/另一账号保留，以及未知结果
重开后只核对原动作的断言不删改。设备文件证明使用每次新的私有容器副本；
预编译、模板和文件准备都不是实际删除交互 PASS。

### 反馈领域的指定真机入口

`check_feedback.py` 支持设备/TLS、精确后端 pin 与预编译参数。设备与模拟器
均使用系统默认字号；实际系统设置仍另记。
回答关联默认关闭、自愿填写、general refs=[]、原回执哈希、跨账号拒绝、最小
内容和真实定位符证明不删改。预编译不计业务 PASS，账号 token 不进设备启动环境；
输入清理、导出扫描、服务/PG停止及源码 pin 核对完成后才写终态。

### 离线缓存领域的指定真机入口

`check_offline_trips.py` 支持显式设备/TLS 和 `--prepare-only`，原 `--seed-only`
仍仅诊断正式来源创建。设备用例使用原签名 MESSAGE/worker/采用链和缓存读取，
不提供伪造 Trip 或缓存字节。设备文件观察经每次新的私有容器副本，不复用旧文件。

原 `/offline` 停止的是本机 API，设备版明确只证明服务不可达时的缓存路径，
不当作 Wi-Fi/飞行模式物理断网。受控时钟不当作真实经过14天，容器副本权限
不当作锁屏文件保护。实际物理断网、系统锁态和真实期限继续在#29
记录；本轮均使用系统默认字号。

### 注销与结构/AX 的指定真机入口

`check_account_cleanup_component.py --device` 限定为 `--native-device --all-provided`
的 CJProbeApp 31个已提供域路径，仍要求预算4及精确后端 pin。原组件/完整阻塞
清单用例保留模拟器入口，外部处理不计完成。设备前后文件证明使用每次新的
私有容器副本，保持另一账号哈希、21个设备目标和原调用/回执检查。

`check_shell_structure.py --device` 支持 structure/accessibility/account-deletion：
普通 App 与标明合成、只读的 ShellFixtureApp 分开记录；只读夹具不冒签名业务。
夹具与控制使用批准的本机 HTTPS，控制 audit/release 要求本轮令牌；原只读接口
仍只接受标明SYNTHETIC的读取身份。设备与模拟器不使用夹具字号覆盖。
所有中英业务用例、完整.all AX及其他原失败断言均保留。
这些入口的 `--prepare-only` 仍全部记为 `PREPARED_EXECUTION_UNRUN`。

## #4 的候选矩阵

包版本以当前锁文件为准；Swift OpenAPI Generator 的真实生成与结构化错误/流式
消费使用既有生成检查及领域用例。当前产品用原生 RunReadableText/RunSelectableText，
不引入 Textual；历史 Textual 原型不等于产品依赖。中英长文、链接、选择、滚动、
默认字号布局和无脚本执行分别由 structure/accessibility 与领域实际页面验证。
最低 iOS17 和当前安装 runtime 分开记录；iOS17.5 不冒称 iOS17.0 或真机已验证。
远程图像/未许可链接遵守现有呈现与显式 Link 行为，不新增自动抓取/预览服务。

历史记录（不作为继续大字号复验要求）：2026-11-04 本机补验原 CJ004 Textual0.5.0 原型：Xcode27.2/iOS18.0 首次启动
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

## 2026-11-05 字号范围修订与证据复用

JT 已取消最大／大字号完成门槛，保留中英流程、普通触控/键盘与完整 `.all` AX。
历史最大字号 PASS／FAIL／UNKNOWN 与原 head 原样保留，不改成新默认字号 PASS。
有效业务/安全证据按源码实际影响复用，不因本次范围调整重跑无关通过项；
尚未完成的中文路径继续执行，不删方法或跳过失败。指定手机先恢复原默认设置
L／滑块50%／更大无障碍字体关闭，实际读回记录在仓库外。

## 最新范围：取消 VoiceOver 验收（JT，2026-11-05）

#498、#29、#4 本轮不再执行 VoiceOver，也不把听读、屏幕阅读器焦点/返回/激活
作为完成或关闭门槛。仍须完成默认字号下的中英业务、普通触控/键盘、完整 `.all` AX
与原离线、语言、时区、身份隔离要求。历史最大字号及 VoiceOver 的
PASS/FAIL/UNKNOWN/UNRUN 原样保留，取消不计 PASS，不再为其单独复验。
本机已核实默认字号恢复记录；如启用过 VoiceOver，切换批次前须恢复原状态。
