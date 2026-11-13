# #924：首份计划的显式节奏分组

以 #922 §3.9 为准：轻松 **2 景点 + 2 餐**，适中 **3 + 2**，紧凑 **4 + 2**。
这是 WP1 的生成侧配套，不是 WP7 structured.4，也不证明 G6 全项通过。

## L 装配接口

`cj_draft.rich_first.LioRichFirstPlanPublisher` 和
`LioRichFirstCalendarPublisher` 分别沿用原 grouped dated/calendar publisher 的构造参数，
另外必须传 `pace=cj_draft.rich_schema.Pace.RELAXED / MODERATE / PACKED`。
L 从受保护的画像事实编译这个枚举；缺省由 L 显式选 MODERATE，并向用户说明。
不得把 prompt 中的版本字符串或客户端 flag 当作选择格式、修改来源或授权发布的依据。

`grouped_input` 仍冻结实际 publisher、捕获的 source context、system、messages、provider；
原 worker / model.draft 注册出口使用同一个 packet。原件声明和供应商 wire 使用
`grouped_plan.response_format` 与 `response_format_sha256` 的同一选定 profile。
实际生成 system 可通过 `rich_first.rich_system_for(ordinal=...,pace=...,guidance=...)`
同源派生，装配来源清单时使用相同的真实 guidance；此函数不激活策略或授予调用资格。
新增六个生成版本，旧四个版本和 response_format 字节保持不变：

| 日历 | 版本（`<pace>` 为 relaxed / moderate / packed） |
| --- | --- |
| 有日期 | `TRIP-lio-dated-<pace>-first.1` |
| 无日期 | `TRIP-lio-day-<pace>-first.1` |

首份响应恰为 `version,title,days`；每天恰为 `[日期或天序,sights,meals]`。
每行仍为 `[id,完整名称,HH:MM,HH:MM,subjects]`。例如轻松一日：

```json
{"version":"TRIP-lio-day-relaxed-first.1","title":"北京一天","days":[[1,[["a","故宫","09:00","11:00",["self"]],["b","景山公园","14:00","16:00",["self"]]],[["c","京味斋","12:00","13:00",["self"]],["d","四季民福","18:00","19:00",["self"]]]]]}
```

生成分组显式区分景点和餐饮，不能根据地点名称猜测。代码检查每组数量、完整日期/天序覆盖，
复用原 grouped decoder 校验日期、ID、参与者和时区，再按起始时刻排列。
原 publisher 继续检查内容、正向时间区间、来源窗口、固定项、参与者、当前版本、签名与唯一提交。
新格式不接受旧首份响应，旧格式也不接受新响应；截断、重复键、伪造字段和非法分组整份拒绝，
不修补、不重试供应商、不在供应商失败后换格式。

## 兼容范围与退出条件

- 仅对 **无已保存上下文、NEEDS fixed_items 为合法空数组** 的首份计划启用。
- 已有行程走原 delta；来源带固定项的首份计划走原 first profile。这在调用前选择，
  原条目、标题、来源、顺序和锁定项完整保留。无可信类型时不猜、不删、不用新增条目数冒充总密度。
- 保存仍为 structured.2 / structured.3，不向旧内容追加 kind，不改 structured.1–3、迁移或历史。
  `sights/meals` 仅是模型提议的类别，不是高德确认，也不成为已保存的类型事实。
- 这段兼容范围由 structured.4 与 WP8 新策略接替后退出；旧版本和消费者路径仍保留。
- 到达/离开日规则、POI/路线、住宿片区、开放时间与理由/提醒由 WP7–9 落地。
  此切片的数量检查不把这些未完成项记 PASS；固定项/retained 的总丰富度保持 UNKNOWN。

## 验证边界

C 的 L0 覆盖中英 4–5 天、三档节奏、有日期/无日期、完整名称/subjects 保持、旧 delta 保全与负例。
相关私有 PG 组验证原签名发布保护仍通过；这不代替 L 在实际装配后负责的中英各 3 条签名组合。
供应商的输出上限本切片不改（现有 grouped wire 为 1024 tokens）；必须用真实新配置证明多日输出完整，
不能用 fixture UTF-8 长度或格式正确性推断供应商 token 数、延迟或全国规划通过。
L 装配、部署、真实模型、#815 新窗口和 JT 复测仍单列 UNRUN；只用 WP0 合并后的原额度。
