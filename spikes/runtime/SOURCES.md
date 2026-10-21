# 官方来源核验（2026-10-21）

这里只记录公开文档和安装包事实，没有发起模型请求、读取账号或复用旧凭据。

| 内容 | 官方来源 | 本轮结论 |
|---|---|---|
| AgentScope 发布 | [v2.0.10](https://github.com/agentscope-ai/agentscope/releases/tag/v2.0.10)、[PyPI 元数据](https://pypi.org/pypi/agentscope/2.0.10/json) | 安装 2.0.10；Apache-2.0；Python >=3.11 |
| DBOS 发布 | [PyPI 3.3.0](https://pypi.org/project/dbos/3.3.0/)、[元数据](https://pypi.org/pypi/dbos/3.3.0/json) | 安装 3.3.0；MIT；Python >=3.10 |
| 持久边界 | [Workflow](https://docs.dbos.dev/python/tutorials/workflow-tutorial)、[Steps](https://docs.dbos.dev/python/tutorials/step-tutorial) | DBOS 保存完成步骤；不据此推导外部服务 exactly-once。本地重启行为另见实测 |
| 取消 | [Workflow management](https://docs.dbos.dev/python/tutorials/workflow-management) | 在下一步骤开始处中止；在途同步效果不代表回滚。本地测试覆盖在途、提交后、发布前 |
| 模型 ID 与地域能力 | [Qwen3.8-Flash](https://www.alibabacloud.com/help/en/model-studio/qwen3-8-flash)、[发布清单](https://www.alibabacloud.com/help/en/model-studio/newly-released-models) | 官方列出 `qwen3.8-flash`；未找到可据此固定的 dated snapshot，不造 ID |
| HTTP 端点 | [OpenAI compatible Chat](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope) | 区域绑定 key 与工作空间端点；仅记录模板，不选资源或创建凭据 |
| 状态/API 版本 | [AgentScope 2.0.10 文档入口](https://docs.agentscope.io/en/versions/2.0.10) | 使用实际安装的 2.x `Agent.reply_stream`，没有混用 1.x ReActAgent 示例 |

模型页列出北京、新加坡、香港、法兰克福、东京、弗吉尼亚的能力表，含工具调用和结构化输出。它证明公开文档声称支持，不能证明本账号已开放、地域网络可达或费用已知。

端点模板（不是实际资源地址）：

- 新加坡：`https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1`
- 香港：`https://{WorkspaceId}.cn-hongkong.maas.aliyuncs.com/compatible-mode/v1`
- 北京：迁移说明写 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com`；同页 BASE_URL 表却把北京写成 `ap-southeast-1`。存在公开资料矛盾，真实接入前必须从新账号对应区域的官方控制台核地址，不能照抄错误地区。

未核准目标地域/工作空间，因此运行环境没有默认 provider endpoint。真实 model ID 接受、流式工具组合、限额、可用性、用量/费用、延迟、网络及数据处理范围均为 **UNKNOWN / UNRUN**。

离线探针另发现固定版本 `OpenAIChatModel.Parameters(max_tokens=64)` 在出站 JSON 中使用 `max_completion_tokens`。官方通用兼容页列 `max_tokens`；MockTransport 通过不能证明 Qwen 接受该字段。正式 adapter 必须在获准真实验证时确认有效输出上限，不允许无上限放行。

安装源和全部依赖 hash 在 `uv.lock`；安装包关键模块 SHA-256 在 `evidence/sdk-probe.json`。这是包级许可证记录，未宣称完成所有传递依赖的法律审查。DBOS Conductor/Cloud 和 AgentScope 服务端产品未启用。
