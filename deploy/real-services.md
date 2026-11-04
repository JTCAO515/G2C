# M4 合成数据真实服务 profile

`scripts/run_worker.py --real --tools-profile real-m4` 只在显式
`CJ_M4_SYNTHETIC_ONLY=1`、CJ-LOCAL-RUN@2、`m4-synthetic-*` 邀请主体和原保护配置下启用。
正式 MESSAGE/RUN/OperationStore/Meter 的原身份、唯一 attempt、计量限额、取消、撤权、
Memory fence、原动作只读恢复均继续生效。默认 local/Fake 路径及所有冻结 wire 不变。

密钥只从 `CJ_MODEL_API_KEY`、`CJ_AMAP_WEB_KEY` 环境变量或各自 `_FILE` 600 文件读取，
每项只能选一个。Mac operator 可在进程内从已授权 Keychain 取值；不在命令行、响应或日志打印。
北京固定 `qwen3.8-flash` / `https://dashscope.aliyuncs.com/compatible-mode/v1`，
无国际站、重试、HTTP 重定向或请求输入指定 URL。

原注册出口先持久 input bytes/attempt，再经原 Meter reserve/claim/最后 guard。
真实 adapter 补一份授权累计意图账本，固定在用户数据目录 `g2c/m4-real-services`，
不取代产品 Meter。北京每 intent 保守占用 ¥1、保留 M1 的 ¥13，占用达到 ¥240 后停止；
地点/路线/天气每 intent 保守占用 ¥1，合计达到 ¥80 后停止；免费公开事实页仍记最多120次。
各分类同时保持 M4 的600/300/100/120次数上限，2026-11-30 到期；UNKNOWN 不释放占用。
完整 receipt 的 `provider_call=1` 只证明完成一次调用，绝不表示人民币实付已知；实际账单 UNKNOWN。
更换数据库、RUN period、配置或版本不允许重置此账本。迁往测试主机前须停 Mac 出口并迁移账本，
不能把 Mac 与云主机各当一份新预算。既有验收 batch 再运行只读，不新建原动作或重发。

工具接入：

- place：复用原 Gaode prepare、窄 HTTPS transport 和 parser；固定 restapi.amap.com 的四条地点/路线路径。
  `PLACE-result.1` 已支持 live_provider，保留原查询时估计、GCJ-02、入口/中心、缺失字段和来源。
- weather：北京110000的高德 forecast，检查原区域和返回日期范围；不把预测或未返回日期说成保证。
- fact：固定国家移民管理局英文官方首页，公开 DNS 全部地址必须通过 public-address 检查，
  使用原数字 socket/SNI/证书绑定 HTTPS primitive，单次、无重定向、有限字节与时间。
  只提供原文片段和 hash/抓取时间；旅客资格、地域/日期适用性保持 UNKNOWN。
  Mac 的代理 Fake-IP 不能冒充公开目标 IP；如遇该边界，保留 UNKNOWN，待获准主机网络验证。

模型原生 function calls 转为既有内部 MODEL-tool-turn.1 数据，再由代码注册表选择工具。
网页/工具输出以不可信数据传给模型，不能提供 owner、密钥、预算或写入权限。
RUN 对外使用已有普通文本读回：来源链接与双语选定语言的回答。
不扩大冻结 synthetic TOOL-output.1 / FACT-output.1、FACT-result.1，现有资料卡模式仍仅 synthetic；
App 若后续需要真实专用资料卡，须先证明已合消费者缺陷，再独立追加所需版本。

验证：`scripts/test.py`、完整 `scripts/pg_suites.py`；新增 real_services 组使用真实私有PG与
原签名API/RUN/Meter，HTTP明确为离线 fixture。`scripts/real_services_acceptance.py run`
为单次固定中英合成批次，读 Keychain 并实际调用；`inspect` 只读原结果。
`resume-setup` 仅用于明确的准备阶段失败：原全部案例仍PLANNED、授权账本0意图且私有PG目录不存在，
三者同时证明没有已接收消息或外部请求时，才允许显式恢复准备。任何accepted/INTENT出口均不适用。
真实 PR 必须另列包版本、模型/端点、原 attempt、用量、费用与 UNKNOWN/FAIL，不以 fixture 充数。
