# PR717 规划回归

适用于阶段②的签名私有 PG 和原 worker。按 [#716 的三轮 HOLD 记录](https://github.com/JTCAO515/G2C/issues/716#issuecomment-6739071290) 和对应代码、夹具整理，输入可直接复用。阶段①只验问答。

每个用例从独立合成会话开始。检查原消息、原 RUN、回复、行程卡、原 NEEDS 绑定和 Trip 版本。涉及相对日期时把服务时钟固定为北京时间 2026-11-09。保存的正例用完整的实际签名链路，以同 ID 同字节重发一次，再核提交版本与用量。歧义和拒绝保存的反例先记录 Trip 版本，再核写入差值为零。若缺少原回执，按原 ID 只读对账。

## 拒绝保存

| ID | 依次发送 | 预期 |
|---|---|---|
| R01 | `Plan a trip to Beijing from 2026-12-01 to 2026-12-03. Do not save it.` | 对话说明先不保存。零规划写入、零行程卡。 |
| R02 | R01 的第一句，后接 `Please don't save it yet.` | 同 R01。 |
| R03 | R01 的第一句，后接 `Can you show me before saving?` | 保留草稿请求，零正式写入和行程卡。可以如实说明当前无法预览。 |
| R04 | `帮我规划旅行` → `北京。算了，不要保存。` | 首轮追问。第二轮终止保存，零正式写入和行程卡。 |
| R05 | `Plan a trip to Beijing from 2026-12-01 to 2026-12-03 and save it to my account.` | 资料齐备时，恰好保存一个新版本，行程卡和回执绑定同一提交。 |
| R06 | R01 的第一句，后接 `I do not want this itinerary saved.` | 同 R01。 |

R01/R04/R06 的拒绝轮复用 B 现有无模型早退断言，核零新增模型/工具 attempt、零 NEEDS 规划绑定、零 Trip 提交。R03 核正式写入为零，预览行为按候选实际能力记录。任何「已保存」说法都须与持久提交吻合。

## 追问及后续补充

| ID | 依次发送 | 预期 |
|---|---|---|
| C01 | `Plan a three-day trip to Beijing.` → `Starting tomorrow.` | 首轮只追问缺少的开始日期，未保存。第二轮沿用已明确的三天，得到 11-10 至 11-12，齐备后仅提交一次。 |
| C02 | `帮我规划三天的北京行程。` → `北京，从明天开始，玩三天。` | 首轮追问，补充后与 C01 同期，只提交一次。 |
| C03 | `Plan a trip to Beijing for three days starting tomorrow.` | 得到同一日期范围。资料已齐时直接保存，避免再次问已给出的日期或天数。 |

追问须是可读的完整答复。补充必须绑定当前会话及对应原消息。只读时间线不会执行额外写入、重新派发或重复计费。

## 日期归属

| ID | 依次发送 | 预期 |
|---|---|---|
| D01 | `Plan a trip to Shanghai from 2026-12-01 to 2026-12-03. Plan a Beijing itinerary.` | 北京日期缺失，追问，零北京正式写入。 |
| D02 | `Plan a Beijing itinerary. Trip dates from 2026-12-01 to 2026-12-03 are for Shanghai only.` | 同 D01，日期限定词适用于上海。 |
| D03 | `Plan a trip to Shanghai from 2026-12-01 to 2026-12-03.` → `2026-12-04 to 2026-12-06.` → `Beijing.` | 北京不得继承两组日期中的任何一组。追问北京日期，零北京正式写入。 |
| D04 | `Plan a trip to Shanghai from 2026-12-01 to 2026-12-03.` → `Beijing, from 2026-12-11 to 2026-12-13.` | 北京只用 12-11 至 12-13，齐备后只保存这一组日期。 |
| D05 | `Plan a trip to Beijing starting tomorrow, but we have a 7 day Shanghai trip later.` | 北京行程仍缺完整日期。追问北京天数或结束日，零正式写入。 |

用签名私有 PG 的 `scripts/pg_suites.py hk_typed_worker` 检查正文与实际写入。阶段②的 PR 证据按上表列出原件、预期、实际和判定，保留三个历史 HOLD。

## 离线定位记录

同一输入离线调用各提交的 `lio_planning_grounding.py`。R01–R06 检查 `planning_withdrawn`，C01–D05 检查 `grounded_fields`。这些结果只定位解析分支，签名 API、实际 Trip 写入和计量仍需按上文复验。

| 历史 head | 可重现的差异 |
|---|---|
| [ad7535dc](https://github.com/JTCAO515/G2C/commit/ad7535dc) | 缺少拒绝保存判断。C01–C03 日期缺失，D01/D02 错带上海日期，D03 接受另一组旧日期，D04 误取上海范围，D05 借用上海七天。 |
| [531dca85](https://github.com/JTCAO515/G2C/commit/531dca85) | C01/C02 与部分换城得到修正，R02/R03/R06 仍未阻止保存。C03 日期缺失，D01/D02 仍取上海日期。 |
| [226ac2d7](https://github.com/JTCAO515/G2C/commit/226ac2d7) | R02、C03、D01 得到修正，R03/R06 仍未阻止保存，D02 仍取上海日期。 |
| [c7c720f3](https://github.com/JTCAO515/G2C/commit/c7c720f3) | 上述 14 条离线断言通过。此提交是本地准备候选，阶段②精确发布和公网验收待执行。 |
