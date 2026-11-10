# G · #773 学生模型训练准备

父专题 [#767](https://github.com/JTCAO515/G2C/issues/767)。本目录只准备环境、配置和离线预检；没有训练启动器，不代表正式训练、学生质量或上线放行。权重、数据发布目录、原始运行日志和秘密必须放仓库外。生产根依赖不变。

## 固定环境与官方接口

核对日期：2026-11-11。选择 **ms-swift 4.6.0**，官方 tag 对应源码 `ad818a2cdfafaf4305ac40c4acd892a211978bc2`；不跟随 main 或 `pip -U`。

- [官方 release](https://github.com/modelscope/ms-swift/releases/tag/v4.6.0)、[Apache-2.0 许可证](https://github.com/modelscope/ms-swift/blob/ad818a2cdfafaf4305ac40c4acd892a211978bc2/LICENSE)。框架许可不覆盖模型、教师输出或数据的使用权，正式起工前分别核对。
- [安装矩阵](https://github.com/modelscope/ms-swift/blob/ad818a2cdfafaf4305ac40c4acd892a211978bc2/README.md#-installation)：文档要求 Python ≥3.10、torch ≥2.0，支持 CPU/MPS/CUDA 等。本方案选 CPython **3.12.14**；[包 metadata](https://github.com/modelscope/ms-swift/blob/ad818a2cdfafaf4305ac40c4acd892a211978bc2/setup.py) 的 Python ≥3.9 是较宽的包约束，不作为推荐环境。
- [实际框架依赖](https://github.com/modelscope/ms-swift/blob/ad818a2cdfafaf4305ac40c4acd892a211978bc2/requirements/framework.txt)：datasets ≥4.0,<4.8.5，peft ≥0.11,<0.21，transformers ≥4.33,<5.20，trl ≥0.15,<1.0。README 中 datasets 下界较宽，解析采用发布包的实际约束。

| 包 | 本轮固定版本 | 已安装包声明许可 |
| --- | --- | --- |
| ms-swift | 4.6.0 | Apache-2.0 |
| torch | 2.8.0 | BSD-3-Clause |
| transformers | 4.57.6 | Apache-2.0 |
| datasets | 4.8.4 | Apache-2.0 |
| peft | 0.18.1 | Apache |
| trl | 0.29.1 | Apache-2.0 |
| accelerate | 1.12.0 | Apache |
| jsonschema | 4.26.0 | MIT |

`requirements-macos-arm64.lock` 锁定全部 118 个安装包及下载 hash；由 uv 0.12.14 解析。许可列是包 metadata 核对，非数据/模型的法律放行。无 DeepSpeed、FlashAttention、bitsandbytes、vLLM、Megatron、付费 provider 或日志 SaaS 的准备需求。

从仓库根目录运行，环境位置自行指定到仓库外（变量不含凭据）：

```sh
export G2C_TRAIN_ENV="$HOME/.local/share/g2c-training-773/venv"
uv venv --python 3.12.14 "$G2C_TRAIN_ENV"
uv pip sync --python "$G2C_TRAIN_ENV/bin/python" --require-hashes tooling/training/requirements-macos-arm64.lock
uv pip check --python "$G2C_TRAIN_ENV/bin/python"
"$G2C_TRAIN_ENV/bin/python" -B tooling/training/environment.py
"$G2C_TRAIN_ENV/bin/python" -B -m unittest discover -s tooling/training -p 'test_*.py' -v
```

不要对已有同名环境执行重建。重新解析仅用于有意升级（会改变锁，须复验），日常复现使用 `sync --require-hashes`：

```sh
uv pip compile tooling/training/requirements.in --python 3.12.14 --python-platform aarch64-apple-darwin --generate-hashes --output-file tooling/training/requirements-macos-arm64.lock
```

**硬件适用范围**：本轮实际机器为 macOS 27.2 / arm64 / Apple M5 Pro / 48 GiB 统一内存。MPS 可用、CUDA 不可用；仅证实依赖导入和单张量前反向，不证明模型可装载、显存足够或训练吞吐。配置暂用 float32/eager、不量化、不 packing/padding-free；具体模型再定精度。CPU 可做结构和 tokenizer 检查，不能据此估训练时长。

将来若选择 Linux NVIDIA：官方推荐 CUDA 12.8/13.0、torch 2.8.0/2.11.0。本轮候选为 Linux x86_64 + Python 3.12.14 + torch 2.8.0 cu128 + 兼容 NVIDIA 驱动。必须在**已有获准设备**上另解平台锁、核驱动/torch wheel/模型算子、实测峰值显存与吞吐，再冻结资源；本 macOS 锁不能冒充 Linux/CUDA 验证。NPU/ROCm/MUSA 各需独立设备及官方适配依赖，均 UNRUN。没有默认 GPU 数、显存配额或云采购。

接口以 [官方参数](https://github.com/modelscope/ms-swift/blob/ad818a2cdfafaf4305ac40c4acd892a211978bc2/docs/source_en/Instruction/Command-line-parameters.md) 和固定源码为准：

- CLI 支持 `swift sft <json-or-yaml>`。`sft.example.json` 是未填写模型/数据/输出的**方案配置**；20 steps 仅是将来有限基线的候选上限，不是执行授权。当前禁止启动该命令。
- [Python 模型接口](https://github.com/modelscope/ms-swift/blob/ad818a2cdfafaf4305ac40c4acd892a211978bc2/swift/model/register.py) 是 `swift.model.get_model_processor`；v4 不能沿用旧 v3 的模块路径。仅 tokenizer 检查使用 `load_model=False, download_model=False`。
- [模板接口](https://github.com/modelscope/ms-swift/blob/ad818a2cdfafaf4305ac40c4acd892a211978bc2/swift/template/register.py) 是 `get_template(processor, template_type=..., agent_template=..., loss_scale='default', template_backend='swift', is_binary_loss_scale=True, truncation_strategy='raise', max_length=...)`，之后 `set_mode('train')` 与 `encode`。`environment.py` 实际导入这些接口并核所有示例配置字段属于 `SftArguments`，不实例化 Trainer。

## 预检入口与 F 依赖

```sh
"$G2C_TRAIN_ENV/bin/python" -B tooling/training/preflight.py config tooling/training/sft.example.json
"$G2C_TRAIN_ENV/bin/python" -B tooling/training/preflight.py dataset /outside/release --version unknown-v1
"$G2C_TRAIN_ENV/bin/python" -B tooling/training/preflight.py swift-jsonl /outside/export.jsonl
```

- `config` 报告缺少 model、model_revision、template、agent_template、dataset、val_dataset、output_dir，并拒绝全 token loss、自动重拆数据、宽松丢坏行和外发日志等设置。退出 1；报告不是训练许可。
- `dataset` 当前退出 **2 / UNRUN / UNKNOWN_DATA_VERSION / F_SCHEMA_UNAVAILABLE**，不读取或接受任何 G2C 版本。#768 尚未发布固定契约，本实现没有第二套 G2C schema，也不会把任意用户提供的版本字符串当已知版本。
- `swift-jsonl` 是与 F 无关的**上游目标格式局部检查**，仅支持纯文本 OpenAI `messages` / `tools` 格式；不是 canonical dataset validator 或 F 转换器。逐行检查必需字段、工具名称及参数 JSON Schema、重复 call ID、调用与结果关联、缺回执和最终答复；坏行报行号与稳定原因码，退出 1，禁止回显内容。该子集拒绝参数 schema 的 `$ref`/`$dynamicRef`（避免外取）及消息的 loss 覆盖（避免工具结果被监督）。它不证明工具真实执行、来源权威、拆分或 D 质检通过。无错误时 scope 内 PASS，但 `training_readiness` 始终 UNRUN。

[官方数据格式及 OpenAI 归一化](https://github.com/modelscope/ms-swift/blob/ad818a2cdfafaf4305ac40c4acd892a211978bc2/docs/source_en/Customization/Custom-dataset.md) 与 [Agent 语义](https://github.com/modelscope/ms-swift/blob/ad818a2cdfafaf4305ac40c4acd892a211978bc2/docs/source_en/Instruction/Agent-support.md) 已核。调用 ID 需在归一化前核对；不能仅检查序列化后的文本。

**待 F 固定后再做映射，精确缺项**：

1. canonical schema 文件、schema version/hash 与发布 commit，行版本未知/空值的规则；获准的 validator/converter 入口。
2. 消息、tool schema/hash、call ID、arguments、实际 tool result 与 execution/receipt 的绑定方式；failed/unknown/cancelled 的终态及哪些样本适合 SFT。不得为未收到结果的调用补假 tool result 或假 assistant 答复。
3. source kind/ID/revision、trajectory/prompt/model/adapter 版本、任务/旅行/中英改写分组身份及去重 hash。
4. 固定发布 manifest、train/validation/test 文件 hash/行数、拆分种子和用途限制、拒绝与去重报告；D 独立检查的精确版本与证据。

F 固定后直接复用其 schema/validator/manifest，不复制定义。对接时增加受影响正负例，原生坏回执必须由 F 拒绝；训练目标导出须记录来源样本与 group/split/hash，保留 F 原分组，test 不进入训练或调参。终态轨迹不能静默丢弃，明确列为不适合当前 SFT 的样本并计数，不把失败转成功。正式教师数据不因合成小样 PASS 自动获准。

## tokenizer / chat template / loss mask 验收方法

**本轮真实模型检查 UNRUN**：标准缓存只见 MiniLM 句向量模型与 MiniMax-H3 的不完整引用，没有获准的学生聊天模型快照。没有下载权重、没有 mock tokenizer PASS。框架支持某架构不等于已选择或许可该模型。

需要 JT/后续 Goal 固定：模型 repo ID、不可变 commit/revision、原模型卡与 LICENSE、使用范围；同 revision 的 `config.json`、`tokenizer_config.json`、`tokenizer.json` 或 vocab/merges/tokenizer.model、`special_tokens_map.json`/added tokens（该模型使用时）、`chat_template.jinja`（外置时）及每文件 SHA-256；ms-swift `model_type`、`template_type`、`agent_template` 和 thinking 设置。仅编码无需权重；正式训练另需对应权重与 index/shard hash。模型含远程自定义 Python 时须先审源码并获准执行；框架 loader 默认可启用 trust_remote_code，不能因 offline 就当安全已验。

1. 对获准**本地**快照核 hash/revision；设置 `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 MODELSCOPE_OFFLINE=1`，不使用 Hub ID。通过 `get_model_processor(local_dir, load_model=False, download_model=False, model_type=..., revision=...)` 取 processor；确认没有 Trainer、模型权重加载或生成。
2. 先使用 F 已验的中英直接答、澄清、改口、取消、成功/失败/未知工具、多轮与并行调用轨迹。只对适合 SFT 的完整样本编码；保持原始调用和实际工具结果，不把未知变空值。检查 OpenAI preprocessor 输出的 tool_call/tool_response 顺序，给结果文本置于无损可识别的合成标记以便定位，记录这仍是合成测试。
3. 固定 Swift 训练模板与 agent template。核 BOS/EOS、角色边界、工具定义/参数 JSON、Unicode、思考标记及轮次拼接；与同 revision tokenizer 的 `apply_chat_template`（支持工具时）和模型卡例子对照。差异必须解释并由 D/R 复核，不能用 Jinja 渲染等同于训练模板：官方 Jinja backend 不支持训练 loss 范围计算。
4. `set_mode('train')` 后 `encode`，取 `input_ids`、`labels`、可能的 `loss_scale`；逐 token/span 检查长度一致、未 mask 的 label 对应原 token。system/user/tool_response 内容应全部 `-100`（或有效权重 0）；assistant 工具调用、可训练答复应有正 loss，不能训练模型复述工具真实结果为“自己生成的工具回执”。检查多轮历史、EOS、空思考和失败说明的边界，最后一 token/因果 shift 另核；任何工具结果进入监督区域立即 FAIL。
5. 对 max_length 边界前后、padding/batch、并行调用次序作核对。编码预检用 `truncation_strategy='raise'`；正式候选虽为 delete，但必须先统计全量 token 长度并明确列出超限样本，未审查不得默默删样本。先保持 packing/padding_free 关闭。
6. 仓库外保存 token/span/mask 检查制品及材料 hash；PR 仅报统计与脱敏合成证据。通过仅表示该固定材料与模板通过，换 revision/框架/模板/thinking/packing 必须定向复验。D/R 独立核查后才能进入有限训练 Goal。

## 正式训练起工清单（当前未放行）

- [ ] F 固定**正式**数据 release/version/hash、schema/工具/轨迹/prompt/教师版本、来源与使用权；拆分在任务分组之后，中英改写/同旅行不跨用途；锁住独立 test。
- [ ] D 独立质检对该 release 出具报告：工具实际执行与原回执、来源、未知/失败/取消、去重/泄漏、已知坏样本、双语语义。结构合成检查不能代替此项。
- [ ] 固定学生 repo/revision/模型许可、全材料 hash、环境锁/hash、LoRA 模块/精度/seed；真实 tokenizer/template/mask 全部通过。
- [ ] 另行明确已有设备或获准算力、GPU/内存/磁盘/最长时长/费用上限、唯一 owner、输出目录及 checkpoint 留存范围。先测实际模型峰值与 tokens/s。本轮可用范围仅本地准备、额外 GPU=0、云资源=0、付费模型请求=0、正式训练=0。
- [ ] 有限基线计划固定（当前示例候选 rank 8、batch 1、累计 8、max_length 2048、最多 20 steps；未执行），不得自动升级步数、模型或资源。记录可训练参数数目、实际 token 数及排除样本。
- [ ] 比较使用 D/R 同一固定留出和原 API 原 harness / 原 API 优化 harness / 学生优化 harness 三组；分别记录任务成功率、工具名称/参数/执行状态正确率、事实来源/严重编造/写权限错误、中英分项、p50/p95 首正文与完整时延、吞吐/峰值显存、实际费用。质量阈值由后续 Goal 与 D 评分固定，不由训练 loss 降低推导通过。影子评测禁止真实写工具。
- [ ] 停止条件：数据/版本/权限/回执异常、工具结果被监督、NaN/Inf、OOM、预算或时间界限、隔离/正式写入错误立即停止新工作；记录 FAIL/UNKNOWN，不自动重试或扩资源。loss/验证质量退化阈值须在有限训练前固定。
- [ ] 恢复演练：确认进程退出、保存完整的最近 checkpoint 及 optimizer/scheduler/RNG/trainer 状态、同环境锁/数据/模型 revision/配置/step/hash。SIGINT 不保证即时保存，恢复只用最后完整 checkpoint，丢失区间显式记录。按官方 `resume_from_checkpoint`，保持 `resume_only_model=false` 和 `save_only_model=false`；仅加载 adapter 不算恢复。恢复不得覆盖旧实验，先核原进程与输出，获得对应后续 Goal 授权后才执行。
- [ ] 学生质量达标后由 B 另票做接入/路由/回退；保留原 API。训练准备、有限训练、独立比较和上线是不同授权及证据。

## 本轮证据分层

命令见上文；精确提交、CI run、独审与合并结果见 #773 / PR。

| 项目 | 状态与边界 |
| --- | --- |
| 官方版本/许可/接口与完整本地锁 | PASS，固定 v4.6.0、118 包；不含模型许可 |
| Python 包一致性、接口导入、示例参数名 | PASS；`uv pip check` 与 `environment.py` |
| MPS 张量前反向 | PASS，输入 2 的平方梯度 4；不是模型训练 |
| 独立目标格式合成边界检查 | PASS；`test_preflight.py`，不代表 F 数据验收 |
| F schema/固定数据集成 | UNRUN，#768 尚未交付，未知版本明确拒绝 |
| 真实 tokenizer/template/loss mask | UNRUN，缺选定并获准的本地模型材料 |
| 正式训练/恢复/质量/生产上线 | UNRUN，本轮未授权 |

没有删除任何原边界检查或测试；新增检查均在外部配置/JSONL 的进入边界，复用 `cj_strict_json.reject_duplicates`。本轮停点按 tooling/training/** 归属在 #773/#767 交接，不改其他线 handoff 文件。后续由 Claude 编写 Goal、JT 转交。
