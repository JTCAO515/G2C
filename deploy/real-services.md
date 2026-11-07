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
不取代产品 Meter。按 [JT 2026-11-06 决定](https://github.com/JTCAO515/G2C/issues/495#issuecomment-6688002330)，
模型总上限与停止线均为 ¥10,000，北京每 intent 保守占用 ¥1、保留 M1 的 ¥13，
累计9,987个M4模型intent（含M1合计¥10,000）后停止，不释放任何旧UNKNOWN/INTENT。
原387停线只作为显式历史测试保留。地点/路线/天气每 intent保守占用¥1。
JT于2026-11-05在C会话把工具停止线改为¥10000（[#495记录](https://github.com/JTCAO515/G2C/issues/495#issuecomment-6644812116)），
原工具总预算¥200未提高，实际出口按停止线与总预算的较小值拒绝新付费意图，因此当前最多保守占用¥200。
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

固定NIA页的live profile显式接受identity或单成员gzip；通用FACT传输的默认配置继续拒绝压缩。
压缩后的HTTP读取仍受原body/wire/chunk/deadline上限约束，解压后另限262144字节；CRC错误、
截断、额外成员或尾随字节均UNKNOWN，关闭原响应，不重试。`original_bytes`/`original_sha256`
仍指用于提取原文的完整UTF-8实体字节（有界Content-Encoding解码后）；传输编码元数据与
实际压缩字节摘要应在真实调用证据中另列，不把压缩传输数据当UTF-8原文。该修复不变更
冻结的合成FACT wire，也不增加来源/URL/适用性权限。

事实页失败日志 `M4_FACT_PAGE_UNKNOWN` 仅记录 DNS/HTTPS/状态/正文读取/UTF-8/片段提取阶段、
白名单原因码、已取得的HTTP状态（未取得为UNKNOWN）和已观察正文的字节数；不记录正文、
响应头、地址、异常文本或凭据。该诊断不增加抓取、不改变成功结果或失败分类，不补造回执，
不释放原INTENT；历史未保留的HTTP状态与失败阶段仍UNKNOWN。取消继续向外传播。

模型原生 function calls 转为既有内部 MODEL-tool-turn.1 数据，再由代码注册表选择工具。
网页/工具输出以不可信数据传给模型，不能提供 owner、密钥、预算或写入权限。
原生参数现在用完整类型定义的 place_search/place_detail/place_route/weather/fact，
host 转为原 PLACE-query.1 / FACT-query.1 再经已有严格 codec。模型不必猜封装版本或坐标Decimal字段。
续接保留实际 `assistant.tool_calls` 和逐一匹配的 `role=tool/tool_call_id`，
同时保留工具调用响应中合法的说明文字；它只随原assistant消息续接，不作为最终回答或工具权限。
正式M4使用 `model-tool-turn-function.1`，将原 `MODEL-tool-turn.1` envelope作为唯一
`m4_tool_turn` 命名函数的参数传输。依据[官方强制函数说明](https://help.aliyun.com/en/model-studio/qwen-function-calling)，
非思考模式显式选择该函数；不使用Qwen不保证支持的required策略。原input bytes绑定新profile。
wrapper仅是本次模型输出，收费仍为一次原model调用；内层每条真实查询仍逐一通过原tool.round.index、RequestRef、Registry和Meter。
供应商唯一真实wrapper ID对应一条按原顺序含index/name/result的聚合tool回复，不生成供应商子ID，不重放已完成的内层调用。
已观测北京命名函数流使用自然结束`stop`；与`tool_calls`一样，仅表示待核的结束候选。
函数参数schema必须与冻结parser的互斥分支一致：tool为answer=null且1–4个调用；answer为
非空白zh/en且calls=[]。非final使用交叉约束，不能把独立nullable字段的任意组合宣称合法；
最终消费仍只取原parse_turn及原4查询/末轮限制，schema声明本身不证明模型遵循或真实通路通过。
该命名函数显式设置 `function.strict=true`，沿用[官方 Chat Completions 工具定义示例](https://help.aliyun.com/zh/model-studio/context-cache)
的参数约束开关；工具轮和终答轮都携带。函数名、schema、冻结parser和原Meter不变，
不把无效返回修成有效包、不重派原UNKNOWN。真实英文天气曾在工具回执后出现
`native_envelope_fields`；原具体缺失/额外字段仍UNKNOWN，补开关本身也不代称真实修复已通过，见#523。
英文天气08真实通过后，C 的英文地点＋路线首轮仍出现同类字段拒绝（未到工具），原具体字段仍UNKNOWN。
命名函数的系统指令明确要求四个顶层字段全部出现、版本字面量、null/空数组与终答限制；
这是生成端约束，不补造供应商字段、不放宽解析器。真实效果须经独立新场景验证，不能据提示或strict声明判定。
命名函数参数失败的固定reason另分`native_json_invalid/duplicate`、`native_envelope_type/fields`、
`native_version_literal`、`native_answer_fields/calls/text`、`native_kind_literal`、
`native_tool_answer`、`native_calls_type/bound`、`native_call_fields/name/arguments`和
`native_contract_bound/invalid`；不记录值、字段名、异常文本或参数片段。原INTENT保持，旧日志
没有的拒绝字段与token数仍UNKNOWN，不能用较新的分类倒填原请求。
字段形状错误另记录 `M4_NATIVE_ENVELOPE_SHAPE`：同attempt SHA，present_mask的1/2/4/8位
表示version/kind/answer/calls是否存在，extra_count只记额外字段数量；不记录未知键名、值或原参数。
原 `M4_MODEL_UNKNOWN` 格式保持，旧失败证据不会补出此位图。
必须同时收到DONE、完整usage、同一模型/响应身份，以及唯一合法wrapper和原envelope后，才结算或执行内层工具；
缺件、截断、length、过滤和未知结束原因仍拒绝，不把停止标记本身当成功或重试依据。
末轮限制kind=answer，在提交回执前拒绝外部工具；上限仍八个模型回合、每回合最多四查询和原RUN工具总限额，不增加第九次或修复调用。
旧 `bilingual-json-schema.1` 已在真实工具流中未获有效JSON，其FAIL/INTENT保留；只为既有直接invoke消费者保留显式兼容路径，
待这些调用方完成迁移后再移除。正式RealTools始终选新profile，没有运行时自动fallback。
非native的既有结构化调用继续原JSON Object模式；1024输出token与原Meter限额不变，无效/缺字段/截断仍UNKNOWN。
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
另记固定拒绝原因、归一化finish枚举和拒绝前已累计arguments字符数，区分最后解析阶段与后续wire/SSE读取失败。
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
