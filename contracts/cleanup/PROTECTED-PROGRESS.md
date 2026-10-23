# CJ-CLEANUP-PROGRESS-READ@0.1.0-rc.1

当前有效 AUTH 身份读取自己的**已有原操作**进度，内部 consumer 候选。
基线08358f79921b8a3102a2be73b40f7c9e56d5dd80；消费 canonical AUTH
8b6abb236cf10c1865a9cc8c6155bd8ac732c07e 的
CJ-AUTH-READ-CONTEXT@0.1.0-rc.1。无新 AUTH 状态/身份/权限来源。

## 唯一内部接口与 wire 交接

```python
from cj_auth.read_context import ProtectedReadBoundary
from cj_cleanup.protected_progress import Configuration, ProgressReader

configuration = Configuration(environment, issuer, audience, max_steps, max_response_bytes)
reader = ProgressReader(canonical_read_boundary, trusted_resolver, configuration=configuration)
final_bytes = reader.read(original_token, original_operation_id, project=final_envelope_encoder)
```

boundary 必须为 canonical ProtectedReadBoundary；resolver 是服务端固定的同步
`(TrustedPrincipal, environment, guard) -> cj_cleanup.postgres.Repository`。
repository.scope 必须等于 `Scope.from_principal(environment, principal)`，guard 必须为
传入的原 guard。没有请求 owner/scope/环境/permission 参数，不从 operation ID 推身份。
环境/issuer/audience、步骤上限及输出bytes上限均由已批准 host 显式配置，不给生产默认值。
max_steps1..128，max_response_bytes1..65536；超限整份拒绝，不截断或补零。

request 只含原 token + operation ID。`project` 是可信 CJ005 最终编码回调，不是请求代码；
它接收已筛过的 exact bytes，必须同步返回 exact bytes，完整 BASE response/envelope 在
原 context 内生成，不能在返回之后延迟编码私有内容。上限作用于完整最终bytes。
未来公开路由/schema/generated客户端仅 CJ005 唯一 wire owner 有权实现；本切片没有路由。

## 白名单投影

仅输出：`operation_id`、`revision`、原聚合 `status`、`steps`、`reasons`。
steps 每项仅 `target` / `state` / `reason`，target 为有界 registry/barrier ID，禁止正文。
不输出 principal/scope/确认摘要、manifest版本或digest、invocation、receipt bytes、原journal、
hook内容或异常。reason 仅固定枚举，原自由格式gap详情不输出。

step reason：original_result_confirmed / original_result_unknown / original_result_failed /
hook_unavailable / original_call_in_progress / revocation_unconfirmed /
task_stop_unconfirmed / pending_original_result。
operation reasons：coverage_incomplete / registry_review_required / hook_unavailable /
original_result_unknown / original_result_failed。

未知原结果明确unknown；缺hook明确hook_unavailable，离线/备份/外部屏障pending不等于0。
缺原记录和他人记录均拒绝，不返回空数组或complete。complete只沿原冻结操作的有限语义，
不是现实全域注销完成或新增域已清理声明；本reader不扩大原清单、不自动audit或结算。

## 只读、寿命与最终围栏

只调用既有 `Repository.query`：SELECT + journal精确回放（recover_inflight=False），
没有create/recover/intent/receipt/audit/delete/claim。in_progress原状态原revision保留，
只读请求不能偷偷生成恢复事件或重发hook。没有destructive factory。

整个查询和最终投影在同一 canonical read context 内，PG连接close后的原guard仍有效；
close错误/ACK不明/取消/撤权都扣住私有返回。resolver、repo、投影回调和每个AUTH callback
之后核对原principal/profile与捕获绑定。最末 outer AUTH callback 也可能改repo/config；
outer返回后不复活context、不再调用任何外部checker/resolver/project/IO，只核对原reader
boundary/resolver/config身份及配置值、repository.scope/connect/guard/scope_bytes，才返回
已物化bytes。回调仍返回同principal但换绑定也拒绝。无第二鉴权/第二AUTH来源。

同步围栏不是跨worker撤权原子锁；可信Python callback也不是沙箱。查询是该原operation
的数据库快照，不保证显示后进度永远不变。原CommitUnknown等主异常不映射成未发生/成功，
更不授权重发删除或换ID。未知仅原操作安全只读核对。

## 注销后凭据查询未开放

此接口仅 **当前仍被 canonical AUTH ALLOWED 的身份** 能读自身原operation。
被拒/撤销/UNKNOWN均不能用它读，不能重新获得普通业务访问。
`post_logout_query()` 明确 ProgressUnavailable；原 `core.public_query()` 仍closed。
不签发bearer/capability/token/验证码，也不允许注销后凭据绕过准入。
原Issue27注销后的受限进度查询、真实旧token撤销、原域清理/设备/备份和完整I仍未完成，
本切片不替代它们。仅交 Main→CJ005 按本内部签名做唯一正式wire消费。
