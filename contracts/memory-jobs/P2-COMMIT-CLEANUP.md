# CJ020 Review P2 — 事务不确定性不能被 cleanup 覆盖

差额 parent：`656fdf37464843754b5298d1c6054df9bb305751`。
原 head 的 20 PASS 保留为历史作者证据，不改写为本次 fixed head 全套重跑。

## 原 FAIL 与修复

只读原 Review 的 `CJ020-656fdf3/probe_commit_cleanup.py` 及日志，并实际执行
原脚本复现：SQLite commit 已成功但 ACK 抛 OSError，随后 close 实际关闭连接
再抛 RuntimeError；外部错误被错误地报告成 RuntimeError，原 job durable state
却已是 completed。该结果违反 CommitUnknown → 原 job/attempt 只读对账语义。

原 probe 与 FAIL 日志按原 bytes 归档在 `evidence/p2-commit-cleanup/`，不覆盖
Review 原文件。归档脚本保留其相对 `snapshot` 路径，仅作原证据；当前候选的
同场景可运行反例为 `TransactionFaults.test_original_review_commit_then_close_double_fault`。

`LocalStore.transaction` 现在先固定 CommitUnknown，再尝试 best-effort close，
close 抛普通异常或取消都不能覆盖该主结果。commit 未知不尝试 rollback、不
自动 retry；无论测试注入点是否实际已提交，都必须重开原库查原 job/attempt。
body 异常且 rollback 成功时保留 body（包括取消）；rollback 自身不确定时报告
CommitUnknown，保留 body 为 cause，后续 close 不能遮蔽。guard close 同样
不能覆盖或吞掉已有事务主异常；成功动作之后 guard close 失败仍报告未知。

没有新增 ID、dispatch、生产 authority、模型、SQLite 自动重放、共享 DB 或
配置变化。只使用任务 tempfile 新文件，没有接旧库。生产 factory 仍关闭。

## 本轮实际限定验证

Python 3.9.6，标准库 SQLite/unittest；新文件：
`backend/memory_jobs/tests/test_transaction_faults.py`。

```
PYTHONPATH=backend/memory_jobs:backend/message:backend/memory_jobs/tests python3 -m unittest discover -s backend/memory_jobs/tests -p test_transaction_faults.py -v
Ran 9 tests in 0.019s
OK
```

9 个新故障组合 PASS，stdout 位于本聊天工具结果：
原 commit-ACK/close 双故障与 completed 读回；commit/close 双取消；commit 前
失败仍 unknown；body/rollback 正常、body cancel/rollback 正常；body/rollback/
close 三故障；body/rollback/close 三取消；guard close 不盖 commit unknown；
guard close 不盖已 rollback 的 body cancel。断言没有 commit 重试或未知后的
rollback，原 completed 的重复完成只返回原回执，不发新 attempt。

受影响旧检查仅执行 5 项，实际 **5 PASS**；原始输出保存于
`evidence/p2-commit-cleanup/affected-regression.log`：commit ACK 恢复、guard
close unknown、final guard rollback、停用拒绝迟到、原 attempt 重开恢复。
其余无影响的 codec/幂等证据复用原 656 的 20 PASS，不重复全套。

独立 Review/Testing 的新 head 复验：UNRUN，交 Main 原双审。
原 FAIL 保留；作者新 PASS 不冒独立解除 P2。真实授权、模型、MEMORY、I 验收、
部署/发布仍沿原 VALIDATION.md 的 UNRUN，不关 Issue #23。
