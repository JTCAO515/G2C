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

## 2026-11-21 · 全国 r11 真实回归

[#815 原回执](https://github.com/JTCAO515/G2C/issues/815#issuecomment-7055473601)保留所有已发原件与三栏费用。沿[全国固定题](../../../eval/lio_national_cases.v1.json)和原 `question_day` 做本地对照。用 `backend/cj_api/tests/test_lio_planning_flow.py` 的 `run` 重放原进件和行政区结果；续轮用同一会话的原上下文。可见正文另在回答层对照，费用和写入以原件核对。这些本地对照不发供应商请求。

- **成都英文、杭州英文**：完整日期和本人集合已给。三天建议可见，但无正式 Trip，不能编辑或撤销。本地用原进件可复现退回普通答复，零保存。正例保留日期、固定时段和明确未知，在原授权允许时读回完整正式 Trip。
- **西安中英**：原行政区候选把陕西西安市、吉林西安区、黑龙江西安区当成同等级歧义。原输入与候选本地复现多余追问。保留真正的同名市歧义对照，按目标层级核行政区原件，无可靠原件时继续安全追问。
- **上海中英**：中文漏问天数，且没有天气工具原件却给出明确预报；英文首轮正确问天数，续轮已知上海却重复要求确认时区。分别用原进件核普通答复分流和固定项时区分支。正例只询问缺失天数，续轮用原确认城市的本地时区，勿编具体预报。
- **杭州中文**：原进件已提取日期和时段，把「我」的集合标成全团，随后重复问参加人、日期和时段。从完整原句辨认参与范围，保留明确群体限定语的拒绝对照。
- **重庆中英**：两种首轮均正确问缺失城市。中文补重庆后停在第 2 天标题，英文补 Chongqing 后改用中文再次问目的地。原进件本地复现续轮退回普通答复。完整答复应保留已确认城市和日期，按提问语言给三天实际安排，并单独核写入。
- **深圳英文**：ACK 后界面 failed/unavailable，原 RUN 与 Meter UNKNOWN，末笔模型 INTENT 保留，原正文不可读。沿既有 UNKNOWN 夹具核停发、同一原消息只读和保守占用，禁止重发或把空原件当作成功。深圳中文原保存、定向替换、绑定撤销全过，供正例对照。
- **成都中文选项偏离**：C 实际选了菜单第二项，原问答及费用保留，冻结首选仍 UNRUN。动态编辑选菜单中第一项与所选目标不同的地点；该地点若在其他时段出现，仍按原固定题选择，核只改所选目标。

## 2026-11-21 · 全国 r12 真实回归

按[全国固定题](../../../eval/lio_national_cases.v1.json)和原 `question_day` 重放。用 `test_lio_planning_flow.py` 的 `run` 注入原进件、城市和写入回执，用 `test_m4_real_services.py` 的 `RealTools.answer` 夹具注入原工具结果。原件与真实结果见 [C 判定](https://github.com/JTCAO515/G2C/issues/815#issuecomment-7060446204) 和 [B 同轮审计](https://github.com/JTCAO515/G2C/issues/815#issuecomment-7060484557)。

- **成都中文**：整句「去成都玩三天」进入城市查询，唯一候选成都仍触发确认。给出已在原文中明确的城市和天数，回读三个有活动且有顺序的日程。保留真正歧义时要求选择的对照。英文已有三天正文，但仍须在冻结题授权允许时核正式保存。
- **西安中文**：原回复称未拿到保存确认，同时没有四天正文。注入写入未获确认，正文仍应给出四天安排并说明保存状态；读回确认才判保存通过。用同轮西安英文核对正式保存、仅替换目标项及撤销后逐字恢复。
- **上海中英**：已明确城市时只追问缺失天数。用原进件覆盖中文重复问城市，以及英文改用中文问到达时间和住宿两种偏差。
- **杭州中文**：原 RUN 返回 `failed/unavailable`，同轮审计见 `unknown_paths`，两轮模型工具决策相同、仅登记一次 fact。按原轮次注入进件拒绝、fact 返回 `unknown` 和重复工具建议。核服务继续给有依据的中文回答或明确说明缺项，禁止重复发同一工具、凭空断言、或在写入证据不足时保存。原故障由 B/L 结合审计继续定位。

既有边界对照可从仓库根目录执行：

```sh
uv run --locked python -B -m pytest -q backend/cj_api/tests/test_lio_national_intake.py backend/cj_api/tests/test_m4_real_services.py -k 'NationalLioNationalIntake or non_transit_fact or cannot_redispatch_same_canonical or unknown_fact_audit'
```

## 2026-11-23 · 千问中→英语音 502

- **现场原件**：香港中→英语音原请求返回 502。访问日志和原账只证明 ASR 已登记 INTENT，MT 未派发。原响应未留上游状态，历史上游根因仍为 UNKNOWN。保留原请求、原 hold 和费用，未知结果不重发。[#1234 同轮核证](https://github.com/JTCAO515/G2C/issues/1234#issuecomment-7090390102)
- **离线回归**：[B 的诊断 PR #1332](https://github.com/JTCAO515/G2C/pull/1332) 中，`deploy/tests/test_translation_relay.py` 的 `test_asr_502_exposes_only_diagnostics_and_keeps_the_original_hold` 用无网对照区分供应商拒绝、传输失败和回执缺项。错误只记录固定诊断字段，502 保留原 ASR INTENT，MT 零派发。该用例的 PASS 只证明诊断与原账边界。
- **真机复验**：按[构建 52 清单 MT02](../build52-release-acceptance.md#千问翻译)，用已获准的内部账号在匹配香港源像上各测中→英和英→中。只有真机可见正确听写和千问译文，并能核同轮 ASR、MT 终态与原账，才判对应在线方向 PASS。当前构建 52 复验 UNRUN。

## 2026-11-23 · 三日游地点精度质量回归

- **现场历史**：香港源 `97fbd310` 的中文三日游第 3 天只有「长城」，同轮结构缺具体段名、活动城市码和其他可独立核实的北京活动。原冒烟按当时规则记 UNKNOWN，B 已回滚，英文、L8 r08 和 C r13 均 UNRUN。原判、原占用与三栏费用留档，同一原请求不重发。[B 原判及归还](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-7092347403)
- **发布后结构回归**：按 [JT 决定](https://github.com/JTCAO515/G2C/issues/495#issuecomment-7094664500)，核 3 天且每天至少 2 个带地名的具体活动。地名精度单列为回答质量，交 L，由全国 16 条评估。地点精度本身无需回滚，UNKNOWN 用于费用或状态无法核清。历史原件第 3 天只有 1 项，结构负例可据此重放。按后续加速发布决定，构建 52 的快速冒烟只核中文回答、文字译文与打车链接。三日游和全国 16 条均在发布后核。
- **现行对照**：构造同轮 3 天、每天 2 个具名活动的结构，只替换一处「长城」和「慕田峪长城」。两份均通过结构对照，泛称在回答质量中单独记录。删掉第 3 天的第二项，结构应失败。用全国 16 条的原冻结判据验证修复版是否给出可以定位的地点。

## 2026-11-23 · 短语音真实 502 与对照

- 香港 `2abaed51` 的一条 0.935 秒中→英合成语音在真实路由返回 502。上游 HTTP 200，原回执报 `speech_usage_seconds`，只登记 ASR INTENT，原保守占用 ¥1 保留。同段语音补静音到 1 秒的独立对照返回 200，ASR 和 MT 原账各一笔 RECEIVED，估算与保守占用均 ¥0.0002463。实付待账单。[S 原件摘要及修复 #1382](https://github.com/JTCAO515/G2C/pull/1382)
- 53 的 MT02 在匹配修复源上复验正常长度和不足 1 秒的获准示例。核可见听写、正确译文、同轮 ASR/MT 回执和日额；不足 1 秒已校验语音应可译，计量仍按原音频进位且最少 1 秒。保留超长、上游计量缺失、去重和未结占用的原对照。新源香港及 53 真机均 UNRUN。

## 2026-11-23 · 西安 r12 草稿活动 ID

- r12 西安中文原模型草稿把 `self` 同时用作本人标识和活动 ID。S 用原捕获日期的去敏草稿回放，看到了四天八个唯一活动、本人的参加范围不变。原 r12 FAIL 保留；该回放为本地证据。[S 原草稿和修复 #1383](https://github.com/JTCAO515/G2C/pull/1383)
- 在该原形及显式 ID 冲突的本地负例中核替代 ID 不抢占别的活动显式 ID，保留参加者、固定项、改稿及保存守卫。真实复验继续按 #815 西安中文的原日期、正式保存、指定项修改和撤销判定。新源全轨迹 UNRUN。

## 构建 53 复验

JT 已决定跳过 52，原执行单并入 [53 验收清单](../build53-release-acceptance.md)。以上现场判定、原件和费用保留。53 的真实复验另记，当前均 UNRUN。

| 原故障 | 53 复验及取证 |
| --- | --- |
| 千问中→英语音 502 | 清单 MT02 在实际 TestFlight 53 上用真机麦克风测两方向。把可见听写和译文对应到香港原 ASR/MT 终态与计量；单独保留历史 502 与 hold。 |
| 三日游地点精度 | 清单基础 07 核实际正文三天、每天至少两个带地名的具体活动。[#1359](https://github.com/JTCAO515/G2C/pull/1359) 的本地对照只证明结构保留；地名精度按全国冻结判据另读真实正文和来源。 |
| 全国 r11／r12 | 原失败批次不补样。每个实际修复源在 [#815](https://github.com/JTCAO515/G2C/issues/815) 绑定同源资格，按原序、全新动作 ID 重跑。单列语义、服务、回执和费用，交付一轮完整结果或停发时已证实的失败。 |

### 53 发布前已确认的候选问题

| 原证据 | 复现与判据 |
| --- | --- |
| [#1370 两次模拟器对比度 FAIL](https://github.com/JTCAO515/G2C/issues/1370#issuecomment-7097195549) | 系统默认字号打开地铁指南，检查「官方票务指南」控件 `lio.metro.source`，中英文分别验浅深色及完整 `.all`。A 的原候选 L1 失败保留；实际分发版重新验收。 |
| [#1370 上海线路图入口](https://github.com/JTCAO515/G2C/issues/1370#issuecomment-7097251728) | 在地铁指南选上海，点「官方线路图」。原候选跳到运营方「车站信息」；通过时直接落在运营方网络示意图或已核的官方原图，核页面内容与所属城市。北京与成都入口各复核一次。 |
| [#1369 常用语两处语义差异](https://github.com/JTCAO515/G2C/issues/1369#issuecomment-7097151302) | 点菜 `dining-mild` 保留「不辣」与英文等义；打车 `taxi-stop` 两种语言都明确请求停车。核大字卡的中英文及实际朗读与所选句子一致。 |
| [#1371 两次模拟器对比度 FAIL](https://github.com/JTCAO515/G2C/issues/1371#issuecomment-7097327837) · [微信支付链接核对](https://github.com/JTCAO515/G2C/issues/1371#issuecomment-7097363399) | 用中英、浅深色、默认字号分别在支付宝和微信支付指南核「官方开通指南」控件 `lio.payment.official`，运行完整 `.all`。点开后须读到对应平台的开通与绑卡说明。原腾讯链接 HTTP 200 但本次未读到指南正文；用实际 iPhone 落地确认。 |
| [#1258 总领馆检索与缺领区指引](https://github.com/JTCAO515/G2C/issues/1258#issuecomment-7097705482) | 原候选随包记录用同一匹配规则搜索「英国」「美国」「韩国」均为零。修复后用常用中英文国名找同一国家的总领馆，并核韩国和朝鲜分别匹配。奥地利驻广州的中国外交部条目缺领区，缺值提示应准确指出，并提供能核到领区的奥方官方入口。按官方目录核领区与可办理事项，再验发布版落地。 |

本节记录候选内容、链接核对和模拟器结果。构建 53 真机复验当前 UNRUN。
