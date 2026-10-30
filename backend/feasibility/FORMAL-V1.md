# CJ-FEASIBILITY-FORMAL-INPUTS@1 — frozen

C #281；2026-10-30。前置：PLACE@1.0（PR298）和 NEEDS@1.0（PR304，main9a005683）
均已冻结；不能再把“NEEDS未冻结”作为停点。当前 B #305 仍负责本地运行生产者接线。

`cj_feasibility.formal_v1` 直接使用 `cj_needs.contract_v1` 的 snapshot/revision codec，
以及 `cj_place.contract_v1` 的 result/query codec。输出顶层 `FEASIBILITY@1.0`、
新输入标识 `CJ-FEASIBILITY-FORMAL-INPUTS@1`；旧 v1 facade / candidate profile 不改。

- `check_constraints`：完整有界原 revision 链 → 原唯一 evaluate/history replay。
- `check_edit_scope`：同一原 protect，不改固定/选择保护语义。
- `check_route`：严格正式 route envelope → 原条件路线 checker；原查询/来源/显式缓冲
  休息/有效秒数/DST/版本/过期检查继续执行，不复制约束、solver、来源链算法。
- 调用方明确固定 max_revisions/max_input_bytes，不从 wire 接受 owner/限额/授权。
  解码严格不代表当前来源许可。完整编码/投影必须留在真实 ProtectedReader lifetime 内；
  RUN/Trip 发布仍必须使用原 canonical revision lease、MESSAGE needs_reference 和 AUTH。

兼容范围：原条件路线 checker 只接受 synthetic/unverified 两类内部 Source。
新适配将正式非 synthetic 来源保守地作为 unverified 计算，完整正式原 bytes、
录制引用、offset/fold 和来源标签保留在 `FormalResult.place_original`，不提升真实可信度。
即便 label 是 live_provider 也不能证明本次实际采集/权限，不得到整体可行结论。
此桥只用于原条件计算器；退出条件是它直接消费正式来源模型并保留同等负例，
本轮不删除旧消费者，也不提前激活真实 provider/费用。

实际本地 producer 与当前性组合须等 B #305 可消费的运行接线；当前纯 codec 单测只证明
严格数据适配与原算法复用，不冒充签名API/受限PG/工具 dispatch/授权的L1。

## 固定 Python interface

`check_constraints(snapshot_raw, revision_raws, *, max_revisions, max_input_bytes)`、
`check_edit_scope(snapshot_raw, revision_raws, candidate, *, selected_fields, selected_item_ids,
max_revisions, max_input_bytes)`、`check_route(snapshot_raw, revision_raws, candidate, window,
result_raw, *, route_index, request, config, as_of, selected_fields, selected_item_ids,
max_revisions, max_input_bytes)`。模块为`cj_feasibility.formal_v1`，无SQL/dispatch/HTTP入口。

raw为原bytes，revision_raws为按序1..snapshot.version的完整tuple；明确正整数host边界
在解码前执行，B自己的envelope/domain长度与严格版本规则保留。非法codec输入抛原
InvalidInput/ValueError，不吞成空成功。原引擎仍负责完整来源链重放，矛盾链/保护返回INVALID。
PLACE结果上限沿其1MiB contract，不把result.source标签或解码成功当成真实出处证明。

返回`FormalResult(operation, report, place_original)`；version固定FEASIBILITY@1.0，
input_profile为本新版本，operation=check/protect/route，status直接取原report.status。
check/protect的place_original为None，route为完整原result_raw。旧v1.Result及其旧输入profile
逐字不改。原报告/Source carrier只用于既有条件计算，精确正式来源/录制引用必须从
place_original保留；没有迁移/写权限/旧消费者删除。

可执行正负例在`backend/feasibility/tests/test_formal_v1.py`：版本/重复键/缺链/顺序/host
边界拒绝，后续revision保留字段伪造被唯一原引擎拒绝，条件路线/缺证据/来源绑定/过期
及recorded/live标签均不升级整体真实可行。全部fixture明确synthetic，不代替B305 L1。
