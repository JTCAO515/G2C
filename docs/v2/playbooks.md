# JT Agent 建单与 playbook

[#1711 Part 1](https://github.com/JTCAO515/G2C/issues/1711#issuecomment-7183383867) 提供本地合成演练后端。工作台案件页面归 Part 2。第 1 阶段的 [Signal 和 Case](signal-contract.md) 继续使用原版本。

## 建单与合并

`CaseWorkflow.ingest(signal)` 为首次接收的受支持信号创建随机 UUIDv4 的 `case_id`。Case 只存信号 ID 与选定的 playbook 版本，内部会话及行程关联留在建单器内。来源混有多个会话或多个已知行程版本的信号直接拒绝。

| 情况 | 处理 |
| --- | --- |
| 同一个信号 ID、内容完全相同 | 返回原案件的当前状态。不开新单、不重复产生建单审计。 |
| 同一个 ID、内容不同 | 拒绝并保留原关联。 |
| 不同 ID、同会话、同信号类型、同行程引用版本，已有未关闭案件 | 向该案件附加信号 ID。无已知版本视为独立的一组。 |
| 不同 ID，且没有匹配的未关闭案件 | 开新单。关闭案件收到原 ID 的重投时仍返回原案件。 |
| 类型没有对应 playbook | 拒绝建单并报告原因。 |

`ingest` 返回 `CaseIntake(execution, audit)`。开单和合并返回审计事件，幂等重投的 `audit` 为空。禁止将 Case 里的标识当作员工权限凭据。

## 首批 playbook

每个案件固定创建时的 playbook ID、版本和步骤顺序。

| Playbook · 版本 1 | 信号 | 顺序及模式 |
| --- | --- | --- |
| `p0_assistance` P0 协助 | `safety`、`illness` | `prepare_emergency_guidance`（`ai_auto`，准备演练指引）→ `verify_assistance`（`human_only`，人工核实）→ `draft_assistance_summary`（`ai_draft_human_confirm`，拟定协助摘要） |
| `document_loss` P1 护照丢失 | `document_loss` | `prepare_replacement_checklist`（`ai_auto`，准备流程清单）→ `verify_document_situation`（`human_only`，人工核实情形）→ `draft_document_guidance`（`ai_draft_human_confirm`，拟定指引） |
| `flight_change` P2 航班变动 | `itinerary_disruption` | `summarize_flight_change`（`ai_auto`，整理变动）→ `draft_itinerary_change`（`ai_draft_human_confirm`，模拟改行程，**须客户同意**）→ `simulate_paid_rebooking`（`human_only`，模拟付费改订，**须单独客户同意**） |
| `ai_failure` P4 AI 失效 | `ai_failure_loop` | `summarize_repeated_failure`（`ai_auto`，整理反复失败）→ `verify_unresolved_request`（`human_only`，人工核实）→ `draft_recovery_summary`（`ai_draft_human_confirm`，拟定恢复摘要） |

目录按步骤效果 `change_itinerary` 和 `spend_money` 推导客户同意门槛。工作人员确认草稿和客户同意是两个独立操作。P0 的规则识别与页内告警继续走信号路径。

## 工作台接口

每个本地工作台实例持有同一个 `CaseWorkflow`。`get(case_id)` 读当前状态。返回的 `jt-case-execution.v1` 包装原 `jt-case.v1`，增加 `revision`、从 0 开始的 `step_index`、`draft` 和 `customer_consent_recorded`。完成最后一步后，案件关闭且 `active_step` 为空。

| 调用 | 行为 |
| --- | --- |
| `advance(case_id, expected_revision=..., actor_id=...)` | 完成当前的自动步骤或登记人工步骤完成。遇到需人工确认的模式，首次推进只生成合成草稿。有待审草稿时继续推进会被拒绝。 |
| `confirm(case_id, expected_revision=..., actor_id=...)` | 确认当前草稿并进入下一步。有客户同意门槛时，须先有当前步骤的独立同意。 |
| `reject(case_id, expected_revision=..., actor_id=...)` | 驳回当前草稿，保留在该步骤，清空该次草稿及同意。再次推进生成新的草稿。 |

这些操作一律返回 `CaseActionResult(execution, audit)`，包括过期请求、缺少草稿或同意等拒绝结果。审计提供时间、动作、员工 ID、案件 ID、步骤 ID、版本号、结果和固定原因，不携带对话或草稿。Part 2 工作台在调用前完成员工会话、角色、案件范围和 CSRF 校验，从会话提取员工 ID，并把返回的审计追加到现有审计存储。工作台使用服务端持有的案件状态，向浏览器展示当前动作与结果。

可信合成演练脚本可单独调用 `record_synthetic_customer_consent(case_id, expected_revision=..., step_id=...)`。这一步针对当前案件、当前步骤和当前版本，有草稿的步骤还须已有待审草稿。工作台员工接口不提供此操作。过期版本、错步骤、重复确认和已关闭案件都会拒绝。完成或驳回会消耗或清除当前同意，下一步须另行确认。

本地状态只存内存。草稿是固定的合成文本，推进只改演练状态。接口不修改正式行程，不发起支付，不向客户发送消息。真实接入仍按既有授权和确认流程办理。
