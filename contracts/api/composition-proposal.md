# CJ005 AUTH / MESSAGE composition：最小 wire 待消费确认

消费修订：Main已转交CJ009、CJ007对实际2331bdad的receive/query窄范围最终确认及约束；双方确认闭环，Main明确允许落正式schema/路由。本段不冻结完整AUTH/MESSAGE，也不纳未fixed的新JWT profile。

候选输入固定：AUTH `79f88b6552da1bd3d4b27e22f64a158bddf2853b`（CJ-AUTH-SERVER@0.1.0-rc.1），MESSAGE `cec92299aa77e74baafba473ecf9db7b926fbe4e`。后者独立末审状态由Main确认，本文件不称已通过。CJ005起点 `b510b6ca7661ead67e8a719c53318545d5cb2021`；此文件记录2331bdad原提案与消费确认，正式wire现纳唯一 `openapi.json`；不改两领域源码/原始字节语义。

`composition-schema-proposal.json`仅保存2331bdad历史提案，不供runtime/生成器消费。当前正式source与生成器仅用 `openapi.json`。

## 已确认首slice（仅receive/query，不是完整MESSAGE@1.0）

| 项 | 实际wire边界与后续真实验收限制 |
|---|---|
| 接收 | POST `/v1/messages`，Authorization Bearer；Content-Type `application/octet-stream`，body为原完整UTF8 JSON bytes，直接传 `Boundary.receive(token, raw)`。Binary媒体是为了官方Swift生成HTTPBody保持原字节，不让JSON encoder在重试时重建 |
| 原JSON内容 | 严格复用domain.Command：`version=MESSAGE-draft.1`、conversation_id/message_id/text非空、trip_id只能null、creation_intent仅none/consider_trip；拒绝重复/未知字段，不添加owner/身份/准入字段。与旧fixture非null Trip允许项有差异，以固定domain实际边界为准 |
| 接收响应 | 200 `{request_id, receipt}`，receipt只投影六个已存在字段：message_id/conversation_id/generation/sequence/run_id/input_sha256。首次/完全相同原字节重复在当前准入与聊天创建代次仍有效时200，不猜accepted/running/结果状态，不含正文 |
| 原动作查询 | GET `/v1/message-receipts?message_id=<opaque>`；用query避免domain允许任意非空opaque ID时slash路径问题；ID按标准percent-encode后仅decode一次，拒重复/额外参数，不trim/大小写/Unicode规范化；`Boundary.query`只返回收据，不回显Stored.raw |
| 查询响应 | 200 `{request_id, receipt: object-or-null}`。null只说明该账本未观察到，不是权威not_received，不授权任何写重试；保留窗口未定、过期/清理/依赖失败/拒绝都不能变成“未发生” |
| 上界 | 请求body byte上界由host显式必配，读取流逐chunk累加并在完整缓冲前拒超限，不只信Content-Length；本提案不猜产品值。读取时也需有界，不先把无限body读进内存再判长。ID格式不擅自收紧为UUID |
| 排除 | 不提供page/cursor/pending、conversation创建/删除、RUN/SSE、模型派发、真实账号/DB、迁移或线上权限；没有真实仓储时拒启动，不用内存库冒持久化 |

## 已确认统一BASE错误

统一沿用现有ErrorResponse与server-owned request_id/header，不暴露token/principal/provider原因/exception/他人资源；code/category为已有开放字符串，不扩BASE枚举。

| 内部结果 | HTTP及BASE语义 |
|---|---|
| 缺Bearer/IDENTITY_INVALID | 401，failed / do_not_retry；本次拒绝不是原动作未收到证明 |
| 其他Admission DENIED | 403泛化拒绝，failed / do_not_retry，不向caller枚举成员/邮箱/邀请事实 |
| entry/transaction-entry Admission UNKNOWN | 503，unknown / retry_safe_read；只许安全验证/查询，不授权POST重发；原动作原ID/bytes仍保留 |
| InvalidInput / InputConflict | 400输入或409冲突，failed / do_not_retry；不覆盖/转换已保存原bytes |
| commit-stage（无法证明rollback）或return-stage（commit_possible=true）的 AccessBlocked/IdentityChanged | 503，unknown / reconcile_original；即使本次资格拒绝，也不能假回滚/假not_received |
| CommitUnknown | 503，unknown / reconcile_original；不retry commit，不新message_id/run |
| 仓储Unavailable或其他执行异常 | 保守unknown；写请求reconcile_original，只读请求retry_safe_read，泛化安全文案；不假成功或伪造不在账本结论 |

## composition依赖与源码pin

`AdmissionChecker(PyJWTVerifier(explicit_config, explicit_keys), authoritative_access_provider)` → `Boundary(checker, trusted_repository_resolver, new_run_id)`。JWT profile/key provider、成员/邮箱/邀请provider、repository resolver、run ID factory、body上界全部由服务端注入，缺失拒启动或明确Unavailable；不接客户端owner/scope/issuer配置。默认服务继续local-only，没有公网监听命令。账号注册/验证/找回不进入这个受限消息gate。

AUTH/MESSAGE不在当前CJ005分支源码树内；实施时不写其owner目录、不复制出第二套领域实现。测试/构建用固定Git对象导出到clone内忽略临时依赖目录并核sha256，正式集成由Publish先纳入精确原commit后再装配；源pin/hash由CJ005登记，不能靠相同RC版本字符串证明源码一致。PyJWT[crypto]依赖将与AUTH固定版本一致，根runtime收窄为>=3.12,<3.15；本机3.14.7验证，不冒3.12/3.13通过。

resolver持久scope不得按token iat/nbf/exp分区，必须由批准环境/profile+可信issuer/subject等映射；当前无真实映射/会话revision/撤销原子fence。Boundary重复准入只是同步边界，非跨事务撤销原子保证。真实PG并发/提交崩溃/两账号隔离待CJ009及目标配置；本地合成key+事务double只能验证接线，绝不代替这些证据。

消费状态：Main已转交CJ009与CJ007对2331bdad的最终明确确认，非工具ACK推定。缺generation/run_id有效值不能伪造填充，run ID factory在写入前校验，非法收据投影安全失败且保留unknown。拒绝/异常/代次失效不能转null；commit_possible/CommitUnknown/无法确认回滚先于普通身份拒绝映射unknown/reconcile_original。拒绝重复或合并Authorization header，不回principal/reason/token。发布与独立Review/Testing仍PENDING。
