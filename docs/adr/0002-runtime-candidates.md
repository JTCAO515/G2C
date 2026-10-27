# ADR-0002：技术候选与替换条件

- 状态：**proposed**；以下均未安装、组合验证、锁版或配置
- 日期：2026-10-21
- 验证 owner：CJ-002 [#2](https://github.com/JTCAO515/G2C/issues/2)、CJ-003 [#3](https://github.com/JTCAO515/G2C/issues/3)、CJ-004 [#4](https://github.com/JTCAO515/G2C/issues/4)、CJ-005 [#5](https://github.com/JTCAO515/G2C/issues/5)

## 背景与选项

需要移动端双语体验、可靠执行、可管理长记忆和有依据的旅行规划。选项包括重用旧完整栈、组合成熟组件并重建业务核心、同时引入多个 Agent/记忆框架。建议采用第二项，复用经过筛选的规则/反例和小组件，不搬完整旧 Session、全部迁移或旧治理流程。

## 提议

| 层 | 首选候选 | 验证与替换条件 |
|---|---|---|
| 客户端/认证 | SwiftUI、Supabase Auth 官方 Swift SDK | CJ-004 验证 SDK/会话与候选系统矩阵；认证供应商不拥有旅程写权限。最低 iOS 由 CJ-001 定，不由依赖倒推 |
| API/生成 | Python FastAPI/Pydantic、HTTPS JSON + SSE；Swift OpenAPI Generator + URLSession transport（讨论简称 Swift client） | CJ-004/005 验证正常/错误/流中断与生成一致性；无法满足时比较最小替换，保留唯一正式契约 |
| 正文渲染 | 原生能力与 Textual 候选对比 | CJ-004 验证中英混排、选择、滚动/大字体；无版本兼容结论，失败则替换独立渲染层，不提高产品最低系统迁就组件 |
| Agent/模型/执行 | 单主 Agent；AgentScope + Qwen3.8-Flash + 优先验证 DBOS | CJ-002 固定真实版本/端点/模型 ID，验证流式、工具、取消、重启、未知费用；若不满足，按同用例评估 Pydantic AI + DBOS，最终只保留一个主框架 |
| 正式数据/记忆 | PostgreSQL（Supabase 候选）保存业务状态；ReMe 只作内部记忆组件 | CJ-003 验证隔离、版本、清理、重建；不满足同标准时评估 Mem0，最终一套。CJ 管理授权、正式条目与撤回，组件不是第二权威 |
| 旅行证据/计算 | Gaode（高德）地点与路线，按需时效事实来源，确定性校验 + OR-Tools | CJ-012/034/035 [#13](https://github.com/JTCAO515/G2C/issues/13)、[#16](https://github.com/JTCAO515/G2C/issues/16)、[#18](https://github.com/JTCAO515/G2C/issues/18)验证身份/坐标/时间/来源/超时。求解成功不证明输入事实真实 |
| 质量/运行 | 行为测试，Promptfoo 作为评测候选；持久存储与 API/worker 分工 | CJ-028/027 [#32](https://github.com/JTCAO515/G2C/issues/32)、[#30](https://github.com/JTCAO515/G2C/issues/30)给证据；宿主/地域/容器/ECS/Vercel 均未定，不创建资源 |

## 取舍

成熟依赖可集中处理认证、生成和求解，但组合正确性、许可、地域网络、长期存储与成本仍由 CJ 验证。DBOS 不等于外部调用 exactly-once；ReMe 的内部隔离不能替代真实账号授权。保留替换接口有助于验证，现阶段不建设通用多模型或多记忆平台。

## 验证与接受条件

对应 Issue 产出真实依赖锁定、许可/限制、正负用例、失败和未知结果、必要设备/服务证据后再更新 ADR。真实付费调用须未来获准范围与预算；缺凭据记 UNRUN。本轮不引用旧研究中的版本号作为当前兼容保证，也不为写 ADR 启动技术试验。
