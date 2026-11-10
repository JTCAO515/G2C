# Lio 公网规划回归

2026-11-10 的两次公网规划失败保留在原 RUN 与原账本。以下故障注入只在私有 PG 和夹具供应商运行。公网复验使用独立合成原件。

| 场景 | 原件及原结论 | 私有复现和通过条件 |
|---|---|---|
| 完整首问进入提取后结果未知 | `2432D743-02F0-4857-83E3-A9A68E2A8A6B` → `dd1682eb-29f0-43b0-90ed-e240f76f5f9a`。UNKNOWN/ACK，唯一提取操作已结算，352 入／393 出，¥1 保守、¥0.0013427 估算、实付 UNKNOWN。无 NEEDS、草稿或 Trip 写入。 [原记录](https://github.com/JTCAO515/G2C/issues/702#issuecomment-6757497540) | 在 PR731 修复前的源码，将下方完整首问经签名 Lio 送入现有 `scripts/hk_demo_local_check.py` 组装。令 `model.lio_intake.0` 返回带正常用量回执的无效 envelope，例如缺 `extraction`，核对 UNKNOWN、原操作只结算一次且零 Trip 写入。实际供应商输出已无法取回，此夹具代表校验分支。修复后中英完整首问均应绕过提取，原 NEEDS 绑定、草稿派发和正式 v1 各一次。另用「帮我规划旅行」→「北京，2026-11-11 到 2026-11-13」验证追问续接仍使用原消息引用与提取。 [PR731](https://github.com/JTCAO515/G2C/pull/731) |
| 草稿达到输出上限 | `42981608-C1F8-44C9-B331-29D714A12C40` → `6f6ad68d-f7aa-40f6-ba84-d8f0f6ba9797`。原 NEEDS 已绑定，唯一草稿 `finish_reason=length`，保留 INTENT 和 ¥1 保守占用，实付 UNKNOWN。RUN completed/ACK、`draft_outcome=provider_unknown`，零 Trip 写入。 [原记录](https://github.com/JTCAO515/G2C/issues/702#issuecomment-6758272627) | 在同一签名组装的真实供应商协议夹具中，对草稿原调用注入 `finish_reason=length`。核对原 INTENT、零 Trip 写入、无第二次模型派发。再用新原件返回上限内的完整紧凑 JSON，核对固定项及日期覆盖、原草稿回执、候选哈希与签名 v1 一致。旧模型及输出上限保持。 [PR732](https://github.com/JTCAO515/G2C/pull/732) |

### 公网连续复验

在同一 API/worker 镜像和 B 签名窗口串行做五轮，每轮中文和英文各一次。首轮与陌生人清单规划格共用同一原件。每次前置需证明没有会影响本次日期、Trip 或记忆判定的旧上下文。B 若只提供可续写的合成会话，按原 head 与预期新增版本另记重规划证据，独立首问的缺口保留。

- 中文：「帮我为两个人规划从明天开始的北京三天游，第一天 9:00–10:00 的酒店集合已经定好。」
- English: “Plan three days in Beijing for two people starting tomorrow. The hotel meetup from 9 to 10 a.m. on the first day is fixed.”

每次用新 MESSAGE ID。按北京时间原提问日核对三天日期、首日 09:00–10:00 固定酒店集合、唯一新版本、同 RUN 保存回执和行程卡。完整首问另外核对零提取派发。分中英报告 PASS/5 和合计 PASS/10，保留失败行和未跑行。各原件保留首进度、首正文、完整时间、保守占用、已知 token/工具估算及实付。发现 UNKNOWN 时仅核原件，待原动作状态和本批预算核同后再决定是否继续剩余场次。 [采集规则](lio-run-plan.md)

### 相对时间修改

当前公网已知负例中，第二日停靠点日期已知但两个时刻均未知。定位「第二天下午」时应澄清，保留原版本。按停靠点的原名修改仍可独立验收。 [原负例](https://github.com/JTCAO515/G2C/issues/702#issuecomment-6759210782)

B 生成的新建议可在现有 `structured.2` 中用已绑定行程日期、目的地时区和具体起止时刻表示计划时间段。C 按原可行性及发布校验核对区间，保留来源、核验状态、预约及实测 UTC 偏移的原语义。已保存的未知时刻与固定项保持原内容。B 部署后，新原件覆盖以下组合：

| 输入 | 通过条件 |
|---|---|
| 中英三日新规划 | 第二天唯一新建议有同日的起止时刻，均落在 12:00–18:00，Trip 卡与已保存版本一致。第一天酒店集合仍为 09:00–10:00。 |
| 「把第二天下午换成颐和园，保留其他安排」／“Change the afternoon of the second day to the Summer Palace and keep the other plans.” | 仅唯一匹配项的名称改变，原日期和起止、其他项、锁定项字节一致。仅新增一个版本。撤销新增版本并恢复原规划内容。 |
| 同日有未知时间、跨时段、多个匹配项或命中锁定项 | 向用户澄清或拒绝，零 Trip 写入。保留旧负例。 |
