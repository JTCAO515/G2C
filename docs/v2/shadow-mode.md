# V2a 影子模式规格：JT Agent 只识别不行动

状态：**规格草案**，未派工。依据是 [ADR-0005](../adr/0005-proactive-fulfillment.md)。它不属于 P2，也不改变 V1 范围。正式开工需要先建 Issue，并满足下文的前置条件。

## 目标

在真实用户流量上，让 JT Agent 只做信号识别。JT Agent 不建单执行，也不主动触达客户，P0 例外。由人工复核和标注，得到各类信号的真实精确率与召回率，并完成 Jev 与 Qwen 的对比、阈值校准，以及每单人工分钟数的初估，作为进入 V2b（建单与工作台）的依据。

## 范围

1. **事件接入**：消费 CJ Agent 已有的消息和运行事件（带稳定 ID），只读，不在对话关键路径上。JT Agent 故障不能影响对话的可用性和延迟。
2. **本地脱敏**：发给任何外部模型之前，先把姓名、护照号、电话、邮箱、精确位置替换为类型化占位符，例如 `<NAME_1>`。脱敏规则版本化，并有回归测试。
3. **识别**：本地规则（P0 关键词、紧急号码、同一意图重复次数、工具错误计数）、`DecisionModel`（Jev）类型化判断，低置信度时升级到 Qwen。三路结果都要记录，用于对比。
4. **信号记录**：每条信号记录来源事件 ID、规则命中、各模型的输出和置信度、最终判定、模型与规则版本、耗时和费用。
5. **人工复核**：每天抽样复核，P0、P1 全量复核，标注“真实级别 / 误报 / 漏报”。V2a 的复核界面可以是最小化的内部报表，不建工作台。
6. **P0 例外**：影子模式下识别到 P0 时**不静默**，照常通知值班人员进行消息协助。CJ Agent 自己的应急指引不受影子模式影响。

## 反目标

- 不建 Case，不执行 playbook，不做人工工作台，不揭示字段。
- 除 P0 外，JT Agent 不向用户发送任何消息、弹窗或推送。
- 不涉及支付、预订和订单写入。
- 不改 V1 / P2 的接口和行为。

## 接口草案（未冻结）

```text
DecisionModel.decide(redacted_context, questions) -> [{question, answer, confidence}]
  questions: signal_type ∈ {none, safety, document_loss, illness, itinerary_disruption,
                            change_request, complaint, ai_failure_loop}
             severity ∈ {P0, P1, P2, P3, P4}
             needs_human: bool
             repeat_unresolved: bool
  实现：JevDecisionModel（首选）、QwenDecisionModel（对照 / 兜底），按配置切换

Signal { signal_id, source_event_ids[], rule_hits[], model_outputs[], final_severity,
         final_type, versions{rules, redaction, models}, latency_ms, cost, review? }
```

接口在 V2a 开工 Issue 中冻结后，才能开始实现。

## 数据与隐私

- **启用前提**：隐私政策和用户说明已更新，写明对话会被自动分析、可能有跨境处理和人工复核；已取得单独同意。
- **数据去向**：信号记录与复核标注登记到存储登记表，接入清理 hook。用户删除记忆或注销时一并处理。用户主动删除必须执行。
- **复核权限**：复核人员只看到脱敏后的片段，不看到用户 UUID。

## 验收

| 项 | 标准 |
|---|---|
| P0 召回 | 标注集中所有 P0 全部识别到；任何一例漏报都要单独复盘，不允许按平均值放过 |
| 分类质量 | 每类给出精确率和召回率，Jev 与 Qwen 分别列出；样本量不足的类标 UNKNOWN，不凭推断给结论 |
| 对话无影响 | 启用前后对话首 token 延迟 p95 和失败率没有可测的劣化 |
| 故障隔离 | 停掉 JT Agent 或 Jev 不可用时，对话正常；本地规则仍能识别 P0 |
| 成本 | 每千轮的识别费用，按模型分别列出 |
| 脱敏 | 脱敏回归测试通过；抽样发给外部模型的内容中没有未替换的个人信息 |

## 前置条件（operator）

- V1 已有真实用户和事件流。
- 隐私政策与同意文案已定稿。
- 已取得 TypeSafe Jev 的 API 访问权限，并确认数据保留与训练政策。密钥存入 Keychain，不写进聊天或文件。
- 值班人员和复核排班已确定。

## 进入 V2b 的条件

- P0 召回达标；
- 主要类别的精确率可以接受（阈值由 JT 定）；
- 每单人工分钟数有初估；
- 合规评估没有阻塞项。
