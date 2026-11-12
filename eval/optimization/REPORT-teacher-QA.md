# #788 固定 Fake 包独立质检报告

本轮证据限本机公开Fake组合，不是实际教师、C领域事实质量或正式训练放行。
代码与规则版本：G2C-teacher-quality.1 / G2C-teacher-quality-rules.1。
输入：F PR794已审c68d6f44、source_root/merge21e66d5b；manifest SHA
`75d8655b3c2e5432e5a2a4dd86c2c4130c5b88d34e11426ec106e0fa23b34919`。
F已确认此唯一旧输入；全国v2包未纳入本版，不自动更新旧pin。

| 本轮验收 | 状态 | 证据范围 |
|---|---|---|
| F/D输入、规则与双向配对冻结 | PASS（待R实现复核） | #788/#789既有双向关系，F明确确认旧包；输入/规则文件及TEACHER-QA说明 |
| 13制品/16源码和复建一致 | PASS | 固定21e源码重建两包，13artifact/16source等于F发布快照，全部14包文件逐字相同 |
| 独立全量自动检查及错误回执/泄漏硬拒 | PASS（本机Fake） | 原F/C codec、真实Fake原bytes、任务/用途/家族/分母重算；下表及单测 |
| 默认D测试入口 | PASS（本机） | 原21项保留+新增15项=36项；无共享CI或F文件变更，远端CI尚待本head |
| D真人独立抽检/C领域/真实数据版R复核 | UNRUN | 真实小批未到；8接受家族仅演示计划，实际人工0，不声称第3框已验 |
| 真实教师质量 | UNKNOWN | 本轮零真实模型/工具/费用；新teacher来源仍不支持 |
| 正式发布/训练 | UNRUN | Fake训练资格始终false，UNKNOWN或FAIL整版不放行 |

## 原件及完整分母

21计划/21开始任务，31次Fake模型回调、6次本地工具请求；其中4个坏生成已隔离，
17格式候选去重后16，1重复。接受连通家族8；全计划名义trip_family11（另3个只有
坏生成控制），两种单位均披露。接受用途train12/validation2/public-test2；完整回答12、
原failed2/cancelled2仍为control_only，不能当完整SFT对话。
原17负例+2精确伪保存控制复用并重新检查；本轮没有读取真实用户或最终题。

独立报告含每项PASS/FAIL/UNKNOWN/UNRUN、原件ref/原因、21任务独立证据状态、
语言×行为分母、16行digest/原RUN/用途、家族演示清单及摘要、源manifest/规则/checker SHA。
根状态不使用F自评分；已知工具no_results与RUN/answer_state分别核，如实无结果允许completed。

## 独立CLI重复结果

每个原控制各用两个独立CLI进程读取同一冻结包，完整报告字节相同。
下列FAIL是故意错回执控制的预期拒绝；UNKNOWN不是成功，也不作无改善或质量结论。

| 输入控制 | 结果 | 逐项P/F/U/UNRUN | release_eligibility | 完整报告SHA256 |
|---|---|---|---|---|
| smoke | PASS | 96/0/0/0 | fake_only_not_released | `03566e8df74ce4fcd83ede08ccf38efd2cffd7c9a6dc84e4c930a0a7c49cf7a9` |
| bad-receipt | FAIL | 34/1/0/0 | rejected | `efbe7a59da5cc8ea9ed65c248e02c3d087b38fc9043df96a8a8e76d2ddb007bd` |
| unknown | UNKNOWN | 37/0/1/0 | blocked_unknown | `b0928e7ec2d01a40f3345914bf5691d9b9b6329aa5f2827d6b4b025e0da51cb0` |

全部报告training_allowed=false，g_handoff.training_samples为空。bad-receipt原F状态保留UNKNOWN，
D发现已给出的错误attempt关联为FAIL，整版rejected；unknown原收到的前项仍核同，后项缺结果
保持UNKNOWN，后续任务UNRUN，不能训练。两者不换ID重发或修回执。

## 已知正负对照

新增15项测试涵盖：好包和逐字重复；原错回执；原部分结果UNKNOWN停派；篡改supplier bytes；
重算artifact hash后的跨用途家族泄漏；teacher/real_user来源与未知内容污染；错model/task关联；
缺制品/重复JSON键/错manifest hash；路径逃逸/symlink；F自填训练PASS；扩批分层采样行序不变；
已知no_results忠实完成与伪造命中；未settle模型谎称complete；删原始任务却保留总数。
这些用例验证拒绝逻辑，不把修改后的坏包计入原21任务生成分母。

初稿曾把4个隔离坏生成的单用户残片按完整候选minItems检查，导致本机FAIL，原报告保留。
修正只限未进候选的FAIL诊断残片：其他schema仍核，候选原F校验未删或放宽；新增边界集中
在文件/sidecar读入，后续不重复做内部形状防御。缺回执UNKNOWN与已知错回执FAIL明确区分。

运行入口、完整规则、人工未验项和G消费格式见TEACHER-QA.md。R代码/规则/对照独审仅以
本次PR精确head评论为准；本报告不自认证新增判据或真实数据质量。#788第3框保持UNRUN，
整票及#767保持OPEN；PR只用Refs，不运行#765、真实生成、训练或部署。

## 修订：缺字段与早退格式

原3b57候选的[R阶段核对](https://github.com/JTCAO515/G2C/pull/870#issuecomment-6819599573)
确认两个P2：received原件缺时间字段会KeyError/无报告；早退G元数据缺training_samples。
D独立复现同一缺字段，原stderr/失败目录保留。修订在received证据边界一次建立时间/binding/ref/profile；
缺证UNKNOWN、坏类型FAIL，保留冻结输入FAIL优先，不用catch-all吞内部错误。
共同finish在全部早退/FAIL/UNKNOWN路径也固定training_samples为空，训练标志始终false。
新增定向对照并保留原F对null结果的schema拒绝，没有修改/削弱F或重复添加内部类型校验。
修订后原21+新15共36项PASS，三包双CLI重新复核逐字相同；上述三个报告摘要已更新。
