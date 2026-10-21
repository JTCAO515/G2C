# ADR 索引

`accepted` 仅表示明确确认的范围/行为；`proposed` 是待验证建议，不是已实现或不可替换栈。实现状态仍由 Issue 和版本证据说明。新证据改变结论时，以新 ADR 引用并 supersede 原记录，保留历史，不原地把提议伪装成确认。

| ADR | 状态 | 决策 |
|---|---|---|
| [0001 产品与用户控制边界](0001-product-boundaries.md) | accepted | 当前品牌、受众、双语四 Tab、完整长记忆、Muse、全新数据与开工边界 |
| [0002 技术候选与替换条件](0002-runtime-candidates.md) | proposed | SwiftUI / Auth / OpenAPI、Python API、单主 Agent / 持久执行 / 内部记忆与旅行工具 |
| [0003 正式状态、恢复与撤回](0003-state-and-recovery.md) | proposed | 单一业务权威、确认与版本、幂等/未知结果、记忆有效性与撤回 fence |

依据是 CJ Planning（官方 `read_thread` 完整分页读取，线程 `01a15d68-fd8d-7473-991e-2d604486ae75`）、JT 本轮补充与 GitHub r3 Issue。较早三 Tab、弱化首批长记忆等建议已被后续明确确认替代。各 ADR 的验证项仅是未来任务，不在本轮试验。
