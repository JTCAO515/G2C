# CJ020 candidate author evidence — 2026-10-23

Base `8ea1b35756726f60727f10deaf157c40b8df1072`，独立 clone，
branch `cj/020-memory-jobs`。首写为模块 codec 与关闭 factory；Main 可核原聊天
commentary 及本目录 Git 源文件。唯一 HANDOFF 已读，未修改；原 Issue #23 已通过
GitHub connector 只读核对，未写评论/改状态。原 owner 的共享目录均只读固定 Git。

## 实际执行

Python **3.9.6**；标准库 unittest/SQLite/tempfile，无安装。

```
PYTHONPATH=backend/memory_jobs:backend/message python3 -m unittest discover -s backend/memory_jobs/tests -v
Ran 20 tests in 0.049s
OK
```

结果：**20 PASS / 0 FAIL**。这是作者本地 synthetic 测试；SyntheticHost 的
enabled/fence 仅为测试 facts，不是正式授权、生命周期接入或 I 验收。
原始 stdout 位于本聊天工具结果，不将此摘录伪作另一次运行日志。

覆盖：canonical MESSAGE codec/非法重复字段/类型与非规范 bytes、无 Trip、
原 hash/sequence/账号与 generation 绑定、无 host/默认 factory 拒绝、manual
文字不扩授权、原 job/attempt 幂等、不同 payload 冲突、pending 不能完成、
inflight 不重复 begin、unknown 原 ID 核对、重开 SQLite 后恢复、停用阻新/迟到、
source/MEMORY epoch 变更拒绝、事务最终 guard 拒绝回滚、guard close 未知、
commit ACK 丢失后原账本查询、游标只在完成时推进/旧完成不倒退、会话结束
补充 fence、双 scope 隔离、候选大小/UTF8、拒绝已有/其它数据库、双本地连接
串行状态保护。没有模型、MEMORY save、prompt/context 或有效资料出口。

首轮 18 PASS 后针对 commit-ACK 关闭连接行为和缺失 host 的明确 Unavailable
改动，执行受影响 20 项检查；不扩跑共享模块/全套工程。

固定输入证据：`INPUTS.json` 的 12 项 blob+SHA256 均由 `git show BASE:path`
读取并逐一与当前文件 bytes 对比，结果 PASS。

## 原 FAIL / 未运行

本模块在 base 不存在；未收到 CJ020 的既存失败测试或固定失败候选，不能编造
“原 FAIL 已解决”。HANDOFF 中其它 owner 的 FEAS/组件原 FAIL 不属于本任务，
未改动、未重跑或宣称消失。源码不复制其数据库/日志/私有对象。

- 作者代码/限定 synthetic 检查：PASS。
- 独立 Review、Testing、CI：UNRUN，等待 Main 原职责收取固定提交。
- 真实 source 启用/权限/撤回 epoch 组合：UNRUN，公共 seam 未固定。
- 模型 dispatch / RUN-USAGE 费用对账 / 真实摘要提取：UNRUN，入口关闭。
- canonical MEMORY/ReMe 写入、跨会话召回与实际回答生效：UNRUN。
- PostgreSQL/已有数据库/真实个人数据：未执行；仅 tempfile 新 SQLite。
- iOS、设备、provider、网络服务、部署/发布、公开 factory activation：UNRUN。
- Issue #23 真实 I 验收与关闭：未完成，不关票。

精确 source、跨 epoch 状态查询、RUN/USAGE、MEMORY/CLEANUP seam 请求见
`SEAM.md`。没有正式架构或契约冻结声明，也没有新增治理/跨 owner 写权。
