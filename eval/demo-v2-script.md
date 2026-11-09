# Demo v2 · 打开就能问

[#702](https://github.com/JTCAO515/G2C/issues/702) 的中英零配置验收脚本。行程与偏好均为虚构。内部测试员用邀请码登录并同意后，直接在助手首页提问。首页应显示 3–4 个示例问题。选择需求、会话、旅行、规划模式或记忆槽位中的任何一项才可以继续，计本语言首场失败。

After signing in with the internal invitation and consenting, type the first question on the Assistant screen. You should see three or four example questions. Use fictional travel details throughout. If you have to select a needs record, conversation, trip, planning mode, or memory slot to proceed, the first scenario fails.

同一语种按编号走。第 4 场修改第 3 场刚采用的行程，第 5 场用助手的「新对话」验证记忆。中英分别从各自的获准合成账号开始。除登录与同意外，测试员只需要发消息、点卡片和切换 Tab。

Run each language in order with its own authorized synthetic account. Scenario 4 edits the itinerary adopted in Scenario 3. Scenario 5 uses New Chat to check recall. After signing in and consenting, testers only send messages, tap cards, and switch tabs.

| 中文 | English | 覆盖 |
|---|---|---|
| Z01 | E01 | 地点、步行路线、引用 |
| Z02 | E02 | 天气、官方来源、未知项 |
| Z03 | E03 | 需求卡、分天候选、明确采用 |
| Z04 | E04 | 对话修改、采用、固定项 |
| Z05 | E05 | 记忆确认、跨对话召回、丢弃与删除 |

## 01 · 地点与步行 / Places and walking

**Z01**　北京故宫博物院和景山公园在哪里？我想从故宫步行到景山公园，请查一下距离和大概多久。入口、营业时间或购票信息如果没核实，就说不知道。

**E01**　Where are the Palace Museum and Jingshan Park in Beijing? I’d like to walk from the Palace Museum to Jingshan Park. Can you check the distance and how long it takes? Say if you couldn’t verify the entrance, opening hours, or tickets.

- **看到 / Expect**　出现服务端进度，随后得到完整回答。两处地点和步行路线对应，距离和时长标为查询时估计，来源标签可打开。A server progress line appears before the complete answer. The route connects the two places, distance and time are estimates, and source labels open.
- **失败 / Fail**　路线两端错配、无可核对的正文、编造已核实信息或产生行程写入。Wrong endpoints, no verifiable answer, invented verified details, or a trip write.

## 02 · 天气和官方来源 / Weather and official information

**Z02**　明天北京天气怎么样？请告诉我预报来源和发布时间。另一个问题，我下周在深圳宝安机场转机，哪里可以看国家移民管理局的官方说明？我的个人资格还没核实，请不要替我下结论。

**E02**　What’s the weather forecast for Beijing tomorrow? Please include the source and when it was issued. Separately, where can I find the National Immigration Administration’s official guidance for a connection at Shenzhen Bao’an Airport next week? My individual eligibility hasn’t been verified.

- **看到 / Expect**　天气绑定北京时间的明日、北京及实际预报来源。转机信息引用实际官方来源，可确认的规则、日期及个人未知项分开。The forecast is for Beijing tomorrow in local time. The airport guidance links to the actual official source and distinguishes the rule from unverified applicability.
- **失败 / Fail**　调换地点或日期、虚构来源、保证个人资格、漏答其中一问或无有效终态正文。Wrong city or day, invented sourcing, an eligibility guarantee, an omitted question, or no valid terminal answer.

## 03 · 对话规划与采用 / Plan and adopt in chat

**Z03**　帮我们两个人规划从明天开始的北京两天游，节奏轻松。第一天早上 9 点到 10 点在酒店大堂集合，这段时间已经定了，别动。

**E03**　Could you plan a relaxed two-day Beijing visit for two people starting tomorrow? Our hotel lobby meetup from 9 to 10 a.m. on the first day is fixed. Please keep it as it is.

1. 核对需求卡上的日期、城市、人数、节奏和固定集合。点「确认」继续。Review the dates, city, party size, pace, and fixed meetup in the needs card, then tap **Confirm**.
2. 展开行程候选的两天，核对各日地点、时段、来源和固定项标记。未知字段应明确显示。点「采用」，到行程 Tab 看正式版本。Expand both days of the itinerary candidate. Check locations, time windows, sources, and the fixed-item marker, with unknowns made explicit. Tap **Adopt** and open the Trip tab.
3. **失败 / Fail**　需求未经确认就开始正式规划、采用前写正式 Trip、两天分组错误、锁定集合或时间被改动、来源凭空出现、采用后找不到对应的正式版本。Planning before needs confirmation, a formal write before adoption, incorrect day grouping, a changed fixed meetup, invented sources, or no matching committed trip after adoption.

## 04 · 用一句话修改 / Change the plan in chat

**Z04**　把第二天下午换成去国家博物馆。如果开馆或预约没核实，请标出来；第一天和其他安排不要改。

**E04**　Could we go to the National Museum of China on the second afternoon instead? Flag anything you haven’t verified about opening hours or reservations. Keep the first day and the rest of the plan as they are.

- **看到 / Expect**　助手沿用刚采用的行程，显示只改第二天下午的候选。在点「采用」之前，行程 Tab 仍是原版本。采用后只前进一个版本，第一天和固定集合不变。The assistant offers a change to the second afternoon on the adopted trip. The Trip tab keeps the old version until adoption. Adoption adds one version while preserving the first day and the fixed meetup.
- **失败 / Fail**　要求手选行程、改错日期或其他条目、未采用即写入、重复增加正式版本，或把未核实的营业或预约说成已确认。A manual trip selector, unrelated edits, a write before adoption, duplicate committed versions, or unsupported claims about hours or reservations.

## 05 · 记住、丢弃与删除 / Remember, dismiss, and delete

**Z05**　以后帮我安排旅行时，我长期喜欢慢节奏，每天最多两个景点。

**E05**　For future trips, I generally prefer a slow pace, with no more than two sights per day.

1. 确认回答下出现「记住／不用」，先到记忆 Tab 确认没有已保存项，再回助手点「记住」。开一个新对话，问「按我的旅行偏好，一天最多安排几个景点？」Look for **Remember / Dismiss** under the reply. Check the Memory tab for no saved item yet, then return and tap **Remember**. Start a new chat and ask, “Based on my travel preference, how many sights should I plan in one day?”
2. 说「我以后也总是喜欢靠窗座位」或 “I also generally prefer window seats.”，在候选上点「不用」。记忆 Tab 不应出现座位偏好。Dismiss the window-seat candidate and verify it is absent from saved memories.
3. 从记忆 Tab 删除刚保存的景点偏好并确认。再开新对话，问「我以前说过每天最多安排几个景点吗？」或 “Do you still have my old limit for sights per day?”，期望不再召回被删偏好。Delete the saved sightseeing preference, then ask in a fresh chat. The deleted value should not return.
4. **失败 / Fail**　点「记住」前保存、点「不用」仍保存、保存后新对话未召回、删除后仍进入模型上下文，或需要选择槽位。Saving before confirmation, saving after dismissal, missing recall in a new chat, injecting the deleted preference, or requiring a slot selection.

## 执行记录

- 中英各 5 场；逐场记录 PASS／FAIL／UNKNOWN／UNRUN。规划、修改和记忆的多步动作分别关联原消息、RUN、候选、动作和回执。同一原件结果不明时只读核对。
- 从客户端提交开始，分别记录首个真实 RUN 状态到达、App 首次显示、首正文和完整正文；API 冒烟与 App 显示分列，未知时钟保留 UNKNOWN。记录工具来源和终态正文，对记忆用原模型上下文、版本与删除回执验证召回和删除。
- 每场分别记录保守占用、按模型 token 和工具原回执估算、实付。没到账单写 UNKNOWN。新复验使用独立运行 ID，并保留旧结果。合成 #702 冒烟、JT 真机走查和 #32 正式质量验收分别报告。
