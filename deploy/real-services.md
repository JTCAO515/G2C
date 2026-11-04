# M4 合成数据真实服务 profile

`scripts/run_worker.py --real --tools-profile real-m4` 只在显式
`CJ_M4_SYNTHETIC_ONLY=1`、CJ-LOCAL-RUN@2、`m4-synthetic-*` 邀请主体和原保护配置下启用。
正式 MESSAGE/RUN/OperationStore/Meter 的原身份、唯一 attempt、计量限额、取消、撤权、
Memory fence、原动作只读恢复均继续生效。默认 local/Fake 路径及所有冻结 wire 不变。

密钥只从 `CJ_MODEL_API_KEY`、`CJ_AMAP_WEB_KEY` 环境变量或各自 `_FILE` 600 文件读取，
每项只能选一个。Mac operator 可在进程内从已授权 Keychain 取值；不在命令行、响应或日志打印。
北京固定 `qwen3.8-flash` / `https://dashscope.aliyuncs.com/compatible-mode/v1`，
无国际站、重试、HTTP 重定向或请求输入指定 URL。
线上模型请求使用固定端点的 asyncio/h11 窄 HTTP 流，DNS/TLS/写入/读取共用一个可中止的总时限，
按原始字节（含空行）与单行缓冲限制 SSE；HTTPX 只用于显式离线 fixture。
天气同样复用窄 wire reader，含 Web Key 的 URL 不经过 HTTPX request logger。

原注册出口先持久 input bytes/attempt，再经原 Meter reserve/claim/最后 guard。
真实 adapter 补一份授权累计意图账本，固定在用户数据目录 `g2c/m4-real-services`，
不取代产品 Meter。北京每 intent 保守占用 ¥1、保留 M1 的 ¥13，占用达到 ¥240 后停止；
地点/路线/天气每 intent 保守占用 ¥1，合计达到 ¥80 后停止；免费公开事实页仍记最多120次。
各分类同时保持 M4 的600/300/100/120次数上限，2026-11-30 到期；UNKNOWN 不释放占用。
完整 receipt 的 `provider_call=1` 只证明完成一次调用，绝不表示人民币实付已知；实际账单 UNKNOWN。
模型 receipt 身份只取供应商ID的hash，独立于token用量；授权账本跨attempt拒绝重用ID，第二次保持UNKNOWN。
更换数据库、RUN period、配置或版本不允许重置此账本。迁往测试主机前须停 Mac 出口并迁移账本，
不能把 Mac 与云主机各当一份新预算。既有验收 batch 再运行只读，不新建原动作或重发。

工具接入：

- place：复用原 Gaode prepare、窄 HTTPS transport 和 parser；固定 restapi.amap.com 的四条地点/路线路径。
  `PLACE-result.1` 已支持 live_provider，保留原查询时估计、GCJ-02、入口/中心、缺失字段和来源。
  真实profile显式使用基础v3：extensions=base、不传高级多语言langCode；默认中文，未取到入口/导航等字段保持missing/UNKNOWN。
  既有prepare/transport/parser默认仍保留旧all/langCode模式，其绑定不改变；实际基础请求以相同basic配置校验绑定。
  这是预先选择已授权基础资料，沿用同一Key/endpoint，不是收到拒绝后改路径自动重试；10012完成回执后立即停止该RUN新出口。
- weather：北京110000的高德 forecast，检查原区域和返回日期范围；不把预测或未返回日期说成保证。
- fact：固定国家移民管理局英文官方首页，公开 DNS 全部地址必须通过 public-address 检查，
  使用原数字 socket/SNI/证书绑定 HTTPS primitive，单次、无重定向、有限字节与时间。
  只提供原文片段和 hash/抓取时间；旅客资格、地域/日期适用性保持 UNKNOWN。
  Mac 的代理 Fake-IP 不能冒充公开目标 IP；如遇该边界，保留 UNKNOWN，待获准主机网络验证。

模型原生 function calls 转为既有内部 MODEL-tool-turn.1 数据，再由代码注册表选择工具。
网页/工具输出以不可信数据传给模型，不能提供 owner、密钥、预算或写入权限。
原生参数现在用完整类型定义的 place_search/place_detail/place_route/weather/fact，
host 转为原 PLACE-query.1 / FACT-query.1 再经已有严格 codec。模型不必猜封装版本或坐标Decimal字段。
续接保留实际 `assistant.tool_calls` 和逐一匹配的 `role=tool/tool_call_id`，
不会把已执行的结果改成新的 user 请求。该标识仅关联数据，执行仍逐步经过原Meter/final guard。
这是对已合PR524真实失败的实现修复，旧wire语义不变；协议依据
[DashScope Function Calling](https://help.aliyun.com/en/model-studio/qwen-function-calling)。
RUN 对外使用已有普通文本读回：来源链接与双语选定语言的回答。
不扩大冻结 synthetic TOOL-output.1 / FACT-output.1、FACT-result.1，现有资料卡模式仍仅 synthetic；
App 若后续需要真实专用资料卡，须先证明已合消费者缺陷，再独立追加所需版本。

验证：`scripts/test.py`、完整 `scripts/pg_suites.py`；新增 real_services 组使用真实私有PG与
原签名API/RUN/Meter，HTTP明确为离线 fixture。`scripts/real_services_acceptance.py run`
为单次固定中英合成批次，读 Keychain 并实际调用；`inspect` 只读原结果。
`resume-setup` 仅用于明确的准备阶段失败：原全部案例仍PLANNED、授权账本0意图且私有PG目录不存在，
三者同时证明没有已接收消息或外部请求时，才允许显式恢复准备。任何accepted/INTENT出口均不适用。
`verify-native` 是修复后独立的两例中英合成验证，使用新scope、原共享授权账本与固定新batch。
其重跑只读本批次；原八例UNKNOWN与全部费用意图仍保留，不覆盖或重派。
`verify-base-search` 只验证新的基础字段地点样例，使用独立固定batch；不会重新调用已完成的天气例。
真实 PR 必须另列包版本、模型/端点、原 attempt、用量、费用与 UNKNOWN/FAIL，不以 fixture 充数。
