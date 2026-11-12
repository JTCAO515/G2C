# #788 独立教师包质检：固定 Fake 输入

本轮仅 D `eval/optimization/**`；F 唯一拥有 `tooling/datasets/**`。
配对 [#789](https://github.com/JTCAO515/G2C/issues/789)，父专题 #767。
不启动真实生成、模型/工具请求、训练或 #765 比较。

## 唯一输入与版本

- F PR794 已审 head `c68d6f4411cb9cda735c1e74cc715409d8466f27`，
  merge/source_root `21e66d5b19453708f70da44c87df48e655b4f74e`。
- `G2C-teacher-handoff.1` / `F789-fake.1` / batch `f789-smoke-v1`。
  行保持唯一 `G2C-dataset.1`，不另造训练行格式。
- D 独立重建的 handoff SHA256：
  `75d8655b3c2e5432e5a2a4dd86c2c4130c5b88d34e11426ec106e0fa23b34919`。
  13个制品、16份源码与 F 发布的 `teacher-fake-manifest.v1.json` 全部摘要相同。
  原 manifest 生成 revision 为2cc；重建如实记录21e，未改写旧快照。
- 唯一输入描述 `teacher-input.v1.json` 另固定原 bad-receipt、unknown 两个诊断控制。
  caller提供的manifest摘要也必须匹配D已冻结的控制摘要，不能自行重新hash授权新输入。
- F已确认上述旧包边界。F后续全国handoff.2/candidate/data/prompt新版本和新sidecar
  **本版不支持**；新版本须显式增加输入描述、对照及独审，不能放宽旧包或混分母。

当前main的B/C实现已经前进，不能用当前TOOLS/codec解释旧包后宣称固定源核同。
checker先核source_root的Git提交、干净工作树及16 source hash，才在独立CLI解释器
导入该F/C源码。只读原件；不调用FakeTeacher、FakeTools.execute、模型或HTTP。
这不是加载任意不可信代码的沙箱：source_root必须是操作者拥有的可信固定Git checkout。

## 冻结规则与检查

`teacher-rules.v1.json` / `G2C-teacher-quality-rules.1`，评分输出
`G2C-teacher-quality.1`。文件hash和checker源hash进入报告。

自动检查覆盖全部交付文件/候选/原模型与工具记录，不抽样。逐项包含状态、原件引用和原因：

1. 冻结版本/manifest/source/artifact hash与大小、精确文件库存、严格JSON，拒绝重复键、
   非有限数、非法Unicode、额外文件、路径逃逸和symlink。不按未知版本回退。
2. 原F schema/validate/convert/C codec重用：source仅synthetic；不把teacher/real_user换标签。
   所有候选原记录和实际任务/语言/行为身份、RUN/attempt、原模型输入与base64回复核同。
3. 工具requested_execution、原call、op/attempt/RUN/receipt关联；received supplier原字节
   独立经原C prepare/parse_response/encode_result重算，核原binding/时间/查询与实际结果。
   核全批可见投影及未收/取消后不伪造结果。错误回执为FAIL，缺原件或未知为UNKNOWN。
4. 记录全部21任务，包括四个被拒生成的原始用户残片。这些诊断残片不适用候选的完整
   对话minItems要求，不能进入候选；其余schema仍核，候选的原F检查一项不放宽。
   已知坏提议必须隔离，未知之后未开始任务保持UNRUN，不换ID/补样。
5. 从全候选重算connected task/trip/rewrite/content家族、去重、lineage及各用途字节；
   train/validation/public-test不跨家族，不能只删被抽中的坏行或截断中文/改写。
6. 从全部原任务/model/tool记录重算计划、实际、接受/拒绝/重复、语言×行为、RUN终态
   和用途分母；控制失败与pipeline处理状态分开，不用F的PASS字段自证数据质量。
7. 原17负例+2已知伪保存回复重新校验。no_results的两个公开已知正例正常completed，
   把无结果改成已命中事实的精确负控拒绝；这是固定Fake标注，**不是通用语言裁判**。

固定公开制品hash给出了本版来源/污染边界：任意新增内容（包括秘密/最终题/真实用户）
都不是已允许的Fake输入，必须拒绝。checker不声称用关键词发现所有未知语义改写或秘密；
未来真实teacher准入和语义/事实仍必须另行实现与独立核对。

## 全家族采样与真实未验项

seed `D788-complete-family.1`，先固定输入manifest，按
`SHA256(UTF8(seed + NUL + connected_group_id))`升序（相同时group_id升序）排序。
独立于行顺序/结果/人工标签，不允许换seed挑成功样本。

- 首批不超过10完整家族：100%全检；每家族全部任务/语言/改写/原attempt链一起选。
  20轨迹只是每家族一个任务且中英一对时的规模，不截断派生任务凑数。
- 扩批：先选 `ceil(20% × 总家族数)`，再按语言×行为层的字典序补第一个未覆盖家族；
  每层至少1家族，只有1家族的小层全检，补层可使总比例高于20%。
- 本Fake包接受集8个连通家族，演示清单全选8；全21个计划任务的名义trip_family为11，含3个仅坏生成控制家族，另行披露，不能称为真实首批家族分母。接受集清单不丢弃同家族的失败/重复attempt，已拒生成原件仍100%自动核对。演示清单和摘要可复现，不能套作未来真实首批清单。实际真人审阅数仍0。
  报告中的 D_independent_sampling / C_domain_review / R_dataset_review 均UNRUN。
  R对本代码和已知对照的APPROVE不能替代未来真实数据版的R复核。

接受集有任一硬错则整版拒；普通语义/事实错误也不放行。未知/未验不计合格分子。
修订须新数据版和完整分母，不能仅修被抽中项。采样不保证未抽部分已证明无错误。

## 运行与复现

先保留原工作，再建立固定输入checkout；输出目录/文件须尚不存在：

```sh
git worktree add --detach .local/f794-source 21e66d5b19453708f70da44c87df48e655b4f74e
(cd .local/f794-source && uv sync --locked && uv run --locked python -B -m tooling.datasets.teacher \
  --mode fake --batch-id f789-smoke-v1 --output ../f794-input)
uv run --locked python -B -m eval.optimization.teacher_quality \
  --source-root .local/f794-source --bundle .local/f794-input \
  --manifest-sha256 75d8655b3c2e5432e5a2a4dd86c2c4130c5b88d34e11426ec106e0fa23b34919 \
  --output .local/d788-report.json
uv run --locked python -B -m unittest eval.optimization.test_score
```

重建仅执行原F已允许的本地Fake生成/C解析；checker自身不生成或执行工具。
同一输入、checker和规则的报告逐字重复；没有timestamp/本机路径入报告。
退出0仅表示自动Fake检查PASS；FAIL或UNKNOWN退出2，未知不补PASS。旧输出拒绝覆盖。
输入损坏时保留可验证的逐项原因；分母不可验证时为null，不能据声明制造分母PASS。

默认D测试入口保留原21项评分测试并导入独立质检测试；不改共享CI或F测试。
测试在新临时worktree重建固定F输入，用原代码检查，不从当前main猜旧TOOLS。
日志/原件/完整报告只在忽略目录，Git中仅公开规则、摘要、测试与说明。

## release_eligibility 与交 G 格式

G消费一个固定的D完整报告（先核其文件SHA），以及报告绑定的原F manifest和13制品hash。
报告内 `g_handoff.version=G2C-quality-handoff.1`；记录源manifest SHA、checker/规则版本，
行摘要/组/用途/原RUN与answer_state，所有任务的独立证据状态、原因及完整分母。
不是另一套训练行schema，实际消息继续从原F的G2C-dataset.1取。

| 条件 | release_eligibility | training_allowed |
|---|---|---|
| 任一硬检查FAIL（包括错误回执/来源/泄漏） | rejected，整版拒绝 | false |
| 缺证/UNKNOWN，或计划尚未完整执行 | blocked_unknown | false |
| 本固定Fake包自动项全部PASS | fake_only_not_released | false |

本版本没有training_eligible分支、人工PASS开关或真实teacher入口。即使F自填quality/training
PASS也拒绝。原failed/cancelled/partial记录明确control_only；完整Fake回答也仅fake_interface_only，
`g_handoff.training_samples=[]`。用于G模板/tokenization的控制消费仍沿G另行授权，不是正式训练。

未来真实放行须先有已审teacher来源准入及B原件/用途、全部自动项PASS、D完整家族抽检PASS、
C领域PASS、R同数据版复核PASS，并核同source/manifest/report hash；训练还需G自己的授权。
任一UNKNOWN/UNRUN或同版分歧均不可训练。本轮#788第3框保持UNRUN，整票及#767保持OPEN。
