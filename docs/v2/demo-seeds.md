# 员工后台演示种子

`jt.synthetic.generate_demo_dataset(seed=1887)` 生成单独的合成队列批次。固定种子决定信号 ID、案件 UUIDv4、事件时间、案件初始状态与演练历史。每次生成新的工作流实例，加载完成后的员工操作使用实际时间。

| 队列 | 业务场景 | 打开案件时的状态 |
| --- | --- | --- |
| P0 求助 | 旅客走散，在虚构地点寻求协助 | 已有合成协助草稿，待确认 |
| P1 护照丢失 | 旅客需要查明遗失地点，并赶次日火车 | 草稿已驳回，停留在同一步 |
| P2 航班变动 | 航班延误影响接站和住宿 | 改行程草稿已在合成同意后确认，付费改订仍须另行同意 |
| P3 请求变更 | 广州中英商务陪同时段有变，待确认双方时间 | 已建单，待准备选项 |
| P4 AI 未解决 | 两次问能否安排陪同，工具反复失败 | 合成演练完成，案件关闭 |

中英片段内涉及身份、电话、地点、证件和航班编号时均使用类型化占位符。广州陪同示例区分整理需求、确认共享信息和实际安排，保留 [ADR-0010](../adr/0010-local-assistant-and-scene-packs.md) 的人工接单边界。原 `generate_dataset()` 供现有测试与工作台调用。可选的 `DEMO_PLAYBOOKS` 供 #1713 的合成脚本通过 `CaseWorkflow(playbooks=DEMO_PLAYBOOKS)` 演练 P3，保留独立客户同意。

## JT2 加载

同一演示工作台应共用一次生成结果。

```python
from jt.synthetic import generate_demo_dataset
from jt.workbench.cases import CaseWorkspace
from jt.workbench.queue import MemoryQueue

demo = generate_demo_dataset()
workspace = CaseWorkspace(demo.workflow, tuple(item.case.case_id for item in demo.cases))
queue = MemoryQueue(demo.signals)
# create_app(auth, queue=queue, cases=workspace)
```

部署入口如使用现有 PostgreSQL 队列，可用 `store.seed(demo.signals)`，再把 `cases=workspace` 传给 `create_app`。默认启动入口由 JT2 选择何时接入此批次。案件和历史属于演示快照，`demo.history` 可以给演示页面只读展示已确认、已驳回等历史状态。启动时应避免把这些固定历史重复追加到实际员工审计。运营台服务请求的演示数据源由 JT2 持有。
