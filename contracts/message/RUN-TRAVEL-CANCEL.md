# RUN-CANCEL@2 — frozen

JT 新版本预授权下新增，不改变 RUN-CANCEL@1 或其旧 wire/行为。
`POST /v2/run-cancellations`，application/json 原 UTF8 body 恰为
`{version:"RUN-cancel.2",message_id:<original>}`。无 query/owner/run/context/attempt 字段。
body≤65536 bytes；message_id 为非空白、无 NUL 的 UTF8 字符串，≤16384 bytes，
覆盖全部实际已接受 send.2 原 ID，不截断或换 ID。重复键/额外字段/未知版本拒绝。

服务器在原 canonical owner callback 内查持久 send.2 receipt/reference；然后
在原 RUN fence 内前后复核原来源与身份，取消及未派发 RUN 创建同事务。旅行版本推进、
停用、选择变化或 chat inactive 都不要求重新给执行许可；它们不能阻止 owner 停止原运行。
账户/RUN scope 的原隔离和当前 AUTH 不绕过。错 owner、缺原记录/metadata 和未知依赖拒绝。

响应：request_id、version=RUN-cancel.2、message_id、run_id、status、event_highwater、
reference（原 MESSAGE-travel-reference.1）。重复返回同一终态/highwater，不覆盖既有
completed/failed/unknown。取消 ACK 未知沿 RUN_CANCEL_UNKNOWN/unknown/reconcile_original，
只核原动作；不重发、不创建第二 run/attempt、不给真实费用结算证明。

已开始调用不能撤回，但后续输出/新步骤不得覆盖 cancelled；原 claimed exposure 保留，
晚到可信原回执只对账原 attempt，不复活 RUN。原 owner/RUN fence仍覆盖取消与 publication。
