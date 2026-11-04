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
不取代产品 Meter。按已合PR540的M4授权，北京每 intent 保守占用 ¥1、保留 M1 的 ¥13，
累计387个M4模型intent（合计¥400）后停止；地点/路线/天气每 intent保守占用¥1，合计¥160后停止。
各分类同时保持M4的1200/600/200/240次数上限，事实页保守占用0，2026-11-30到期；UNKNOWN不释放占用。
提高额度只改变未来新intent门禁；原SQLite路径、全部历史intent/receipt和既有验收批次保持原样，不迁移或清零。
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
同时保留工具调用响应中合法的说明文字；它只随原assistant消息续接，不作为最终回答或工具权限。
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

`verify-diagnostics` 是固定D1合成地点样例，白名单为place_search/place_route，仅请求一次天安门基础查询；
RUN总计最多4个provider_call、最多1次工具调用，仍使用原共享账本，原批次存在即只读。
它用来区分传输、响应身份、工具解码和完整回执阶段的失败；不代表C的路线冒烟或66例质量已通过。
模型失败诊断只记录原attempt的SHA256、固定阶段、HTTP状态、完成标记和数量；
不记录异常文本、请求/响应正文、供应商原ID或密钥。HTTP拒绝仍保持INTENT与费用UNKNOWN，绝不自动重试。

M4基础live步行解析仅在 `basic=True`、RouteQuery/walking、status=1及infocode=10000时接受供应商实际的 `info="ok"`；
默认旧profile、POI和driving仍保持原大小写规则，所有坐标绑定、数量/时效、密钥与JSON检查不变。
同一RUN中已派发的完全相同canonical工具查询不再次注册/调用供应商；模型重复调用会明确失败，费用/原回执不改写。

`verify-route` 为固定R1诊断：北海公园/恭王府各一次基础Search，再仅用本次两条真实回执的POI ID/GCJ-02原坐标/poi_center调用walking一次。
原RUN/Meter与共享账本保持，最多10 provider_call/3tools；错点、错顺序、重复、driving或其他查询在原HTTP前拒绝。
secret-body检查后的原HTTP200公共地图响应留在固定批次私有目录，文件0600；存储失败单独使诊断失败，原收到响应继续解析/计量。
旧批次重跑只读；历史原RUN的FAIL/UNKNOWN不被离线重解析结果覆盖，实际新端到端结果仍需C的新阶段验证。

八轮native上限内，第八个原model.tool_turn.7保留为终答：显式设置供应商`tool_choice=none`，仍保留完整原assistant/tool消息及工具声明。
不增加第九次模型请求、不扩大RUN预算。供应商违背禁用策略返回工具调用时，在回执发布与工具注册前拒绝；原模型费用保持UNKNOWN，不自动重试。
前七轮与非native入口的默认请求字节不变，未修改MODEL-tool-turn.1或PLACE冻结wire。
依据：[DashScope Function Calling](https://help.aliyun.com/en/model-studio/qwen-function-calling)及[兼容接口参数](https://help.aliyun.com/en/model-studio/qwen-api-via-openai-chat-completions)。

`capture-route-geometry` 为固定G1取证：故宫/景山公园各一次Search，绑定本次真实POI回执后，以故宫到景山的同原坐标/poi_center只查一次walking。
它使用新固定batch/scope、原共享账本及相同10 provider_call/3tools上限，复用原secret-checked响应留存；重跑仅只读。
退出成功仅表示三份原HTTP响应已留存并匹配固定查询，不计路线几何或产品质量PASS；`geometry_acceptance=UNASSESSED`。
原C两语言119米投影和英文八轮UNKNOWN保留，不把新取证冒充旧请求的原body或重派旧RUN。
[高德原生参数](https://lbs.amap.com/api/webservice/guide/api/direction)允许坐标外同时提供可选POI ID；端点实际语义须依据原响应核查，不凭两个echo坐标假定入口。

`capture-route-coordinate` 是独立C1对照：同一固定两地点，但显式选择坐标路线profile，原POI ID仍绑定在原query/注册输入中；HTTP仅送原始坐标，不送可选POI覆盖参数。
该profile的prepare、transport复核和parser必须同时选择`coordinate_only=True`；交叉混用在拨号前或解析前拒绝。
旧profile与G1/R1仍保留原参数/绑定，不覆盖旧batch。C1沿用10/3上限、secret检查和只读恢复，只作原响应取证，几何仍UNASSESSED，不是新wire。
M4真实入口默认使用坐标路线profile；生产HTTP不送POI覆盖参数，POI ID仍保留作来源关联。
新profile核steps首尾与原坐标各相距最多25米，并拒绝低于保守两点跨度的距离；缺少path点则UNKNOWN、明显错点或不可能短距离则binding_mismatch，不输出原估计。
25米是本profile的近邻匹配门限，跨度检查另留1%球面/坐标差异及两端门限余量；均不是供应商精度、入口、道路通行或未来可用保证，不修改供应商数值/原坐标或推断出入口。
默认旧adapter解析、冻结PLACE/Geo数据codec、legacy显式`coordinate_routes=False`取证路径不变。退出判定分别核G1/C1 profile，C1逐笔核唯一walking原参数不含POI覆盖。
