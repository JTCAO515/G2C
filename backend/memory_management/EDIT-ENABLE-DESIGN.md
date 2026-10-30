# #17 后端编辑/启停与记忆 fence 设计

> 2026-10-30 JT已批准C1及追加本地迁移/列权限/API写权；以下审批稿保留为设计依据，旧“未批准/未实施”描述属于历史。实施契约见 `contracts/memory-management/edit-v1.md`。C2最小stop-use writer同日另获先写详细稿后直接实施的授权，仍不涉及物理删除或账号清理。

## 已核实的 owning source

- `memory_management/domain.py`、`contracts/memory-management/README.md`：旧动作严格五字段，只允许pause/resume；编辑新字节的来源批准/历史关联是明确未决项。
- `memory_management/postgres.py`：同一Memory scope锁下做item/source CAS、状态/version/epoch和原action回执；resume只认当前版本有本模块pause记录，不能恢复通用disabled/candidate/withdrawn。
- `cj_api/memory_management_boundary.py::create_memory_management_app`无条件closed；review-harness构造器不是可绕过的正式入口。
- 0015仅给Memory四表读/插入、scope.epoch与source.scope锁权限；运行角色不能更新item状态/正文/版本，management_action也未接强制RLS/运行权限。
- `memory_withdrawal`只有read model/check_history，没有权威withdraw writer；#227真实完整撤回组合不能靠初始化身份改flag或合成Context代替。

## 拆分与验收边界

两张C后端子票：#269编辑/逐条启停（含新来源、CAS、原动作），#270旧结果覆盖防护/回补#227框4。App由A另拆/认领#17 UI，C不改ios、不擅改A队列。#12剩余框是挂起状态，不阻塞C做#17。

## C1：建议的新编辑来源契约

旧五字段pause/resume wire及其字节/回执规则不改。新编辑使用新版本动作，候选形状：

```json
{"version":"MEMORY-MANAGEMENT-EDIT@1","action_id":"edit-1","operation":"edit","item_id":"item-1","expected_version":2,"expected_source_version":1,"text":"用户明确提交的新原文"}
```

这只是待批的新契约，不往旧schema加可选字段，不允许owner/scope/source批准/新expiry/状态由客户端传入。

- 可信host从当前item派生原subject/slot/kind/extent/context/大致时间；只改文字，不推断新对象、永久范围、kind或旅行。仅已确认事实/经历/偏好可编辑，candidate/inference/withdrawn不可借edit提升或复活。
- 用户显式保存新文字是这次更正的输入；用当前服务器明确ManualPolicy/收集范围对**新确切字节**作批准，敏感/语义未决/无授权拒绝且旧值不变，不套用旧approved_input，也不增默认允许/默认TTL。
- 生成独立server source ID和新source行，保留旧source原bytes/expiry/批准及原save回执；新来源的期限只能来自当前明确策略，不能续写旧来源。来源ID和原action关联由服务器生成/验证，客户端不能自证来源。
- 同一canonical transaction：原action查询/同bytes重放或异bytes冲突→scope锁→当前item/source CAS→新来源批准和插入→item正文/source指针/version+1→scope epoch+1→原action receipt→commit。失败全回滚，ACK未知只查询原ID，不自动重试或换ID。
- 编辑disabled项保持disabled，不能自动启用。必须保留其由本模块pause产生的因果：新edit-disabled回执携带server验证的本item pause版本anchor，resume只接受当前版本的合法pause或连续已验证edit-disabled因果。否则现有“当前版本必须有pause记录”会让编辑后的paused项永远无法resume。通用disabled/candidate来源仍拒绝恢复。
- scope/item/source CAS、原回执和新的读取只复用原Memory engine/adapter，不另建语义/版本引擎；旧整理结果在#270按同一epoch/来源检查拒绝。

### C1追加迁移/最小运行权限（待批，不预占编号）

在届时最新manifest后追加新up/down；不编辑已应用迁移。建议扩展现有唯一management action账本（不新建第二账本）：

- operation约束增加edit，原pause/resume值和raw bytes不改；新增nullable previous_source_id、new_source_id、disabled_by_version，保留同scope FK和原(scope,item,version)唯一性。
- 新edit行的来源关联必填；disabled编辑必须有经server校验的本item pause因果。旧动作新增列为NULL，不回填推测历史；DB读出边界核投影/原bytes/来源关联一次，之后信任不可变对象。
- management表ENABLE+FORCE RLS，按原事务LOCAL cj.message_scope隔离；runtime只SELECT/INSERT，不授予改写/删除回执。
- item仅增加UPDATE(status,version,original_input,source_id,source_version)所需列权限；scope UPDATE(epoch)复用原权限；source仅复用原SELECT/INSERT及scope列锁权限，不授予覆盖旧approved_input、授权字段或DELETE。已有Memory RLS不减弱，不加superuser/BYPASSRLS/SECURITY DEFINER。
- up/down空私有PG往返；已有旧操作/来源/回执字节保持。只要有新edit/新来源关联数据，down明确拒绝且保留schema和数据；不能丢历史、压扁成旧动作或以删数据凑回滚。生产/云执行不在本授权内。

## 根API与跨线写权

本轮C只获C目录及指定B协调文件的写权；新正式管理能力需要额外明确授权：

- local_app.py：受限角色和显式管理策略组装（协调文件，先核锁/声明）。
- memory_management_boundary.py、memory_management_routes.py：在批准的新本地入口中启用canonical guard、旧pause/resume及新版本edit；不直接调用closed工厂的review-harness分支绕过门禁。
- 必要backend generated.py及contracts/api/openapi.json/新契约，按contracts+generated一组锁；仅所需后端变化。若实际需要其他B文件，重新列范围后停点，不泛授权cj_api目录。
- iOS生成与新操作客户端由A负责；C不改ios。API冻结/兼容和生成输出必须与A按组协调，旧客户端不能把未知新wire当成功；App证据不能由C后端测试代替。

所有新入口只限真实私有PG/本地签名API/FakeProvider，保持Release/云/真实账号/模型未激活。权限/契约/入口未获批前不实施。

## C2：旧结果 fence 与撤回范围

- 复用已合并#227 Part1的canonical capture/lease，在真实edit/pause/resume/到期后阻止旧delta/completed/proposal；原RUN、账本、原attempt和UNKNOWN保持，不能靠Context/hash相等放行。
- 来源撤回需要真实权威producer。建议后续另审**只停止使用**的最小writer：同scope锁下服务端枚举并锁定完整来源历史/反向引用，匹配expected item/source版本，写不可复活的withdrawn/来源失效状态和原动作屏障，推进同一epoch；不物理删除、不调用账号cleanup、不宣布#26清理完成。具体history覆盖、source列权限与up/down须在#270交第二份详细稿后批准；未批准则该组合是明确子票停点。
- 旧提取/索引消费同一epoch/条目/来源协议。不存在的#23生产业务不伪造；L0合约反例与真实服务组合分开记录。
- 编辑/停用/撤回先提交 vs 发布先取锁，两种barrier排序都要实际PG/worker验收；已发给provider与历史展示内容无法收回，不能新发布为有效结果。

## 预定证据（全部新能力UNRUN）

1. 真实签名API＋受限角色，三类编辑、paused-edit-resume因果、来源/原文/范围保留、同对话/新会话新值。
2. 两并发CAS仅一方提交，原bytes重放/冲突，真实rollback/ACK未知/重建原action查询；不调用Trip路径。
3. runtime跨用户API/SQL拒绝、无scope和dirty连接复用拒绝、最小列权限及回执不可改；新迁移往返和非空down拒绝、旧数据/ACL/RLS保留。
4. 正式worker/FakeProvider的真实生命周期与捕获后竞态、撤权/取消/UNKNOWN；回补#227框4和#11/#19转入项。
5. 新head完整test.py/pg_suites.py（B相关组＋新管理/fence专项）、全部CI、独立红线APPROVE、锁head/main CI，之后才勾相应框。App由A验收。

## 请求JT决定

请批准或修订：C1上述新编辑来源/历史/paused因果契约、追加迁移与最小列权限，以及逐文件列明的B管理API本地接入写权。批准前只交设计/拆票，不执行DDL或开启closed入口。C2最小撤回writer仍先交单独详细稿，不把本次批准推导成全量删除或未来typed迁移授权。


## C1具体DDL审阅稿（未执行，不登记migration号）

已在隔离空私有PG只应用现有Memory/management schema，读取pg_constraint确认现有
operation/check/unique名称如下。下列新DDL没有执行；批准后才放入最新manifest后
的新迁移，先核届时schema/ACL未漂移。若既有权限/RLS已变化则重审，不撤销他人新增权限。

```sql
-- up：仅审批稿；后续迁移由现有runner持有原子事务。
ALTER TABLE cj_memory_management_action
  ADD COLUMN previous_source_id text,
  ADD COLUMN new_source_id text,
  ADD COLUMN disabled_by_version bigint;
ALTER TABLE cj_memory_management_action
  DROP CONSTRAINT cj_memory_management_action_operation_check,
  DROP CONSTRAINT cj_memory_management_action_check;
ALTER TABLE cj_memory_management_action
  ADD CONSTRAINT cj_memory_management_action_operation_check
    CHECK (operation IN ('pause','resume','edit')),
  ADD CONSTRAINT cj_memory_management_action_check CHECK (
    (operation='pause' AND status='disabled') OR
    (operation='resume' AND status='active') OR
    (operation='edit' AND status IN ('active','disabled'))),
  ADD CONSTRAINT cj_memory_edit_source_shape CHECK (
    (operation IN ('pause','resume') AND previous_source_id IS NULL
      AND new_source_id IS NULL AND disabled_by_version IS NULL) OR
    (operation='edit' AND previous_source_id IS NOT NULL
      AND new_source_id IS NOT NULL AND previous_source_id<>new_source_id
      AND ((status='active' AND disabled_by_version IS NULL) OR
           (status='disabled' AND disabled_by_version IS NOT NULL
            AND disabled_by_version<version)))),
  ADD CONSTRAINT cj_memory_edit_previous_source_fk
    FOREIGN KEY(scope,previous_source_id) REFERENCES cj_memory_source(scope,source_id),
  ADD CONSTRAINT cj_memory_edit_new_source_fk
    FOREIGN KEY(scope,new_source_id) REFERENCES cj_memory_source(scope,source_id),
  ADD CONSTRAINT cj_memory_edit_pause_anchor_fk
    FOREIGN KEY(scope,item_id,disabled_by_version)
    REFERENCES cj_memory_management_action(scope,item_id,version);
ALTER TABLE cj_memory_management_action ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_management_action FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_m2_memory_management_scope ON cj_memory_management_action TO cj_m1_runtime
  USING (scope=nullif(current_setting('cj.message_scope',true),''))
  WITH CHECK (scope=nullif(current_setting('cj.message_scope',true),''));
GRANT SELECT,INSERT ON cj_memory_management_action TO cj_m1_runtime;
GRANT UPDATE(status,version,original_input,source_id,source_version)
  ON cj_memory_item TO cj_m1_runtime;
```

原unique(scope,item_id,version)被pause版本FK复用，不重复建立索引。FK只证明同scope/
item的版本存在；DB行解码与guarded状态转换还须验证anchor确实为本模块pause，且
当前版本的edit-disabled继承了合法因果；不允许客户端传anchor。原status/version/
scope/item FK约束、Memory四表policy与source批准不可更新权限全部保留。

```sql
-- down：仅审批稿；新语义非空拒绝，不删任何业务数据。
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM cj_memory_management_action
             WHERE operation='edit' OR previous_source_id IS NOT NULL
                OR new_source_id IS NOT NULL OR disabled_by_version IS NOT NULL) THEN
    RAISE EXCEPTION 'edit history is not empty; retain schema and reconcile originals';
  END IF;
END $$;
REVOKE UPDATE(status,version,original_input,source_id,source_version)
  ON cj_memory_item FROM cj_m1_runtime;
REVOKE SELECT,INSERT ON cj_memory_management_action FROM cj_m1_runtime;
DROP POLICY cj_m2_memory_management_scope ON cj_memory_management_action;
ALTER TABLE cj_memory_management_action NO FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_management_action DISABLE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_management_action
  DROP CONSTRAINT cj_memory_edit_pause_anchor_fk,
  DROP CONSTRAINT cj_memory_edit_new_source_fk,
  DROP CONSTRAINT cj_memory_edit_previous_source_fk,
  DROP CONSTRAINT cj_memory_edit_source_shape,
  DROP CONSTRAINT cj_memory_management_action_check,
  DROP CONSTRAINT cj_memory_management_action_operation_check,
  DROP COLUMN disabled_by_version,
  DROP COLUMN new_source_id,
  DROP COLUMN previous_source_id;
ALTER TABLE cj_memory_management_action
  ADD CONSTRAINT cj_memory_management_action_operation_check
    CHECK (operation IN ('pause','resume')),
  ADD CONSTRAINT cj_memory_management_action_check CHECK (
    (operation='pause' AND status='disabled') OR
    (operation='resume' AND status='active'));
```

这里down恢复0010/0015的原权限状态；只允许空的新edit语义，不改旧pause/resume
回执及Memory条目。后续若C2或其他迁移增加依赖，必须先按链逆序回退，不能CASCADE
强删依赖。未批准前不运行这些SQL；新能力/新DDL的up/down/RLS/并发专项均UNRUN。
