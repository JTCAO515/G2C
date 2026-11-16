# M4 阶段 0：回归清单与基础链路冒烟设计

本轮只交设计。唯一观察总表是 [#1048](https://github.com/JTCAO515/G2C/issues/1048)，
客户端与服务端核查分别引用 [A 汇总](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-6905939029)
和 [B 汇总](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-6905940894)。
**本资料没有执行 HK 请求、供应商调用、设备测试、部署或额度变更；没有任何“已修复”结论。**
所有新回放及冒烟结果均为 `UNRUN`。历史 FAIL、UNKNOWN、成功样本和原费用均保留。

文件：

- [构建与服务映射](build-source-map.v1.json)：14 条表格观察（历史 10 条、构建45现场4条），另列5类持续问题。客户端源、当时服务端运行源和逐请求归属分开。
- [中英回归数据](regressions.v1.json)：25 个基础用例，50 个语言变体；输入、双语期望、具体判定、前置及原观察 ID 均登记。
- [七项冒烟设计数据](basic-chain-smoke.v1.json)：7项×中英＝14项检查、8条实际用户消息，含调用预算、窗口、自动化与停派条件；不是可执行许可。

## 1. 每一行如何回放

`H01–H10` 对应 #1048「历次版本观察」原行；`F45_1–F45_4` 对应当前四项。
`P01–P05` 保留表后持续问题，尤其把记忆识别、点击保存和页面布局拆开。
下表的历史认定不是本轮成绩。用例共用时只复用定义，不把某构建的结果转给另一构建。

| 观察 | 构建 | 历史认定 | 回归用例 |
| --- | --- | --- | --- |
| H01 | 18–20 | 规划失败、重复索取已给信息、补充后失败 | PLAN01、PLAN05、PLAN09 |
| H02 | 21 | 身份/能力先成功后失败，规划失败 | QA01、QA02、QA04、PLAN01 |
| H03 | 21后，构建号不明 | 中英及可展开行程成功样本 | PLAN02 |
| H04 | 24 | 半句失败、额度提示、工具来源挤占聊天 | PLAN03、STATE01、UI05 |
| H05 | 25 | 有成功样本，首轮身份仍失败 | QA01、QA04、PLAN04 |
| H06 | 28 | 问答间歇失败、后台恢复当时成功 | QA01、QA02、QA03、UI04 |
| H07 | 30–31 | 可选信息卡住、补充/首次来华失败、恢复断上下文 | PLAN05–PLAN07、QA05、UI06 |
| H08 | 41 | 完整四天请求仅复述、追问失败 | PLAN08、QA06 |
| H09 | 43 | 后台/锁屏及强关重开仍打不开 | UI01、UI04 |
| H10 | 45 | 当前四项全部失败 | UI01–UI04 |
| F45_1 | 45 | 启动旧消息转圈 | UI01 |
| F45_2 | 45 | 本地开场正常，发规划后没有回答 | UI02、PLAN05 |
| F45_3 | 45 | 历史列表不可见 | UI03 |
| F45_4 | 45 | 后台回来对话打不开 | UI04、UI06 |
| P01 | 各次 | 日期/人数被当必需前提 | PLAN05–PLAN07 |
| P02 | 各次 | 失败、半句、只有复述 | UI02、PLAN03、PLAN08 |
| P03 | 各次 | 上下文断开、重复开场 | UI01、UI04、UI06 |
| P04 | 含31 | 豪华偏好、确认保存、等大格子分开核 | MEM01–MEM03 |
| P05 | 含24 | 工具过程/来源项占聊天区 | UI05 |

每个 JSON 用例的 `inputs.zh/en` 是可依次操作的合成输入；`expected_behavior.zh/en`
独立适用于两种输出语言，`judgement_method` 给出具体取证和判定办法。中文成功不能替代英文。
精确历史输入缺失时明确写成“同症状合成回归”，不能冒充原字节重放。不得发送 JT 的旧
MID、复用其账号、读其 journal/密钥，或重建失败原件的能力。英文译例不伪称 JT 英文原问。

多轮用例首步发生非预期 FAIL/UNKNOWN 后立即停新，不能为跑完后半段继续发送。
要复现“失败后再追问”的独立分支，须先合法核清旧动作，再取得新的合成前置和独立窗口；
历史 build41 的旧 barrier 未知，不能靠 effect、截图或临时 DTO 填出来。

## 2. 版本、成功样本和未知边界

构建45客户端归档源是 `28f70861b0df4b2d75ea6a388f9a84723342de85`，
IPA 身份及来源见 [发布原记录](https://github.com/JTCAO515/G2C/issues/702#issuecomment-6905479666)。
B确认目标时段香港实际 API/worker 为
`2e5560cf3c794df4aff48c8431e8424330580e10` /
`sha256:0ad586bea92662028112887ba37351fb307a06717cb84e17a507039c727feeba` / schema55。
这与含较新 PR 的 main 不同，不能以 merge 时间覆盖现场 source。

逐请求仍有缺口：23条完成访问全部 GET/200，分类为 receipts 10、Trip list 7、structured 6；
无目标 Lio 完成日志和新域内消息。A三条问题记录的 ref 均为空，不能借同秒 GET 的
request_id 补上。完成日志缺行不证明请求绝对未到；worker 较早轮转日志也有缺口。
不能据此判网络、供应商、额度或某一客户端分支就是四项现场共同根因。

历史对照特别保留：

- build21早期身份/能力成功窗口可核到 `87eb8f09…`；不代表规划成功或同版稍后状态。
- 21后构建号不明的成功行程，唯一客户端构建/规划 source/MID/时点仍 `UNKNOWN`，不补成22。
- build25早间问答 source只有 `bfd77e54…` 候选区间；成功规划唯一 source仍未知。首问 server
  completed 但英文混中文禁词被App隐藏，是A已证实的旧分支，不能套成今日 waiting 的根因。
- build30约23:03的原件核回绑定 `12a47298…` 并记录了截断；不覆盖build31所有反馈。
- build41原件诊断绑定 `ba98eb32…` 的当时运行；不是当前 source 的结果。

[L阶段0对照](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-6906216124)补齐21早期
运行源像完整值及25候选源像，已沿原部署记录入JSON；25仍是候选，不升级为成功规划唯一源。
[build24原件](https://github.com/JTCAO515/G2C/issues/702#issuecomment-6783491780)的另一条拒绝是
20,611输出＋48,000工具预留超过65,536，账号103/800未耗尽。STATE01分别核单轮与账号
限额；PLAN03保留已知原问片段“Help me planning”，不通过换成更容易识别的句式躲回归。

详细映射及证据状态在 JSON。`null` 一律表示 `UNKNOWN`，prefix和候选另列，不补全冒真值。
缺旧归档不妨碍在新候选重放同症状，但不能声称已逐字复现该历史版本或锁定引入原因。
已从A原发布记录绑定28/30/31/41/43/45的客户端完整SHA；18/19/20/21/24/25仅有
发布/候选材料而无可核完整包源时继续UNKNOWN，不拿对应PR的merge代替。

## 3. 七项基础链路冒烟 / Basic-chain smoke

**未来执行必须是合成账号、真实香港、待发布的同一候选，普通用户 Home 的实际协议。**
本轮不运行。每个项目分别有中文、英文结果，总分母14。当前模式不能自动切成native4；
脚本走4而App走2不能给用户链路放行。版本差异显式绑定，不改旧契约或冻结全国/66用例。

| 项 | 中文步骤与判定 | English step and expectation | 自动化与费用性质 |
| --- | --- | --- | --- |
| SM01 | 强关再启动，恢复真实合成旧CID/消息/草稿，不无限转圈 | Relaunch and recover the same old chat, messages and draft | A UI/真机＋C原CID只读；0新消息 |
| SM02 | 新对话问“北京是中国的首都吗？”，收到真实完整回答 | New chat: “Is Beijing the capital of China?”; complete real server answer | A发1条/语言，C观察同一原件；本地开场不计 |
| SM03 | 历史中看到旧、新对话并打开正确CID | Find and open both old and new chats in history | A本机journal/合法reconcile＋C已知CID只读；不虚构conversations API |
| SM04 | 在原对话留草稿，后台10秒和锁屏60秒各返回，内容连续 | Background and lock, then recover the same chat and draft | A转场＋C前后原件/attempt差值；0新消息 |
| SM05 | 新对话首问“你是谁”就有可读、语言正确的Lio身份答复 | “Who are you?” succeeds on the first request | A发1条/语言，C核server正文与UI都成功 |
| SM06 | 新对话首问“你能做啥”就有有用能力答复 | “What can you do?” returns useful capabilities | A发1条/语言，C同源原件/全费用 |
| SM07 | 新对话“北京三日游”，拿到完整day1–3的具体行程 | “A three-day trip to Beijing.” yields all three concrete days | A发1条/语言，C核实际规划正文/对象及模式对应持久状态 |

SM07不接受ACK、需求复述、半句、模板空卡或只索取日期/人数。完整可回看的三日正文是
legacy2预览路径的最低实际行程；它不能计作自动保存通过。native3/4或界面宣称“已保存”时，
必须核对同原动作的正式版本、历史和回读。候选有日卡时还核展开；不得用不存在的卡片
或另一个模式的行程代替。M4的自动保存、丰富度、硬项及质量门槛继续独立验收。

观察期限使用更严格的现有 transport/资格期限，单项最长90秒；转圈/无完整结果不得无界等候。
分别记录UI表现、服务端终态、首个真实服务端进度、首正文与完成时间。未观测的进度不补0，
本地spinner不算进度。既有 #630/#32 的5/15/90及native4门槛继续保留；本小样本不声称证明总体p95。

判定：

- `PASS`：同候选、同原件的UI与原生/持久证据完整，行为符合期望且无未授权副作用。
- `FAIL`：已核前置下，界面或可复核行为违反期望；server completed而App隐藏也不通过。
- `UNKNOWN`：原件、身份/源关联、写入终态或费用对账缺失；不是空值/零费/PASS。
- `UNRUN`：未取得资格、缺合成前置，或首败停派后尚未执行。

逐条串行，首个非预期 FAIL/UNKNOWN 即停新，剩余保持UNRUN。仅14/14 PASS才可通过基础门禁；
不得用6/7、中文全过、健康检查、CI或安装成功替代。基础门禁通过也不关闭历史回归或M4。

## 4. 脚本与App如何共用原件

A的普通Home发出本轮8条消息；C的脚本观察**这些同一原件**，不再发送一套重复问题。
A完成启动/历史/后台/锁屏/布局的真实UI断言；C完成原receipt、原RUN、正文/Trip、原clock、
全模型/工具/Memory attempt、Meter与费用核对。分别保存App意图、实际HTTP/lookup、原响应、
CID/MID/RUN/request_id、构建/源像和安全问题记录；无共同ref时保留关联UNKNOWN。

可复用的现有位置：

- [HTTP单次提交与只读续接](../../../eval/demo_v2_transport.py)、[计费解析](../../../eval/fees.py)、
  [规划发布回归](../../../eval/lio-pr717-regressions.md)、[无日期模式差异](../../../eval/lio-calendar-acceptance.md)。
  这些提供原语/期望，不是已接好本七项的HK执行器；未来适配须固定实际Lio契约，不能直接
  把Demo路由当Lio路由或增加任意 `--real`。
- A可复用 `ios/App/Acceptance/LioHomeUITests.swift`、`ios/Modules/CJShell/Tests/CJLioUserTests/`
  和 `ios/Modules/CJMessageClient/Tests/CJMessageHTTPTests/` 的状态/断言骨架；当前本地fixture
  不当真实HK成绩。没有合规的实机UI自动化时，A按上表手工并留同源证据，不为过门禁改产品。

A使用已获准的隔离测试安装/身份，不为准备合成测试退出JT当前会话、覆盖其journal或清数据。
若不能同时满足隔离和普通Home同源性，该项保持UNRUN，先核准安全前置。

构建45历史列表来自本机journal，未决首发才触发原lookup，不是必发远程conversations列表。
账户校验的 receipts 200/null 不等于timeline已读；HTTP–也不等于没到服务端。问题记录只20条且
会去重，不能拿它当完整请求清单。诊断与判定须保留这些实际接口差异。

“已有合成旧对话”必须有真实已完成原件与客户端持久记录。首次没有时，单独准备每语言两轮，
不得导入伪造Snapshot或借JT数据。UI01的合法未决首发变体属于关联历史回归：A用同源可核
合成前置复现，先由B确认原动作/费用，不通过发一个真实UNKNOWN然后直接忽略STOP来准备。
该额外变体不在下面基础报价里，后续需要独立登记输入、调用和窗口。

## 5. 一次需要的额度：只取C既有子额

这是**未来低复杂度普通入口的设计预留**，不是现有实现调用上界已证明、不是发票，也不是新授权。
每语言4条用户消息：3个问答各预留前台模型≤3、一次简单规划≤6；每条另预留2个后台模型
覆盖Memory等费用。工具为问答≤1、规划≤4。codebank实际零模型可以如实记录，不能强迫
模型调用；未知工具不能记0。实际需要超出此报价的候选，在任何调用前重新核算，不能减少
行程内容、放宽G10或调env/额度来凑通过。后台预留也不允许超越产品调用门槛。

| 场景 | MESSAGE | 模型（含后台） | 收费工具 | 未完整回执全hold上界 | 建议测试消费上限 |
| --- | ---:| ---:| ---:| ---:| ---:|
| 已有旧合成对话的单次中英冒烟 | 8 | 46 | 10 | ¥56 | ¥60 |
| 首次需准备两语言各2轮旧对话 | 12 | 66 | 10 | ¥76 | ¥80 |

本轮读取的 [B实际快照](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-6905940894)
为 C100、原保守占用 ¥8.0472741，算术余额 ¥91.9527259；可覆盖上述设计上限。
这是快照，不保证未来余额、原生period、每类次数或同账号资格。未来B须重新核C当前主体/
period、原账/旧hold、有效期、分类次数和限额；最多在原C范围内收紧临时测试上限，不增钱、
不迁移/重置旧账。资料不齐或余额不足则不跑，保持UNRUN并重新报价。

三栏必须分开：

| 保守占用 / conservative | token估算 / token estimate | 实付 / supplier paid |
| --- | --- | --- |
| 标准最大56元、首次准备最大76元，按每原模型/收费工具1元原hold计；已定价原完整回执按现行规则计，旧hold照留 | 标准假设46次、每次4096 input+1536 output，模型约¥0.341504；若10次全为可定价v3工具另约¥0.030000，总约¥0.371504。首次66模型对应约¥0.519984含同工具估算 | 未拿到实际供应商账单则UNKNOWN，不将保守预留或token估算冒实付 |

计价参考为固定main `28f70861b0df4b2d75ea6a388f9a84723342de85` 的
`backend/usage/cj_usage/authorization_budget.py`：CNY scale=10,000,000，模型 input/output=8/27单位每token，
即¥0.8/¥2.7每百万token；可识别v3高德每次30,000单位，即¥0.003。模型为北京端点
`qwen3.8-flash`。4096输入是假设，不是缩短真实输入的额度技巧；v5/未定价/缺回执工具继续
UNKNOWN并持有原占用。未来按实际同源pricing和原receipt重算，不沿用本表覆盖新source。

native4或高复杂度候选每份可能达45高德调用时，当前10工具报价不适用。七项行为定义不变，
但须在发送前另算全部调用/后台与余额，并由B交相应资格；不能沿用旧低报价而悄悄截断/降节奏。
这不是请求新增C子额度，更不把本报价当全25用例、全国16或66例/actor的预算。

## 6. 窗口与部署/发版放行点

建议普通单次60分钟，首次准备90分钟，结束前10分钟停新，余段只读收尾。由B另行签发
未来C独占窗口，A同次协作使用C合成身份，排除JT和其他writer；未获准不自动到点开跑。
实际原件reader全串行，native reader UNKNOWN marker由B核清，不能并发重启或补退出码。
raw在ends_at前按实际保护读取；过窗缺raw保持UNKNOWN，metadata可在当前原保护下对账。

**部署/发版前门禁必须针对待发布的实际候选。** B须在既有授权内提供香港预发布候选槽/
受控候选装配，与待放行API和worker完全同source/image/配置。旧现役测试不能放行新镜像。
如果目前只能直接切换后验证，那份结果只能叫“部署后验证”，不能填写“部署前已通过”；
部署/公开放行继续受阻，按B既有权限保持维护或回退。阶段0不 provision 槽、不买资源、
不开端口、不部署，前置不足是待下一阶段解决的明确依赖。

App发版前由A固定待发布归档/build/source/配置与同源安装候选，在真实HK执行UI部分。
Debug mock、签名构建成功、TestFlight可安装均不能替代；待发归档或服务端任一pin变化，
原门禁不再覆盖该候选，另用新run/MID/窗口验证。服务端单独API诊断若另发消息须另外计费，
不能把它拼成本报价中的App通过。

## 7. 阶段0交付与停点

本PR只新增文档和设计数据，未接入可执行CI/运行门禁。静态JSON、覆盖/引用检查和PR CI
只证明资料可读且对应原观察，不证明25个回归或14项真实检查通过。
当前资料中所有新运行均UNRUN，根因候选/历史成功source未知保留，不关闭#1048或任何产品故障。

本线在#1048发布一条汇总：PR、25个双语用例、七项门禁、60/90分钟窗口与60/80元既有子额
报价。阶段0交付后停止，等JT下一阶段提示；不自动进入修复、真实调用或部署。

English summary: this is a design-only stage-0 delivery. The dataset preserves every
historical/current observation and includes Chinese and English inputs and expected
behavior. The seven checks require the same qualified Hong Kong candidate and actual
ordinary App path, with shared original evidence and all foreground/background costs.
All new executions remain UNRUN. No repair, deployment, source qualification or live
acceptance is claimed; the next stage requires a new JT instruction.
