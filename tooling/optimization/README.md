# GEPA 离线 Fake 适配（#763）

本目录只做离线接线：真实 GEPA 搜索器 → Fake 调用 → 评分桩 → JSON 候选。
两个公开合成任务（中英各一）没有用户数据、真实工具或模型请求。
桩的分数是三个文本槽与合成目标的匹配比例，**不表示真实效果改善**。
不会注册到用户请求链；所有制品均为 `FAKE_ONLY`、`runtime_eligible: false`、
`promotion: UNRUN`。没有真实模式、服务端点、凭据读取、部署或新费用账本。

## 独立环境与官方版本

从仓库根执行，macOS/Linux，使用 Python 3.12–3.14（实测 3.14.7）：

```sh
uv sync --project tooling/optimization --locked --python 3.14
uv run --project tooling/optimization --locked python -B -m unittest tooling.optimization.test_optimization -v
uv run --project tooling/optimization --locked python -B -m tooling.optimization run --run-dir .local/optimization/demo
```

环境为本目录 `.venv`，根项目依赖不变。`uv.lock` 固定 **gepa 0.1.4** 及下载摘要。
选用基础包，不安装 `full`/跟踪/模型 SDK；此版本基础包无第三方运行依赖。
官方声明 Python `>=3.10,<3.15`，本项目收窄为 `>=3.12,<3.15`。
GEPA 是 MIT，发行包保留许可证及 Lakshya A Agrawal 的版权声明；不复制其实现。
升级须重新核接口、依赖、许可与恢复负例，旧检查点不能跨版本恢复。

核查来源（2026-11-11）：

- [PyPI 固定版本与发行文件](https://pypi.org/project/gepa/0.1.4/)
- [固定版本 MIT 许可证](https://github.com/gepa-ai/gepa/blob/v0.1.4/LICENSE)
- [固定版本 optimize 接口](https://github.com/gepa-ai/gepa/blob/v0.1.4/src/gepa/api.py)
- [固定版本 GEPAAdapter / EvaluationBatch](https://github.com/gepa-ai/gepa/blob/v0.1.4/src/gepa/core/adapter.py)
- [固定版本反思异常处理](https://github.com/gepa-ai/gepa/blob/v0.1.4/src/gepa/proposer/reflective_mutation/reflective_mutation.py)

实际调用 `gepa.optimize(seed_candidate, trainset, valset, adapter, ...)`；适配器实现
`evaluate`、`make_reflective_dataset`、`propose_new_texts`，返回 `EvaluationBatch`。
读取 `GEPAResult.best_candidate` / `val_aggregate_scores`。
固定 seed、轮换单组件、二条反馈、禁 merge/缓存/外部跟踪，最多四个被接纳候选。
全部提议（包括未被接纳者）保存在动作记录中，合法提议另有内容寻址制品。

GEPA 的 `max_metric_calls` 在算法边界检查，不能代替出口逐次准入。
本适配器在每次任务/评分/反思前分别核持久累计上限，默认 48/48/6；
跨恢复不重置。默认累计活跃运行时间 300 秒，允许 `--seconds` 调整至最多一天。
使用 `SIGALRM` 中断超时调用，SIGINT/SIGTERM 同样安全停止；恢复前固定原参数。
GEPA 0.1.4 的批量反思会捕获普通异常并重试，即使 `raise_on_exception=True`。
本层将反思失败转为专用 `BaseException` 停止控制流，避免库内重发。

## 停止、恢复和状态

```sh
uv run --project tooling/optimization --locked python -B -m tooling.optimization stop --run-dir .local/optimization/demo
uv run --project tooling/optimization --locked python -B -m tooling.optimization status --run-dir .local/optimization/demo
uv run --project tooling/optimization --locked python -B -m tooling.optimization resume --run-dir .local/optimization/demo --clear-stop
```

`STOP` 文件让已准入调用收尾，阻止下一次调用与最终选择发布；不自动删除。
`resume --clear-stop` 是明确恢复动作。SIGINT/SIGTERM/超时若发生在调用中，结果保留 UNKNOWN。
运行输出末行为状态 JSON；`COMPLETED` 退出 0，停止/未知退出 2，异常为非零。
已完成运行的重复恢复不派新动作。耗尽累计调用或时间预算不能通过恢复扩大。

`checkpoint.json` 保存运行清单、所有动作的请求/摘要/原 attempt ID、开始/结束时间、
回执、失败类型，以及运行/停止事件。先 fsync 意图，再调用，再 fsync 回执；
原子替换并 fsync 目录。系统文件锁保证同一目录单 writer，进程退出自动释放。
SIGKILL 留下 PENDING 时，恢复将其变成 UNKNOWN，并在任何调用前停止。
未知结果、无效回执与反思异常不自动重试；保留原 ID，待未来 B 提供只读核原动作接口。
可序列化回执先持久保存原 JSON 与摘要，再校验格式；无效提议保留原内容、FAIL 与拒绝原因。
非 JSON 响应或无回执异常保留 UNKNOWN，不凭异常推断未执行。
确定失败单列 FAIL；任务明确失败以零分及失败轨迹参与 Fake 反馈，不伪装成成功调用。
缺评分证据 UNKNOWN/UNRUN 会停止选择，不能当作零分或 PASS。

恢复使用固定 seed 从头重建 GEPA 内存状态，并按原顺序消费已保存回执；
只有尚未开始的动作会调用桩。请求/顺序漂移即停。JSON 检查点有重复键拒绝与校验和，
不加载 GEPA 的 pickle，不支持导入外来检查点；校验和仅检测损坏，不是签名或权限隔离。
候选记录与最终选择的摘要也固定在检查点，恢复、状态查询和选择发布前读回核对；
包括 COMPLETED 运行在内，制品缺失/损坏会显式报错，不能仅凭文件存在或完成标记成功。
代码 head/文件摘要、Python/GEPA 版本、模型/数据/参数必须完全相同。
因此需在原精确 checkout 恢复；换 head 或改代码后不能续跑旧目录。
本地制品保存在忽略目录或仓库外，不将运行日志或检查点加入 Git。

## 候选格式与约束

`candidate-<SHA256>.json` 为可读取候选记录，`candidate.json` 为最终离线选择引用：

```text
G2C-offline-candidate.1
  candidate_id = SHA256(按键排序、紧凑 UTF-8 JSON fragments)
  fragments / fragment_sha256 / parent_candidate_id
  run_id / provenance
  evidence = FAKE_ONLY / runtime_eligible = false / promotion = UNRUN
G2C-offline-selection.1
  candidate_id / candidate_file / fragments / synthetic_score
  run_id / provenance / 同上离线标记
```

`provenance` 含 Git head、逐源码与锁文件摘要、适配器/模型/评分桩版本、参数、
数据/seed/合成目标摘要、实验来源、允许槽位及策略版本；`run_id` 回链检查点全部尝试。
提示与工具文本逐项 hash，不用显示名代替模型版本。初始候选父 ID 为 null。
候选正文可用标准 JSON 读取，再用 `fragments()` 与 `digest()` 核其格式与内容 ID。

本轮允许表只覆盖**合成控制**的 `prompt.answer_style`、`tool.lookup.description`、
`example.clarification`。反思只能返回本次被选择的槽位，未知/额外/空文本拒绝。
没有任意文件、Python、工具 schema 或配置 patch 执行器。
身份、权限、保存条件、计量、评分器及阈值均不在参数空间；生产提示片段尚未获准交付。
这些文本白名单不替代 B 的身份和业务校验；后续 B 必须将可调文本与权威策略分离。

## 未来 B/D 接口与 #764 起工输入

`contracts.py` 定义 `TaskCaller.call`、`Scorer.score`、`Reflector.propose` 的类型接口：
均传递原 `attempt_id` 与剩余超时。当前只构造 `FakeCalls`，这些是 E 本地 seam，
**不是已交付的 B/D 生产契约**，没有直连真实 provider 的路径。

后续起工需由 Claude 编写新 Goal、JT 转交，至少取得：

1. **B #762 固定版**：真实调用和反思均沿现有身份/工具/唯一费用出口；原动作/原 RUN、
   模型/提示/工具版本、超时取消及原 attempt 只读核对、UNKNOWN 占用和回执关联。
   明确批准的生产文本槽与基线片段摘要，权威权限、保存、计量策略不可调。
2. **D #761 固定版**：`score('development', batch)`、`G2C-dialogue-score.1`、
   `G2C-dialogue-cases.1`，冻结评分代码及数据摘要、可信采集归一化与独立回复标注。
   已合入 PR #774；本轮只读核到代码提交 `ee9026eabaa9be08df804b224983787c969a441b`，
   数据 SHA256 `8e3b9c2d410e569de520243540e364d7fed6033087de8173adc5e87e17fe92f3`。
   实际消费前重新固定交付版；本轮未将 Fake 桩称为 D 评分接线。
3. **#764 预登记**：原 API/harness 基线、模型/工具/环境/数据与候选选择方式；
   指标/停止线、获准预算和资源范围、所有尝试及失败/未知的保留方式。
   费用沿 B，不在 E 新设费用账本。已知硬失败不得被平均分抵消。
4. **#765 D/R 独立比较**：开发/公开验证/受控最终集用途分离，最终题由独立主体保管，
   冻结 hash/分母及实际允许/拒读证据。E 不读取最终题，不自评晋级；
   通过后由 B #766 独立接入可回退配置。用户请求链只能消费以后验收通过的版本。

本轮 #764 真实实验、真实质量改善、D/B 实接、晋级、部署均 UNRUN。
本目录测试未加入根项目默认 CI 入口（本轮仅此目录写权）；执行上方独立环境命令
验证本模块，仓库现有 CI 另行报告。后续自动触发接入需共享入口 owner 授权。

## 停止恢复的验证范围

测试包含实际 GEPA 闭环且 socket 连接禁止、单 writer、三种累计调用边界、
中途 STOP 后回执重放、最后回执后不发布选择、SIGTERM、调用超时、真实子进程 SIGKILL、
反思超时/越界不重发、坏提议原文和原因保留、已知任务失败、重复恢复、
候选/选择制品损坏或丢失、检查点损坏/重复键/版本漂移与顺序漂移。
它们证明 Fake 离线协议；真实 B 的取消传播、计量与只读原动作恢复仍需另验。
