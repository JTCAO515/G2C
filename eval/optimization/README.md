# 对话行为评分接口

D 线 [#761](https://github.com/JTCAO515/G2C/issues/761) 的离线评分器。E 固定
`G2C-dialogue-score.1`、`G2C-dialogue-cases.1`、数据文件 SHA-256 和仓库提交。
评分接口只读取观测并返回报告。模型、工具、计量及请求执行由调用方沿 B 的现有出口取得。

## 运行

在固定 G2C checkout 根目录运行：

```sh
mkdir -p .local/optimization
uv run --locked python -B -m eval.optimization.examples --control good > .local/optimization/observations.json
uv run --locked python -B -m eval.optimization --observations .local/optimization/observations.json > .local/optimization/report.json
uv run --locked python -B -m unittest eval.optimization.test_score
```

切换 `--control bad` 得到已知坏样例。验证组在两条命令上显式使用
`--split validation`。`examples.v1.json` 中的中英文本和标注均为合成控制。
CLI 退出 0 表示已生成报告。错误版本、重复/计划外尝试或无效输入退出 2。
E 按报告状态决定是否计入优化。

Python 调用入口为 `from eval.optimization.score import dataset, score`。
`dataset()` 返回公开任务文档和数据 SHA-256。先按任务选择 development，
再按任务语言运行完整会话。传入 `score('development', batch)`。
批次结构：

```json
{
  "version": "G2C-dialogue-score.1",
  "dataset_version": "G2C-dialogue-cases.1",
  "dataset_sha256": "<dataset() 返回的摘要>",
  "run": {
    "candidate_id": "<冻结候选>",
    "adapter_version": "<执行适配器>",
    "model_version": "<模型>",
    "prompt_version": "<提示词>",
    "tools_version": "<工具>"
  },
  "observations": [{
    "task_id": "dev-airport",
    "language": "en",
    "attempt_id": "example/airport/en/1",
    "reply": {
      "attempt_id": "example/airport/en/1",
      "ref": "<可追溯的独立标注>",
      "values": {"mode": "answer", "addresses_request": true, "claimed_effects": []}
    }
  }]
}
```

示例省略 state，因此这格为 UNKNOWN。完整 state 与 reply 输入见运行示例生成的
JSON。每个候选批次一格最多一次，用原任务尝试及原件引用。保留首轮和各次复跑
报告，分开传入，不能择优回填。报告按总计和语言分组输出计划分母、四态、硬失败数。
`rows[].checks[]` 含要求、观测、证据引用与失败或缺证原因。未开始为 UNRUN，
已尝试但缺少关联证据为 UNKNOWN，已知 FAIL 优先。语言分数不参与状态判定。
输出中的 PASS 只表示该格满足此版本判据，产品放行仍走 #32/#702 原评测口径。

## 采集边界

`cases.v1.json` 固定每个任务的预置条件、完整用户轮次、检查和双语变体。
每个证据段都有相同的任务级 `attempt_id`、可定位原件的 `ref`、以及 `values`。
可信 runner 在填表前核同 owner、会话、原动作/原 RUN 和相关轮次。一次任务可以
引用多个原件，ref 指向该次任务的证据清单。缺测用缺字段或 null。0、false 和
空数组只用于已观察完相应范围、可证明为零或没有事件的情况。

| 段 | 证据来源和归一化 |
|---|---|
| `state` 基础 | 原 C 判据读受限角色、其他 owner 的 MESSAGE 读写和正式 Trip 数。每任务从隔离预置状态开始，`memory_item_count` 记录任务过程中新增的未确认条目，排除预置数据。跨账号任务另测目标 Trip 的越权读取、变更与正文私有哨兵。 |
| `state` 写入和撤回 | 原确认提交回执及实际持久状态。新增保存读取确认次数、正式版本、确认的原候选字节摘要与实际持久内容摘要。局部修改及撤回比较完整草稿再投影到变更路径，包含锁定项。取消读取原 RUN 终态、晚到可见发布及取消后派发。工具失败读原工具 attempt 状态和派发数。 |
| `state` 删除后召回 | 原 stop-use 提交与 fence、条目资格、后续完整 provider 输入和最终正文。检测被删除项哨兵并保留另一条有效偏好作正控；这一场景覆盖停止使用和后续召回，物理清理仍沿现有生命周期验收。 |
| `state.verified_effects` | 末轮回复所引用的同一操作、对象和版本中，有独立回执或状态证明的效果。必须排除之前尝试的回执和错目标回执。仅在完整核对后填空数组。 |
| `reply` | 从实际末轮可见内容独立标注行为。澄清标注实际索取的字段，按字段名升序。记录全部执行声明，包括否定与假设语境的区分。回执词、候选自评或模型的 PASS 字段均不可作为状态证明。 |

执行声明使用 `trip_saved`、`draft_undone`、`run_cancelled`、
`memory_withdrawn`、`tool_succeeded`。其它实际执行声明及错对象、错轮次、
错版本声明标为 `unmatched_execution_claim`，无法出现在已验证效果中。对前述五种可验证效果，评分器还逐项核对同次状态。
失败回执不能支撑成功声明，只有效果标签、缺少状态为 UNKNOWN。
自由文本含义未核时保留 UNKNOWN，评分器没有关键词成功判据。

报告复用 `eval/judge.py` 的角色、跨 owner、写入计数和正式版本判据，
以及 `evaluation/cj028/evaluate.py` 的严格 JSON 读取和分母表示。
本切片没有新增依赖或使用 AgentEvals。语言辅助评估如需新增，应另行核实官方
接口与许可证并锁定版本。

## 数据用途和交接

- development 用于开发和 E 的反馈循环。validation 用于冻结候选后的内部核对，
  内容也公开，只能证明公开验证。每次运行以整个任务为单位保留前后轮次与中英改写。
  `trip_family` 分组在加载时检查，同一旅行及其派生任务必须沿用原 family ID。
- 最终题及答案不在本仓库、Git 历史、普通 Issue、共享 worktree 或 CI artifact。
  当前没有已授权且验证过的最终题保管位置，最终集和实际访问拒绝均 UNRUN。
  保管方须先交付隔离存储和不同权限主体，实测受控执行主体可读、普通开发主体拒绝
  （包括镜像、缓存、制品路径）。由保管方在内部去重旅行家族和翻译改写，记录冻结
  数据摘要、任务分母、策略与拒绝证据。对外只交允许公开的汇总和版本引用。
- B [#762](https://github.com/JTCAO515/G2C/issues/762) 交可关联原动作的可信观测。
  E [#763](https://github.com/JTCAO515/G2C/issues/763) 固定上述版本与摘要。
  R [#772](https://github.com/JTCAO515/G2C/issues/772) 独立核对规则和已知好坏样例。
  真实服务回归由 #32/#702 承接。候选比较和晋级等后续 Goal。
