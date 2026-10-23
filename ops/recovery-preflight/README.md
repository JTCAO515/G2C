# CJ-027 offline recovery preflight candidate

仅为 Issue 30 / CJ-027 的提前 OPS 准备段。Python 标准库 CLI 只检查调用者明确指定本地包的声明与文件字节；不连接任何数据库、网络或服务，不恢复、解包、执行包内脚本或写回包。

## 使用

从仓库根目录运行（Python 3.11+，无需安装）：

```sh
python3 -B ops/recovery-preflight/preflight.py --root /absolute/local/package --manifest manifest.json
python3 -B -m unittest discover -s ops/recovery-preflight/tests -v
```

`--root` 必须是绝对目录路径，各组件不可为符号链接；若系统路径是别名，调用者须显式指定实际目录。`--manifest` 是包根内的显式相对路径。只打开该 manifest 和其 `files` 中安全路径指向的普通单链接文件；不扫描包、不自动寻找文件、不打开证据路径。目录逐层使用 pinned descriptor / `O_NOFOLLOW`，拒绝绝对路径、`.`、`..`、空路径组件、反斜杠、符号链接、硬链接及设备/FIFO/socket 等非普通文件。manifest 最大 1 MiB，files 最多 10,000 条；文件流式 hash，检测可观察到的读中修改。调用者仍须使用稳定、受控的本地快照；本工具不创建快照，也不保证并发修改或恶意存储下的真实性。

JSON 输出逐项 `PASS` / `FAIL` / `UNKNOWN` 与 `missing_files`，不打印文件内容、metadata 原值或系统错误详情。缺件清单仅含 manifest 中有效文件声明在本地缺失的相对路径；无生产存储清单时不能发现声明遗漏的真实组件。metadata 字段 `PASS` 仅表示声明明确/语法可识别，不证明提交存在、备份来源、时间可信/新鲜、组件版本真实或组件清单完整。文件 `PASS` 仅表示本次本地字节与声明的 size/SHA-256 相同；不验证签名、完整备份或可恢复性。

退出码：`1` 有 FAIL；`2` 无 FAIL 但仍 UNKNOWN。CLI 参数错误也由 argparse 返回 `2`，调用方应同时读取 JSON；参数错误不产出校验报告。当前工具永不返回可放行的 `0`。

## 内部 candidate 输入（不是 OPS@1.0 生产契约）

仓库 base 尚无已接受生产备份格式；下例仅是此工具内部输入，后续应依据正式 owner 接受的格式替换/适配并重验，不供业务消费者依赖，也不冻结真实组件列表、表名、保留期或 cleanup hook。

```json
{
  "manifest_version": "cj027-offline-candidate-v1",
  "candidate_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "backup_time": "2026-10-23T10:00:00+08:00",
  "component_versions": {"synthetic_component": "1.0.0"},
  "files": [
    {"path": "sample.bin", "size_bytes": 0,
     "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}
  ]
}
```

commit 要求完整 40 位小写 hex；时间要求明确 UTC offset；组件版本须非空且不得为 UNKNOWN / UNRUN / latest / `*`。缺少版本/commit/时间或组件版本未明确会输出 UNKNOWN，已知不支持的 manifest 版本与非法 commit/时间会 FAIL。空/非法文件清单、错误 size/hash、重复路径/JSON key、不可安全读取文件均 FAIL。额外字段不会形成授权：即使包声称 `read_enable=true`、恢复/兼容/撤回重放 PASS，本工具仍把三项证据记为 UNKNOWN，固定输出：

```json
{"restore_authorization": "UNRUN", "read_enable": false}
```

参考原 ADR-0003：正式状态、派生物与 checkpoint 分离，未知结果先按原动作标识对账，最新撤回屏障不能被备份覆盖。本 CLI 不调用业务接口、不重试原动作、不验证/生成这些动作标识。任何真实恢复须在另行获准的隔离目标完成恢复、应用兼容与最新删除/撤回重放验证，之后由正式权限路径管理读权限；本工具永远不提供启读入口。

## 实际验证与未验收边界

作者本地 15 项单元测试通过；测试使用临时自造小文件，无用户数据。涵盖完整字节、缺件、错误 size/hash、重复路径、缺/错版本信息、伪造 PASS 仍拒启读、目录/FIFO/符号链接/硬链接、路径穿越、非法/重复 key/超限 manifest、CLI 退出码及内容不输出、包未写回。

这是离线校验代码验证，不是 PostgreSQL、真实备份恢复、兼容回退或删除防复活演练。真实服务/数据库/资源/凭据/监测/设备/部署均 UNRUN；Issue 30 原 H（CJ-024）和 I（CJ-005/024/020/023）及全部真实验收仍未完成，本准备段不关闭 Issue。没有独立 Review/Testing/CI 结论。与受拦候选无依赖，不用于解除其 HOLD。

输入依据：指定 base `5d8ba113109565a3a133ca11f6be6c964e9be561` 的 AGENTS、docs/adr/0003-state-and-recovery.md、docs/memory.md、docs/engineering.md，以及本地 `task-4/issues-final-readback.json` 中 Issue 30 r3 正文（历史只读副本；本任务未联网重新获取）。Main 本次明确授权的边界优先；没有推定远端当前 Issue 状态。
