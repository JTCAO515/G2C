# CJ-AUTH-READ-CONTEXT@0.1.0-rc.1 — 最小同步只读寿命候选

实际 parent：4eac0ad8db0ac33c89c7cc5b88d66b58d0fd6a7e，首写前 clean。
输入：CJ008固定68763c44fddf2e6d11799d1311dbd497d9c657c9 的 READ-STATUS.md。
仅新增 backend/auth/cj_auth/read_context.py，复用原 AdmissionChecker/TrustedPrincipal/
CJAccessFacts；旧AUTH接口、JWT/provider、iOS用途/Keychain状态不变。候选待原双审。

## 固定公开用法

```python
from cj_auth.read_context import ProtectedReadBoundary
boundary = ProtectedReadBoundary(canonical_checker, max_response_bytes=host_explicit_limit)
result_bytes = boundary.with_read_context(original_token, server_owned_callback)
# callback(context): context.principal, context.guard()/require_current() -> None
```

checker 必须是原 AdmissionChecker，字节限额必填正整数，无生产默认值。
context 在 entry checker/provider 回调前登记；只有新鲜 ALLOWED+TrustedPrincipal
才执行业务 callback。每次 guard 都调用**同一个原 checker、原 token**，重核准入及
原 TrustedPrincipal 的全部字段。身份/时间快照变化即终止原 read；预算持久分区仍
不得使用 iat/nbf/exp。UNKNOWN/DENIED 不输出私有结果；资格恢复不复活旧 context。

每个 boundary 同时仅一回调，context 限原线程使用。嵌套/并发重入拒绝并终止原
lifetime；checker/provider 回调中重入也不能绕 entry 检查。invalidate 只终止该读
寿命，不 claim/cancel 外部任务或改任何权限。callback/异常结束后 context 关闭，
guard/principal 在回调外不可再用；新的 context 只在旧回调退出后重新准入。
普通公开构造不能生成脱离 boundary 的 context；这只是防误用边界，非 Python 沙箱。

callback 必须同步且返回 exact bytes（可为空），不接受 awaitable/generator/bytearray/
memoryview 或其他延迟结果。最终长度检查后再 guard，之后直接返回原 bytes；任何
拒绝都不返回半份内容。限额是最终输出上界，不能阻止任意可信 Python 在 callback
内部先行分配内存；repo/投影仍须自己的有界读取。业务 primary exception 保留，
finally 关闭 context 不覆盖原 repo/commit-unknown 错误。错误消息不带 token/principal。

## CJ008 最小消费约束

可信 host 在 callback 内由 context.principal 和已批准 environment/issuer/subject/
audience/历史 budget period 映射原 budget repo，不能让 caller owner/period/unit
选择存储，也不能通过两次无绑定鉴权拼接 scope。AUTH context 不知道预算、账本、
SQL或 MESSAGE 仓库，不提供数据库/预算/dispatch能力或新权限源。

调用 repo.read_status(..., guard=context.require_current, ...)；连接、SQL、fetch、
投影/最终外层编码、commit 和 close 回调后的原 scope检查仍由 repo/host执行。
整个安全编码须在 callback 内完成，包括 request_id/公开响应 envelope；关闭连接
之后 outer boundary 再核原准入，返回后不要新增私有投影/延迟编码回调。

ReadAdmissionFailure 提供原 AdmissionStatus/reason（仅内部），按 BASE 原规则泛化：
原身份 INVALID/明确拒绝不泄露原因，UNKNOWN为 unknown/retry_safe_read，仅安全读。
ReadContextViolation 的失效/跨线程/重入/身份变化也不得授写重试。实际 repo 已有
CommitUnknown/未定完成优先保持 reconcile_original，不用当前准入结果假报未发生。
没有新HTTP路由/错误码、环境配置或假request_id。

同步guard只能观察当前提供者事实；没有实时撤销版本、事务锁或跨worker派发fence。
任意可信callback已获得的数据不能被此对象物理抹除，也不能据此称任意Python只读
或安全沙箱。真实资源/provider缺失仍由原checker/repo安全拒绝，不能拿测试替身接生产。

## 验证

本机Python3.14.7；独立包基线>=3.12,<3.15。新13项context测试 + 原准入6项回归
=19项PASS，日志 backend/auth/evidence/read-context-tests.txt 和
read-context-admission-regression.txt。使用canonical types/checker + 注入 verifier/
access facts，无真实JWT、账号、数据库、网络、Keychain或外部资源。
覆盖原身份重复guard/finalguard、拒绝/UNKNOWN、撤销/身份变化、恢复后旧ctx不复活、
回调内和entry-provider重入、guard递归、跨线程、并发重入、回调外使用、仅bytes/
限额/延迟结果拒绝、异常/取消后关闭、新context与缺资格提供者拒绝。
原密码学/Swift/平台证据复用，无根锁或其他domain改动。固定source供Main→CJ008消费，
不宣称真实只读DB、原子撤销、费用或完整Auth服务验收。
