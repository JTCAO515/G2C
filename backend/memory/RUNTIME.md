# MEMORY-RUN-CONSUME@1（本地可信 host 接口）

#227；JT 已批准运行消费/发布 lease 方向。此接口不修改 MEMORY wire、
`local-memory-policy.1` 或 bytes-only `with_operation/consume_current`。
实现与验收以 Issue/PR 为准；本文件不是 L1 完成声明。

## 选择与捕获

`RuntimeMemory(service, guard, Selection).capture(original_binding)` 只由可信
worker 调用。guard 返回 canonical TrustedPrincipal 和服务器 scope；原 binding
来自已接受 MESSAGE receipt。capture 通过原 with_operation/consume_current，
以唯一 current_context 选择当前有效项。匹配原 conversation 的 current 覆盖
long_term；别的 conversation 不携带其临时条件。当前本地 MESSAGE 不支持非空
trip_id，因此这里的 context 不是正式 Trip 选择。

同 subject/slot、来源授权/确认/语义/启用/到期和 epoch 的规则不复制。
服务器显式选择 canonical subject/slots 和 UTF-8 byte 上限，不能根据 JWT subject
或自由文本猜语义。只把所选有效项编码成带来源/范围/版本的数据消息；当前用户
文本是后面的当前指令。保留原文，既不翻译合并，也不写回长期值。

捕获对象是进程内原 RUN 输入，不能作为发布许可。外部 HTTP 没有上传 Context、
捕获对象或版本 hash 的入口。queued RUN 在首次执行时读取；已 running 的进程
中断沿用 unknown，不重新捕获并重发。没有持久快照恢复或旧运行重执行功能。

## 发布 lease

host 先取原 RUN 锁，再进入 `captured.hold(original_binding)`；错 RUN 绑定拒绝。
ExitStack 在 RUN 事务外层退出，
让 MEMORY scope 行锁保持至 RUN 实际提交。lease 内的 check 只在原线程和生命周期
有效，每次 fresh AUTH 后 require_current 重读完整 canonical snapshot，而不是只
比 epoch。即使只有来源到期、epoch 未变，也阻止新输出。

新 provider 首步、text_delta/completed、draft outcome 和草稿实际发布前检查。
provider factory 和计量准备后，在实际首步前再检查；不持锁覆盖整个模型流。
草稿 publisher 的 before_publish 在内容、来源和 proposal 构造后、正式 publish 前
调用。既有 RUN→USAGE/NEEDS 顺序保留，不新增第二账本或步骤许可。

编辑先提交：旧捕获拒绝。发布先取得锁：先提交的原结果仍可查询，编辑随后生效。
到期时点为实际副作用前最后检查；不声称网络/数据库提交瞬间的绝对时钟原子性。
已发送给 provider 或历史已展示内容不能撤回；失效后不再发布新回答/候选。

不在 RUN 提交后追加“授权拒绝”来伪装原子回滚。草稿可能独立先提交；随后 RUN
回执未知保持原动作对账。读 lease ACK/存储未知或 cleanup 不确定时保持 unknown，
不替换已提交的 RUN 事实、不重发、不清零计量。与原操作无关的异常不吞掉。

## 显式本地配置

worker 新参数 `--memory-run-policy` / `CJ_LOCAL_MEMORY_RUN_POLICY` 指向 operator
私有配置文件。文件检查复用原 MEMORY 私有文件加载规则。JSON 格式：

```json
{
  "version": "local-memory-run.1",
  "collection": {
    "version": "local-memory-policy.1",
    "expires_at": "2030-01-01T00:00:00+00:00",
    "profiles": {
      "synthetic-user": {
        "subjects": ["self"],
        "slots": {"dietary": {"kind": "preference", "collection_allowed": true, "semantic_resolved": true}},
        "extents": ["long_term", "current"],
        "context_ids": ["synthetic-conversation"]
      }
    }
  },
  "selections": {"synthetic-user": {"subject": "self", "slots": ["dietary"], "max_bytes": 32768}}
}
```

日期和身份仅说明格式，不是默认配置或真实用户授权。重复/额外字段、非整数上限、
越界/未批准 slot、错 canonical subject 拒绝。collection 仍由原解析器验证。
显式 memory scope 在原受限角色下初始化，不授予新权限。已有 MEMORY scope 而
缺运行配置时，CLI 在 credential factory 前及 run_once 在 RUN accept 前拒绝，
不会静默退回只看聊天的路径。没有 MEMORY scope 的旧消费者行为保留；启用后须
提供配置。此进程检查不承诺防御任意旧二进制或恶意管理员绕过。

此版本只允许 FakeProvider，运行策略不能启用真实模型/云服务。旧保存读取接口和
现有计量配置格式保留；#242 未合并消费者不会自动纳入本接口。后续 B 升级须用原
RUN/计量/撤权反例验证此组合。编辑/启停/撤回写入仍由各生命周期 owner 提供，
本接口只消费其 canonical 当前性，不授予这些写入权限。

## 可复验范围

`uv run --locked python -B scripts/pg_suites.py memory_run`：全新私有 PG/全迁移，
签名本地 API、受限运行角色、正式 run_once/CLI 与 FakeProvider。上下文及实际回答
从真实库读取；不以手造 Context 或初始化身份代替业务 SQL。与单独 memory 组、
完整 test.py/pg_suites.py、精确 head CI/独立审查共同提供证据。真实模型、真实用户、
云、设备和发布仍属于 L2/L3，不由此本地接口证明。
