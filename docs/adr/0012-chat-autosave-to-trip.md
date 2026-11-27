# ADR-0012：聊天回答自动保存到行程（来源标记、撤销、审计）

- 状态：**accepted**（以统筹审定合并为准；合并前是待批草稿。Claude 服务端线起草。规则主体由 JT 2026-11-27 确认，见「决定来源」）；修订 1：2026-11-27，新建行程首次保存的撤销（统筹按 JT 预授权批准，停点 5）
- 日期：2026-11-27
- Issue：[#1983](https://github.com/JTCAO515/G2C/issues/1983)（F-1，总票 [#1974](https://github.com/JTCAO515/G2C/issues/1974)）
- 关联：[ADR-0003](0003-state-and-recovery.md)（单一业务权威、确认与版本、幂等与未知结果）、[ADR-0007](0007-issue-closure-workflow.md)（证据级别、红线审查）、[CJ-TRIP-INTERNAL](../../contracts/trip/README.md)（Proposal / Action / confirm）、[TRIP structured.4 与 `TRIP-lio-undo.3`](../../contracts/trip/STRUCTURED-V4.md)、[LIO-trip-history.4](../../contracts/message/LIO-TRIP-HISTORY-V4.md)；后续票 F-2 [#1984](https://github.com/JTCAO515/G2C/issues/1984)（`LIO-answer-rich.1` 的 `trip_receipt`）、T-1 [#1994](https://github.com/JTCAO515/G2C/issues/1994)（实现，迁移 0061）、T-5 [#1998](https://github.com/JTCAO515/G2C/issues/1998)（隐私政策）

## 背景

JT 要 58.1 的回答「和行程有关就自动进画布，可以撤销」，不再要求用户每次点「保存」。

**仓库现状**（`origin/main` `57d2da47`）：

- **行程只有一张表**。Lio 写的和用户自己改的都落在同一张 `cj_trip_record`（每个 Trip 一行，只存当前版本），历史版本由已接受的 `cj_trip_proposal` 内容还原。对话绑定的那一趟由 `cj_trip_needs_current` 指向（迁移 0025），按 `lio_needs_id(scope, conversation)` 查询。用户手动编辑走 `POST /v1/trip-needs-edits` 和 `/v1/trip-needs-saves`，只能改这张当前选中的 Trip（`backend/trip/cj_trip/needs_edit_store.py` `_selected`）。
- **Lio 的规划和调整已经是服务端自签提交**。worker 产出 `trip_proposal` 后，`backend/draft/cj_draft/lio_plan.py` 的 `_commit`（`lio_rich.py` 经继承来的 `_save` 也走到这里）在同一个事务里 `confirm.issue(...)` 自签、`_act_in_tx` 提交新版本。action_id 固定为 `lio-plan-<run_id>` 或 `lio-edit-<run_id>`。用户不点确认，这条路径照样写进对话绑定的 Trip。
- **「必须用户明确确认」只约束外部的接受**。合同 README 规定 `confirm(scope, action, proposal)` 必须核对服务端持有的证据，证明同一个已认证用户看过这份摘要并明确选择了这个动作；「客户端看过、模型文字、非空引用」都不算授权。代码里这一条落在 `backend/trip/cj_trip/postgres.py` 的 `_act_in_tx`（`confirm(...) is not True` 即拒绝）和 `confirmation.py` 的 `tc1.` MAC 引用上，引用由 `POST /v1/trip-confirmations` 签发，`POST /v1/trip-actions` 消费。
- **App 的「保存到行程」现在只写本机**。#1958 先 `GET /v7/trip-structured` 读地点，再把摘要写进设备本地文件，服务端不写，开关 `G2C_CHAT_TRIP_PLACES_ENABLED` 默认关。
- **撤销只能撤最新一版**。`lio_history.py` 的 `_append_undo` 要求当前版本号和哈希都等于请求里的值，然后把上一版的字节作为新版本追加，basis 为 `lio-undo.1`。`fixed=true` 的点不能被撤销改动（structured.2 用 `_protect_fixed`，structured.4 用 `rich_history.protect_fixed`）。撤销没有时间限制。`TRIP-lio-undo.3` 在此之上加了 content_version 的精确匹配。
- **审计链**：回执表 `cj_trip_receipt` 有 scope、action_id、kind、proposal_id、candidate_hash、trip_id、committed_version、original_input。`cj_trip_needs_basis` 把 proposal 关联到 message_scope 和 run_id，再经 `cj_message_receipt` 关联到 message_id 和 sequence。**没有提交时间**，只有 proposal 的 `expires_at`。
- **点没有来源字段**。structured.4 的 item 有 id、text、verification、evidence、schedule、fixed、source_category（unknown、user_provided、queried、estimated，说的是事实来源，不是谁写的）、source_refs、kind、place、note、tip、reason_refs。没有 origin、author。
- 没有任何开关控制 Lio 写行程或撤销。

所以 58.1 真正要改的不是「从确认改成自动」，因为 Lio 自己的写入已经是自动的。要改的是三件事：Lio 写入时不能碰用户的点；每次写入给一个 24 小时内可撤的回执；回答里把这个回执告诉用户。

## 决定

1. **写在哪里、谁能写。**
   - 只写这个账号自己的、当前对话绑定的那一趟 Trip（`cj_trip_needs_current` 指向的那一张），scope 照旧来自 `scope_for(issuer, subject)`。不写别的 Trip，不跨账号，不新建第二张「画布」表。
   - 只有服务端判定为行程相关、并且通过现有 structured.4 来源绑定和校验的 RUN 结果才写。模型在文字里说「已保存」、App 传来的标记、回答类型字段，都不构成写入依据。
   - 写入仍走现有的唯一提交路径：proposal 不可变、内容哈希绑定、预期版本 CAS、NEEDS 来源租约、`fixed` 保护、持锁期间不调供应商。

2. **来源标记 origin。**
   - 每个版本的每个点都有一个 origin：`lio` 或 `user`。由服务端在提交事务里计算，模型、App 和请求体都不能指定。计算放在唯一的提交点 `_act_in_tx`，按这次写入的来源判定，所有写入路径都经过这里：Lio 的 plan 和 edit、`/v1/trip-actions`、NEEDS 编辑、manual、scoped，以及撤销。
   - **存放方式**：不改 structured.4 内容格式，冻结的内容和哈希不变。T-1 用迁移 0061 加一张只追加的表，键是 (scope, trip_id, trip_version, item_id)，和版本一起写，一经写入不再修改。读取接口把 origin 和内容一起返回，返回格式由 F-2 定。
   - **规则**：
     - Lio 新增的点是 `lio`。
     - 用户通过手动编辑或 NEEDS 编辑（改文字、改时间、换天、拖动顺序、标为固定）动过的点，从那一版起是 `user`。
     - origin 只能从 `lio` 变成 `user`，不能反过来。数据库用触发器强制：同一个 item_id，前一版是 `user`，后一版只要它还在，就必须还是 `user`。
     - 0061 之前就有的点没有 origin 记录，一律按 `user` 处理。宁可让 Lio 少改，也不误改用户的点。
   - **用户删除**：用户删掉的点记一条 `user` 删除记录（墓碑），键是 item_id，有高德地点 ID 的再加上 amap_id。没有 amap_id 的点只按 item_id 拦，不按名称比对，免得同名的不同地点被误拦。之后自动保存不再把同一个地点加回这一趟，Lio 只能在文字里建议；用户点了建议再加，这个点算 `user`。

3. **Lio 能做什么。**
   - 可以：新增点；修改或删除 `origin=lio` 的点；规划类回答新建或重排「Lio 草拟」的天，但只动这一天里 `lio` 的点；只提到某个地方的回答，把它放进「想去」（具体结构由 F-2 和 T-2 定，规则一样）；路线类回答更新相邻两点之间的路段。
   - 不可以：修改、移动、删除 `origin=user` 的点；改变两个 `user` 点之间的相对顺序；写别的 Trip。
   - 路段（legs）由服务端按相邻关系算出。用户手动选过交通方式的那一段算 `user`，Lio 不改。
   - **服务端在提交前做逐点比对**，在事务里核对：上一版每个 `user` 点在新版里逐字节不变（用 `packed(item)` 比），`user` 点之间的相对顺序不变，墓碑地点没有被加回。比对不过，整次写入拒绝，不做部分写入。回答照常返回，回执状态为 `not_saved`。

4. **确认流程怎么换（与 CJ-TRIP-INTERNAL README 对照）。**

   | 现有规则 | 自动保存之后 |
   |---|---|
   | `confirm` 必须核对用户看过并明确选择的证据；客户端看过、模型文字都不算 | **外部接受不变**：`/v1/trip-actions` 仍要 `tc1.` 引用。自动保存不走这条路，走 Lio 的服务端自签路径，这条路径今天就存在 |
   | 自签路径的授权来源是「本账号的这条消息和这个 RUN」 | 不变，另加三条前提：开关打开；第 3 条的逐点比对通过；写入范围限于第 1 条 |
   | proposal 不可变，接受时绑定哈希和预期版本 | 不变；预期版本冲突（用户刚改过）就不写，回执 `not_saved`，不重试、不合并 |
   | 同 action_id 同输入返回原回执；提交结果未知就按原 ID 查询 | 不变；回执状态 `unknown` 时，App 按原 action_id 查，不另发新动作 |
   | 拒绝不写 Trip；过期按数据库时钟 | 不变 |
   | 撤销 = 追加一个恢复上一版字节的新版本，不覆盖历史 | 不变，另加第 5 条的 24 小时窗口和 origin 复原 |

   「用户点了接受」换成「服务端自动接受，并留下可撤销的回执」。没有删掉任何校验，只是 Lio 的写入多了限制。

5. **撤销。**
   - 每次自动写入出一张撤销回执：`action_id`、`trip_id`、`committed_version`、content_version 和哈希、上一版号和哈希（也就是 `TRIP-lio-undo.3` 和 `LIO-trip-history.4` 的 `undo_target`），以及 `undo_until`（提交时的数据库时间加 24 小时）和一句摘要，例如「北京 · 第 1 天加了 3 个点」。这张回执放进回答的 `trip_receipt`（F-2）。
   - 撤销复用 `TRIP-lio-undo.3` 的现有处理：只有当前版本正好是这次自动写入的那一版，才能撤；撤销追加一个恢复上一版字节的新版本，origin 表照抄上一版的记录。服务端按数据库时钟检查 `undo_until`，过期就拒绝。
   - **只能撤最新的一次**：这正是 `TRIP-lio-undo.3` 今天的语义。版本号和哈希都必须等于当前版本，恢复的是 `current.version-1`（`lio_history.py` `_append_undo`、`lio_rich_undo_routes.py`、`rich_history.py`）。所以一张回执只在它那一版仍是当前版本、并且在 24 小时之内时才能撤。之后只要又有任何新版本，不管是 Lio 又写了一次、用户改了、还是撤销本身追加的版本，更早的回执都不能再撤。App 把它标成「之后有改动，已不能撤销」，用户可以自己删 Lio 的点。不做逐个往回撤：撤掉 B 之后再撤 A，版本对不上；如果硬要按新版本撤，恢复的其实是 B。
   - 按点撤销（只去掉那次加的、还没被动过的 `lio` 点）和逐个往回撤都需要新的撤销扩展，改 `_append_undo` 和路由。先不做，记成 T-1 的后续项，到时另写 ADR 修订。
   - 24 小时检查放在所有撤销入口共用的那层处理里（`_append_undo` 和 rich undo）。只要被撤的那一版是自动写入的，不管从哪个路由进来，都按数据库时钟检查，旧路由 `/v4/lio/trip-undos` 也绕不过去。
   - 撤销本身不是「用户动过」，不会把任何点改成 `user`。
   - **新建行程第一次保存的撤销**（修订 1，统筹 2026-11-27 按 JT 预授权批准）：自动保存新建了这一趟（committed_version = 1）时也出回执、可以撤销，但**不删除行程**。撤销追加一个新版本，把这份行程标成「已撤回」：这一版的内容是撤回标记，具体形式（状态字段或墓碑）由 T-1 定，App 不再显示这份行程；历史版本、回执、origin 和审计记录全部保留。
     - 只有同时满足两个条件才允许：这一趟只有这一版；里面没有任何 `user` 点。否则不能撤，回执显示「之后有改动，已不能撤销」。
     - 24 小时窗口、数据库时钟、只撤当前版本、按同一 action_id 对账，这几条和其他撤销一样。
     - 撤回之后，这个对话绑定（`cj_trip_needs_current`）标成已撤回，Lio 不再往这一趟回写；之后的规划另建新的一趟。
     - 撤回不算删除用户数据。真正的删除仍然只走注销账号的清理。
     - 回执在 wire 上的形状见 `LIO-answer-rich.1`（`undo.kind = withdraw_created`，请求 `LIO-trip-undo.5`）。

6. **审计链。**
   - 每次自动写入和撤销都留下：scope、action_id、消息（message_scope、run_id、message_id、sequence，沿用 `cj_trip_needs_basis` 和 `cj_message_receipt` 的关联）、candidate_hash、trip_id、committed_version、**提交时的数据库时间**（0061 新增，现在没有）、这一版的 origin 记录。
   - 撤销不删除任何记录，被撤销的那一版和它的回执都留着。
   - 保留期和清理跟随现有 Trip 数据：注销账号时一起清除。0061 的新表要登记进 `backend/storage-registry.json`，香港的注销清理清单（`deploy/hk/configuration.py`）也要加上。

7. **开关与上线顺序。**
   - 新开关 `CJ_LIO_TRIP_AUTOSAVE`，默认关，按账号名单打开。关着的时候，行为和今天完全一样：Lio 照旧自签写入，不做第 3 条的比对，**所以 Lio 仍可能改到用户动过的点**，和今天一样，这是有意保留的；回答里不出 `trip_receipt`，旧 App 照旧。origin 记录照样按第 2 条写，这样开关打开时数据已经齐了。（0061 之前的点都算 `user`，所以开关一开，Lio 就不能再改老行程里的点，只能新增。）
   - 打开之前必须满足：T-5 已合并，并且线上 `/privacy` 读回到新句子；0061 已在香港应用；统筹批准（停点 6：开关默认从关改开）。
   - 开关变量名在回滚目标镜像也认识之前，不写进香港的 worker.env（规则见「名单环境变量」）。

8. **失败不影响回答。** 自动保存失败，回答照样返回，回执状态三选一：`saved`；`not_saved`（版本冲突、会动到用户的点、超出单次上限、开关关闭）；`unknown`（提交结果未知，按原 action_id 查询）。一次写入的条数和天数设上限（T-1 定数值），超过整次不写。

9. **隐私。** 行程本来就存在香港，范围不变。隐私政策「行程」一节补一句：对话中和行程有关的建议会自动保存到你的行程，24 小时内可以一键撤销，也可以随时删除。这一句由 T-5 落地，在开关打开之前合并并读回。

## 不变量（T-1 的红线审查逐条核对）

1. Lio 的任何写入都不改 `user` 点的字节，不改两个 `user` 点的相对顺序，不加回墓碑地点。
2. origin 只能 `lio` → `user`，由服务端计算，数据库强制，按版本只追加。
3. 只写本账号当前对话绑定的 Trip；模型输出和 App 标记不是写入授权。
4. 唯一提交路径、proposal 不可变、哈希绑定、版本 CAS、NEEDS 租约、`fixed` 保护全部照旧。
5. 每次自动写入都有回执；撤销按数据库时钟限 24 小时，所有撤销入口都检查；只有当前版本能撤，追加新版本，不覆盖历史。新建行程的撤销只追加「已撤回」版本，不删除。
6. 外部接受仍要 `tc1.` 确认引用，不因自动保存放宽。
7. 开关默认关，关着时行为与今天一致；打开前隐私政策已上线读回。

## 不做

- 不改 structured.4 内容格式，不新开内容版本。
- 不给记忆加自动写入：记忆仍然要用户点「记住」（#1747、#1970）。
- 不做按点撤销，不做跨 Trip 的移动和复制。
- 不改外部 `/v1/trip-actions` 的确认要求。

## 决定来源

- JT 2026-11-27 定的规则（`strategy/59-dialogue-trip-memory.md` 第 0 节第 1 条）：Lio 只新增点、只改自己写的点，用户动过的点不碰，每次自动保存给撤销入口，24 小时内可撤。
- 统筹 2026-11-27 拆票 #1983：用户动过即永久 `user`；撤销复用 `TRIP-lio-undo.3`；审计链不断；对照 `backend/trip` README 写清替换点和不变量。
- 本 ADR 补充的细节（origin 存放、墓碑、只撤最新一次、开关前提、失败回执）由服务端线提出，随 ADR 一并请统筹批准。

## 验证（转给 T-1）

- 本地 PG 测试至少覆盖：
  - Lio 新增点；改 `lio` 点；试图改、移、删 `user` 点被拒；墓碑地点不能加回；
  - 用户编辑后 origin 变成 `user`，触发器拦住 `user` → `lio`；
  - 自动写入和用户编辑并发时版本冲突，回执 `not_saved`；
  - 撤销在 24 小时内成功、过期拒绝；后面还有新版本时拒绝；
  - 同 action_id 重放返回原回执；提交未知后按原 ID 对账；
  - 开关关闭时不出回执。
- 回答评测（Q-1 #2011）统计自动写入成功率和撤销成功率；L2 和 L3 转记 #32 和 58.1 真机回归票。
