# G2C-runtime-adapter.1 · #762 Part2

依据 [B 约定](https://github.com/JTCAO515/G2C/issues/762#issuecomment-6783508534)，
消费 [E 预登记v2](https://github.com/JTCAO515/G2C/issues/764#issuecomment-6791824507)
及 D `score.2/cases.2/task-contract.2`。只新增本模块和专属测试，不修改 B 的在途文件。

此模块实现完整任务编排、反思请求、原始操作映射及只读证据核对。
**它不构造真实 backend、身份、额度、窗口或费用账本，也未挂载到生产调用链。**
本轮没有香港操作、原账操作或真实模型/工具请求。B 组合和实际运行镜像/子限额未交时，
真实调用必须保持 UNRUN；本地受控 backend 不是线上接线或数据质量证据。

## 跨 binding fixture v1：记录边界与已知未交部分

`fixture_records.py` 固定消费 D/R PR900 的 `G2C-cross-binding-fixture.1`，
来源提交 `929db2b28abc2f0c75ab0a49ba0ac82219213afa`，schema SHA256
`488ab9357fd15b6188207a714e07e109ec942435144eaad8dc2f440bdc0340aa`。
`decode_record(raw)` 复用既有严格 JSON codec，接受 canonical UTF-8 definition/use，
拒绝未知版本/字段、重复键、错误 null/状态和非法 UTF-8；沿冻结规范处理 FAIL 优先级。
复用已有运行依赖 Pydantic，运行时不加载开发目录或依赖 dev-only JSON Schema validator。

`link_records(definition_raw, use_raw, binding=..., pins=..., request=...)` 仅验证声明之间
及其与已建立 G 消费上下文的一致性：原定义字节 hash、fixture 标识、E binding/owner、
pins、完整 request hash/原 ID、observer 的原 producer Binding.key、原 charge/batch。
它不解析 C 的 ref、不获取 C 资格，也不返回真实性 PASS。`LinkedRecords` 保留原 wire，
不能把规范化模型重新序列化后的 hash 冒作原件 hash。不同 metadata ref 可以描述同一
observer Binding.key；v1 不允许用同 owner 的新 session 替换原 producer。

当前这部分**尚未接入 G 自动证据判定**。真实 metadata-only producer/observer、其各引用
原件的受保护返回形状、动态资格与身份/费用/时间/隔离/扫描核对仍须 B 提供和组合；
不能仅凭 ref 存在、hash、producer/check 标签或上述声明关联宣称完成 X01–X12。
19 个 protected 语义向量、完整 fixture 验证与实际运行资格仍 UNRUN；原 G 外层和
single-binding 校验不变，`quality_status` 仍是 UNKNOWN。

```sh
uv run --locked python -B -m pytest backend/tests/test_cross_binding_fixture_adapter.py -q
```

## 文件与默认验证

- `contract.py`：不可变 Binding/Pins、候选/输入边界；复用 `cj_strict_json`。
- `profiles.py`：三个来源文本锚点、只改文本的 renderer、原注册模型反思 preparation；宿主接线均UNRUN。
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
可编辑安装和生产 wheel 均暴露 `from runtime_adapter import RuntimeAdapter` 及原
`cj_*` 领域导入名。镜像保留仓库相对根；非 editable wheel 的公开固定材料和策略源码
安装在标准 data 目录 `share/g2c/runtime-source`，由 B 组合时显式传入。
`configuration.source_c0()`还会从仓库相对根读取以下公开固定输入：
`eval/optimization/cases.v2.json`、`eval/optimization/score_v2.py`、
`tooling/optimization/uv.lock`。`source_c0(*, resource_root=None)` 与
`freeze_pins(runtime_card, *, resource_root=None)` 保留旧默认 ROOT；可选根是 B 的部署配置，
不接受模型/候选/HTTP任务输入，不指向身份/额度包。资源根下的策略源码须与实际导入源码
逐字一致；缺文件或错源直接失败，不搜索目录或回退其他数据。adapter 摘要来自实际安装模块。
构建只新增这三项明确公开输入，不复制其他 eval/tooling 文件、最终题、私有原件、日志或凭据。

```python
from pathlib import Path
import sys
from runtime_adapter.configuration import source_c0, freeze_pins

public_root = Path(sys.prefix) / 'share/g2c/runtime-source'
source = source_c0(resource_root=public_root)
pins = freeze_pins(b_actual_runtime_card, resource_root=public_root)
# Reuse the existing explicit dataset_path, without replacing the loader.
adapter = RuntimeAdapter(b_registered_backend, b_original_binding, pins,
                         private_mapping_directory,
                         dataset_path=public_root / 'eval/optimization/cases.v2.json')
```

资源可读只证明打包/同源材料可用，不改变三槽、身份、费用、实际运行卡或宿主 UNRUN 状态；
本切片不启用 national.2/profile2 或原本未连接的全国 clarification。

## C0 与固定材料

`c0.source.json` 是 **C0-source-national.1 源配置**：

- 三槽仍为 `prompt.answer_style`、`tool.lookup.description`、`example.clarification`。
  原文分别来自 `PERSONA` 的风格句、`NATIONAL_TOOLS.place_search.description`、
  旧 `DISCUSSION_PROMPT` 的澄清句；第三句不是当前全国reg7路径的消费锚点。
  不是 E 的合成 SEED，也不把身份/权限/保存条件放入槽位。
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

### 现役reg7消费路径与B所需hook

下表为已接受源码的可组合位置，**不是已接线证据**；三槽宿主状态均UNRUN。

| 槽 | 实际路径 / renderer profile | B最小hook与当前限制 |
| --- | --- | --- |
| `prompt.answer_style` | `cj_message.lio_context.answer_prompt(locale)`包含PERSONA；`local_lio_national.intake_prompt`把它接到CURRENT_SYSTEM前，注册`model.lio_intake.7`生成reply；`RealTools.answer`也把它接到TOOL_SYSTEM后。profile=`answer`。 | 在原prompt组装处，仅对`answer_prompt(locale)`这段调用`render(..., [], fragments, profile='answer')`，再接回原策略/日期/源索引；两个入口都需按原RUN绑定候选，不替换CURRENT_SYSTEM、响应schema、compiler或保存authority。 |
| `tool.lookup.description` | `RealTools._model_input(ModelInput(..., national=True))`序列化`self.national_tools`；`model.tool_turn`消费place_search描述。该tools参数可随任一profile处理，纯工具阶段用`authority`（system不变）。 | 每RUN从原工具列表拷贝、只替换description，在原注册准备/原输入hash/Meter前传入；不全局修改`self.national_tools`。无工具的consult不消费本槽，不能把这类轨迹算作lookup接线验证。 |
| `example.clarification` | profile=`discussion`只适用于旧`local_lio_planning.DISCUSSION_PROMPT`。reg7的consult/discuss直接取intake.reply，实际intake_prompt不含此锚点；profile=`authority`也不替换prompt。 | **全国NOT_CONNECTED**。B须在#762给明确允许的reply-only文本hook与C0原字节等价方案，必要时与E重新固定基线；不能把旧锚点追加到CURRENT_SYSTEM、改schema/compiler或凭空新增指令。未交前，B整任务准入须将依赖此槽的非C0候选明确UNRUN，不能静默忽略后称三槽已优化。 |

accepted main中人设入口是`backend/message/cj_message/lio_context.py:answer_prompt`，
没有名为`lio_answer_prompt.py`的文件；固定实际定义文件hash，不创建影子源码。
source bundle另固定现役start/flat/facts schema及flat/sourced compiler，保留历史策略hash供来源核对。
本模块renderer的本地C0 no-op只证明所传原system/tools原样返回；真实宿主尚未调用renderer。
B挂接后必须在两个真实输入入口逐字比较C0序列化请求（含response_format和tools），
并用非C0单槽候选证明仅目标文本变化、其余authority字节不变。缺失路径继续UNRUN。

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
同一步先核受保护action/inventory及操作集合，再读取每个operation全部已有输入/输出、
provider/Meter/fee原件。某一坏件不隐藏本operation其余回执或后续operation，
`operation_checks`逐项保留UNKNOWN与稳定错误码；不可信顶层/库存不据其refs继续遍历。
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
  生命周期status及inventory/result/state_evidence的原引用，不能串用同owner另一动作的RUN或状态，
  也不能把原FAIL/CANCELLED改成PASS来继续后续步骤。
- inventory原件映射独立绑定client_step_id、request_sha256、message/action ID、原身份、
  完整run_ids、有序完整operation_ids。由原存储关联枚举，不能信任客户端声明的RUN集合。
  action/inventory必须由B受保护的原client-step持久关联（或可核来源的只读映射）生成；
  不能在query时将待验snapshot的字段复制成“证明”，从而形成自证闭环。
- 每operation：原operation_id/attempt_id/run_id/registration_id/kind、input/output/meter/provider/fee
  引用、provider_state/meter_state/fee_state和实际model配置。model/memory必须匹配模型pin。
- 引用为 `{ref:<B opaque original>, sha256:<原字节>}`，解析器不支持任意URL或本机文件路径。
  Meter/原注册操作的只读关联映射绑定attempt/operation/run/registration/kind、input_sha256、
  output_sha256（缺输出显式null）及owner/status；不能改kind/registration绕过模型pin。
  fee映射绑定原attempt/ledger/state，provider映射绑定原attempt、输入/输出hash，model/memory还须
  绑定实际model描述（原准备输入/实际provider回执所得，不抄待验envelope）。
  INTENT不能伪造已收到回执，NOT_SENT不制造provider/fee回执。
- reflection的output必须是原RegisteredExit流最终文本的原字节，provider回执映射绑定该输出hash；
  result必须与该唯一模型output为同一字节hash，再严格解析JSON。不能将另一份合法槽文本替作结果。
- response缺失为null，不填空JSON或0费用。正式状态/全部Trip历史、undo_target、实际上下文/续接
  与provider输入/投影前工具结果及可见投影均在state_evidence/原件中保留，由D据实归一化并独立标注。

本地映射目录必须owned0700、文件0600、同目录单writer；checksum仅检测损坏，不是鉴权。
不要删映射/换目录绕未知；即使丢失，B canonical claim仍须拒绝已存在原ID。
源码/配置可入Git，原用户内容/运行日志/权重/凭据均在Git外；本轮测试只用公开合成数据。
