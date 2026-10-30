# RUN-TRAVEL-READ@1 — frozen

JT 2026-10-30 新版本预授权下发布，供 MESSAGE-send.2 原关联读取。
不修改旧 RUN-display.1、RUN-draft-status.1/.2 的 schema、来源规则或状态机。

- `GET /v2/run-display?message_id=<original>`：RUN-display.2，字段恰为
  request_id、version、snapshot（复用旧九字段 RunDisplaySnapshot）、reference
  （MESSAGE-travel-reference.1）。
- `GET /v3/run-draft-status?message_id=<original>`：RUN-draft-status.3，旧 .2
  原字段加 reference；budget_exhausted_stage 仍只读持久 budget_denied，不能从失败推断。

两入口只支持持久 marker=1、完整不可变 reference 的原 MESSAGE-send.2。
旧消息继续使用其原读取版本，不自动猜旅行或 fallback。缺失、损坏、错 owner、
未知依赖及不支持版本均拒绝，沿现有 RUN_*_UNAVAILABLE / unknown / retry_safe_read。
未知原动作不授权新 generation、message、attempt 或旅行重绑。

响应在同一 canonical MESSAGE history callback 内完成：先核原 receipt/raw hash/
reference，再以原 binding 两次读 RUN、两次核原来源，编码及大小检查后 fresh AUTH
return guard 才发布。Ctx reference 不要求仍为当前旅行，因此可核失效后的原历史事实；
它不授新步骤/发布许可。读取没有 provider、USAGE reserve/claim/settle 或新 RUN 写入。
owner_scope 不进入 wire，客户端仍须按原环境/owner/generation及当前显示身份核晚到结果。

新入口沿 host 显式 ID/文本/响应上限；新模型仅由根 OpenAPI 生成到后端。
App 新生成/采用由 A 线执行；B 的合成本地 L1 不代表 A/C typed 业务或真实服务验收。
