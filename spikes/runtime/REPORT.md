# CJ-002 local candidate evidence

## 已确认模型接入（非秘密配置）

续作 base `f48aaf8aa60a1c36712dc43f6ae05712d7f06938`。JT 确认 `qwen3.8-flash` 后，现有模板 `model_id` 填入该模型名，映射兼容请求 `model`；误发数字已由 JT 撤回为无用，不映射任何字段。官方模型表/兼容参数与现有契约一致。仅配置与文档增量，无新增运行时代码；离线预检/请求构造 PASS。缺 key 时仍 not-ready，实际运行窗口留待 owner 在获准执行前填写；无秘密配置授权、未读取秘密、未发真实请求，原 DEFERRED 门不变。证据：`evidence/beijing-model-profile-20261023.json`。

## 北京非秘密目标接入

续作 base `d581235dd513e8eec838c5e05e025b04be2359f6`。已接入 JT 指定北京 workspace/兼容端点，DashScope 端点仅记录，不新增协议实现；实际 model ID/key 未给，模板 model 留空，preflight 明确不就绪。首写 `provider-approval.example.json`，代码增量仅预检缺项枚举增加 model_id。仅离线请求形状和预检差额 PASS，未重跑既有探针、未建 DB/访问资源或读取秘密。见 `REAL-ACCEPTANCE.md` 最新目标与 `evidence/beijing-profile-20261023.json`。真实 provider 仍 UNRUN，原双门限制保留。

## 2026-10-23 provider-entry P2 返修

独立 Testing 对 `50cd98f` 的两项 P2 已在原 owner 范围修复：显式 certifi TLS 验证上下文在 transport 构造前禁用环境 keylog 路径；对截断 JSON 的普通 Unicode 转义做有界保守识别，返回/持久化前拒绝可恢复 key。作者定向 3 组 PASS，待原双门复审；真实调用仍禁止。原逐字探针的 raw-HTTPX keylog 观察仍为 true/aggregate exit 1，实际修复入口另测无 keylog 文件；不把上游观察改报绿。准确原探针归因、结果与复现见 [P2 报告](regressions/provider-p2/REPORT.md)。原 FAIL、17+3 与原新增 7 组均保留，未重跑旧套件。

## 2026-10-23 真实验收续作

本段原固定 head `edb72ff` 的局部 Review/Testing 已接受并进入主线。Main 本次只授权原 owner 准备/执行原 Issue #2 最短真实验收；最新 JT 百炼测试费用授权已接受：费用不设上限，由百炼余额控制。下方原报告中的“费用上限待明确”是历史状态，现已覆盖，不再作为等待事项。

新增独立真实验收入口及配置模板、7 组新增代码离线检查；原 runtime/ledger/SDK probe/validate/锁文件逐字节保全，17+3 未重跑。入口真实发送需要精确 CJ workspace、region、官方 base URL 与专用新 key 的临时安全注入，当前均未配置；仅核存在性，未读取秘密/旧账号/Keychain。真实 provider UNRUN，不能关闭原票。准确安全步骤、命令与范围见 [REAL-ACCEPTANCE.md](REAL-ACCEPTANCE.md)，准备证据见 `evidence/provider-readiness-20261023.json`。

本次 requested `gpt-6.1-sol / medium`（Main 官方调用）；effective UNKNOWN。原 `candidate-sources.json` 对应旧 head，不重写历史 hash；新增候选源码 hash 由 readiness 文件记录。本票无 App/Auth/DB 整票前置，本轮不追加 PostgreSQL 门槛。

## 2026-10-21 原本地段（保留）

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
