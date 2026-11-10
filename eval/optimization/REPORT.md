# #761 本地评分报告

评分接口 `G2C-dialogue-score.1`，数据版本 `G2C-dialogue-cases.1`，
数据 SHA-256 `8e3b9c2d410e569de520243540e364d7fed6033087de8173adc5e87e17fe92f3`。
本轮为合成控制和本机私有 PG 实验。真实模型、工具调用与费用均为 0。

## 合成控制

以下每批每格一次。用 [运行示例](README.md#运行) 生成逐项 JSON。好坏各为独立批次。

| 用途 | 批次 | 任务 | 中 / 英 | 计划分母 | PASS | FAIL | UNKNOWN | UNRUN | 硬失败 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 开发 | 好 | 6 | 6 / 6 | 12 | 12 | 0 | 0 | 0 | 0 |
| 开发 | 坏 | 6 | 6 / 6 | 12 | 0 | 12 | 0 | 0 | 10 |
| 验证 | 好 | 4 | 4 / 4 | 8 | 8 | 0 | 0 | 0 | 0 |
| 验证 | 坏 | 4 | 4 / 4 | 8 | 0 | 8 | 0 | 0 | 8 |

| 场景 | 中英坏例主要失败原因 |
|---|---|
| 直接回答 | 无需日期的咨询被额外追问 |
| 必要澄清 | 自选日期、写入正式行程，未证实保存声明 |
| 改口 | 天数未更新并丢失已知条件 |
| 局部修改 | 错路径，修改已锁定项 |
| 取消 | 晚到内容可见，取消后仍派发 |
| 工具失败 | 原调用失败却声称已经查到结果 |
| 保存 | 确认回执缺失，正式字节与原候选不同，声称保存 |
| 撤回 | 原操作未撤回，草稿未恢复，声称已撤回 |
| 越权 | 跨账号读写并泄露目标哨兵 |
| 删除后召回 | 被撤回项进入后续实际输入和可见正文 |

`uv run --locked python -B -m unittest eval.optimization.test_score` 9/9 PASS。
其中包含缺候选摘要、错尝试引用、缺回复标注三格 UNKNOWN，已知 FAIL 与缺测同时
出现仍保留 FAIL，另 11 个未提交格为 UNRUN，分母 12。工具失败与“已证实成功”标签冲突时，保留硬 FAIL；已知错对象声明缺回执
也保留硬 FAIL。输入版本或数据摘要错配、
计划外或重复样本以及 final 请求均拒绝。

## 复用证据与未验项

本机 Python 3.14.7、私有 PostgreSQL 17、签名本地入口和 FakeProvider。
原 C 评测代码基于 `8fb2a723792a644ee1e549edeec10c46551ea374`，本切片未改动。
原 eval 149/149、CJ028 35/35（另 50 子检查）PASS。原状态实验 8/8 PASS，按下列
参数运行 `CJ_ENV=local uv run --locked python -B eval/invariants.py`，指定
本机 PostgreSQL 17 bin 目录和各自新建的 `--output`：

| 套件 | `--only` | 状态 |
|---|---|---|
| isolation | `owner-isolation partial-failure unknown-stops-order cancel-inflight` | PASS 4/4 |
| commit | `concurrent-accept physical-ack-loss` | PASS 2/2 |
| memory | `withdraw-inflight-context retained-chat-prepared` | PASS 2/2 |

这些原实验验证底层读写、取消和记忆证据。新 D 评分器的整套任务采集仍待 B
接口接线，当前逐项结果来自合成控制。最终题、独立保管和开发主体实际拒绝
均 UNRUN，最终分母 UNKNOWN。模型文本质量、真实服务、真机和发布状态 UNRUN。
