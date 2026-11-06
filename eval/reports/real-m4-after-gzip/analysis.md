# PR569 后 C 首格协议失败：停止后续派发

候选 runner `3eab64cabeef2bbdb932e3f234bcaf48b299691a` / backend `5348e7b0077b6c50323325f09d064aeac8bdbcd7`，manifest `3e47d283b3789ca86d47ccb72a60a8fd7276da7047c0ac4ee1029a9831fcdb12`。B 公网 06 已提供真实 NIA 摘录、后续模型与同 RUN 正文/ACK；C 随后独立核对原 341 行账本、完整镜像、638 源摘要和最小两项 0600 服务凭据，再启动唯一新阶段 `hk-gzip-smoke-001`。B 的单例不计入 C 六格。

## 原计划、触发与结果

| 前置场景 | zh | en |
|---|---|---|
| 地点＋路线 | FAIL：原 RUN UNKNOWN / 正文 0 | UNRUN |
| 天气 | UNRUN | UNRUN |
| 固定官方事实页 | UNRUN | UNRUN |

原顺序、输入和判定未改。首格失败即停止其余五格和正式 66，未重派任何旧消息/运行/attempt，未换输出名重认领同一 adapter。FACT 实现在本轮未被执行，不能把该首轮模型协议错误归给 NIA 抓取，也不能把 B06 的成功填入 C 格子。

- 触发：原 `place-route/zh` 合成请求，`m4-synthetic-r2-smoke-place-route-zh-task`；原 RUN `8ee5ba2e-df89-46fc-870d-83c2293baef1`，签名消息 inputSHA `25358622538638ff5087b4536e0bfecc40d3f380c43238968b085399293d02fb`。
- 预期：两个实际地点查询、路线回执、后续模型和同 RUN 完整非空正文；无行程或记忆写入。
- 实际：仅注册 `model.tool_turn.0`，原 attempt `f10983f673584540b2a3ed04e35e8d19` 为 INTENT，模型 request inputSHA `49bdae18302938d0f942d5db9b63a2eb0f6db080554797066b923ceb674fef59`。工具 0，后续模型 0，正文 0，原 RUN unknown。
- 原绑定诊断：`phase=native_function_turn`、HTTP200、done/finished/usage=true、`finish_reason=stop`、tool_count=1、argument_chars_before_rejection=246、`reason_code=parse_error`。分类 **integration_protocol**；原参数内容、具体拒绝字段和深层根因 UNKNOWN，不能根据字符数猜测。

[已交 B 的 P1 复现](https://github.com/JTCAO515/G2C/issues/523#issuecomment-6678053103)。传输结束/usage 布尔标志不能替代有效模型回执；缺失 token 数和费用不补造。中途保护快照 503 只读重入到同原 RUN，未重 POST。

## 独立来源对照与证据保全

旧936候选实际通过的同场景 RUN `e3091c9d-bbe0-4ac8-9ba0-eb0819d140e5` 与本次首模型的 registered input 逐字段相同，实际 HTTP request SHA 均为 `49bdae18…ef59`；旧模型 RECEIVED/最终 completed，本次 INTENT/最终 unknown。两个核心 provider/real_services 文件 SHA 同一。这证明本次首请求未被 C 阶段身份或 gzip 接线改写；不据此推断具体模型输出或重新执行旧动作。旧 PASS 仅保留其原候选/原时点意义，不升级为本候选通过。

原 16 文件只读归档 SHA `9d09094044c8ece3de83b23a9f7e4c060c599d56744ac6eb1526fad75d5d1c77`，唯一 raw SHA `e215008d337332aa1a54700ff6d70e0459e1748f7fb41c8c4c287e0a5c3cd5d2`；逐文件摘要、实际源码/镜像、原 RUN/attempt、持续统计、过程和 canonical FAIL 封印见 `evidence.json` / `progress.json`。adapter `a18a58fe257032bbe99009e03efb6690aa0af5b9f0154d87d929ba27995268c7` 的原 claim 保留四源摘要，未创建 full claim。

wrapper PID19 正常 exit1，容器最终仅 sleep，评测 Python/私有 PG 为0。报告在原香港容器读取原账本 CPU 生成，报告生成无新供应商调用。旧 Mac 仍 SEALED，旧375f阶段和全部历史 FAIL/UNKNOWN/INTENT 不变。

## 中英统计、时延和费用

| 语言 | 计划 | PASS | 前置 FAIL | UNKNOWN | UNRUN | 原 RUN unknown |
|---|---:|---:|---:|---:|---:|---:|
| zh | 3 | 0 | 1 | 0 | 2 | 1 |
| en | 3 | 0 | 0 | 0 | 3 | 0 |

前置 FAIL 和原 RUN UNKNOWN 分列。此候选成功回答 n=0；首正文/完整回答 p50/p95/max 均 UNKNOWN。2.976435 秒仅为到原 unknown 终态的时间，不是成功回答延迟。正式 33 对/11 固定留出/66 次全部 UNRUN，中英各33计划/0执行，正式完成率≥90%、严重错误0、首字p95≤5s、完整p95≤90s四项均UNRUN。独立事实/语义审查 UNKNOWN，不宣称严重错误0。

新增模型1 INTENT、付费工具0、FACT0，保守占用新增模型¥1/工具¥0。有效完整模型回执0，实际输入/输出/总 tokens UNKNOWN，整段 token 估算 UNKNOWN，实付 UNKNOWN。生成器的 known_receipt_subtotal `0.0` 是零个完整回执的小计，不是本次实际费用为0。

开跑前实核同一 ledger_id `32d95019ea16443b81e648960c4baba0`、341行/65INTENT/276RECEIVED，ADOPTED `4c31822d…89ca7`；保守模型含M1为232、paid工具108，六格＋66预估153/62 → 385/170，授权预检PASS。停止后342行/66INTENT/276RECEIVED，ADOPTED `8a63860f9fed4ab147ffa54254db1d0b60a941f31e827298db93f70e75d3d2d1`；模型含M1为233、工具108，原341行逐字段未变，未知占用不释放。模型400停/500总、工具10000停但200总及次数/2026-11-30期限不变。

## 当前处置

#541/#32 保持 OPEN、不放行。C 的阶段身份 PR570/独审/122离线/精确CI全部通过仅是代码证据；不能取代实际六格与质量。B 已收到原阶段诊断，先静态核 schema/parse 一致性，当前 C 不再发请求或重认领；正式根因修复后按冻结规则复验，六格同候选实证齐备才原66，留出不调。

目标网络按 JT2026-11-06 / #32 / PR568：现有境内 Mac+VPN 访问 api-beta 的真实分组证据，当前仍UNRUN，不要求另一台海外客户端，不把HK私有PG/loopback或B06升级为该证据。生成报告保留的旧 travel-phase 字段并不增加两个物理客户端要求。未更新handoff、未提前complete。
