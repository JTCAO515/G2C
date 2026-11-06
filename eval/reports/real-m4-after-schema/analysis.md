# B572 schema 修复后的 C 冒烟：3 PASS / 1 FAIL / 2 UNRUN

实际 runner `04dd91b28218517ef49cc7f60add34ee975ee9fc`，backend `c4c3b30274ed130a9df21e30d701646a90d8cdd7`，manifest `997b1897e09533c033eacf971bd9b25749cd4adca2d50e2ad4fee5211f44e73a`，adapter `86fcc1ce5ab05fb304f046c3782472c498ff6115bac9c2e6d6f57dbdac40a0da`。C 独立核验完整 operator43a、639 源摘要、最小两项0600服务凭据、原唯一346行ADOPTED锚及旧Mac SEALED后，启动唯一 `hk-native-schema-smoke-001`。

| 固定前置格 | zh | en |
|---|---|---|
| 地点＋路线 | PASS | PASS |
| 天气 | PASS | FAIL：天气已收，后续模型 UNKNOWN |
| 官方事实页 | UNRUN | UNRUN |

前三格均由原判定证明指定真实工具回执、后续北京模型、同 RUN 完整非空正文及原 Meter/授权依据。英文天气失败即停止剩余两格与正式66，不以旧候选或B07单例补格，不选最好attempt，不变样本、留出、judge或门槛。

## 英文天气最小复现

- 原 message `m4-synthetic-r2-smoke-weather-en-task`，RUN `3f2efc4c-23e7-4cfa-935d-05d776d429b7`，generation `958ba6a4088447f1bfc47cb2e6ff7563`，签名消息 SHA `b9c5698f83aab80dd883ad77b72e6fbcac67666e155402beb6ad3be27ea2215a`。
- 原问题要求查询北京2026-11-07天气、按实际来源/报告时点回答，未知项保持未知，不重复或保存行程。预期实际天气 → 后续模型完整回执 → 同 RUN 可见正文。
- 第一模型 `a256c705fdb24e53a415a792faf376a7` RECEIVED（912入/101出）；原天气 `4ff37b2ec6b1432ba008d467176c9fd9` RECEIVED/observed，responseSHA `cfc556f6fd1c811c337ec48993fa1b564c8912c29ed30bcd6eeae7d8b1cda15f`，北京110000/Asia-Shanghai、提供方报告16:34:01、实际检索08:35:10Z，日期与原参数相符。
- 后续 `model.tool_turn.1` 原 attempt `6bcc33186c1d410387c3167fe8381714` 为 INTENT，inputSHA `a0962b2e79dda4933c2fa8f9b12f0a698c84be9bdb2041de16a001172a1712c4`。原天气结果确实进入该次模型原注册输入；实际续接被拒，最终仅56字符Source链接，没有有效回答，RUN unknown。

原绑定 attemptSHA `c72d398c2fb7c144acb854a36188899ee559512f795edcf045e7ad8a82430dd8` 的诊断为 `native_function_turn / HTTP200 / done=true / finished=true / usage=true / finish_reason=stop / tool_count=1 / argument_chars=1014 / reason=native_envelope_fields`。分类 **integration_protocol**；明确为原顶层字段集合校验拒绝，但具体多/缺哪个字段与原参数文本仍 UNKNOWN，不能从字符数倒推，也不能把完整传输标志当有效模型回执。[P1复现已交B](https://github.com/JTCAO515/G2C/issues/523#issuecomment-6680874961)。

原未知模型不重派、不释放。原a18/f109等历史错误仍在原报告，不将本次更精确reason倒填旧样本。B后续strict opt-in/静态验证不是本候选通过。

## 中英计划、原状态与时延

| 语言 | 计划 | PASS | 前置 FAIL | UNKNOWN | UNRUN | 原 RUN completed / unknown |
|---|---:|---:|---:|---:|---:|---|
| zh | 3 | 2 | 0 | 0 | 1 | 2 / 0 |
| en | 3 | 1 | 1 | 0 | 1 | 1 / 1 |

前置 FAIL 与原 RUN UNKNOWN 分别保留。完成子集的首正文/完整正文：zh两例12.123831及21.818402秒，p50=12.123831/p95=max=21.818402；en仅一例14.898046秒，p50/p95/max均14.898046。三个首正文均超过5秒，不能被完整时间低于90秒抵消；该子集不冒正式66的p95。失败天气的10.244316秒仅终态时间，不是回答延迟。

固定33对、11留出、66正式评测仍全部UNRUN，中英各33计划/0运行；完成率≥90%、严重错误0、首字p95≤5s、完整p95≤90s四项正式门槛UNRUN。完整独立事实/语义审查UNKNOWN，不据没有已知硬错误宣称严重错误0。

## 用量、预算与停止边界

新增模型10（9 RECEIVED/1 INTENT）、地点4/路线2/天气2均RECEIVED，FACT0。9完整模型回执合计17798入/2528出/20326 tokens，已知token费用小计¥0.021064；另1模型tokens未知，所以整段估价UNKNOWN，工具实际费用/实付UNKNOWN。保守占用新增模型¥10/paid工具¥8，未释放旧UNKNOWN。

阶段起点346行/66INTENT/280RECEIVED、ADOPTED ef9624…d84d8b，模型含M1为235、paid110；按原153模型/62paid预估六格＋66→388/172，开跑前PASS。终点364行/67INTENT/297RECEIVED、ADOPTED `ad4ea4b7b17440a6fa4f1a65fce68740c50bc46ba23cb4b2cad8ea44ef2a2b14`，模型含M1为245、paid118，原346行逐字段不变。

不降低原估算：下一六格＋66预估153/62→398/180；若B修复后最少2次模型后验，再执行原计划将预测400，触原400停止线（预测必须严格小于停线），即便总额仍500。[预算停点495](https://github.com/JTCAO515/G2C/issues/495#issuecomment-6680936625)已请JT决定保持400或调整停止线，决定前不先发新的B/C付费阶段。报告记录的是当前实际与条件预测，不把未来2次当已发生调用。工具10000停仍受总200、次数及2026-11-30期限约束。

## 证据与当前处置

原19文件只读归档SHA `308b4c5d8250b899db51726533882e7cd1bdc409cc11dc19949f5dfe977736cb`；英文天气rawSHA `27bed6a5ccf7edc2c69d766a7acac22ea7ffe58e6d82a3c60bd815c0ebea8cb0`。逐文件哈希、canonical FAIL封印、原四源/镜像/配置、所有attempt与过程持续统计在evidence/progress JSON。原wrapper19 exit1，实际只剩sleep、评测Python/私有PG=0，无full claim。报告在原香港容器对原账本CPU生成、0新增调用。

私有质量候选c4与后续公域bb分列，不因部署commit变化重置四源adapter或提升旧head证据。目标条件按JT11-06为境内Mac+VPN；PR579六次protected-GET基线仅证明读取，不能补原用户POST起的首字/完整回答或本六格，相关质量网络指标仍UNRUN。真实用户内容仍禁。

#541/#32保持OPEN、不放行；失败报告合并只保全事实。B先无费用定位/修复，预算决定与正式新候选到位后按冻结规则复验，六格同候选齐备才原66；保留全部历史、未知费用和失败，不更新handoff或提前complete。
