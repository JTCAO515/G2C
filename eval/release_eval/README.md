# 发布评测（#1761 W6-1）

每次香港发布后，用同一题库对新版本发题，每题 3 次，按「必须说对」「绝不能说」打分，记首字和完整耗时，和上一次发布出对比报告。本目录是离线部分：题库、打分、报告和跑批接口。**这里没有任何联网代码，也不调用真实模型。**

## 题库 `bank.v2.json`

- 共 70 题：原 22 题（`v1_cases` 按 id 引用 `eval/lio_answer_quality_cases.v1.json`，加载时合并，正文不复制）+ 48 道新题。
- 新题中 30 道是旅游+商务混合任务题（`kind: mixed`，中英各 15），其余 18 道覆盖支付、上网、地铁、高铁、证件和手机丢失、急救、规划、推荐、中英双语和商务礼仪。
- 每题字段：`id`、`locale`（zh/en）、`scenario`（沿用 v1 的场景）、`kind`（travel/business/mixed）、`turns`、`must_say`、`must_not_say`。v1 引用只写 `id`、`kind`、`must_say`、`must_not_say`。
- `must_say`：列表的列表，每组至少命中一个（正则，不分大小写）。只写稳妥、长期成立的要点（「120」「护照」「预约」「官方」），不写价格、政策天数等会变的数字。签证、入境类只要求指向官方渠道（国家移民管理局、领事服务网、使领馆），不要求具体政策内容。
- `must_not_say`：正则列表，抓编造、危险、越界的说法：给诊断或药名、承诺代办签证、说外国人不能用支付宝、把免签说成对所有国家适用、教人虚开发票等。`@名称` 引用 `forbidden_sets` 里的共用组；`always_forbidden`（「保证」类承诺、声称已替用户下单付款）对每题都查。
- 正则只抓肯定说法：否定的正确提醒（「不是所有国家都能免签」「不能抱熊猫」）不算违规，`eval/tests/test_release_eval.py` 逐条校验。新增正则时同样补一对「正确说法 / 错误说法」。
- 校验：id 唯一、字段齐、总数 60–80、混合题恰好 30、正则可编译、v1 的题全部引用且都存在。

```sh
uv run --locked python -B -m eval.release_eval.bank list
```

## 打分和报告（离线）

运行结果文件：

```json
{"run": {"source_sha": "…", "started_at": "…", "model": "…", "bank_version": "…", "repeats": 3},
 "answers": {"<case id>": [{"text": "…", "first_token_ms": 820, "total_ms": 5400, "error": null}, "…×3"]}}
```

- 一次回答通过：没有错误，`must_say` 每组都命中，没有触发 `must_not_say`；原 22 题还要通过 `eval.lio_answer_quality.check_answer`（detail profile）。
- 一题通过：超过一半的回答通过（3 次里至少 2 次）。
- 汇总：通过题数、must_say 命中率、违规数、错误数、首字和完整耗时 p50/p95（最近秩法），以及按 kind、locale 的通过数。

```sh
uv run --locked python -B -m eval.release_eval.score RUN.json [--output SCORED.json]
uv run --locked python -B -m eval.release_eval.report single RUN.json [--output REPORT.md]
uv run --locked python -B -m eval.release_eval.report compare OLD_RUN.json NEW_RUN.json [--output REPORT.md]
```

对比报告：总表（两次并列和差值）、变差的题（通过次数变少或违规变多，附违规原文片段 ≤80 字、漏说的要点）、变好的题、耗时对比、错误、只在一次中作答的题。

## 跑批和费用护栏 `run.py`

- `Sender` 协议：`send(case, turn_texts) → {text, first_token_ms, total_ms, error}`；多轮题一次 send 走完所有轮，返回最后一轮的回答。
- `FixtureSender` 从 JSON 回放答案，用于测试和报告演练：`python -m eval.release_eval.run run --fixture ANSWERS.json --output RUN.json`。
- `plan` 打印调用次数（题数 × 次数，默认 70 × 3 = 210）、模型轮数和按 `--cost-per-turn-cny` 估算的费用。
- 真调用必须同时给 `--real`、`--max-calls`、`--max-cost-cny`、`--cost-per-turn-cny`，且计划不超过两个上限，否则拒绝。真实 Sender 本次没有实现，调用会报「未实现」退出。
- 输出文件已存在时拒绝覆盖；运行结果不入库，放 CI artifact。

## 待定和已定事项

统筹 2026-11-26 按 JT 预授权决定：

- 发布后挂点：由 CI 评测线之后在 `deploy/hk/application_release.py` 加可选步骤（默认关），等 S 线 #1808 部署后再做。
- 账号：先用 `deploy/hk` app_smoke 现有凭据，之后换「评测」类专用码。凭据只放服务器配置或 GitHub secret，不入库。
- 费用：每月上限 ¥50；单次估算超过 ¥20 先报统筹；第一次真跑只跑 5 题 × 1 次。

仍待做：香港发题适配层（真实 Sender）、挂点实现和第一次真跑。真跑属于花钱停点，每次 `--real` 先问统筹。
