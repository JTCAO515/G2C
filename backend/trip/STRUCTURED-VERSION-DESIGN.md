# TRIP structured.1 与受保护手动保存设计

状态：C 设计稿，2026-10-30；JT 已授权设计后继续实现，不再逐项审批。
关联：#285（父 #22）、#204（父 #21）。基线 main b6705192。
backend/trip/** 现归 C；旧票“等 B owner 扩展 Trip”停点撤销。
本文不修改 contracts/**、旧 frozen 版本或迁移0001–0020，不代表实现/验收已完成。

## 1. 已接受实现与最小改动位置

- `cj_trip.domain.Proposal` 已持有 canonical content、basis、expected_version、expiry；
  digest 同时绑定 scope 和这些字节。当前只接受 legacy 与 provenance.1。
- `Repository.act` 是唯一正式 Trip 写入：原 action 查询、确认、expiry、Trip CAS、
  record/version、proposal terminal、receipt 同事务，scope行锁串行。
- `ConfirmationSigner.issue/check_before_commit` 已提供原候选hash/版本/动作签名及最后时钟检查。
- `Boundary.with_operation` 已覆盖fresh AUTH、scope、线程/同步投影与最后private return。
- `cj_manual_edit.core` 只支持文本预览；不伪造其 save 已可用。
- FEASIBILITY@1.0 已由 #280 发布；旧 NEEDS candidate 不等于 B 的正式 NEEDS 冻结。

扩展内容校验放在 `cj_trip.structured`；手动准备/提交放在 `cj_trip.manual`。
所有调用者跨同一个 interface，不在 draft/manual_edit/API 各写状态机或约束算法。

## 2. 新内容版本与明确字段

新增 opt-in `content_version: "structured.1"`；不改 legacy / provenance.1。
候选仍是原 Proposal，正式记录仍是原 Trip；不新建第二份正式数据。
示意（原文、显式观察值与未知分开）：

```json
{
  "content_version": "structured.1",
  "title": "用户明确的标题",
  "items": [{
    "id": "appointment-1",
    "text": "原文字，不从这段文字解析时间",
    "verification": "pending",
    "evidence": [],
    "schedule": {
      "start": {
        "date": {"state":"known","value":"2026-11-02"},
        "time": {"state":"known","value":"09:00:00"},
        "timezone": {"state":"known","value":"Asia/Shanghai"},
        "utc_offset": {"state":"unknown"}
      },
      "end": {
        "date": {"state":"known","value":"2026-11-02"},
        "time": {"state":"known","value":"10:00:00"},
        "timezone": {"state":"known","value":"Asia/Shanghai"},
        "utc_offset": {"state":"unknown"}
      }
    },
    "fixed": {"state":"known","value":false},
    "source_category": "user_provided",
    "source_refs": []
  }],
  "sources": []
}
```

精确字段、重复JSON键、非有限值、非法ID/重复ID、上限和canonical UTF8在入口校验。
沿用现有 Proposal 总字节上限；item数与字段长度在新版本冻结时显式固定，不能默认为无限。
全局 item ID 唯一，不按日期重新编号；按显式 start.date 显示每日分组，无独立悬空day对象。
允许跨日项目，但不把缺失end.date补成start.date。

Observation 由本 TRIP 新版本拥有：known带精确类型value；missing/unknown不带value；
uncertain带有界note。date是严格ISO日期；time是显式本地时分秒；timezone是显式IANA名；
utc_offset是明确偏移观察值。未知不是null日期/零时长/设备时区，也不从“明早/Day 1”推断。
只有能由明确字段确定唯一instant时才比较先后；DST fold/gap、偏移不一致或缺字段保持UNKNOWN。
最终时间解释调用FEAS共享实现，Trip grammar不自写第二个时间/冲突引擎。

fixed同样是明确观察值。unknown不当作false，不允许自动修改/移动；用户明确lock/unlock
是单独选中的变更意图。锁定项目的内容、时间和位置默认保持，不能把unlock混入普通改文。
结构合法、用户声明、来源关联、已采用均不等于事实verified；更改文字/时间不继承旧事实证据。
来源快照复用provenance的host记录原则；模型不能上传source/owner/verified或选择范围批准。

## 3. 旧消费者与兼容

- 新版本在新 projection/endpoint或明确版本协商下使用；旧读取遇structured.1明确不支持，
  不去掉schedule/fixed/source、不降成字符串。先部署兼容consumer，再启producer。
- 旧 Proposal 内容与 digest 算法逐字不变；structured.1内容由原digest覆盖全部新字段。
- legacy/provenance.1缺固定状态时，不假设空锁集合。保留原只读预览；需要正式手动保存时
  先由用户明确补全/确认成一个新版本候选，不能自动迁移并宣称有完整固定事项依据。
- 回退保留识别新版本且fail-closed的consumer；不改旧记录、原source或原receipt凑兼容。

## 4. 手动编辑唯一 interface

拟新增受保护 `OperationContext.prepare_manual(original_input)` 与
`OperationContext.save_manual(original_input)`；两者只能在原with_operation生命周期内调用。
外部请求带稳定原ID、Trip ID、expected_version、精确选定item/字段及期望变化；
不接受owner、保护集合、来源授权或client viewed/confirmed布尔。

prepare：受保护读取原Trip → 同版本/原bytes绑定 → C手工模块构造候选/diff →
FEAS共享结构/范围保护 → 可信原Proposal ingress发布不可变候选。
未选中/固定item保持精确内容与位置，未知保护状态拒绝自动变更。
返回proposal ID/hash、exact before/after/diff和UNKNOWN，不写正式Trip，不把预览当确认。

save：用户对这份diff点击保存，发送原save/action ID、proposal ID/hash；
服务端读取canonical ProposalDetail，复用既有 ConfirmationSigner，随后执行原act逻辑。
一个用户保存动作不增加第二次确认弹框，不以客户端布尔替代可信确认绑定。

为隐藏服务端confirmation_ref并保持unknown可恢复，新增不可变manual-intent记录，
保存原客户端save bytes和对应Action.raw。其写入与现有act正式事务同一cursor提交；
原 Trip receipt仍是唯一正式结果，不增加另一份Trip或另一套版本账本。
将现有act SQL提取为同模块内部事务implementation，旧Repository.act与新save共用；
不复制accept/update/version/receipt算法。相同原ID/bytes读原结果，异bytes409。

正式事务仍顺序检查：原receipt → pending候选/hash/source → fresh AUTH → 可信确认 →
原Trip expected_version → scope锁内原子写record/version/proposal terminal/receipt/intent →
最后DB时钟与confirmation expiry → commit。禁止直接UPDATE Trip绕过Proposal/act。

## 5. 新发布 seam 与 NEEDS 依赖

增加 C-owned `TripPublicationBasis`：manual-unbound 或 needs-bound，两种明确模式。
它是原来源数据，不是权限token；不能用构造DTO、hash相等或版本数字授予发布权。

manual-unbound：绑定实际原Trip版本/bytes、明确选定范围、固定状态、当前候选hash。
可独立交付标题/条目/固定状态及明确时间的结构与内在先后校验；没有NEEDS时不制造
空Snapshot、假party/booking/价格/交通或“整体可行”。几何时间交叠的占用含义不明则UNKNOWN。

needs-bound：必须由真实受保护NEEDS producer提供同principal/context的Snapshot与完整
Revision链，保留原bytes/hash/版本及明确Trip-item↔NEEDS-item映射；B正式NEEDS未冻结前
不固定其字段或方法名，不拿旧candidate/客户端声明顶替。相应实现是子票级停点。
来源读/发布seam的最小要求：

1. 原来源受保护读取，回调得到完整原Snapshot/Revision；fresh owner/context/currentness。
2. 服务器校验来源关联，生成不可变basis，持久关联scope/proposal ID，不由模型/client创建。
3. `hold_for_publication(original_basis)` 真实lease在publish和accept提交前重读原来源，
   保持到实际Trip commit；来源变化/失效/错owner/缺链拒绝，无当前来源不自动换新版本。

不可变 proposal-basis/manual-intent 如需新表，用最新manifest顺延的local runtime only迁移，
same-scope FK、FORCE RLS、既有runtime最小SELECT/INSERT；无DELETE/TRUNCATE/新角色/
BYPASSRLS/SECURITY DEFINER。空库往返；有basis/intent新语义时down拒绝，不删数据。

锁序：先短读Trip/basis并释放（数据不授予权限）→ 取得原NEEDS/B上下文lease →
原Trip scope事务 → recheck原版本/bytes/basis → 原发布/act → commit后释放lease。
实际NEEDS接口未冻结的具体锁图标依赖，必须与B验证；不持Trip锁去获取未知外部来源。
手动无NEEDS路径只取Trip锁，所有同模块调用者一致，不出现反向索引/自动重绑。

## 6. #204 与 FEAS 共用规则

在 backend/feasibility 提供TRIP新版本adapter；只消费已校验显式字段。
把当前NEEDS validator内时间/区间公共implementation提升到同模块的小interface，
旧evaluate/protect保留原codes/evidence/语义；Trip adapter也调用它，不伪造NEEDS Snapshot。
保留 ITEM_TIME_ORDER / ITEM_TIME_REVERSED / ITEM_TIME_UNKNOWN、相接半开区间、跨日、
DST fold/gap及已有重叠判定。参与人/独占意义必须来自已冻结、当前的NEEDS来源；缺少则
UNKNOWN，不把所有可见事项默认为同一人/必然互斥。整体预算/路线可行性仍需其真实证据。

#204发布：先从真实授权NEEDS绑定构造basis，再在原RUN/取消/记忆/NEEDS保护内调用
共享FEAS并准备Structured Proposal。CONFLICT/INVALID整份拒绝，proposal/Trip/RUN effect
均无新增；UNKNOWN可解释但不宣称整体可行，不把拒绝降成无效文本候选。
来源改变或prepared basis不当前时，不发布旧结果；有效候选仍走原确认/CAS事务。
双语解释来自同一Check及其source/basis，不另翻译一套判定。

## 7. 分段交付及证据

- 本设计：只backend/trip与C ownership规划。不是新契约冻结/DDL执行或功能PASS。
- 独立实现：structured.1 grammar/投影、manual-unbound范围保护和唯一受保护保存；
  实际runtime PG的确认/hash/CAS/固定、rollback/ACK未知/重建、跨owner/旧版本拒绝。
- #204先交TRIP adapter和纯时间反例；真正NEEDS授权/发布组合待冻结后实现，原验收不删除。
- NEEDS就绪：真实来源链与lease两种排序、过期/变更/取消拒绝、完整新head test/PG/CI。
- shared contracts+generated只在组锁空闲时新增版本与正负例；C后端生成，iOS仅check。
  新版本通知#286/A及#204/#285消费方，不等回执；App不由C后端测试代验。
- 红线迁移/RLS/权限/记忆fence按现行ADR一轮独立P0/P1审查，其他代码自查与精确CI；
  --match-head-commit合并，不等main CI。所有实际未跑项保留UNRUN。

当前以上新行为/DDL/接口实现、L0/L1、生成、CI均UNRUN。
