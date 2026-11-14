> 历史 v1 记录：当前 Lio 已由 v2 取代。本文件原结果和分母保留，不能作为 Lio v2 完整采集；现行证据见 `REPORT-v2.md`，用途见 `release-index.json`。

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

## 2026-11-11 签名本机采集与封存补充

本轮 base `449a04fb98cd9f14b3dc9e4561a66b19324561d0`，评分器仍为
`G2C-dialogue-score.1`，源码SHA256为
`08dcdb1624790f735ffcb1c6db5d6f47b75ef2a28d02a20a31313256380f3adf`。
公开题集和正负控制未修改。新 `signed_probe.py` 通过原 C harness、受限本机 PG、
签名 API 和原 worker 采集，运行命令见 README。每份观测固定输入摘要、原动作/候选/
回执/持久内容或后续实际上下文，供两个独立评分 CLI 读取同一文件并比较完整输出。

| 本机控制 | 中/英原观测 | 应得硬状态 | 主要原证据 |
|---|---:|---|---|
| 正确保存 | 2 | PASS | 原确认字节、同 action/proposal 的真实持久回执、正式v1与内容摘要 |
| 错候选保存 | 2 | FAIL | 实际签名保存B，原请求和确认绑定A，原候选字节与正式内容不同 |
| 编造执行 | 2 | FAIL | 实际可见Fake回答声称保存，原动作提交与正式Trip均为0 |
| 撤回后正常上下文 | 2 | PASS | 原stop-use回执/fence，完整provider输入只保留独立有效偏好 |
| 删除后错误召回 | 2 | FAIL | 同一真实撤回后，故意错误Fake回答实际发布被删哨兵，硬检查拒绝 |

这是10份原观测和五批评分控制。每批验证计划分母8、已采集2、其余6为UNRUN；
不能汇总成完整40格通过。负例的FAIL是预期校准结果，产品语义质量另待独立证据。
`G2C-signed-score-probe.1` 的report给每批两次完整评分摘要及来源版本。
首轮probe错误使用了仓储的Service方法，次轮使用旧显示版本读取新travel ABI被拒。
两次原FAIL日志和partial报告保留在忽略目录，修正调用到原Service和v2显示入口。

新增封存控制使用已安装age v1.3.2，官方CLI/许可证已核，无生产Python依赖变更。
公开非最终哨兵实际加密/解密往返、篡改拒绝、无秘密解密零输出拒绝及元数据不含正文
的回归通过。实际最终集封存和D/E/B拒读以 `final-manifest.v1.json` 与PR里的三会话
原证据为准；未交字段保留UNRUN/UNKNOWN。口令通过JT本机隐藏窗口进入短生命周期
内存与匿名管道，题集具体随机参数、明文和口令不打印或持久化。作者看到的编制规则
和代码片段曝光保留记录，不宣称作者盲测或操作系统所有缓存已清除。

完整B可信采集仍等 #762，实际比较、真实外部调用、模型质量和产品晋级UNRUN。
教师独立质检登记在 #788（配对F #789），三组比较仅预登记在 comparison-plan.v1.json。
