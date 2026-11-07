# 候选 337 真实冒烟记录

**3 PASS、1 前置 FAIL、2 UNRUN，质量暂不放行。** 英文地点与路线已走通。本轮在英文天气续接模型返回 UNKNOWN 后按原规则停止。正式 66 例和境内 Mac＋VPN 客户端 POST 计时均 UNRUN，事实与语义的独立人工判定为 UNKNOWN。

| 固定前置格 | 中文 | 英文 |
|---|---|---|
| 地点＋路线 | PASS | PASS |
| 天气 | PASS | FAIL，工具已回执，续接 RUN UNKNOWN |
| 官方事实页 | UNRUN | UNRUN |

## 开跑证据

- 实际候选及 runner/backend 均为 `337e4d4e0147bc4197afa69781cac22908f152f1`。PR615 合并提交为 `d13f5fe02aa5c701142ded8bd36c92c48bc2ba0b`。B 英文地点＋路线公网09的原 RUN、659 字节完整正文 SHA、ACK、三条模型和三条工具回执均核对通过。该单例承担开跑前置。 [PR615](https://github.com/JTCAO515/G2C/pull/615) · [B 公网09](https://github.com/JTCAO515/G2C/issues/523#issuecomment-6701793418)
- 容器 `g2c-c-runtime-337e4d4e`，镜像 `sha256:17c87fd4a04c3f2dd9f0aac69e5dcf5575c55e109b2947892fb0bf6cf00016da`，manifest `5f812ca089413f85774aeeec432f7fbce743b6ca9d0f6fc0ff01776ceb1d1f61`，实际源码 640 项。核对 UID10001、只读根文件系统、原两项 0600 服务键、唯一账本与控制直挂及待命时仅 sleep。新 adapter `4ee4aa52151b6609fc5fc331fe7df7ce7e458f95a31622caa3a1fca141f0e2d2` 在开跑前两阶段均无 claim。
- 起点 ADOPTED 381 行、68 INTENT、313 RECEIVED，账本 ID `32d95019ea16443b81e648960c4baba0`，SHA `62194a5659abb9dc2bdb7b0da48e9c1979ce2f90347e414f709ccb35ac3888e1`。逐字段核对原 375 行和 B 新 6 条 RECEIVED。含 M1 的模型保守占用为 ¥255，工具为 ¥125。按原六格＋66预测增加 ¥153／¥62，合计 ¥408／¥187，符合模型 ¥10,000 和工具总额 ¥200。预测未入账。

## 英文天气故障

原英文输入要求查询北京 2026-11-08 天气，按实际来源、报告时点和未知项回答。RUN `74c45935-3c18-4ccb-999e-eacbf7f990e6` 的首轮模型 `8bf0d520f21e4fa09d10b65c40fa2333` 和天气工具 `dca4b8457e32440a84ec6f350b388167` 均 RECEIVED。工具响应 SHA `95b57dce9ea1744c1e645e50bb2edba8b4b22e90dd7e4ee4908cd2e28b10060a`。

续接 `model.tool_turn.1` attempt `78f5affcd9394a38bb4811d51135632d` 停在 INTENT，原请求 SHA `ad5a018dc2117b90633d5025e377df68f64199356ea3c8e3f6e304790d433b6c`。原诊断为 HTTP200、done/finished/usage true、finish stop、一个函数、994 字符参数和 `native_envelope_fields`。旁路只接受安全诊断的完整格式。它记录同 attempt SHA `0840ad4f12e17d99c5f672204d9737a89ba91d96b6fefaf5b65bd7de95a0c1dc` 的位图 4 和额外键数 0。按 337 的字段顺序，唯一在场的键是 `answer`，缺 `version`、`kind`、`calls`。原值字节与该次 tokens 均 UNKNOWN。

原 RUN 为 UNKNOWN，交付只有 56 字符来源行。10.117819 秒是失败终态时间，首有效正文和完整正文时间均缺失。按 `integration_protocol` P1 交 B。 [原失败](https://github.com/JTCAO515/G2C/issues/523#issuecomment-6701946075)

## 时延、占用与封存

| 范围 | 有效首正文与完整正文时延 |
|---|---|
| 中文成功格 | n=2，12.095510 秒、10.939817 秒 |
| 英文成功格 | n=1，11.632673 秒 |
| 英文失败格 | 首有效正文 UNKNOWN，完整正文 UNKNOWN |

三条成功样本的首正文都超过 5 秒。上述为香港私有 PG 与原 worker 的六格诊断样本。正式中英文完成率、严重错误、两项 p95 均 UNRUN。`review.md` 和 `review.json` 给出原问题、回答与实际工具结果，人工已审 0。

本阶段新增 10 模型意图（9 RECEIVED、1 INTENT）、4 地点、2 路线、2 天气。已知 18,550 入／2,865 出 tokens，小计估算 ¥0.0225755。剩余模型用量、整段费用与实付 UNKNOWN。本段保守增加模型 ¥10／工具 ¥8。终点含 M1 模型 ¥265／工具 ¥133，ADOPTED 399 行、69 INTENT、330 RECEIVED，SHA `81b7717be34b0377aaa29d8db90351695bf6357cdb2df7d5e26caef38a6106ea`，原 381 行逐字段一致。按本终点预估下一六格＋66为 ¥418／¥195，下一候选需以届时实际锚重新预检。

canonical smoke 封印 FAIL。wrapper19／runner25 正常 exit1，容器仅 sleep，评测 Python 与 PG 均为 0，full claim 缺席。原归档 SHA `59ad9b3c63f3aeb635c650cd92c816727050ee9f703b1c88805a6a8706ec5671`。`report.*` 用原镜像内生成器在封存证据上生成，`progress.*` 取原持续报告。`evidence.json` 记录逐文件摘要。日志、原 HTTP 和压缩包保留在私有归档。第一次只读预检用了宿主 Python 3.6 不支持的 `text` 参数，改用 `universal_newlines` 后验证通过，当时尚未派发。

#541/#32 保持 OPEN。下一候选等 B 的新生产契约、独立真实后验、实际锚和最小入口齐备后复验。固定六格同一候选全部 PASS 才启动原 33 对、11 留出和 66 例。
