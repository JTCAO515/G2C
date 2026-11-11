# Lio 全国验收：首条 UNKNOWN 后停派 / Stopped after the first unknown RUN

2026-11-11，北京时间。父票 #815 / #702，B 失败归因票 [#822](https://github.com/JTCAO515/G2C/issues/822)。本批未通过，不开放 #32 新六格。This batch is not accepted; the new six-cell gate remains closed.

## 固定范围 / Fixed scope

公开合成 `LIO-national-cases.1`，8任务×中英=16完整轨迹：成都、西安、上海、杭州、重庆、深圳12条，加Taizhou/Suzhou歧义4条。输入SHA `478f772d6b78817c8a88b9d48448f3f05c0bb5c0f31661ade3f6edec5fddce7f`。人数补答在首次派发前预声明，原v1输入、90消息与16原生撤销ID不覆盖、不补样。此套不是留出集，也不是正式66例。

实际部署源 `ec7269cf49fb59ce4c7faa9d3fce2242cb231c36`，API/worker镜像 `sha256:dceaa82178247b066744e7013d318b6df957989cffcbcf598970898dd34d2e35`。正式窗 `b759-national-20261111-01` 先现场ACTIVE，首条出错后B置STOP_NEW。只POST一次，没有继续补答、英文、其他城市或撤销，也没有重放未知原件。

## 结果 / Results

| Language | Planned full trajectories | PASS | FAIL | UNKNOWN | UNRUN | Verified PASS / planned |
|---|---:|---:|---:|---:|---:|---:|
| 中文 / ZH | 8 | 0 | 0 | 1 | 7 | 0/8 |
| English / EN | 8 | 0 | 0 | 0 | 8 | 0/8 |
| Total | 16 | 0 | 0 | 1 | 15 | 0/16 |

UNKNOWN保留原RUN语义；界面已显示failed/unavailable，但不能据此把底层UNKNOWN改成完成或确定归因。Full trajectories completed:0. Availability failed at the first clarification turn; underlying execution and root cause remain UNKNOWN. No overall semantic or severe-error rate is certified.

| Observed original request | First server progress (client poll) | First body | Complete answer | First failed-state observation |
|---|---:|---|---|---:|
| 成都中文开场 / Chengdu ZH opening | 1.285903459s | UNKNOWN | UNKNOWN | 4.956513459s |
| English requests | UNRUN | UNRUN | UNRUN | UNRUN |

进度由C的API轮询观测answering状态，不是JT真机的首屏渲染时延。末列是读到failed的客户端时钟，不是完成时延。只有一个原请求、没有完整轨迹，不报告总体p95。正式66例及其分语言p95、JT本人双语人工审阅和#6本批复核均UNRUN；本地66测试组不是正式66例。

## 原件与失败边界 / Original evidence

用户只发送“去成都玩三天”，正确下一步应询问缺少的日期/人数。尚未发送携带“明天”的补答，不能编造起止日期。

- MESSAGE `cnat-20261111-chengdu-zh-t1-1b7a24aa551e`；RUN `b5cebd0c-a86f-481f-8708-a778d7a2c017`；conversation `lio-dialogue-fbb8d669605804f52ef1a801230a052b`。
- POST ACK和按原wire SHA的GET回执核同。界面answer空、failed/unavailable；原events仅started→unknown，原question_day为2026-11-11。
- 仅 `model.lio_intake.0` / `model.lio_intake.1`，attempt `e831ca70ee934cef80052d1e84e1237b`。原出流RECEIVED，PG Meter settled/cancelled=true/exceeded=false，输出913。未注册City工具、NEEDS或Memory job；该新对话Trip/history0，原生undo入口空，完整active Memory items与派发前相等。
- 原模型响应未在C收到的导出中提供，失败字段仍待B沿原attempt读取。不能推断为超时、截断、费用拒绝或C领域保存错误。No speculative diagnosis and no retry of the original unknown request.

账本1097 / `7f4344ddcb5eff5c7cf7826eca68911b5fb3c107007ad606bda41cfb60dcbe9e` →1098 / `7ef48d05b8c0ef41da0fcad913619099c04eaaa00d7f5513a1f9cb114260c63f`；唯一新增1模型attempt，付费工具0。原旧UNKNOWN/INTENT及hold不重置。

## 三栏费用 / Cost columns

| Conservative full reservation | Receipt/token estimate | Actually billed |
|---|---|---|
| Model ¥1; tools ¥0 | Model ¥0.0018726; tools ¥0 | UNKNOWN |

原回执1281输入/314输出token，总1595。估算按当日官方北京qwen3.8-flash公开输入¥0.8/输出¥2.7每百万token，不假定缓存、免费额或折扣；取消标志不把已收到的收费调用算免费。[Official model list price](https://help.aliyun.com/zh/model-studio/qwen3-8-flash)。该估算不更改B原账或释放任何旧hold，也不是供应商账单。

## 保留与恢复 / Retention and next gate

同原件analysis-r01/proof快照、POST/GET原字节、每次客户端读时钟和全部原attempt留在受限证据存储；仓库只提交去敏汇总和摘要。详见同目录report.json。原proof SHA `61758837ebe07a12228353e4cb877593688734fcbfd95b38cd168a38b8516ba4`，观测SHA `28457fe0a7dd1bc4ec500a1167ce171ddebe606b5bb8fbb36d3a9dd6bf84fc4d`。

C观察端preflight-r01（文件权限假设）与r02（只读Trip漏参）失败分别留存，新r03/r04通过；它们均无业务POST，不计入16轨迹。Memory响应request_id变动只属响应元数据；正式派发前修正比较完整items/version，旧程序和摘要保留。本次业务RUN UNKNOWN已由独立原账/原件读回，不因修观察器自动续派。

下一步由B完成#822原因核查和修复，履行精确head审查/CI、同源部署，再明确交新阶段/正式窗口；本ec阶段原UNKNOWN、费用与16分母保留，不换ID补当前批。全国全部16轨迹认证PASS后，才另申请#32六格；六格全过后才正式66→JT审阅→#6。This report is a stopped acceptance batch, not product release approval.

### B后续确认 / Subsequent B finding

B在#823确认：本次913字节返回正文未持久，无法从原attempt恢复；原RUN UNKNOWN及费用不改。后续独立追加`G2C-lio-intake-evidence.1`与固定诊断码只是观测前置，未改validator或业务逻辑，不构成#822已修复。若需要新的不同诊断题/ID，由B独立登记，不替换C这16条或重放本MID；C仍STOP_NEW。原analysis-r01按当时证据保留，后续诊断单列。

原national-01窗口随后已由B正式CLOSED，关闭原件核同仍为唯一上述RUN UNKNOWN、唯一1模型、账本1098；89个未提交消息与16个undo不作补派。关闭proof SHA `9a63b86bbc0c2a7837177b70d12306d6c1f7056d3c618830e1805d609565505f`。到点或B新独立诊断均不会重新授权本窗口。
