# ADR-0008 消息发送许可：服务端会话序号作为不可回退的证据

- 状态：proposed（Claude 起草，待 JT 批准；批准后改为 accepted）
- 日期：2026-10-27
- Issue：[#162](https://github.com/JTCAO515/G2C/issues/162)（父票 [#10](https://github.com/JTCAO515/G2C/issues/10) CJ-009）
- 实现：[#163](https://github.com/JTCAO515/G2C/issues/163) 服务端，[#164](https://github.com/JTCAO515/G2C/issues/164) App
- 契约：[contracts/message/SEND-PERMIT.md](../../contracts/message/SEND-PERMIT.md)（`MESSAGE-SEND@1`）

## 背景

[`ios/Modules/CJMessageClient/ACTIVATION-GATE.md`](../../ios/Modules/CJMessageClient/ACTIVATION-GATE.md) 禁止 App 真实发送消息（live POST）。原因如下：

- 客户端用本地加密快照记录“已暂存 / 结果未知”的发送动作。
- 这个快照可以被回滚：备份恢复、重装、旧密文重放都会造成回滚。
- AES-GCM 和 key ID 只能证明快照没被篡改，证明不了它是最新的。
- 回滚后，客户端不知道之前已经发出过一条消息，可能换一个新 `message_id` 再发一次，造成重复消息和重复运行。

该文件要求的解锁条件是：一份**不可回退**的原动作证据，绑定已验证的账号和环境，并且在重启、备份恢复、密钥生命周期变化和结果未知时都成立。

**仓库证据**（`origin/main` 795ee19）：

- `POST /v1/messages` 的幂等键是 `message_id`：
  - 同字节重复提交，返回原回执；
  - 不同字节，返回 409 `INPUT_CONFLICT`。
- `GET /v1/message-receipts` 只返回回执或 `null`。
- `cj_message_chat` 已有 `generation`（每个会话一个，不变）和 `last_sequence`（每接收一条消息加 1）。
- 接收在作用域行锁（`FOR UPDATE`）内串行执行。
- 关闭的会话不会被重新激活（`Service.open_conversation`）。
- 没有任何写接口接受“预期序号”。

## 决策

### 1. 权威来源是服务端的会话头，不是客户端快照

**会话头**指 `(conversation_id, generation, last_sequence)`，由服务端在作用域锁内维护，只增不减。

每条新消息的请求体都必须带上客户端**从服务端读到的**预期会话头，即 `expected_generation` 和 `expected_sequence`。服务端在同一事务里按下面顺序判断：

1. 按 `message_id` 查已有回执。
   - 同字节：返回原回执（200）。
   - 不同字节：返回 409 `INPUT_CONFLICT`。
2. 会话不存在、属于他人或已关闭：沿用现有的 unavailable 语义，不暴露是哪种情况。
3. 当前会话头不等于预期值：返回 409 `SEQUENCE_CONFLICT`，`recovery = reconcile_original`。
4. 等于预期值：按 `sequence = last_sequence + 1` 接收，同一事务写回执和投递义务。

**会话头就是“首次发送许可”。** 同一个会话位置 `(generation, s)` 最多接受一条消息。后果如下：

- 客户端的本地状态无论被回滚到哪个版本，最多导致预期值过期、请求被拒绝，不可能产生第二条被接受的消息。
- 已在途的旧请求和新请求带着同一个预期值，只有一条能成功。
- 会话头一旦越过 `s`，带 `s` 的请求就**永远**不会再被接受。这是判断“结果未知”终态的依据，见第 3 条。

### 2. 发送状态读取：原子返回回执和会话头

新增只读接口 `GET /v1/message-send-status?conversation_id=&message_id=`（`message_id` 可省）。它在**同一个读事务**里返回：

- `receipt`：按当前作用域查 `message_id`，没有则为 `null`；
- `head`：会话头，会话不可用时为 `null`。

二者必须来自同一快照。如果分两次读，“先读回执为空、再读会话头已前进”会把一条刚刚被接受的消息误判为“永不接受”。

### 3. 结果未知的对账语义（客户端判定表）

对一条预期值为 `(g, s)` 的消息 M，用发送状态的一次读取判定：

| 读取结果 | 判定 | 客户端动作 |
|---|---|---|
| `receipt` 非空且 `input_sha256` 与原字节一致 | **已接收** | 显示回执；后续运行状态由 RUN 查询 |
| `receipt` 非空但哈希不一致 | **完整性错误** | 停止该会话的发送，报告；不重发 |
| `receipt = null`，`head = null` | **未接收（终态）**：会话已不可用，M 永远不会被接受 | 标记未发送，保留原文本供用户另行处理 |
| `receipt = null`，`head.generation ≠ g` | **未接收（终态）** | 同上 |
| `receipt = null`，`head.last_sequence > s` | **未接收（终态）**：位置已被别的消息占用 | 同上；先刷新历史，再由用户决定是否重新发送 |
| `receipt = null`，`head = (g, s)` | **仍可接收** | 只允许用**原 `message_id` 和原字节**重新提交；结果只有两种，见表下 |
| `receipt = null`，`head.last_sequence < s` | **服务端回退**（只可能来自服务端备份恢复） | 停止该会话的发送，进入 `resync_required`，按 L2 验证票 [#30](https://github.com/JTCAO515/G2C/issues/30) 处理 |

“仍可接收”时用原 `message_id`、原字节重新提交，结果只有两种：

- 被接受（原请求从未到达）；
- 返回原回执（原请求已经先到达）。

不存在第三种结果。这不是“换 ID 重发”，也不重建输入，与 CJ-009“不自动生成新消息 ID 重发未知请求”一致。

“未接收（终态）”之后，用户可以把原文本作为**新消息**发送：这时用新的 `message_id`，以当前会话头为预期值。这是用户的新动作，不是自动重发。

### 4. 账号与环境绑定

- **服务端作用域**由已验证的 issuer、subject 和环境 profile 决定（`backend/cj_api/composition.py`；当前只接受 `local`）。
  - 会话头、回执和 CAS 都在这个作用域内。
  - 其他账号的会话一律表现为不可用，不能枚举。
- **客户端**缓存的会话头属于“环境 + 账号 + 会话”。下列任何一项变化，都要丢弃全部缓存的会话头，重新读取：
  - 账号切换；
  - 环境切换；
  - 会话凭据变化；
  - CJSession 的 generation 变化。
- 读会话头和提交，都必须使用同一个已验证会话。服务端在事务、提交、返回三个阶段复核身份（现有 `Boundary._bind`）；身份在中途变化时，按现有规则返回 `ACCESS_DENIED` 或 `MESSAGE_OUTCOME_UNKNOWN`。

### 5. 保留期

| 数据 | 保留期 | 过期后的语义 |
|---|---|---|
| 回执（含原字节）与会话头 | 会话处于活动状态、账号存在期间一直保留；M1 不设 TTL | — |
| 关闭的会话 | 不重新激活，`conversation_id` 不可复用（已有行为） | 发送状态返回 `head = null`，按第 3 条判为终态 |
| 账号注销（CJ-024 [#27](https://github.com/JTCAO515/G2C/issues/27)） | 整个作用域删除 | 旧令牌认证失败，不会落入新账号的作用域 |

去重的承诺范围是“会话存活期间”，不是无限期（`docs/contracts.md` 的幂等规则）。

### 6. 重启、备份恢复、密钥生命周期

| 场景 | 结论 |
|---|---|
| App 重启，或进程内状态丢失 | 本地动作只是缓存；未结案的动作按第 3 条用发送状态对账 |
| 客户端快照回滚或备份恢复，旧动作丢失 | 丢失的动作如果已被接受，会出现在历史里，会话头也已前进，新发送会拿到新的预期值；如果没被接受，它的在途请求最多和新请求竞争同一个位置，只有一条成功 |
| 消息密钥丢失或轮换 | 等同于本地数据丢失，同上；密钥不参与发送权威判定 |
| 服务端备份恢复（会话头回退） | 不在 M1 范围；客户端检测到 `head.last_sequence` 小于已知回执序号时停止发送，进入 `resync_required`（L2 → [#30](https://github.com/JTCAO515/G2C/issues/30)） |

### 7. App 侧激活条件（替代 ACTIVATION-GATE.md 的“永不激活”）

真实发送只有在**全部**满足下列条件时才能打开：

1. **构建与会话**
   - M1 阶段只在 DEBUG 模拟器、显式开发会话下可用，条件与 #172 的 Trip 宿主相同。
   - Release 和真机保持关闭，直到 CJ-007 [#8](https://github.com/JTCAO515/G2C/issues/8) 的真实账号绑定达到 L2，并由 JT 批准。
2. **请求体**：必须是 `MESSAGE-send.1`。预期会话头来自本进程内、同一绑定下的一次发送状态读取；本地快照里的会话头不能当作预期值。
3. **先结旧案**：同一会话里本地已知的未结案动作，先按第 3 条结案，然后才能暂存新消息。
4. **一次性许可**：保留 `FRESH-AUTHORIZATION.md` 的进程内一次性许可。从存储加载的 `staged` 仍然改成 `queryRequired`。`queryRequired` 和 `notObserved` 都只能先读发送状态，判定为“仍可接收”后才能用原字节重新提交。
5. **测试通道不变**：`interceptedTestTransport` 仍只用于测试，不是生产激活路径。`liveReadTransport` 改为“带预期会话头的提交可用”，其余提交仍在取凭据之前被拒绝。

#164 负责按本条改写 `ACTIVATION-GATE.md`，并为每个条件写负例测试。

### 8. 版本与迁移

- **请求体版本**
  - 新增 `MESSAGE-send.1`：在 `MESSAGE-draft.1` 的字段基础上，加 `expected_generation`（字符串）和 `expected_sequence`（≥ 0 的整数）。
  - `MESSAGE-draft.1` 的 POST 撤回：新消息和重放一律返回 400 `INVALID_INPUT`。目前没有生产数据，也没有任何客户端真实发送过（App 的 POST 门禁一直关闭），所以没有处于“结果未知”的 draft.1 动作需要兼容。
  - 已存的 draft.1 回执照常可以通过历史和回执查询读取。
- **新错误码**：409 `SEQUENCE_CONFLICT`，`category = conflict`，`outcome = failed`，`recovery = reconcile_original`。沿用现有 `ErrorInfo` 枚举，不新增枚举值。
- **新接口**：第 2 条的发送状态读取。
- **数据库**：不需要新迁移。`generation`、`last_sequence`、作用域行锁和关闭语义都已存在。
- `contracts/api/openapi.json` 由 #163 按本 ADR 更新。#163 的允许修改范围相应加入该文件和生成的客户端代码。

消费影响表：

| 消费者 | 影响 | 处理 |
|---|---|---|
| iOS `CJMessageClient`（POST 一直关闭） | 无真实流量 | #164 实现 `MESSAGE-send.1` 与发送状态读取 |
| 后端测试与本地端到端脚本（使用 draft.1 POST） | 会失败 | #163 一并改成 `MESSAGE-send.1` |
| `contracts/message/model.py` 草案模型 | 仍描述 draft.1 | 保留为历史草案；`MESSAGE-SEND@1` 以本 ADR 和 SEND-PERMIT.md 为准 |

## 被否决的方案

- **客户端单调计数器或硬件安全存储**：iOS 没有跨备份恢复的单调计数器；Keychain 也会随备份恢复。
- **服务端签名的发送许可令牌**（仿照 Trip 确认，先 prepare 再 act）：需要新表或签名 key 和过期时间窗，多一次往返。会话头已经是现成的、只增不减的服务端状态，可以给出同样的单次接受保证，而且不依赖时间。
- **只靠 `message_id` 幂等**：本地动作丢失后，客户端不知道旧 ID，只能换新 ID 发送，正是要防止的情况。

## 已确认 / 证据 / 待决 / 推断

- **已确认事实**：第“背景”节列出的仓库证据。
- **用户决策**：待 JT 批准本 ADR（ADR 修改属于 ADR-0007 第 3 条的停点）。
- **待验证假设**：
  - 作用域锁加 CAS 在并发下只接受一条消息，由 #163 的 PG 并发测试证明；
  - 新可选字段对旧解码器的影响，由 #163 和 #164 验证。
- **Claude 的推断**：单个会话串行发送的限制对 M1 的聊天体验没有影响。多设备同时在同一会话发送时，后发的一方会收到冲突，需要刷新后重发；这与 `docs/contracts.md` 里“同聊天顺序”的约定一致。

## 验证

- `contracts/message/check_send_permit.py`：判定表和请求体正负样例（L0，进入 `scripts/test.py`）。
- #163：PG 并发 CAS、结果未知与崩溃恢复、跨账号枚举负例（L1）。
- #164：模拟器上的真实发送，以及回滚、重启、结果未知的对账（L1）。

## 回滚

本 ADR 和契约文件可以直接 revert。#163 合并之后再回滚，需要同时 revert 服务端实现，App 的 POST 门禁随之恢复关闭。
