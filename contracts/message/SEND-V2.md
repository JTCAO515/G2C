# MESSAGE-send.2 — frozen

JT 2026-10-30 批准 #273 r1。只新增版本，MESSAGE-send.1 不改。
正式 producer 在 #273 第二实现切片接入；未接入前不得宣称 API/worker PASS。

新写路径 `/v2/messages`。原八字段（version/conversation_id/message_id/text/
trip_id/creation_intent/expected_generation/expected_sequence）及原 bytes/CAS
语义保留，version 为 MESSAGE-send.2，trip_id 仍必须 null。额外必填：

- travel_context：显式 null（无旅行，仅长期值）或 owned `{id,expected_version}`；
  缺字段不等于 null。没有正式 Trip 也可选旅行。
- needs_reference：intent=none 时必须 null；consider_trip 时显式
  `{id,expected_version}`，引用现有 owned/current NEEDS，不沿用旧 conversation selection，
  不新增需求事实或声称属于该旅行。

接受事务在 M scope 写锁内先查原 receipt，再核 chat CAS、T active/version 及
显式 NEEDS，然后固定 receipt/raw/reference/requirements/outbox。原已接受 bytes
即使旅行后来失效也优先返回历史回执，不给新执行权。拒绝时不留部分 receipt/outbox。
原 message/run/generation/owner 不变，重启、ACK 未知不刷新版本/换 ID/改引用。

同 conversation 连续相同 kind/id/version 的首 message sequence 为 selection_epoch；
变化时取新 sequence。A→B→A 的旧 A epoch 不复活。同旅行跨 conversation 共享
旅行键，各自维护 epoch。已有 send.1/draft.1 不回填、不猜旅行。

新接受响应为 MESSAGE-accept.2（receipt 加原 reference），新 status 在
`/v2/message-send-status` 同快照读原 receipt/head/reference。v1 不得剥掉
send.2 引用投成 legacy；不支持则明确不可用。send.2 缺失持久 metadata 为
unavailable/unknown，不默认 none。

输入错误 400；错 owner/不存在/依赖未知为 503 MESSAGE_CONTEXT_UNAVAILABLE；
已知 owned 上下文停用/版本过旧为 409 MESSAGE_CONTEXT_CONFLICT；均沿 r1 第6节
BASE outcome/recovery。commit ACK 未知沿 MESSAGE_OUTCOME_UNKNOWN。
先兼容 consumer，后在原 M2 scope 显式激活 profile；不重置 scope/period/UNKNOWN。
