# CJ-003 本地记忆组件候选

本段只评估 **ReMe `0.4.1.13` 的 LocalFileStore + BM25 + LocalFileGraph**。建议有条件保留这一条路线，作为 CJ 权威条目的派生检索组件；禁止把它作为可直接信任的多用户记忆服务。无需引入第二套 Mem0：本地路径可用，已识别的授权、正式版本和撤回责任本就属于 CJ。该建议不是 ADR 接受、正式 MEMORY 契约冻结或 Issue #3 完成。

## 版本、来源与环境

- 项目 base：`13905e4587feb8611ebde5e3621024f3338532ae`，分支 `cj/003-memory`；仅 `spikes/memory/**`。
- 官方发布：[PyPI 0.4.1.13](https://pypi.org/project/reme-ai/0.4.1.13/)，Python 要求 `>=3.11`；发布 wheel SHA-256 `82fbf5a53674348afb9054387227ee948e1ca677663b14741b95564a5c756ca8`。
- 本次实际运行：macOS arm64，CPython `3.14.7`；完整平台值见 `evidence/results.json`。这不是 Python 3.11 至 3.14 全矩阵保证。
- `requirements.lock` 固定全部 136 项依赖及哈希；`evidence/installed.txt` 是实装清单。只安装 `as` extra 以满足包的导入依赖，未安装 `core` 全套、Studio、FAISS、zvec 或本地模型。
- ReMe wheel 自带 Apache-2.0 LICENSE；精确许可路径和实装源码 SHA-256 见 `evidence/provenance.json`。完整传递依赖许可审计 UNRUN。
- [官方仓库](https://github.com/agentscope-ai/ReMe) main 在检查时为 `a4f606c6a8ad0d90743c658bfe19151450416236` / `0.4.2.0`，仅作定位参考；**测试执行与结论均来自已安装的 0.4.1.13 wheel**。滚动网站文档不能冒充固定发布版本证据。
- requested 模型：`gpt-6.1-sol` / high（派工创建参数）；current effective：UNKNOWN。组件不调用模型。

## 重跑

在本目录执行，所有缓存、虚拟环境和合成数据都留在本目录：

```sh
UV_CACHE_DIR="$PWD/.uv-cache" uv venv --python /opt/homebrew/bin/python3.14 .venv
UV_CACHE_DIR="$PWD/.uv-cache" uv pip sync --python .venv/bin/python --require-hashes requirements.lock
.venv/bin/python probe.py
.venv/bin/python source_history_probe.py
.venv/bin/python single_writer_probe.py
UV_CACHE_DIR="$PWD/.uv-cache" uv pip check --python .venv/bin/python
```

前三条中的第一条仅用于环境不存在时；已有 `.venv` 不需覆盖。下载依赖需网络，探针运行不需网络、凭据或服务。其他机器使用其已安装的同版 Python 路径；本次只验证上述平台。使用独立虚拟环境，不能对共享环境执行 sync。

每次运行创建新的 `.data/run-<uuid>/`，不覆盖旧合成数据。worker 是独立子进程，各自 cwd 是独立工作区；运行时不继承 provider/代理/服务环境变量，并用 Python audit hook 拒绝 `socket.connect`。没有假 embedding、假 ReMe store、LLM stub 或 HTTP 服务。测试手工构造独立条目的真实 `FileNode`/`FileChunk` 输入，不验证 LLM 自动提取或完整文件 watcher。两个合成用户每人有事实、经历、偏好三个条目，包含独立 source id、时间、类型、版本和确认状态；中英文字面查询指向同一条目，**不证明跨语言语义召回**。

`evidence/results.json` 为逐项 PASS/FAIL；`workers/` 为真实组件日志；`data-manifest.json` 记录本次本地快照相对路径、大小和哈希。本地原始快照不提交仓库。脚本退出 0 表示预定观察及断言成立，**不表示所有产品硬条件 PASS**；保留的原生 FAIL 是可复现反例。首次脚本输出解析和 reindex scope 使用错误已修复，前者的初次 workspace 保留在 `.data/`，后者栈在 `evidence/harness-scope-failure.log`，不是组件能力失败。

## 原生能力与缺口

| 检查 | 结果 | 含义 |
|---|---|---|
| 两工作区、独立条目和来源元数据；dump/close 后新进程检索 | PASS | 组件分区与正常 checkpoint 持久化；不是账号认证 |
| 同路径纠正替换旧 chunks；删除后仅 BM25 重建及重启 | PASS | 最新 chunk 视图可以正常替换/删除；重建只消费当前 chunks |
| 用户更正后旧任务 v1 写入 | FAIL | 无业务 expected-version 检查，v1 可覆盖 v2 |
| 仅 metadata `enabled=false` | FAIL | 组件不会自动解释 CJ 的启用/确认/适用范围语义 |
| 删除后旧来源重新写入并重建 | FAIL | 无 CJ 撤回依据，旧来源能恢复有效检索结果 |
| `LocalFileStore.delete` 清理原始文件 | FAIL | 它删除派生 nodes/chunks/index entries，不替调用方删除磁盘来源 |
| upsert 返回后异常退出，未 dump/close | FAIL | 本次观察未 checkpoint 内容丢失，不能据此给持久保存回执 |
| 两实例共用一工作区的旧 snapshot checkpoint | FAIL | 另一实例可恢复被删派生条目，实例内 asyncio lock 不等于跨进程锁 |

固定发布源码位置：`reme/components/file_store/{base_file_store,local_file_store}.py`、`components/keyword_index/bm25_index.py`、`components/file_graph/local_file_graph.py`。`upsert/delete/clear/dump/reindex` 由实例内维护锁串行化；`dump()`、`close()`、`delete(path)`、`optimize_index()`、`clear()`、`reindex("bm25")` 为本次实际调用的生命周期/清理入口。BM25 有 lazy deletion，物理整理和 checkpoint 另行调用。组件 pickle 快照只允许来自受控可信存储，不读用户上传 pickle。

本配置存储为原始合成文件、压缩 JSONL chunks/graph、BM25 pickle；无向量或外部数据库。各工作区必须有持久盘和单 writer owner。不得用进程级 `chdir` 在一个并发服务里切用户：本探针按子进程 cwd 分区，生产接入需由已验证 principal 确定 ApplicationContext/workspace，并限制内部入口。本地受控入口的跨进程独占实验见下；分布式事务、崩溃到多文件 checkpoint 中间、磁盘故障和性能容量均未验收。

## 受控入口的进程间 writer 独占差额

从 `56b85ebd93f9a4d48a057757a5305704a25fec11` 继续本地实验，`writer.py` 使用真实 POSIX `flock(LOCK_EX | LOCK_NB)`。取得工作区持久 `.cj003-writer.lock` 的独占锁后才构造和启动真实 ReMe；第二 writer 立即显式失败，不读取/覆盖旧快照。CJ `FenceExperiment` 拒绝裸 ReMe store，`probe.py` 的 guarded 路径统一通过 `WorkspaceWriter`；原生路径仍直接测 ReMe，六项原生 FAIL 不变。

锁覆盖 ReMe 启动、整个 CJ 权威/派生写操作、checkpoint 和所有依赖的 close；关闭完组件才关闭锁 fd。锁文件从不 unlink，不用删除 PID 文件猜测接管。关闭的 writer 永久失效，不从新 owner 借锁来复用旧内存；PID/cwd/锁 inode 变化亦拒绝。`FenceExperiment.project` 的来源文件写入和 SQLite 变更也在 owner operation 范围内，防止只保护索引但漏掉原始文件。这里的锁不是认证或恶意同 UID 代码的沙箱：原生裸 store、直接磁盘访问、主动 unlink/替换锁文件、不同主机/网络文件系统不在受控范围；不能据此承诺生产级物理清理。

`single_writer_probe.py` 启动真实子进程，验证同一工作区第二 PID 被拒绝且文件哈希不变、其他工作区独立、正常关闭后新 PID 接手、持锁子进程被 SIGKILL 后 OS 释放锁并允许重启。旧 owner 释放后仍保持进程和原始条目对象存活；在新 owner 已读到 `cleanup=complete` 时，依次尝试 11 个物理/权威写入口和晚到 close，均拒绝或无操作。对比整个工作区文件哈希，并让新 owner 重读 SQLite、解压 ReMe chunks/graph、BM25 快照及源文件，确认被删样例文本没有复活，另一条事实仍可检索。

差额产物在 `evidence/single-writer/`（结果、PID/锁 inode 事件、日志、当前源码哈希与证据复用清单）；`evidence/single-writer-run.log` 为运行输出。先前来源 P2 的七项双审 PASS 和原生 FAIL 证据按 `56b85eb` 复用，不重复执行；旧 `evidence/verification.json` 是该基线的作者记录，当前差额以 `evidence/single-writer/verification.json` 为准。此实验新增本机单 writer 条件下的清理防复活证据，不补足备份、分布式、外部 provider、账户权限或完整记忆产品验收。

## CJ 必须补充的语义与已做实验

`fence.py` 是**本地单 writer 实验**，SQLite 表只承载合成权威条目/撤回来源/epoch/cleanup 状态。它不是正式 schema、通用 adapter 或认证实现。它围绕真实 ReMe store 验证：

1. expected revision 阻止旧提取覆盖更正；缓存结果进入上下文前重读权威版本，返回权威新值而非信任旧 chunk 文本。
2. 停用立即排除上下文，重新启用经版本校验；上下文/回答发布须核当前 epoch（本段只测试 epoch gate，不声称实际 LLM 发布）。
3. 每次成功保存将条目与来源的关联追加到独立 `item_sources`，更正不能覆盖历史来源；删除在同一事务撤回该条目的全部历史来源，并提交 tombstone 和 pending，再做派生清理。旧任务、旧来源换新条目 ID 重放、旧快照重建均受 fence 校验。单进程 `asyncio.gather` 交错实际旧源写入与重建，未声称分布式竞态覆盖。
4. 清理故障保留 failed；新进程读取仍 failed，排除旧上下文；随后重试实际 delete、原始文件 unlink、optimize、dump，并从权威有效条目重建。另一条事实与另一工作区保持可检索。
5. 检查清理后受控 SQLite、解压 chunks/graph 与 BM25 快照中没有被删样例文本标记；该检查不覆盖日志/备份/供应商/磁盘可恢复副本，不等于安全擦盘。

定向 P2 回归另见 `source_history_probe.py`、`evidence/source-history/`：先以 S1 保存，用 S2 更正，在新进程删除，再以新条目 ID 重放 S1/S2；确认均被拒绝、不会进入上下文，且重启/重建后仍受撤回约束。相邻来源 `S1-neighbor` 和不同条目的 `S3` 仍能读写，新明确 `S4` 保存允许。修复前真实失败保留在 `evidence/source-history/before-fix-delete.log`（旧 S1 被接受并进入有效上下文），修复后结果单独记录。

本实验的 `source_id` 是独立条目的原子来源标识，按精确相等匹配，不按前缀撤回；正式系统复用一整条消息生成多项记忆时仍须由 MEMORY owner 固定细粒度来源身份与撤回范围，不能把本实验直接当生产 schema。历史关联只保留 ID、不保留旧正文。旧版已保存 payload 的实验库无法补造被覆盖的 S1，启动时显式拒绝缺少历史关联表的非空旧库，须创建新的合成验证空间；不自动迁移或覆写旧 `.data/`。

这些实验通过只说明最小本地 fence 设计可行，不会把缺失语义自动加到原生 ReMe。正式 MEMORY/CLEANUP owner 还必须实现：真实 principal/account generation、来源修订和授权范围、事务/回执/未知结果查询、候选推断确认、跨进程单 writer、防止其他原消息/摘要/cache/checkpoint 绕过 fence、在途模型结果失效、各域持久 cleanup hook 和失败恢复、备份恢复先重放撤回依据再开放读取。CJ 权威提交与派生 checkpoint 之间发生失败时应保留可重建状态，不能报全成；本实验尚未实现生产 outbox/派发恢复。

## 放行边界与下一步

代码/本地合成组件与 fence 实验：已执行，详见结果；原生硬条件缺口明确 FAIL。真实模型/embedding、真实 Auth/RLS、共享 PostgreSQL、自动提取/摘要质量、实际 prompt/下一轮回答、新聊天/不同旅行产品闭环、App/真机、备份恢复、部署与发布：**UNRUN**。本段没有网络服务、端口、云资源、旧数据/凭据、对外发布或 push。

单路线建议：继续 ReMe 受控派生检索；前提是 CJ-011/019/020/021/024 按上述 fence、权威与清理职责接入后独立 Review/Testing。若需要组件原生承担多 writer 耐久事务、授权和撤回，当前 ReMe 本配置不满足，不能直接接入放行。由 Main 路由固定候选，随后等待，不关闭整票、不改原 13 文档或正式契约。
