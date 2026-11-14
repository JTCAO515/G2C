# Strict 候选真实冒烟：1 PASS / 1 FAIL / 4 UNRUN

**不放行。** 新阶段 `hk-strict-10000-smoke-001` 在英文地点＋路线首轮模型返回 UNKNOWN、正文为空时停止。中文地点＋路线已由原独立程序证明真实工具、后续模型和同 RUN 完整正文；其余四格、正式66与客户端提交计时未派发。不用 B 英文天气单例、旧候选或 fixture 补格。

## 开跑条件与版本

- B PR613 已锁 `c9adb9a15b6ec366201ad4d89d821ae010292b48` 合 `e18f248e490f8e958f8ebc2a692df04539d90bb1`；现场模型 stop=total=10000、M1原13保留，M4意图上限9987。
- [B 公网 strict 英文天气08后验](https://github.com/JTCAO515/G2C/issues/523#issuecomment-6701236470) PASS。C只读核四文件SHA、原三条 RECEIVED/同 RUN 正文与 ACK；这是开工前置，不是 C 冒烟、质量或 p95 通过。
- C_SOURCE=BACKEND=`c9adb9a15b6ec366201ad4d89d821ae010292b48`，640实际源码摘要；manifest `44b72f9ca0ab54e40a81703d7d26156fcbea9f6ce02a63846cdd144492b354f2`，四源 adapter `b49bbb2526255f597afe0648e23904c237dc1eef79aaecd856c188c8d617ad09`。
- 实际新待命入口 `g2c-c-runtime-c9adb9a1`，image `sha256:4b238d00738b8875d4e27ec5f7d7c4dbef0daf3196072c20ea45d214ac4251d3`，继承 B operator `246fc4ed555d98bd897dc3e5b727f14694fa0ff048a13a4908b70dff61cdd342`。UID10001、rootfs只读、无端口/socket；原两项服务键以0600只读文件提供，无云库/operator/cleanup/OSS身份。旧 Mac transfer 仍 SEALED。
- 唯一原 HK ledger `32d95019ea16443b81e648960c4baba0`，起点367行/67 INTENT/300 RECEIVED、ADOPTED `b52ed0c23a81c3eb167834a199260d501963a4099811f18968ad448204c1afe2`。实际含M1模型247/paid119，加未派预测153/62→400/181，在模型10000、工具总200内；预测没有入账。

## 原六格与最小复现

| 固定前置格 | zh | en |
|---|---|---|
| 地点＋路线 | PASS | FAIL：首轮模型 RUN UNKNOWN、正文0 |
| 天气 | UNRUN | UNRUN |
| 官方事实页 | UNRUN | UNRUN |

失败问题是原冻结英文输入：查询 Forbidden City、Jingshan Park，北京，各 page1/page_size1；复制实际 POI ID、GCJ-02 原坐标及点角色查询 walking，按真实来源说明查询时估计与未知项，不写行程。未修改提示词、模型或判定来寻求最好结果。

- 原 message `m4-synthetic-r2-smoke-place-route-en-task`，RUN `33fe95cc-7bb0-4d3c-bd72-30af70516bb3`，generation `e933c6cb954345e2ac3263e3204cf8c8`；场景输入 SHA `8038779ba545c4f09f124eaa6c4b3f70629e2056d1edaab3845e35c7deed1a94`。
- 原 `model.tool_turn.0` attempt `842207975a98472daf0c40916c30ac63` 为 INTENT，无合格模型回执；注册输入 SHA `61ecca295020184daafe623e43d486ca8ee0797dcaf58e2b4af5d372c9b4e3ea`。
- 诊断绑定 attemptSHA `c41fdfa60ecccfb4128a4e9c786d9534ab302a8a5433085e4818d48fe801aaf5`：`native_function_turn / native_envelope_fields / HTTP200 / done=true / finished=true / usage=true / content_chars=0 / tool_count=1 / finish_reason=stop / argument_chars=267`。
- 预期冻结 `model-tool-turn-function.1` 信封被接受后调用指定真实地点＋路线，后续北京模型返回同 RUN 完整正文。实际失败在**任何英文工具调用之前**，英文工具0、正文0；2.868429秒只表示终态，不能计回答延迟。

分类 **integration_protocol**，P1 [已交 B #523](https://github.com/JTCAO515/G2C/issues/523#issuecomment-6701275432)。具体多/缺哪个顶层字段、原参数字节及该意图 tokens 仍 UNKNOWN；完整传输标志不等于有效模型回执。没有证据把它归为地点/路线来源失败，也不修改 B 文件。strict 英文天气已通过不保证同候选其它场景通过。

## 中英统计与质量边界

| 语言 | 冒烟计划 | PASS | 前置FAIL | UNKNOWN | UNRUN | 原RUN completed / unknown |
|---|---:|---:|---:|---:|---:|---|
| zh | 3 | 1 | 0 | 0 | 2 | 1 / 0 |
| en | 3 | 0 | 1 | 0 | 2 | 0 / 1 |

前置 FAIL 与原 RUN UNKNOWN 分开保留。中文成功 RUN `71c8adba-97cb-4bf4-b205-4b3d83cc893e` 的首有效正文/完整正文均23.884289秒，n=1，p50/p95/max均该值；首字已超过5秒。英文没有有效回答时延，失败终态不入回答分布。不剔除失败或未跑分母来宣布整组达标。

| 正式语言 | 计划 | PASS / FAIL / UNKNOWN / UNRUN | 完成率≥90% | 严重错误0 | 首字p95≤5s | 完整p95≤90s |
|---|---:|---|---|---|---|---|
| zh | 33 | 0 / 0 / 0 / 33 | UNRUN | UNRUN | UNRUN | UNRUN |
| en | 33 | 0 / 0 / 0 / 33 | UNRUN | UNRUN | UNRUN | UNRUN |

原33对、11固定留出、66正式运行均保持未派，四个正式门槛没有被本次冒烟认证。事实/语言/严重错误完整审查 UNKNOWN，不把“没有已知严重错误”写成严重错误0。`review.md`/`review.json` 给 JT 原问题、原回答、实际后续模型中的来源结果与待审疑点；人工已审0，仅一条完整中文回答可审，英文为空、其余未执行。通路 PASS 不是质量 PASS。

## 全部用量与费用

| 范围 | 保守占用 | 按token估算 | 实付 |
|---|---|---|---|
| 本阶段模型 | 5意图／¥5：4 RECEIVED、1 INTENT | 已知4回执9483入/1191出/10674总，小计¥0.0108021；另1意图tokens未知，整段 UNKNOWN | UNKNOWN |
| 本阶段付费工具 | 地点2＋路线1／¥3，均 RECEIVED；天气0、FACT0 | UNKNOWN，不从次数推实付 | UNKNOWN |
| 历史共享累计（本段终点） | 含M1模型¥252；paid工具¥122 | 不把本段小计冒充完整历史费用 | UNKNOWN |

终点375行/68 INTENT/307 RECEIVED，ADOPTED `42aca1ce8aa21f80de3f1058271c206b8135d7d66682818e51221215fbd35b55`；原367行所有字段保持。全部8个 attempt 含原输入绑定、回执/未知状态保留于报告和持续进度。未重派、释放或覆盖任何新旧 INTENT。

从该历史终点，尚未派发的下一六格＋66仍预测153模型/62paid→405/184；它不是预留，不冻结 B 合法独立阶段。B修复/后验后必须重读实际锚重估，工具总200、分类次数1200/600/200/240、期限2026-11-30及只用合成数据不变。

## 封存、网络与后续

原18文件归档 SHA `c76a94e8ccda24e09cb56c79e8bb9b3f587c8c500b5ba404d5b9e580b959b1e1`；中文 raw SHA `7080042915978f3e1ca96f38088184ea66b1b7fc40a494def2ef6edb01bf7c02`，英文 raw SHA `6b72b07aa5fa0ad74f7f719fb9adce9195f8a91fc7115c6de6ca48adabf81642`。canonical b49 smoke 封印 FAIL、无 full claim；wrapper19/runner24正常exit1，现场只剩sleep、评测Python/PG=0。`report.*`由本候选原生成器在香港对封存结果CPU生成，0新增调用；`progress.*`逐字复制原持续报告。日志、原HTTP及压缩包不入库，逐文件摘要保留于 `evidence.json`。

当前批准网络为 JT11-06/PR588 的**境内 Mac＋VPN**，无需海外客户端。真实客户端 POST 至首有效/完整正文仍 UNRUN；原 GET 基线和服务器香港位置不能补格。生成器保留的旧海外/境内 UNRUN 字段只是历史格式，不新增海外验收要求。因本轮冒烟前置失败，不另派同根因网络任务。

环境观察失败也保留在原私有过程资料：宿主Python3.6不支持 `text` 参数，以及本机Python的 `tarfile.extractall(filter=...)` 不可用；前者仅影响首次只读观察、后者仅影响已下载归档解包。改为兼容的只读观察/逐文件安全解包后完成，不重派任何产品请求，不把环境错误当成本次模型根因。

#541/#32保持 OPEN、质量不放行。本报告可合并以保全失败证据，不能关闭质量验收。等待 B 修复生产根因并正式交付；按原冻结规则复验，只有同候选六格全部 PASS 才执行原66。旧 PR531/546/567/571/582 的 FAIL/UNKNOWN 与未释放 INTENT 原样保留；不提前 complete、不重复 handoff。
