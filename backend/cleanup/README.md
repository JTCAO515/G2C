# CJ024 注销清理核心

可运行纯状态机、CAS 内存 repository 与 metadata journal。后置新增 PostgreSQL 事务 repository 候选见下节；真实 hook、生产接入与公开查询仍未实现。原纯序列化切片不承诺进程崩溃自动落盘。

```sh
PYTHONPATH=backend/auth:backend/cleanup /opt/homebrew/bin/python3.14 -m unittest discover -s backend/cleanup/tests -v
```

需要 Python >=3.10（当前实际验证3.14）；系统 `/usr/bin/python3` 3.9 无法导入原 AUTH 的 union 注解，最初命令在导入前失败，未改 AUTH。14测试合成 PASS；首次测试样例参数重名失败保留 [tests-before.txt](evidence/tests-before.txt)，修正后 [tests.txt](evidence/tests.txt)。

接口与原域接入缺口见 [内部候选](../../contracts/cleanup/README.md)。默认 registry1.6.0+无能力为 blocked，真实执行和公开进度查询始终关闭。测试完整确认只证明合成状态转移，不证明真实删除、生产持久化或权限隔离。其他用户不受影响仅是本 repository 同 scope 键隔离测试；业务数据/设备隔离仍 UNRUN。

P2 receipt 解码返修：原两条独立 probe 逐字重放2PASS，新增3项 parser/journal控制PASS；原14PASS复用，不重跑无关状态机。见 [返修证据](evidence/P2-REPAIR.md)。旧e16仍HOLD，不追认为通过。

## PostgreSQL 元数据持久化候选（964 后独立差额）

`cj_cleanup.postgres.Repository(connect, scope, guard)` 使用显式注入的全新 psycopg3 连接，不读取 DSN。只访问 `cj_cleanup_journal_candidate`，不会执行任何其他域 SQL。`sql/candidate.sql` 仅可在已授权空库应用，不能自动迁移旧实例。

签名：`create(op)`、`query(operation_id)`、`journal(operation_id)`、`intent(operation_id, revision, target, invocation)`、`receipt(operation_id, revision, target, raw)`、`audit(operation_id, revision, manifest)`、`recover(operation_id, revision)`。scope 固定在 trusted host repository 实例；guard 必须由 host 提供，不能用空 guard 声称生产授权。

scope 主键阻止换 operation ID，行锁 + CAS 串行同操作变更；原 journal、派生状态、revision 同事务提交。每次加载逐事件重放并核对派生状态，拒绝不一致。原 reducer `rebuild(..., recover_inflight=False)` 只供持久适配精确回放，默认重建行为保留。query 不写、不重试、不确认 hook；确认上个 writer 已丢失后显式 recover 才以同 CAS 将在途意图记为 unknown。

intent 必须 COMMIT 成功返回后，未来获准 host 才可能调用 hook；本候选不调 hook。提交开始后异常、成功提交后 guard/close 失败均 `CommitUnknown`，只能用正常只读连接查询原 operation，不得换 ID、重发 hook 或假称回滚。提交前验证/CAS/guard失败回滚，不发布候选进度。

作者在**新建**私有 PostgreSQL16.15 Unix-only 空cluster验证12项真实事务测试及同实例一次停启原操作/unknown/history；这些仅覆盖 synthetic cleanup metadata，无真实账号/业务删除。源/证据提交分别固定，不改变964正在独立审验的切片。现生产部署、最小权限连接/策略、跨业务权威联动仍 UNRUN。

这张候选表自身含 scope/operation IDs 和最小确认摘要/回执元数据，属于私有存储；需要正式 owner 注册 canonical storage ID、留存/清理及恢复围栏后才能激活。本写区没有根 registry 写权，也没有自造注册条目；当前真实注销不得忽略这项新增存储，不能据候选表存在声称全域 complete。只在授权 synthetic 空库创建它。

本地 runner 使用已安装 psycopg3.2.10（局部 pin：tests/pg_requirements.lock），显式 `--pg-bin`/`--driver`。`tests/private_pg.py` 拒绝复用已存在路径；已保留实例不得再次自动启动。首次实际运行的资源和结果见后置 evidence/PG-RESULT.md。

P2 close 后最终围栏返修：最终 captured guard/context 检查在最后外部 `close()` 正常完成后；原 body/COMMITunknown 结果优先，close/rollback 错误不能遮盖原失败。新55458空cluster的原两probe + 8项相关txn控制10PASS，原55457/Testing实例未重启。详见 evidence/PG-CLOSE-REPAIR.md。

## 当前认证原进度读取（083后新切片）

`protected_progress.ProgressReader` 消费 canonical AUTH8b 的 ProtectedReadBoundary；
只读自身已有 operation 的有限白名单结果。只调用旧 PG query，不写恢复/receipt或删除。
完整返回bytes在原AUTH寿命内生成，AUTH 在进入与返回前各检查一次；不再复核宿主组合（rc.2）。
接口、限量、原因枚举、final-envelope接缝见 [PROTECTED-PROGRESS](../../contracts/cleanup/PROTECTED-PROGRESS.md)。
本目录原base的AUTH没有read_context：消费测试必须显式使用canonical8b源，不能回退假AUTH。
新正式集成由Main/CJ005带已合AUTH一起接，不把忽略目录的临时导出作为第二AUTH来源。

2026-10-23作者使用新私有PG16.15/Unix55459、canonical AUTH8b + synthetic verifier/accessfacts、
SELECT-only runtime role执行12定向组合检查PASS，旧14/strict/PG/close门复用、不重跑。
实际账号/真实撤权provider/注销后凭据和Issue27 I仍UNRUN；core.public_query和destructive入口保持关闭。
