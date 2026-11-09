# G2C 内部 Demo · 双语脚本与快速冒烟

依据 [#685](https://github.com/JTCAO515/G2C/issues/685) 和 [JT 的 Demo 授权](https://github.com/JTCAO515/G2C/issues/495#issuecomment-6730538594)。中文 5 场景、英文 5 场景，分别记账。只在 `api-beta.go2china.space` 的获准 Demo 窗口执行，身份用 B 为本窗提供的合成身份或 JT 指定的内部测试账号。使用虚构行程与偏好。邀请、令牌、姓名、行程原件和明文记忆不进公开报告。

演示者先用 Beta 和邀请码登录，确认会话语言正确，再按所选语言复制提示。换场景时新开会话；规划及修改保持同一行程，记忆回读须新开会话。`{北京明日}` 填当天北京时间下一日的 `YYYY-MM-DD`，提交前把实际日期记入该次原件。C 的 API 冒烟与 JT 的 TestFlight 操作分别记录。

Sign in to the Beta with the invite code. Use the prompts for your language and start a fresh conversation for each scenario. Keep the same trip for planning and editing. Replace `{北京明日}` with tomorrow’s date in Beijing (`YYYY-MM-DD`). Use fictional details throughout.

| 场景 | 中文 | English | 验收覆盖 |
|---|---|---|---|
| 01 | Z01 | E01 | 地点和步行路线 |
| 02 | Z02 | E02 | 天气和通用反馈 |
| 03 | Z03 | E03 | 权威事实 |
| 04 | Z04 | E04 | 正式规划、采用、手动修改 |
| 05 | Z05 | E05 | Typed 记忆保存、跨会话回读、停止使用 |

## Z01 / E01 · 地点与步行路线

**Z01**　这是虚构旅行演示。请先查北京故宫博物院和景山公园的位置，再查这两处之间的步行路线。说明查询时的距离和时长估计。入口、开放时间或购票信息如果没有核实，请明确说未知。先回答，不保存行程。

**E01**　This is a fictional trip. Look up the Palace Museum and Jingshan Park in Beijing, then check the walking route between the two actual results. Give the estimated distance and time at the time of the query. Mark unverified entrances, hours or ticket information as unknown. Answer without saving a trip.

1. 提交后观察真实进度与正文。预期同一 RUN 有地点与步行回执，使用同源端点与对应地点，正文可完整读回。
2. 对照返回路线和正文。距离、时长为查询时估计，缺来源的字段保留未知。无候选采用、正式 Trip 写入或预订。

**失败 / FAIL**　路线与查到的地点不一致、无有效正文的失败终态、编造已核实信息，或产生未确认的正式写入。缺少可核对回执时记 UNKNOWN。 Expect one completed answer with a walking route grounded in the two place results. A mismatched route, an unsupported verified claim, or an unauthorized write fails the scene.

## Z02 / E02 · 天气和通用反馈

**Z02**　这是虚构北京行程。请查 `{北京明日}` 的北京天气，起止都是这一天，按北京时间。说明实际报告时点、当天预测及未知项，不保存行程。

**E02**　For a fictional Beijing trip, check the forecast for `{北京明日}` only, in Asia/Shanghai. Include the source and its report time, the forecast for that day and anything still unknown. Do not save a trip.

1. 提交一次。预期同 RUN 的天气回执绑定北京和指定日，正文引用实际来源和报告时点。
2. 若来源无该日预报，预期明示未知并保留回执。无日期替换、无把天气预报当成实况、无 Trip 写入。
3. 从反馈入口打开通用反馈。**Z02 问题**「虚构演示里，天气来源不容易找到。」 **Z02 期望**「请清晰显示预报来源和报告时点。」

   **E02 problem** “In this fictional demo, the forecast source was hard to find.” **E02 expectation** “Please make the forecast source and report time easy to see.”
4. 提交一次通用反馈。预期看到「反馈已提交」或 “Feedback submitted.” 和回执时间。同一原反馈可读回，无新增模型调用或非预期会话关联。

**失败 / FAIL**　地点或日期错配、把未知写成确定预报、重复提交反馈或反馈已确认但无对应回执。只读核对仍不明确的原动作记 UNKNOWN。 Expect a forecast for the specified day and one generic feedback receipt. A wrong city or date, a false certainty, or a duplicate feedback write fails the scene.

## Z03 / E03 · 权威事实

**Z03**　这是虚构转机场景。假设 2026-11-21 经深圳宝安机场中转，请查国家移民管理局官方信息。说明官方页面能确认什么、旅客还要核对什么，以及哪些个人资格或日期适用性无法判断。请附原来源。

**E03**　For a fictional transfer via Shenzhen Bao’an Airport on 2026-11-21, look up the National Immigration Administration’s official information. Explain what the source establishes, what a traveler still needs to verify and what cannot be determined about individual eligibility or date applicability. Include the original source.

1. 提交一次。预期同 RUN 的事实回执与后续模型均可核对，正文引用实际官方页和相关摘录。
2. 资格或日期条件无法核实时必须明确。只收到来源行、未收到正文或缺官方回执时保留 FAIL 或 UNKNOWN。

**失败 / FAIL**　把无法确认的适用资格写成已确认、伪造来源或已确认终态无有效正文。回执未核实记 UNKNOWN。 Expect an answer grounded in the original official page. Invented sourcing, unsupported eligibility guarantees or a terminal response with no answer fails the scene.

## Z04 / E04 · 正式规划与手动修改

1. 建立或选中本场景的合成 Needs，锁定一项北京酒店大堂集合，日期用 `{北京明日}`，北京时间 09:00–10:00。预期读回原 Needs ID 和版本。另一语种使用独立合成行程。
2. **Z04**　请根据刚保存的虚构需求生成一份简短行程草稿。保留上午在酒店大堂集合的锁定安排，不改日期或时间。先给我候选，等我确认再保存。

   **E04**　Draft a brief itinerary from the saved fictional needs. Keep the locked morning meeting in the hotel lobby on its original date and time. Show me the candidate and wait for my confirmation before saving.
3. 预期原 RUN 完成并能读回同源正式候选，固定项、时间和 Needs 版本核同。在用户确认前正式 Trip 写入为 0。
4. 明确采用候选。预期同一采用动作读回正式 Trip v1，原固定项保持。然后手动把标题改为「北京演示行程」或 “Beijing Demo Itinerary”，明确保存。预期读回 v2，只有标题改变，固定项和原时钟保留。
5. 候选缺失、原动作回执未知或任何固定项被改动时，保留原请求，只读核对。采用或修改的写入需要各自原回执。

**English walkthrough**　Select the fictional Needs with the locked hotel lobby meeting from 09:00 to 10:00 Beijing time. Ask for the draft, then adopt it explicitly. Edit only the title to “Beijing Demo Itinerary” and save. Expect a candidate before adoption, a v1 trip after adoption, then v2 with the new title and the same meeting.

**失败 / FAIL**　原 RUN 明确结束仍无候选、锁定项被改动、确认前正式写入，或采用及修改的回执、版本和内容不一致。原回执无法确认时记 UNKNOWN。 A missing candidate at terminal completion, a changed locked meeting, a write before confirmation or an inconsistent receipt or trip version fails the scene.

## Z05 / E05 · Typed 记忆

1. 在 Typed 记忆界面，用本场景授权的合成 slot 明确保存一条虚构偏好。**Z05**「在演示中我偏好慢节奏，每天最多两个景点。」 **E05** “For this demo, I prefer a slow pace and at most two sights a day.” 预期保存回执绑定当前身份和原记忆项。
2. 新开会话。**Z05**「按我刚保存的演示偏好，给我建议一天安排几个景点。不要保存行程。」 **E05** “Using the demo preference I just saved, suggest how many sights to schedule in a day. Do not save a trip.” 预期实际 Typed 回读或原模型输入证明用到了该偏好，正文遵守数量约束，无新 Trip。
3. 明确停止使用该条合成记忆，再新开会话。**Z05**「你现在能使用我先前保存的演示偏好吗？无法读取就直接说明，不要写入。」 **E05** “Can you use the demo preference I saved earlier? Say so if you cannot access it. Do not save anything.” 预期同项停止使用回执可读，撤回值没有进入下一次模型上下文。正文是否复述不单独作为证明。

**English walkthrough**　Save the preference explicitly in the assigned Typed memory slot. Recall it from a new conversation, stop using the original item, and ask again in another fresh conversation. Verify the save and stop-use receipts and the original model context for the two recalls.

**失败 / FAIL**　已保存偏好未用于下一会话、撤回后仍进入上下文、跨身份读写或产生未确认的正式写入。缺上下文或原回执记 UNKNOWN。 A confirmed missing recall, reuse after withdrawal, a cross-account effect or an unauthorized write fails the scene.

## C 快速冒烟记录

- 每个编号只算一个场景。多步场景保留所有新原动作及回执，任何必要步骤未执行均保留 UNRUN。记录原候选版本、语言、阶段、原 RUN、attempt、工具回执、费用和原证据摘要。运行未知先只读对账。
- 计时使用同一客户端从真实提交起算。首个服务端状态事件到达、App 首次显示该事件分别记。首正文排除来源行，完整正文须和同 RUN 终态正文核对。只读终态恢复不补首正文时钟。服务器阶段单列，缺测填 UNKNOWN。
- 多步场景保留每次回答的原时钟。采用、保存和反馈另记提交到原回执的时钟，不填首正文。不要用多次执行中最快的一次替代原件。
- 按中文 5、英文 5 分别记录 PASS、FAIL、UNKNOWN、UNRUN 与计划分母。C 的合成冒烟通过、TestFlight 安装和 JT 的人工演示走查分别报告。
- 只把已确认的行为或验收偏差记为 FAIL。缺回执或时钟保留 UNKNOWN，未执行保留 UNRUN。判定或环境问题经核实后用新 ID 复验，原记录保留。问题按 owner 归档，标明是否挡 Demo。
- 保守占用、按原回执估算、实付分列。未结算原 INTENT 保留占用，实付未见账单填 UNKNOWN。Demo 使用 B 交付的新窗口和同一现役账本。旧六格和正式 66 的原件、FAIL 和 UNKNOWN 保留，按 JT 决定暂让路。

## TestFlight 走查后的服务端核对

1. 按同一窗口、应用版本、场景编号和内部账号代号定位原动作，不收集邀请码或真实身份信息。
2. 核同登录后的原 owner、MESSAGE/RUN、候选与采用及编辑回执、Typed 保存及停止使用回执、反馈回执。按原账本关联 Meter 及供应商 attempt，标出未结算与缺证据。
3. 在 #685 分开汇总真实走查结果、服务端确认与费用三口径。App 时钟仅使用走查时实际采集的数据。对不上时保留 UNKNOWN 和原证据。
