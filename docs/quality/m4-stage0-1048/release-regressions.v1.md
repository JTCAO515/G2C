# #1048 发版故障本地回归

按 [JT 部署决定](https://github.com/JTCAO515/G2C/issues/495#issuecomment-6972695033)
和 [回答优先、写入从严](https://github.com/JTCAO515/G2C/issues/495#issuecomment-6972760640)
核对修复候选。下列用例使用隔离的本地账号、私有 PG 或模拟传输。
[原回归集](regressions.v1.json)、[阶段 0 冒烟设计](basic-chain-smoke.v1.json)及各评测分母保持原版本。

## 锁等待 / Timeline reads during provider response

原件见 [构建 47 两次 timeline 503](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-6968815874)。
两次读取均在 MESSAGE 锁等待超时后失败；历史持锁事务及与两条 RUN 的逐条映射仍 UNKNOWN。
[进件](https://github.com/JTCAO515/G2C/pull/1170)和[普通讨论](https://github.com/JTCAO515/G2C/pull/1174)
各有独立的本地红绿对照。

- 先在同一会话留一轮完整原件。分别在 `model.lio_intake.9` 与
  `model.lio_discussion.0` 已发出请求、响应被夹具暂停时，从同一账号读 timeline。
  每次读取应在释放模拟响应前实际返回 HTTP 200，并保留旧回答。放行后核同一原 RUN、
  一次上游发送、同一计量链及 Trip 零写入（讨论）。保留普通问答与跨 owner 负例。
- 本地组件检查覆盖两条路径的发送交接及原计量保护。签名 PG 投影组另查真实争锁时的
  原 503 保护、无锁的队列读取以及 owner、RUN、原参考绑定。该负例的 503 应继续成立。
  候选还需用同一 worker/PG 和暂停响应覆盖实际读写重叠，组件检查单独通过不能填这一格。
- 进件、讨论的原组合执行回执分别为
  [503→200](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-6968967148)和
  [正常响应及缺 DONE](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-6969237889)。
  [PR #1181](https://github.com/JTCAO515/G2C/pull/1181) 已把签名 PG 并发用例接入下方
  `lio_projection`，含原进件、讨论、截断、Memory 与日期草稿。后续改动以候选自己的运行结果为准。

```sh
CJ_ENV=local uv run --locked python -B -m pytest -q \
  backend/agent/tests/test_provider.py backend/cj_api/tests/test_m4_real_services.py
uv run --locked python -B scripts/pg_suites.py lio_projection
```

## 格式、来源与流完整性 / Reply and write separation

原 [#994](https://github.com/JTCAO515/G2C/issues/994) 的两条模型回执实际被进件格式或
来源绑定拒绝，用户没收到回答。原输出未捕获，具体坏字段未知；只用新合成坏值回放。
构建 47 另一原 RUN 的供应商原因仍 UNKNOWN，在本地分别构造缺 DONE、usage 或模型身份，
不把任一夹具结果当该原 RUN 的归因。

- 中英分别注入非法进件格式和不匹配的用户原文引用，验证现有预算允许时有实际的普通
  对话正文、原坏值无执行权限、无 NEEDS 或 Trip 写入。预算拒绝应发生在下次出站前；
  原拒绝与账务保留。对合法输入，继续核实际规划和原固定项。
- 单独注入结构化草稿的重复项 ID。用实际 timeline 核到可读的候选正文和未保存提示，
  核原校验失败、Trip 零写入。基础冒烟的三日规划还须核每一天的实际安排。
- 流完结信号、usage 或模型身份缺失时，完整正文和明确截断分别造对照。
  前者应可见，后者不展示为完整回答。两者均核同一原 attempt、财务 UNKNOWN 和原 hold，
  不因展示发放写入权限、不重派。现有供应商测试覆盖谨慎结算、INTENT 及无重派；
  完整正文展示及截断对照须在 B 的候选中实测，旧测试的无正文断言不能代替新验收。

```sh
CJ_ENV=local uv run --locked python -B backend/cj_api/tests/lio_cross_language_pg.py
CJ_ENV=local uv run --locked python -B backend/cj_api/tests/lio_rejected_capture_fallback_pg.py
```

## 上一轮失败后继续 / Follow-up after an unsuccessful turn

在同一中英会话中用夹具使原轮失败或 UNKNOWN，再提交新的、独立的用户消息。
实际验证首轮用户数据进入下一轮、原未决动作不重派、原轮无写入授权、后续应答可见。
覆盖 Demo 与非 Demo 的原日期边界；对话继续不能继承旧的规划执行授权。
真实测试遵守各自的停发规则。全国 #815 r11 按 [JT 的单窗决定](https://github.com/JTCAO515/G2C/issues/495#issuecomment-7040420562) 继续处理已知答复 FAIL。

```sh
uv run --locked python -B scripts/pg_suites.py lio_failed_history
```

## 登录前置 / Sign-in prerequisite

见 [原登录回归](login-prerequisite-regressions.v1.md)与 [#1124](https://github.com/JTCAO515/G2C/issues/1124)。
本地入口为 [check_lio_signin.py](../../../ios/App/Acceptance/check_lio_signin.py)。
分别用 `--language zh-Hans`、`--language en` 和各自新的 `--output`、`--build-dir`
目录运行已授权的本机模拟器夹具。有效签发后应进同一账号 Home，冷启动保留原对话与草稿，
不要求旧 starter，也无新业务消息。使用 `--scenario malformed` 核无效响应应安全拒绝，
保留诊断而不创建会话。实际香港短码登录与真机七项另记其原件。

## 冒烟 API 请求媒体类型 / Smoke request media type

[首轮冒烟](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-6974512936) 的身份请求用
`application/json` 提交原 `/v1/lio/messages`，被原路由以 415 拒绝。C 判工具失败，产品问答、
并发和真机均 UNRUN。回归须经原路由验证同一请求文档的两种媒体类型：错误类型 415 且未派
业务消息，`application/octet-stream` 收到绑定原 ID 的 ACK。ACK 在此只证明请求进入原接口。

B 的 [PR #1184](https://github.com/JTCAO515/G2C/pull/1184) 在候选中加入了
`deploy/tests/test_server_smoke.py::test_smoke_post_is_accepted_by_the_original_lio_wire`。
[R 已独立跑过原路由对照](https://github.com/JTCAO515/G2C/pull/1184#issuecomment-6974549319)。
在含该测试的候选本地运行：

```sh
uv run --locked python -B -m pytest -q \
  deploy/tests/test_server_smoke.py::test_smoke_post_is_accepted_by_the_original_lio_wire
```

## 复核记录

运行前沿仓库既有方式安装锁定依赖。PG 用例使用本地 PostgreSQL 17 的 bin 目录，
通过 `CJ_PG_BINDIR` 指定。PR 回执登记候选 SHA、执行入口和实际结果。
真实冒烟以 [#1048 当前判定](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-6972969188)
和候选原件为准。本地用例不改变已记录的真实失败、未知、费用或释放条件。

## 2026-11-19 · 正文完整性与英文能力

- **PLAN-D1**　[现场原件](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-6999370846) 的 RUN 已 ACK 且 completed，三天正文可见，但第 1 天只有地点，没有活动、时段或顺序，判 **FAIL**。复跑中英各用一组同形合成反例（例如「第1天：故宫、景山」/ “Day 1: Forbidden City, Jingshan”），第 2、3 天都给完整正例。补上明确活动及可执行先后后应通过，例如「上午参观故宫，下午步行游览景山」/ “Morning: Tour the Forbidden City. Afternoon: Walk through Jingshan.” 相同语义的列表、加粗时段和时刻都可呈现实际安排。只有地点、否定活动、问句或待定占位均不通过。真实安排可用日内先后或时段表达，不编精确时刻、预约或营业时间。[提示修复 #1230](https://github.com/JTCAO515/G2C/pull/1230)
- **CAP-EN**　[现场原件](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-7003963155) 中，旧脚本错拒了完整英文能力文案。按 [JT 决定](https://github.com/JTCAO515/G2C/issues/495#issuecomment-7004999143)，当轮人工兜底逐字核原 RUN 正文，别把这一放行当作脚本已修。后续自动门禁的正例为同源 [CAPABILITIES_EN](https://github.com/JTCAO515/G2C/blob/59cc874b5e87bd2e0451b81b144ee0bc2b15b6c9/backend/message/cj_message/lio_context.py#L22) 原文。订票、付款限制是正例的一部分。明确否认规划能力、单独标题、引用文案或在完整文案前后附加与其矛盾的否认均不得通过。例如 “I don’t plan your days.”、“It is not true that I can plan your days.” 及「完整文案 + “I cannot plan any itinerary.”」。在 [B 的 #1233](https://github.com/JTCAO515/G2C/pull/1233) 调原门禁判定；真机同时核正文是否真正可见，欢迎语和 ACK 不计。

两条均保留原现场结果。[补跑回执](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-7004930477)是服务端冒烟证据。

## 2026-11-20 · 三日游短答缺整份行程

**PLAN-NONE**　[现场回执](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-7030713424)：
`cc73ce4b` 中文首轮「北京三日游」的 RUN 已 ACK 并完成，47 字正文可见，但没有分天安排，判 **FAIL**。
原版已回退 `59cc874b`，L8 与全国 16 条 UNRUN。保守占用 ¥0.0060779，已知估算 ¥0.0060779，实付 UNKNOWN。

- 复跑原短问法，在独立新对话核对实际正文、原 MID/RUN 与规划分流。负例使用无日程的合成短答，例如「北京有很多地方可以去，故宫和长城都很值得看。你想先了解哪个景点？」。即使 ACK、RUN completed 和 timeline 200 齐全，缺任一日实际安排仍 FAIL。
- 正例给出第 1–3 天各自可执行的活动和先后或时段。另用相同正文仅改变 Markdown 时段样式作对照，实际安排一致时结论一致。[cc73ce4b 加粗标签离线误拒](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-7030645021)单独登记。
- L 正核对是否从规划进件转入普通回答及触发原因，待同一原 RUN 的分流记录证实。复跑新候选按实际回复和原件判，保留未结算费用与原写入守卫。[L 排查](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-7030689560)

## 2026-11-20 · 只有目的地的规划请求误判为取消

**CITY-ONLY**　[L8 原件回执](https://github.com/JTCAO515/G2C/issues/994#issuecomment-7033353443)：香港 `e28196e9` 新对话首句「去成都」的 RUN 已完成，进件标为 `cancel`，城市及天数为空。可见回复只给了穿衣建议，漏问天数，判 **FAIL**。原轮 2 PASS、1 FAIL、5 UNRUN，费用以原回执为准。

- 本地用原问法「去成都」与英文对照 “Go to Chengdu” 各开新对话，注入与现场一致的进件分支（`cancel`，无城市、天数），核可见回复和原规划上下文。正例保留原文中的成都，询问游玩天数，日期、人数、天数仍为未知，NEEDS、Trip 与活跃 Memory 零写入。
- 本地续答「三天」／“Three days” 后核城市和天数均可追溯至用户原文，给出逐日正文并维持只读。原 L8 续答仍为 UNRUN。
- 「取消去成都」／“Cancel the Chengdu trip” 保留取消分流。「成都明天穿什么」／“What should I wear in Chengdu tomorrow?” 直接答穿衣问题。两个对照均不触发游玩天数追问或写入。
- 既有 [只读正例](https://github.com/JTCAO515/G2C/blob/e28196e900a93dfbd68fbf95e3509ef0517296b9/backend/cj_api/tests/test_lio_readonly_answers.py#L154) 注入的是正确进件；修复 PR 需覆盖错误进件分支，再在新 L8 同源窗按原判定复验。

本地入口为 `backend/cj_api/tests/test_lio_planning_flow.py` 的 `flow(..., city=None, days=None, intent='cancel', questions=())` 与 `run(wire, text, locale=...)`。已有正例可用 `uv run --locked python -B -m pytest -q backend/cj_api/tests/test_lio_readonly_answers.py -k 'bare_city or plan09'` 检查。

## 2026-11-20 · 机场进城误回过境模板

**FACT-TRANSIT**　[构建 49 第 2 项](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-7033981816)：中文界面问 “How do I get from Beijing Capital Airport to downtown Beijing?”，可见回复给了过境免签说明，未回答进城交通，真机表现 **FAIL**。[B 原件对照](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-7033959282)保留两条同题候选，现场原 RUN 以同轮核对为准。

- 本地沿 `backend/cj_api/tests/test_m4_real_services.py` 的 `RealTools.answer` 夹具，用同一机场问法注入 `tool.fact` 的有摘录和无摘录结果。两种均须继续实际回答进城方式。对照地铁、支付也须回答实际问题。没有对应证据的实时价格、班次或政策不作断言。
- 用真正的过境或签证问题对照。有适用来源时按原证据作政策回答；缺可核正文时保留原核证说明。普通旅行问法不得触发过境模板。
- 英问中界面、中文问英文界面均按问题语言输出正文、兜底和引用标题；无法判断问题语言时沿用界面默认。现场语义与语言分别核对，完成状态与 ACK 不能替代正文。

## 2026-11-20 · 补日期后的三日游只返回第一天

**PLAN-DATED-PARTIAL**　[#815 r10 现场](https://github.com/JTCAO515/G2C/issues/815#issuecomment-7038638059)：中文成都首轮给出三天未保存建议。续轮补「明天」和第 1 天 9:00–10:00 的固定酒店集合后，原请求完成，正文只到第 1 天，也无正式行程。本轨迹 **FAIL**，后 15 条 UNRUN，原费用和请求保留。

- 本地沿 `backend/cj_api/tests/test_lio_planning_flow.py` 的 `run` 和同会话原始轮次，使用[全国固定题](../../../eval/lio_national_cases.v1.json)的成都中英两轮。用原进件形状做对照，`party_size=null` 同时出现在 `unknown_fields` 和 `uncertain_fields`。原进件本地触发 `unknown_paths` 后转普通短答。去掉重复标注只作定位，仍需验证完整回答与写入许可。
- 正例按续轮的原 `question_day` 和目的地时区定位「明天」，给足三天，每天有实际活动及顺序或时段，保留固定集合，酒店位置、人数和预约状态保持未知。
- 仅第 1 天正文、只有 ACK 或只承诺稍后补全均 FAIL。正文有效但无写入许可时，可显示未保存建议。正式保存、编辑和撤销另核实际权限和原件，不能因追求完整正文放宽写入守卫。
