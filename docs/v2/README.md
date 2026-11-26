# JT Agent V2

按 JT 2026-11-25 [#1702](https://github.com/JTCAO515/G2C/issues/1702) 的决定，工作台先做成本地桌面网页，供识别复核和后续建单演练。V1 与 P2 交付范围沿用原定义。

| 阶段 | 交付 | 范围 |
| --- | --- | --- |
| 0 | 修订 ADR，冻结工作台规格、信号和案件的内部接口 | 已获准 |
| 1 | 本地工作台、员工登录、脱敏、规则、模拟判断和合成评测 | 已获准，仅合成数据 |
| 2 | 本地建单、playbook 和人工确认演练（#1711–#1713） | 已获准，阶段 1 完成后另行派工，仅合成数据 |
| 3 | 内部部署及真实存储 | 待 JT 授权香港内网入口和资源，届时与 S 线协调 |
| 4 | 真实 CJ 事件接入与影子模式 | 待 JT 授权，依赖 #225、#714，CJ outbox 归 S 线 |
| 5 | 经 CJ 回环，包括主动消息、服务会话、候选记忆 | 待 JT 授权及相应契约、App 工作 |

阶段 0–2 使用本地合成数据和模拟模型，不接外部模型、外部服务或真实用户数据。阶段 1 先交付信号队列与复核，阶段 2 接上[案件与 playbook 演练](playbooks.md)。涉及资金或正式行程的任何动作仍须客户本人确认。

| 线 | 文件归属及交接 |
| --- | --- |
| JT1 规格与骨架 | `docs/v2/**`、`jt/__init__.py`、`jt/common/**`、`jt/synthetic/**`。#1703 单独修改 ADR-0005，由 JT 合并。#1706 Part 1 另有一次 `scripts/test.py` 共享锁及五包骨架授权。 |
| JT2 工作台 | `jt/workbench/**`。Part 1 后做 #1707，Part 2 后消费共用模型做 #1708。 |
| JT3 识别引擎 | `jt/engine/**`、`jt/eval/**`。Part 1 后做 #1709，Part 2 后消费共用模型做 #1710。 |

跨线需求在 [#1702](https://github.com/JTCAO515/G2C/issues/1702) 交给文件拥有方，其中 `jt/common` 由 JT1 负责。[ADR-0005](../adr/0005-proactive-fulfillment.md) 定义 V2 主动履约和人工确认边界，[ADR-0009](../adr/0009-jt-agent-contract-reservation.md) 约束未来 CJ outbox、回环和数据清理。当前实现依据[工作台规格](workbench.md)和[识别与数据契约](signal-contract.md)，真实接入的前置条件见[影子模式](shadow-mode.md)。
