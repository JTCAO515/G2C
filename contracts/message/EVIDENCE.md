# CJ009 本地作者证据

2026-10-21；macOS / Python 3.9.6 标准库；无网络服务、安装、数据库或云调用。
base `59ea8aa46fed3738063b8031250367370c628cf8`，分支 `cj/009-message`。
固定候选为包含本文件的提交（精确 head 由本聊天交付并可 git rev-parse HEAD 读回）。

- PASS：`python3 -B contracts/message/check.py`，17/17，原输出见 check-output.txt。
- PASS：`python3 -m json.tool contracts/message/schema.json`，JSON 语法。
- PASS：提交前 `git diff --cached --check`，只含 contracts/message 路径。
- UNRUN：完整 JSON Schema meta-schema 验证器；本机没有 jsonschema，未安装依赖。
  手写输入校验/正负行为已测；不把 JSON 语法通过称完整 schema 引擎验证。
- UNRUN：独立 Review/Testing、CI、真实磁盘/事务崩溃、服务/API、真实身份/数据库
  隔离、云/模型、设备、部署。deepcopy 重建仅为合成故障状态模型。

固定 AUTH 输入 f20393179333b9ed9a1e7055b5d18aade468833e 的消费语义与缺口见
AUTH-CONSUMPTION.md。原有 15 场景 + 2 AUTH 增补通过；新增默认邮箱门禁影响
所有场景，因此最终一次运行整个小型契约套件。没有重跑无关工程检查。

未 push/PR/merge；未修改共享 OpenAPI、根锁/工程、原文档或 HANDOFF。
Issue #10 保持未完成。草案消费者确认、真实 AUTH/RUN/USAGE/清理接入、留存和
正式事务实现待各 owner 补齐；非空 Trip 明确拒绝，未伪造其权威。

## 文档差额：MESSAGE-semantics-draft.1

差额基线 f43ad4d1ee8eec5126efa84a6f372ddcb66c0061。Main 本轮转交该候选
Testing 17+5 风险 PASS、AUTH owner 消费确认；Review 进行中。上面的独立
UNRUN 是原作者交付时状态，不覆盖此转交更新；本线程未代做独立验收。
本差额仅 README/AUTH-CONSUMPTION/EVIDENCE/SEMANTIC-SCOPE 文档，明确
normative、fixture、真实待实现与排除范围；未修改模型/schema/样例，不重跑17项。
验证：文档相对链接存在、git diff --check、四个实现/样例文件相对基线字节一致。
完整 MESSAGE@1.0、真实服务验收和冻结仍未完成。

## P2 列表快照失效返修

差额 base：4705770530f8e634c651c1bbb306ef0d188655e0，保留该文档成果。
Review 经 Main 转交：列表游标未绑定数据代次，删除未读聊天后仍返回其 ID。
先对未修复模型运行定向检查，6 项中 4 FAIL / 2 PASS，原日志 p2-before.txt；
失败覆盖删除、epoch 变化、同 ID 重建、归属变化。未抹去失败证据。

修复：创建聊天分配内存单调 generation；列表快照保存每条聊天的 generation
和 epoch；每次读页先重查完整快照的存在性、归属和两项代次，任一失效均显式
resync_required，不返回部分旧页面、不静默漏项。另一账号变化不牵连此快照，
普通追加保留旧快照；失效后新快照仍能读取相邻有效聊天。旧格式游标显式重同步。

- PASS：python3 -B contracts/message/check_list_cursor.py，7/7；p2-after.txt。
- PASS：原 check.py 中列表分页、草稿重建、消息游标失效、分页追加/重建四项
  定向回归，4/4；p2-regression.txt。其余原测试证据复用，未重跑全套。
- PASS：git diff --check。schema.json、check.py、check-output.txt 未修改。
- 待独立 Review/Testing 差额复验；不自称 P2 已独立关闭。

范围仍为单线程内存模型；generation 随 image 重建保存，但不是正式数据库
generation/schema。故障注入直接改内存不是删除 API，不证明全域清理或真实隔离。
旧完整 fixture image 不提供迁移保证；本次旧游标格式返回 resync_required，正式
存储迁移/回退仍未实现。UNKNOWN/过期/外来游标均不伪装成空历史。

## P2 消息分页创建代次返修

差额 base：51886def20f97f80924ff5bb834ab7aca3f23c96。输入为 Testing 的
CJ-009-cursor/REPORT.md 与 repro_message_generation.py：原列表 P2 已独立
通过，但 page() 在同 ID 聊天删除重建后仍返回旧消息回执；不能概括为全游标通过。
本地新增定向检查先对原模型运行，4 项中 3 FAIL / 1 PASS，保留
p2-message-before.txt（重建、错创建代次、legacy 绑定失败）。

实现仅两处绑定变更：page() 保存/比较 principal、revision、cid、generation、
epoch。旧四元绑定与错 generation 均 resync_required；不静默空页。新快照可
显式返回重建聊天的空历史；普通追加、另一账号重建不使有效原快照失效。

- PASS：python3 -B contracts/message/check_message_cursor.py，4/4，
  p2-message-after.txt；覆盖同 ID 重建/deepcopy、错代次、legacy、追加/相邻账号。
- PASS：原 check.py 的 test_invalid_expired_and_cross_scope_cursors 与
  test_snapshot_paging_append_restart_and_replay 两项，p2-message-regression.txt。
- PASS：git diff --check。列表实现未改，原列表 7+4 证据复用；未全量重跑17+5。
- 待独立差额审验，不自行关闭新 P2。schema/正式 wire 版本未变，旧 fixture
  消息游标须重新取快照；不提供正式持久存储迁移或兼容承诺。

仍是内存故障注入，不是数据库删除、全域清理或真实隔离/崩溃恢复验收；旧失败
日志与470577文档成果保留，未写共享API/backend/云资源。
