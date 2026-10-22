# CJ024 注销清理核心

可运行纯状态机、CAS 内存事务 repository、metadata journal 序列化与重建。无新增依赖，无数据库/网络/真实 hook；生产 durable adapter 尚未实现。journal 必须完整原子保存才有恢复依据；本模块不承诺进程崩溃自动落盘。

```sh
PYTHONPATH=backend/auth:backend/cleanup /opt/homebrew/bin/python3.14 -m unittest discover -s backend/cleanup/tests -v
```

需要 Python >=3.10（当前实际验证3.14）；系统 `/usr/bin/python3` 3.9 无法导入原 AUTH 的 union 注解，最初命令在导入前失败，未改 AUTH。14测试合成 PASS；首次测试样例参数重名失败保留 [tests-before.txt](evidence/tests-before.txt)，修正后 [tests.txt](evidence/tests.txt)。

接口与原域接入缺口见 [内部候选](../../contracts/cleanup/README.md)。默认 registry1.6.0+无能力为 blocked，真实执行和公开进度查询始终关闭。测试完整确认只证明合成状态转移，不证明真实删除、生产持久化或权限隔离。其他用户不受影响仅是本 repository 同 scope 键隔离测试；业务数据/设备隔离仍 UNRUN。
