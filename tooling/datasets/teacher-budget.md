# F 教师生成预算核查与待批准建议

- 核查日期：2026-11-11（Asia/Shanghai）。
- 范围：#767 教师生成用途；只读官方资料与固定提交 `449a04fb98cd9f14b3dc9e4561a66b19324561d0` 的 B 源码。没有发起真实模型/业务工具请求，没有读取凭据、真实账本、用户日志或最终题；没有修改仓库。
- 状态：**预算建议，尚非运行授权**。F已读回#762及#495：可信导出尚未交付，新增用途当前仅为待批准申请；实际批准以后续JT决定为准。旧额度与源码常量不能替代本用途批准。[#762](https://github.com/JTCAO515/G2C/issues/762)、[#495](https://github.com/JTCAO515/G2C/issues/495)。

## 核实结果

| 项目 | 当前证据与边界 |
| --- | --- |
| 模型与地域 | 官方模型 ID 为 `qwen3.8-flash`，北京支持 Function Calling；北京非缓存原价输入 **¥0.8/百万 tokens**，输出 **¥2.7/百万 tokens**。[阿里云模型页](https://help.aliyun.com/zh/model-studio/qwen3-8-flash) |
| B 的实际配置 | `M4_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1`、`M4_MODEL=qwen3.8-flash`、`M4_REAL_OUTPUT_TOKENS=1536`；真实组装使用该值。请求提交 `max_tokens`，compact/incremental 路径最多1536，其他路径最多1024；`enable_thinking=False`。[provider.py L193-L195、L495-L510](https://github.com/JTCAO515/G2C/blob/449a04fb98cd9f14b3dc9e4561a66b19324561d0/backend/agent/cj_agent/provider.py#L193)、[real_services.py L278-L281](https://github.com/JTCAO515/G2C/blob/449a04fb98cd9f14b3dc9e4561a66b19324561d0/backend/cj_api/real_services.py#L278) |
| 输入边界 | B 限制序列化请求为32768 bytes；**没有核到每请求8000输入 tokens 的硬限**。8000只能作为含系统提示、schema、历史、工具结果的合计估算，不能当已实现上限。[provider.py L495-L510](https://github.com/JTCAO515/G2C/blob/449a04fb98cd9f14b3dc9e4561a66b19324561d0/backend/agent/cj_agent/provider.py#L495) |
| 单 RUN 次数 | 普通 RUN 最多8个 `model.tool_turn`，最多8个外部工具；指定旧受控 probe 为5轮。该上限不是整条跨消息训练轨迹的总上限，不能自动覆盖前序澄清、额外 draft 或 memory 模型步骤。[real_services.py L44、L430-L467](https://github.com/JTCAO515/G2C/blob/449a04fb98cd9f14b3dc9e4561a66b19324561d0/backend/cj_api/real_services.py#L430) |
| 原 RUN 计量 | 注册出口要求 `provider_call` 单位，完整调用按原 attempt 结算1单位；这是请求计数，不是人民币或token额度。[registered_exit.py L55-L63](https://github.com/JTCAO515/G2C/blob/449a04fb98cd9f14b3dc9e4561a66b19324561d0/backend/usage/cj_usage/registered_exit.py#L55)、[metered_exit.py L115-L118](https://github.com/JTCAO515/G2C/blob/449a04fb98cd9f14b3dc9e4561a66b19324561d0/backend/usage/cj_usage/metered_exit.py#L115) |
| 原授权账本 | 源码总限为模型¥10000、工具¥500；计数限为model9987、place1200、route600、weather200、fact240。model/place/route/weather每个未结attempt保留¥1 hold，fact hold为0。完整可定价receipt按公开原价估算；UNKNOWN保留hold。**这里只核源码，没有读取实际剩余额度，也未确认这些历史常量对本用途有效**。[authorization_budget.py L22-L44、L92-L106、L183-L199](https://github.com/JTCAO515/G2C/blob/449a04fb98cd9f14b3dc9e4561a66b19324561d0/backend/usage/cj_usage/authorization_budget.py#L22) |
| 原动作恢复 | 重复原attempt被拒绝为只读；发送前写 durable INTENT，未知不自动重试、不换attempt或地域；供应商receipt身份不能复用。模型receipt中的 `actual_cost_cny` 仍为 `UNKNOWN`。[provider.py L509-L514、L691-L701](https://github.com/JTCAO515/G2C/blob/449a04fb98cd9f14b3dc9e4561a66b19324561d0/backend/agent/cj_agent/provider.py#L509)、[authorization_budget.py L183-L209](https://github.com/JTCAO515/G2C/blob/449a04fb98cd9f14b3dc9e4561a66b19324561d0/backend/usage/cj_usage/authorization_budget.py#L183) |

## 样本、请求与金额建议

| 项目 | 首批 | 同次批准内的累计最大值（包含首批） |
| --- | ---: | ---: |
| 完整 `trip_family` | 10 | 25 |
| zh/en轨迹 | 20 | 50 |
| 模型请求总数 | 160 | 400 |
| 每轨迹模型请求 | 最多8 | 最多8 |
| 模型子限额 | ¥3 | ¥10 |
| 工具子限额 | ¥2 | ¥5 |
| 合计上限 | **¥5** | **¥15** |

初批必须先经 D 对全部20条轨迹独立检查；达到事先约定的质量与安全标准后，才可在**同一份明确批准**内扩大到累计25家族/50轨迹。未完成、拒绝和UNKNOWN请求也消耗已发生的请求数，不补跑、不用新attempt替换。模型总8次须包含前序澄清、所有工具轮后的模型请求，以及本用途必要的其他模型步骤；不得把每RUN8轮相加后仍称每轨迹8次。

建议工具也按**每轨迹总计最多8次外部请求**计数，包含跨澄清消息的调用与任何实际网络扇出，作为工具费用估算的明确假设；当前B只有每RUN8工具上限，尚不能证明这个轨迹总限已实现。原有各类配额、并发、有效期、身份/owner与其他业务门禁继续取更严格者，不扩大配额、不另建预算账户绕过原账本。

## 算式与工具费用

按每模型请求输入8000 tokens、输出1536 tokens、非缓存原价估算：

```text
单次 = (8000 × 0.8 + 1536 × 2.7) / 1,000,000
     = ¥0.0105472
首批 = 160 × 0.0105472 = ¥1.687552
累计 = 400 × 0.0105472 = ¥4.21888
```

算式已用 Decimal 独立复核。它是规划估算，输入8000不是硬限，输出1536是保守采用现有请求参数上界；长历史、schema和工具返回会改变实际输入。初批模型¥3、累计模型¥10提供余量，但**不保证样本一定能在此预算内完整生成**。未完整输出或质量不足仍记失败/未知，不因预算剩余自动重跑。[官方模型价](https://help.aliyun.com/zh/model-studio/qwen3-8-flash)、[实际请求配置](https://github.com/JTCAO515/G2C/blob/449a04fb98cd9f14b3dc9e4561a66b19324561d0/backend/agent/cj_agent/provider.py#L495)。

高德公开原价可核：基础搜索、天气为¥30/万次，基础LBS第一档同为¥30/万次，即**¥0.003/次**；B账本 `AMAP_PRICE=30000`、比例 `CNY_SCALE=10000000` 与此相符。若每轨迹总计8次都按该价收费，首批160次约¥0.48，累计400次约¥1.20。**账号实际套餐、授权范围、月配额、折扣、余额和最终结算均为UNKNOWN**，不将免费额度视为授权，不将公开价视为实际账单。[高德官方计费说明](https://lbs.amap.com/pages/base_service_price)、[B定价常量与endpoint白名单](https://github.com/JTCAO515/G2C/blob/449a04fb98cd9f14b3dc9e4561a66b19324561d0/backend/usage/cj_usage/authorization_budget.py#L30)。

当前工具适配器为高德PLACE/route/weather及固定公共页面fact；fact适配器写入费用0，但本核查不把它扩大为任意检索/外部服务零费用保证。**未核实或新增工具的实际单价一律UNKNOWN，不进入真实执行**。[real_services.py L354-L399](https://github.com/JTCAO515/G2C/blob/449a04fb98cd9f14b3dc9e4561a66b19324561d0/backend/cj_api/real_services.py#L354)。Function Calling支持不等于工具本身免费；若以后提出模型内置联网搜索，它另计费且检索内容增加输入tokens，属于本建议外的新用途。[阿里云联网搜索计费](https://help.aliyun.com/zh/model-studio/web-search)。

## 真实运行前必须补齐

1. #762可信导出与本用途训练数据准入；JT对#495新用途、上述分阶段数量/费用/有效期/执行身份的明确批准。旧预算不自动转授权。
2. B在**原账本与原attempt语义内**证明F任务的首批/累计请求总限、跨消息每轨迹总限，以及模型/工具子限额可在dispatch前原子拒绝。当前源码只见原全局额度，未见上述F子限额的实现；普通RUN8轮不能替代它。
3. 子限额准入须计算**已定价估算＋未决hold＋本次完整hold**，不得仅算已完成费用。沿用当前每个模型/收费工具attempt的¥1 hold与UNKNOWN恢复，不降低hold以让小预算通过；顺序运行可减少在途hold，但不能释放未知hold。
4. 读回原账本剩余的金额和各类次数，并取更低者：初批不超过¥5（模型¥3/工具¥2），累计不超过¥15（模型¥10/工具¥5，包含首批）。剩余额度不可读或无法安全对账时停止；账本公开价估算与供应商财务实际支出分开报告。
5. 逐工具确认现有适配器、计费归类与实际请求数；未核单价/未知网络扇出不得按0估计。遇UNKNOWN先保留原attempt并对账，停止后续生成，不自动补样本。

**简明建议：保留20/50轨迹、160/400模型请求和¥5/¥15分阶段上限；它们足以作为小批质量试验的待批准预算。先补原账本子限额与原attempt恢复证据，再运行。总额包含初批，取原剩余额度更低者；不接Batch新API，不依赖缓存、免费额度或折扣。**
