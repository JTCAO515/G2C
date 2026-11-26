# 景点预约规则（唯一来源）

事实数据线维护；#1755（W5-1）把原先两份规则合成这一份。

- `booking-rules.v1.json`：唯一数据源。每条规则写明官方来源 `sources` 和核对日 `checked_on`（北京时间、实际重读来源的日期）；`review_days` 是复核期限，必须等于 App 的 `LioAttractionBookingRule.reviewDays`。过期后 App 不再显示数字和提醒，只指向官方渠道。
- `generate_ios.py`：校验数据源，并生成 `ios/Modules/CJShell/Sources/CJLioUser/LioAttractionBookingRules.swift`。Swift 文件不要手改。
- CI：`backend/tests/test_attraction_rules_source.py` 会重新生成并逐字比对；数据改了却没重新生成，`python` job 就会失败。

## 改规则

1. 重读官方来源（场馆官网或政府网站）。第三方攻略只能当线索，不写进来源。
2. 修改 JSON，`checked_on` 改为重读当天。来源没写的值保持 `null` 或不写，不推断。
3. 在仓库根目录运行 `python3 -B knowledge/attractions/generate_ios.py`，把 JSON 和 Swift 一起提交。
4. 在 `reviews/` 下记录逐条依据。

字段含义见 `LioAttractionBooking.swift` 里 `LioAttractionBookingRule` 的注释。`closed_weekdays` 为 `null` 表示来源未写，`[]` 表示来源写明没有固定闭馆日。

## 与 `knowledge/visitor` 的关系

`knowledge/visitor/entries-v3/` 里另有一套场馆条目，与本表有 8 处重叠（故宫、碑林、成博、熊猫基地、兵马俑、八达岭、上博两馆），且已出现冲突。这些条目没有运行时消费者，由 #1755 Part 2 下线，此后场馆预约规则只认本表。
