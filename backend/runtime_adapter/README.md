# G2C-runtime-adapter.1 · #762 Part2

依据 [B 约定](https://github.com/JTCAO515/G2C/issues/762#issuecomment-6783508534)，
消费 [E 预登记v2](https://github.com/JTCAO515/G2C/issues/764#issuecomment-6791824507)
及 D `score.2/cases.2/task-contract.2`。只新增本模块和专属测试，不修改 B 的在途文件。

此模块实现完整任务编排、反思请求、原始操作映射及只读证据核对。
**它不构造真实 backend、身份、额度、窗口或费用账本，也未挂载到生产调用链。**
本轮没有香港操作、原账操作或真实模型/工具请求。B 组合和实际运行镜像/子限额未交时，
真实调用必须保持 UNRUN；本地受控 backend 不是线上接线或数据质量证据。

## 文件与默认验证

- `contract.py`：不可变 Binding/Pins、候选/输入边界；复用 `cj_strict_json`。
- `profiles.py`：三个生产文本锚点、只改文本的 renderer、原注册模型反思 preparation。
- `configuration.py` / `c0.source.json`：可重复的源C0配置及逐文件/片段摘要；不填假镜像。
- `adapter.py` / `ports.py`：公开 call/propose/query 与 B 的最小组合接口。
- `journal.py`：本地原操作映射；不保存/结算费用、不替代 B 的任何账本。
- `backend/tests/test_runtime_adapter.py`：由现有默认 `pytest backend/tests` 自动发现，
  无需修改共享 `scripts/test.py` 或根依赖。

```sh
uv run --locked python -B -m pytest backend/tests/test_runtime_adapter.py -q
uv run --locked python -B -m runtime_adapter.configuration
```

源C0生成仅导入固定代码/读取公开输入，不创建 provider、读取凭据或打开费用库。
默认根可编辑安装已暴露 `backend/`，可 `from runtime_adapter import RuntimeAdapter`；
实际生产 wheel 的包含与 B 宿主挂接仍须 B 在其后续接线中显式完成。

## C0 与固定材料

`c0.source.json` 是 **C0-source-national.1 源配置**：

- 三槽仍为 `prompt.answer_style`、`tool.lookup.description`、`example.clarification`。
  原文分别来自当前 `PERSONA` 的风格句、`NATIONAL_TOOLS.place_search.description`、
  `DISCUSSION_PROMPT` 的澄清句；不是 E 的合成 SEED，也不把身份/权限/保存条件放入槽位。
- `render(..., C0, profile=...)` 返回与原 B system/tools 相同的字节内容。
  answer/discussion 仅替换其声明的唯一锚点；authority/intake/save 策略不替换 system。
  lookup 只改变 place_search 的 description；parameters、其他工具/字段均保留。
  未匹配或重复锚点拒绝，不猜值或自动适配未知版本。
- 固定北京 DashScope endpoint、`qwen3.8-flash`、实际代码参数档（thinking/stream/输出等）、
  静态系统策略 bundle、全C0工具与不可调结构、工具实现、D源码/数据和E登记正文摘要。
  每次实际消息/日期/记忆/工具续接输入的原字节另由原件 ref/hash 留存，不以静态策略hash替代。
- `adapter_sha256` 是本目录 Python 源文件集合的hash。code_sha 与 image_digest 必须是
  B 实际运行且包含该代码的提交/镜像，不能拿源基线或本机测试字符串代填。
  B 从实际进程得到 model 参数后才可 `freeze_pins(runtime_card)`；不匹配必须显式修订，
  不能由候选改模型/工具参数来迁就。
- task/cases固定 `G2C-dialogue-cases.2`，score固定 `G2C-dialogue-score.2`，
  E登记正文 `285500035df89e848ef20f9c34fc8f53887b3050cdf7b69e33d818334c7ea91f`。
  v1不自动回退，最终题不加载。F尚未获批的真实教师任务集不由此虚构或准入。

```python
from runtime_adapter import Binding, RuntimeAdapter
from runtime_adapter.configuration import freeze_pins

# 以下对象/实值由 B 现有宿主提供；本模块没有登录/配置凭据/新角色接口。
pins = freeze_pins(b_actual_runtime_card)   # code_sha, image_digest, model
adapter = RuntimeAdapter(b_registered_backend, b_original_binding, pins,
                         private_mapping_directory)
c0 = pins.c0()
result = adapter.call({'id': 'dev-local-edit', 'language': 'en'},
                      c0['fragments'], 'original-logical-attempt', 180)
original = adapter.query('original-logical-attempt')
```

`b_original_binding` 为 B 解析的原 scope/auth_session/ledger_id/producer_id，不是客户端声明。
固定参数和原身份从 `backend.require` 逐次复核；guard 并非缓存的 ALLOWED 布尔值。
`c0().runtime_eligible=False`：配置本身不签发真实实验资格。

## call / propose / query

公开方法参数与 B 约定同名，返回 `version/status/attempt_id/reason/binding_sha256/pins_sha256`
及 started steps 的原证据。status 是执行/收集状态，不是 D 的质量判定，quality_status 始终 UNKNOWN。

### call(task, candidate, attempt_id, timeout)

task仅为公开固定数据的 `{id, language}` 引用，全部原文/步骤从固定cases读取。
先由 B 做整任务合法 setup/recipe 的只读预检；缺前置返回 UNRUN，不能付费尝试构造基线。
预检不接收 variants 中的预期 state/behavior，也不能根据题面编造实际观测。

setup 是有原件的实际操作，其模型/工具调用也进入原 RUN/Meter/共享费用出口。
三个mutation任务执行全部 `variants.steps`；undo 是当前真实 opaque target 的原生操作，
无新增 MESSAGE/RUN。其余任务保留 turns：dev-cancel 用受控生成和原 RUN 取消；
deleted-recall 用实际新会话消息，不以 `[New chat]` 文本自证换会话。
B setup 必须按现役合法槽/对象/权限实现，不能管理员SQL/bootstrap、增槽或借 C 身份。

所有步骤只使用调用者给定的逻辑 attempt；原 client step ID仅由 scope/attempt/index生成，
即使本地映射丢失、候选/参数变化也不会生成替代ID。每步先fsync本地意图，再由 B
原子 claim 原操作；B已有ID只能 query，fresh claim丢ACK同样UNKNOWN，不再claim或dispatch。
claim能力仅在进程中使用，不序列化进日志；B负责一次性消费及原注册/Meter准入。

普通步骤必须终态后才发下一步。唯一例外是公开取消控制已证明 RUNNING 的原动作，
可以发送预先声明的原取消操作，不能发新模型请求替代。确定取消后不重跑同一attempt；
新任务仍须原B取消/租约guard许可。任一未决UNKNOWN会阻断本绑定后续派发。

### propose(candidate, feedback, components, attempt_id, timeout)

仅三个文本槽的选定非空子集。feedback格式为
`{split:'development', dataset_sha256:<当前cases>, rows:[{task_id,language,feedback,evidence}]}`，
只接受当前development任务；validation/未知任务/额外组件拒绝。
caller/D仍负责独立真实反馈标注及原件来源，不准将最终题或预期样例伪标为开发反馈。
输出仅准选定组件字符串；错键/空文本为明确FAIL，不自动反思重试。

`reflection_registration(real_tools)` 只返回 `Registration('model', ...)`，
沿原 `RealTools._model_input` → 原 MeteredDashScopeProvider → 原 AuthorizationBudget。
不传native tools、不改模型、身份或费用出口。B必须在原已准入 MESSAGE/RUN 中登记
`model.runtime_reflection.1`，经原 RegisteredExit.prepare_operation/stream 执行；本模块不自行安装。

### query(attempt_id)

只读本地映射、原操作、RUN inventory、全部provider/Meter/共享原账回执和状态原件。
每个opaque ref由 B 在同一原owner/authority生命周期读取，G重算原字节SHA并核原ID/运行/
身份/pins/原账ID；操作集合与受保护 inventory 精确一致，不能只交最后一次RUN或成功子集。
还要复读相同原snapshot，来源/身份漂移即UNKNOWN。整个query受30秒读取界限约束。
某一步缺失或坏原件仍继续读取其余已启动步骤，逐步保留UNKNOWN；返回前再次核读取资格。
身份变化、撤权或读取资格失效时不返回已读的私密steps/result，不能只改状态而泄露旧载荷。

provider INTENT、未settle Meter、缺回执、找不到原件、坏hash或未知ACK均UNKNOWN，
不释放hold、不生成新动作、不登录/续身份、不resend。查询不改任何 B 数据或本地意图。
实际费用仍取原账；估算/保守占用/实付未知不能由本模块计算出“已结算”。

## B 最小挂接清单（不在 G 目录外实施）

1. **宿主身份/资源**：以现有认证scope、原auth_session、唯一ledger/producer构造 Binding，
   提供 `binding/pins/require`。dispatch逐provider仍调用现有原guard和更严格限额，
   query只使用原受保护读权限；窗口/子额/未知hold仍由B交付，不交给G配额布尔值。
2. **文本/反思**：在原模型输入序列化/注册/Meter reservation之前按RUN绑定候选调用renderer，
   不使用全局可变“当前候选”。固定C0后与原请求字节对比。将反思registration合并到原注册表，
   使用原scope/RUN/模型/原账；现有RealTools没有此registration，G不修改该B文件。
3. **实际动作/安全setup**：`prepare_task`只读核recipe，`claim/dispatch`原子绑定原client step，
   消息、当前Trip undo、受控取消、原Memory STOP-USE、失败fixture沿现有端点/原件。
   claim不派provider；已有client ID不执行，能力只消费一次。缺合法setup直接UNRUN。
4. **完整只读collector**：`inspect/original` 返回下述域内原件映射；从原操作/保护读枚举
   全部RUN及模型/工具/记忆调用，含setup、失败/取消/INTENT与原输入/可见投影/结果。
   公开 `/v1/message-usage-association` 只有最小引用、`/v1/usage-attempt-status`只有最小状态，
   不能冒充本collector；新hook需B在其后续接线中补，不能凭模型自述或题面组装。
5. **实际pin/打包**：给包含本模块的已合代码/镜像、实际静态策略/参数/工具profile及C0；
   确认生产wheel包含本新包。code/image/pin漂移、同源材料或资格缺失时停止，不自动适配。

合并前请 B 在 #762 对本清单、C0文本/参数及接口做一次只读一致性确认。
这不是香港部署或开窗请求；上述宿主挂接仍由 B 在全国规划之后实施。

## inspect 的原件 envelope

固定字段由 `evidence.py` 校验。B collector可作只读投影包装，但每项ref都必须是实际
原字节的受保护引用，不能从期望/模型回复合成。不是新的 F 数据schema。

- 顶层：version、attempt_id、step_id、request_sha256、binding_sha256、pins_sha256、
  status、实际message_id/run_ids/action_id、action/inventory/result/state_evidence引用和operations。
- action原件映射绑定client_step_id、request_sha256、原身份及实际message/action ID、完整run_ids，
  以及inventory/result/state_evidence的原引用，不能串用同owner另一动作的RUN或状态。
- inventory原件映射独立绑定client_step_id、request_sha256、message/action ID、原身份、
  完整run_ids、有序完整operation_ids。由原存储关联枚举，不能信任客户端声明的RUN集合。
  action/inventory必须由B受保护的原client-step持久关联（或可核来源的只读映射）生成；
  不能在query时将待验snapshot的字段复制成“证明”，从而形成自证闭环。
- 每operation：原operation_id/attempt_id/run_id/registration_id/kind、input/output/meter/provider/fee
  引用、provider_state/meter_state/fee_state和实际model配置。model/memory必须匹配模型pin。
- 引用为 `{ref:<B opaque original>, sha256:<原字节>}`，解析器不支持任意URL或本机文件路径。
  Meter映射绑定attempt/operation/owner/status，fee映射绑定原attempt/ledger/state，provider映射绑定
  原attempt及输入/输出hash。INTENT不能伪造已收到回执，NOT_SENT不制造provider/fee回执。
- reflection的output必须是原RegisteredExit流最终文本的原字节，provider回执映射绑定该输出hash；
  result必须与该唯一模型output为同一字节hash，再严格解析JSON。不能将另一份合法槽文本替作结果。
- response缺失为null，不填空JSON或0费用。正式状态/全部Trip历史、undo_target、实际上下文/续接
  与provider输入/投影前工具结果及可见投影均在state_evidence/原件中保留，由D据实归一化并独立标注。

本地映射目录必须owned0700、文件0600、同目录单writer；checksum仅检测损坏，不是鉴权。
不要删映射/换目录绕未知；即使丢失，B canonical claim仍须拒绝已存在原ID。
源码/配置可入Git，原用户内容/运行日志/权重/凭据均在Git外；本轮测试只用公开合成数据。
