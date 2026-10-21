# CJ-002 local candidate evidence

- taskID：CJ-002；Issue：[#2](https://github.com/JTCAO515/Go2China/issues/2)
- status：本地选型段 code-ready；整票未完成，待 Main 路由 Review/Testing。
- repository：`https://github.com/JTCAO515/Go2China.git`
- base：`13905e4587feb8611ebde5e3621024f3338532ae`
- branch：`cj/002-runtime`；精确 head 以本聊天最终交付和本地 Git 为准，避免在提交内容内自引用 commit。
- 写权：只改 `spikes/runtime/**`；原工作树只读，独立克隆初始 clean，所有运行产物隔离。
- requested model：**UNKNOWN**（任务包未提供本线程实际创建配置）；项目执行默认偏好为 `gpt-6.1-sol / medium`。accepted/current effective：**UNKNOWN**，无有效值读回，不声称实际切换成功。

## 实际结果

| 层 | 状态 | 证据与结论 |
|---|---|---|
| 依赖/环境 | PASS | Python 3.12.14、AgentScope 2.0.10、DBOS 3.3.0；固定锁和官方包元数据；`uv sync --frozen --offline` 通过 |
| 首轮本地矩阵 | 14 PASS / 2 FAIL（已修） | `evidence/initial-validation.json`；完整 stdout/stderr 在 `initial-process-records.json` |
| 取消接口修复定向 | 2 PASS | `evidence/cancel-validation.json`、`cancel-process-records.json` |
| 最后模型结果到达后的取消 | 1 PASS | `evidence/cancel-before_publish-validation.json`、对应 process-records |
| 离线 SDK | 3 PASS | `evidence/sdk-probe.json`：中英流解析、双层零重试、显式策略结构失败；是 MockTransport |
| 独立 Review/Testing | UNRUN | 作者自测不替代独立职责 |
| 真实 provider、费用、地域网络 | UNRUN / UNKNOWN | 无预算/新凭据，未发送请求；公开 model ID 不证明账号可用 |
| PostgreSQL、真实账号、产品 HTTP/SSE | UNRUN | 本段仅本地 SQLite/Agent 事件，未绑定共享正式契约 |
| CI、集成、推送、部署、真机 | UNRUN | 本任务授权不包含这些动作；无推送或资源创建 |

有效场景共 17 项：中英各一、7 个进程退出窗口、SIGKILL、3 个取消窗口、超时/结构失败/工具失败、业务与 attempt 边界。

- 已完成 `prepare` 步骤恢复后执行次数仍为 1。
- intent 后、发送中、收到响应但未落回执三个崩溃窗口：恢复后累计 dispatch 分别保持 0 / 1 / 1；换 workflow 也不增加。
- attempt 完整响应已保存但 DBOS 未存步骤结果时，恢复读取原响应；正常两轮总 dispatch 仍为 2。
- 业务事务提交后未保存工具步骤结果即死亡，恢复仍只有一条业务回执。
- 在途模型取消、业务提交后取消、最终结果发布前取消：终态均保持 CANCELLED，重启不复活；已提交回执仍可读。
- 8 个并发本地相同业务动作只生成一条同主体回执；不同输入拒绝，不同合成主体作用域独立。此项不证明真实认证隔离。

## 失败与证据复用

首次取消命令已执行后，读回使用不存在的 `DBOSClient.get_workflow_status`，因此两项 FAIL；没有把命令异常当取消未发生或盲重试。控制器终止了自己创建的暂停 worker，保留该轮日志。修复只将查询改为 `client.retrieve_workflow(id).get_status()`，在新隔离数据库定向重验取消、释放在途步骤、回执读回与重启终态。14 项初次通过的场景复用；其 workflow、step、ledger 源码行为没有变化。

后续只新增 `cancel-before_publish` 场景和验证选择器；依赖清单补列已锁定/已安装的直接使用包，没有改变安装版本。各证据保留实际执行时源码 hash，最终源码 hash 另见 `evidence/candidate-sources.json`。不要把初轮旧 hash 冒充最终文件 hash。

早期手动 smoke 暴露 2.x API 适配问题（权限 decision message、reply_stream、formatter、async step），在正式矩阵前已修复，原本地数据库仍保留于 `.runs/smoke*`。无真实服务失败被隐去。

## 结论、阻塞和下一步

唯一主候选保留 AgentScope + DBOS。硬语义在本地可通过小型 adapter 达到，不启动 Pydantic AI 对照或保留双主框架。这个结论只支持继续验证，不代表生产框架/模型组合已最终采用。

后续范围必须明确：新账号/工作空间、目标地域与已核端点、真实模型 ID 接受情况、调用/输出/费用上限、UNKNOWN 对账能力；在此之前真实调用保持 UNRUN。RUN/USAGE owner 固定正式契约后，将持久步骤/原 attempt 查询/事务回执接入同一 API 与授权边界。若获准真实验证证明必要的工具/流式/输出上限或恢复语义不可满足，再按相同用例有界评估替换主框架。

本段完成后等待，不改 Issues/HANDOFF/原 13 文档，不自行创建线程、推送、合并或部署。
