# JT Agent 识别和数据契约

阶段 1 实现以下 Python 内部契约，供 JT2 和 JT3 在本地用合成数据联调。共用模型与接口位于 `jt.common`，脱敏、规则、模型适配器和评测归 JT3，队列、权限与审计归 JT2。阶段 2 才执行建单和 playbook。

## 分类与判定

| `severity` | `signal_type` | 例 |
| --- | --- | --- |
| `P0` | `safety`, `illness` | 遇险、走失、受伤、急病或紧急号码规则命中 |
| `P1` | `document_loss`, `payment_issue` | 护照丢失、被骗、卡冻结或支付异常 |
| `P2` | `itinerary_disruption` | 航班变动、酒店不认单、交通停运 |
| `P3` | `change_request` | 改酒店或日期 |
| `P4` | `ai_failure_loop`, `complaint` | 同一意图反复未解决、工具反复失败、负面情绪上升 |

类型与级别按表配对。规则利用 CJ 已计算的计数、工具与订单状态、时间节点、中英 P0 关键词和紧急号码。P0 规则独立执行，命中后直接发布 P0 Signal。后到的模型结果可单独留作评测证据，已发布的 Signal 原样保留。模型缺席、错误、低置信或不同意均不影响规则。模型结果本身只作建议，由决策层根据规则和 playbook 处理，并保留人工确认边界。

## `DecisionModel`

```python
class DecisionModel(Protocol):
    async def decide(self, context: DecisionContext) -> DecisionOutput: ...
```

- `DecisionContext` 提供 `redacted_fragments: tuple[str, ...]` 和合成事件的结构化状态 `events: tuple[EventRef, ...]`。适配器可使用已脱敏片段、事件类型及归一化状态。内部会话、消息和行程引用用于关联，仅存本地，不作为未来外部模型输入。
- `DecisionOutput` 仅有 `signal_type`、`severity`、`confidence`。前两项必须匹配上表，或均为空表示未建议任何信号。置信度是 `0 <= confidence <= 1` 的有限数。输出校验失败不进入有效模型结果，P0 规则路径继续运行。
- 阶段 1–2 使用本地 `MockDecisionModel`。千问约束输出与 TypeSafe Jev 的适配器在获准评测前无需实现。模型输出没有动作指令、授权或人工确认字段。

## 记录

以下字段为必填，显式允许为空或空序列的字段除外。ID 为非空、不含业务信息的字符串，`case_id` 使用随机 UUIDv4。时间为带时区的时间戳，以 UTC 保存或序列化。数组在 Python 中使用 tuple。反序列化拒绝未知的 schema 版本、枚举和未声明字段。

| 记录 | 字段及约束 |
| --- | --- |
| `EventRef` | `schema_version="jt-event-ref.v1"`，稳定 `event_id`，内部 `conversation_id`，`message_id` 和 `sequence`（两者同时有值或同时为空，序号从 1 开始），`travel_reference_version`（正整数或 null），`occurred_at`。另有以下事件判别字段和状态。 |
| `Signal` | `schema_version="jt-signal.v1"`，稳定 `signal_id`，`source_events`（非空 `EventRef`，按唯一 `event_id` 引用），`detected_at`，`signal_type`、`severity`（必须匹配分类），`redacted_fragments`（允许空 tuple），`rule_hits`（稳定规则 ID，允许空 tuple），`rules_version`，`redaction_version`，`model_outputs`（允许空 tuple，每项为 `model_version` 加 `output: DecisionOutput`）。 |
| `Case` | `schema_version="jt-case.v1"`，随机 `case_id`，`signal_ids`（非空、唯一），`severity`，`created_at`，`status`（`open`、`in_progress`、`closed`），`playbook_id`、`playbook_version`、`steps`（非空，按执行顺序）。 |
| `PlaybookStep` | `step_id`（同一 Case 内唯一），`mode`（`ai_auto`、`ai_draft_human_confirm`、`human_only`），`requires_customer_confirmation`（布尔值）。花钱或改正式行程的步骤必须声明此值为真，即使步骤类别本身可自动处理。 |

Case 通过 `signal_ids` 追溯 Signal，后者持有来源事件引用。Case 无用户 UUID 或原始对话。工作台将队列状态、响应时限、复核和审计独立维护。页面只展示脱敏证据以及已有的 `case_id`，内部来源引用留在服务端。

## 合成事件

`EventRef` 的 `event_type` 和 `event_state` 搭配如下。无状态项使用空对象。计数由合成生成器模拟 CJ 的累计值，JT 消费时直接读取。

| `event_type` | `event_state` |
| --- | --- |
| `message_accepted` | 空对象，须有 `message_id` 与 `sequence` |
| `tool_failed` | `count` 为该会话累计的正整数工具失败次数 |
| `intent_unresolved` | `count` 为该会话同一意图累计的正整数未解决次数 |
| `trip_time_triggered` | `trigger` 为稳定时间节点名，例如 `check_in_due` |
| `order_status_changed` | `status` 为归一化订单状态，首批用 `confirmed`、`failed`、`changed` |

`SyntheticEvent` 为本地封套 `{schema_version: "jt-synthetic-event.v1", ref: EventRef, synthetic_fragment: str | null}`，对话片段只放在 `message_accepted` 的封套里。生成器接受固定随机种子，输出合成片段、事件和种子信号。样本 ID 与时间由合成输入稳定导出，同一随机种子配合同一参数产生相同内容。

合成消息「请叫救护车」的规则种子信号示例：

```json
{
  "schema_version": "jt-signal.v1",
  "signal_id": "sig-syn-001",
  "source_events": [{
    "schema_version": "jt-event-ref.v1",
    "event_id": "evt-syn-001",
    "conversation_id": "conv-syn-001",
    "message_id": "msg-syn-001",
    "sequence": 1,
    "travel_reference_version": null,
    "occurred_at": "2026-01-01T00:00:00Z",
    "event_type": "message_accepted",
    "event_state": {}
  }],
  "detected_at": "2026-01-01T00:00:01Z",
  "signal_type": "illness",
  "severity": "P0",
  "redacted_fragments": ["请叫救护车"],
  "rule_hits": ["p0_medical"],
  "rules_version": "synthetic.1",
  "redaction_version": "synthetic.1",
  "model_outputs": []
}
```

以下输入均须拒绝：`P4/illness`、置信度大于 1、未知 schema 或缺少来源的 Signal，以及携带用户 UUID 的 Case。

真实 CJ 阶段另行获批后，outbox 按 [ADR-0009 §1](../adr/0009-jt-agent-contract-reservation.md#1-事件-outboxcj--jt) 在业务事务中写入引用，按稳定 `event_id` 至少一次投递并由消费方幂等处理。正文从只读白名单视图按引用读取，在本地脱敏。真实 outbox 无 `synthetic_fragment`，其正式字段由 S 线在真实接入契约 PR 冻结。

## 引擎交付工作台

```python
class SignalSink(Protocol):
    async def publish(self, signal: Signal) -> None: ...
```

- JT3 调用 `publish`，JT2 提供将 Signal 纳入队列的实现。正常返回表示已收下，失败应显式抛出并交由调用方处理。阶段 1 使用本地实现。
- 同一个 `signal_id` 的相同 Signal 重投只入队一次，不重复发告警。同 ID 不同内容拒绝并保留已接收内容。引擎重投时复用同一 ID 和内容。
- P0 接收后触发[工作台本地告警](workbench.md#告警与存储)。队列接收即表示存在待复核信号。阶段 1 无自动建单、执行或对客发送。
