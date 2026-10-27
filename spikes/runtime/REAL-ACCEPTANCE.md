# Issue #2 最短真实验收入口（2026-10-23）

**当前：真实 provider UNRUN，入口准备完成。** 原 17 个本地场景、3 个离线 SDK 探针及原独立门全部复用，没有重跑。新增入口测试仅验证本次新增代码，不替代真实验收。

## 最新北京目标（覆盖下方早期资源待定说明）

JT 经 Main 已明确提供非秘密目标：workspace `ws-obkc0qqp3gynaeiu`，region `cn-beijing`，兼容 base `https://ws-obkc0qqp3gynaeiu.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`，DashScope base `https://ws-obkc0qqp3gynaeiu.cn-beijing.maas.aliyuncs.com/api/v1`。这些是人类给定的目标，不是本轮访问控制台或请求 provider 的结果。已接入现有 `provider-approval.example.json`，不再等待地域/工作空间/端点决定；原新加坡建议已被覆盖。

JT 后续已确认模型名 `qwen3.8-flash`，现填入配置 `model_id` 并用于兼容请求 JSON 的 `model` 字段；同消息中的误发数字经 JT 明确更正为“无用”，已忽略，不写入配置、认证头或其他请求字段。官方[文本生成模型表](https://help.aliyun.com/zh/model-studio/text-generation-model)把 `qwen3.8-flash` 列为模型 ID，[兼容接口参数说明](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope)要求 `model` 使用所选模型名称。公开 ID 与本次人类选择一致，仍不证明该工作空间的真实鉴权或返回结果已验收。

当前仍缺新 key 的安全临时注入，无本次安全配置授权，不读取旧 key、不配置秘密、不发真实请求；原 DEFERRED / 双门限制保持。`expires_at` 为 owner 在实际获准执行前填写的短期本地执行窗口，不是额外预算审批。模型增量离线证据见 `evidence/beijing-model-profile-20261023.json`。

现有 runner 只消费兼容 base 并构造 `/chat/completions`；DashScope base 在此保留为给定事实，未新增第二协议路径、框架或字段。离线请求形状/预检证据见 `evidence/beijing-profile-20261023.json`；未构造真实 transport、未建 DB、未读取秘密、未触网。真实验收继续禁止，待 model/key 与原独立门齐全后由 Main 路由。

## 最新授权与已核事实

- 本次续作来自唯一 Main `01a15e24-928b-7540-97a4-14b52e6ee995`，仍仅 `spikes/runtime/**`。固定续作 base 是原已交付 `edb72fffbf87614dd0dafba3570725be004d1ccb`。
- JT 最新明确：“测试费用不设上限，由百炼余额控制”。该授权已接受，**不再缺测试预算批准**；限本项目百炼测试，不授权新账户/资源费、持续访问、环境或权限变更。
- 本机主线只读快照 `02f672605ad5521f9360e42be8f43ebfd022a0e8` 的 ADR-0002 仍首选 AgentScope + Qwen3.8-Flash + DBOS；`spikes/runtime` 最近提交仍为原 `edb72ff`。没有发现已接受的新框架路线，未新增框架或依赖。
- 已安装与原锁一致：AgentScope 2.0.10、DBOS 3.3.0、OpenAI SDK 3.35.1、httpx 0.28.1、Pydantic 2.14.1，Python 3.12.14。
- 当前进程只做配置**存在性**检查；`CJ_MODEL_ID`、`CJ_MODEL_API_BASE_URL`、`CJ_MODEL_REGION`、`CJ_MODEL_WORKSPACE_ID`、`CJ_MODEL_API_KEY`、`DASHSCOPE_API_KEY` 及新入口专用 `CJ002_NEW_MODEL_API_KEY` 均未注入。没有读取环境秘密值、Keychain、dotenv、旧账号或旧数据。
- 新入口实际工作空间、地域和端点均 **UNKNOWN / 未配置**；原先公开资料确认的请求候选 ID 为 `qwen3.8-flash`，本账号实际接受/返回 ID 仍 UNRUN。配置模板里的 Singapore 是技术建议，不是已创建/已获准资源。
- 仓库现名为 [JTCAO515/G2C](https://github.com/JTCAO515/G2C/issues/2)，本树 origin 仍是旧重定向 URL，本轮没有改 remote。原 Issue #2 明确无整票 H/I 前置，不等 App/Auth/DB。
- 本轮 requested model：Main 官方派发 `gpt-6.1-sol / medium`；effective UNKNOWN。此前统一 Astra 的要求已由最新职责模型规则覆盖。

## JT 只需完成的资源与安全交接

1. JT 已确定本页最新北京 workspace 和端点，已写入模板，不需再次选择地域、交 endpoint 或创建资源。
2. 模型 ID 现已由 JT 确认为 `qwen3.8-flash` 并填入，不需重复交模型信息。真实可用性在获准调用后按实际响应确认。
3. 通过官方 API Key 页面准备仅用于本次 CJ 测试的新 key，按官方支持的自定义模型 scope 仅授本候选所需范围。**不在聊天粘贴 key**，不需要 Keychain 权限，不复用旧 key。由 JT 在自己控制的运行终端隐藏输入，或经另行允许的安全运行器临时注入 `CJ002_NEW_MODEL_API_KEY`。终端隐藏输入示例（只影响该 shell，运行后 unset）：

   ```sh
   read -rs 'CJ002_NEW_MODEL_API_KEY?New CJ Bailian key (hidden): '
   export CJ002_NEW_MODEL_API_KEY
   # 完成本页命令后：
   unset CJ002_NEW_MODEL_API_KEY
   ```

   自动化 owner 当前没有持续修改用户环境的授权；由 JT 亲自注入或授权具体安全运行器，不能据此把 key 写进配置文件。

官方依据：[API Key 获取与区域绑定](https://www.alibabacloud.com/help/en/model-studio/get-api-key)、[兼容接口与 workspace endpoint](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope)、[候选模型](https://www.alibabacloud.com/help/en/model-studio/qwen3-8-flash)。登录/控制台是安全交接入口，不是要求 JT 将密码或 token 发给聊天。

## owner 可自行完成的配置与执行

当具体安全临时注入获准且 key 可用后，由原 owner 把已填北京目标和模型的 `provider-approval.example.json` 复制为本目录忽略的 `provider-approval.private.json`，设置短期验收执行窗口 `expires_at`。授权引用、余额控制策略、最大 6 次请求/每次最多 256 输出 token 已固定，不需 JT 再决定技术参数或批准测试金额。真实配置与新 key 没有齐全前只运行 preflight。

```sh
cd <local>/Documents/Codex/2026-10-21/cj-002-runtime/spikes/runtime
.venv/bin/python -B provider_acceptance.py preflight --config provider-approval.private.json
.venv/bin/python -B provider_acceptance.py run --config provider-approval.private.json --case zh
.venv/bin/python -B provider_acceptance.py run --config provider-approval.private.json --case en
.venv/bin/python -B provider_acceptance.py run --config provider-approval.private.json --case timeout
.venv/bin/python -B provider_acceptance.py run --config provider-approval.private.json --case cancel
.venv/bin/python -B provider_acceptance.py inspect
```

每条 run 分别人工/owner明确执行，不是自动连续请求。任一异常/UNKNOWN 先 inspect 原 attempt 与 provider 原请求证据，不重发该 case、不换 workflow ID；不同既定 case 也须先核上一步状态。没有常驻服务、HTTP listener、自动重试、环境文件加载或代理回退。入口仅在自身短进程内按变量名剔除旧 SDK/DBOS/OTEL 路由环境，不读取其值、不改用户 shell 配置。`inspect` 不需要 key 或未过期配置，只读原数据库。

## 实际验证内容与可证边界

- zh/en：真实模型先选择 `cj002_echo` 并提供整数 7；DBOS 独立工具步骤执行本地确定性函数；真实模型第二次流式输出 JSON `{"value":7}`，严格检验字段/类型/值。工具不连接旅行来源、不伪造天气/地点、不写正式业务状态。
- timeout：单独一请求，客户端 deadline 为 1ms。若在接收前超时，仅可证明客户端超时处理，不宣称 provider 已计费或已执行；保守保留 UNKNOWN。
- cancel：收到真实非最终 stream chunk 后关闭在途调用，不发工具/后续模型调用；费用仍 UNKNOWN。若请求完整完成而未触发取消，记录未达到预期中断，不能报取消 PASS。
- 请求次数最多 6：中英各 2、timeout/cancel 各 1；消息 JSON 最多 4096 bytes、响应最多 1MiB、关闭 thinking，wire 使用 `max_tokens=256`。这些是单次验收的技术限制，**没有声称金额上限**，百炼实际扣费与余额由 provider 管理。
- 真实 HTTP 出口在发送前事务保存精确出站字节 hash 与 attempt；同 attempt 一旦存在即拒绝再次发送。每次独立 DBOS step 保存完成返回，重建进程读回已有 step；若 intent 存在而 step 未完成，恢复保持 UNKNOWN。原完成响应无法恢复的窗口不靠重发补齐。
- 完整结果记录请求 model ID、真实流中 provider 回报的 model ID 列表、response ID、chunk 数与 provider usage；实际金额没有计费对账则保持 UNKNOWN。不存在 synthetic/real 切换 flag，旧 runtime.py 仍是独立 synthetic 脚本。
- 本入口是固定两步验收循环，使用安装的 AgentScope model/formatter、DBOS 持久步骤和模型真实选择的工具；不是生产 Agent/RUN/USAGE 集成。原完整 Agent 事件循环的本地证据继续复用。

准备完成不代表原票关闭。最终还需原 Review/Testing 核真实中英响应、工具与结构、实际 timeout/cancel 观察，和原重启/未知边界证据一起判断全部原 AC。原 Issue 不要求 PostgreSQL 或完整产品作为前置，本页不新增该门槛；也不把本地恢复证据夸为真实 provider 重启/费用验收。

本次新增入口的 7 组离线检查见 `evidence/provider-entry-tests.json`；真实 readiness/源码 hash/旧文件保全见 `evidence/provider-readiness-20261023.json`。原包与 17+3 证据未改、未重跑。
