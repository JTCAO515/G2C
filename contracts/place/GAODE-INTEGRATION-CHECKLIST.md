# 高德接入核对与首测资料清单

核对日期：2026-10-23（Asia/Shanghai）。源码固定
`5904e37f698ceb822c16e39ae36c87552235cabb`，branch `cj/012-place`，起始树 clean。
JT 已明确必须接入高德或百度；本轮沿既有高德实现推进，不并行重写百度。
后续元数据续作基于文档 head `2374b9de298828fdd568c5d3a92cd4da7cf20ace`：
JT 已经父线程/Main 确认现有地图 Key 已有；不创建、不要求重复提供，也未读取其内容。
存在性不等于 Web 服务平台、目标 application 绑定或实际权益已核实。
本文件是原 PLACE owner 的公开资料/源码核对，**不是独立 Review、真实接入回执或 dispatch 放行**。
旧受拦审验及 5525/3106/7432 对象完全 DEFERRED，本轮未读写、替代或解禁它们。

## 四条 API 与现代码的对应

业务 host 固定 `https://restapi.amap.com`，以下均为 GET。官方文档站
`developer.amap.com` / `lbs.amap.com` 不是业务 API host，不需要因此改传输白名单。
依据：[官方 POI 搜索/详情](https://developer.amap.com/api/webservice/guide/api-advanced/search)、
[官方路径规划](https://developer.amap.com/api/webservice/guide/api/direction/)。

| 能力 | exact path | 当前请求/解析对应 | 本轮结论 |
|---|---|---|---|
| search | `/v3/place/text` | 一个 keyword、显式 city；citylimit=true、children=0、extensions=all、langCode=zh、page/offset；解析 pois 的 ID、原中文、中心/入口等字段 | 文档形状对应；实际命中效果未测 |
| detail | `/v3/place/detail` | 一个原 provider ID 写入 id，langCode=zh；响应按 POI 格式解析，并拒绝另一 ID | 文档形状对应；实际高级权限未知 |
| walking | `/v3/direction/walking` | origin/destination 为原经纬度，origin_id/destination_id 带下划线；解析 route 的坐标、paths.distance/duration | 文档形状对应；真实路线未测 |
| driving | `/v3/direction/driving` | originid/destinationid 不带下划线；strategy=10、extensions=base；解析原 route 坐标及 paths | 文档形状对应；普通驾车估算，不宣称已验限行/车型条件 |

代码依据：[prepare/parse_response](../../backend/place/cj_place/gaode.py)、
[单一 PLACE 类型](../../backend/place/cj_place/models.py)、
[受限 HTTPS 候选](../../backend/place/cj_place/https_transport.py)。
输出为 JSON；原 source/query time、GCJ-02、ID/分店/入口角色、米/预计秒语义保留。
本次未发现可以据公开文档确定的新增兼容缺陷，因此**不新增产品源码或镜像测试**。
这不等于实际账户权限、全部响应类型或真实服务兼容已经通过；现解析是已明确的保守 v3 profile。
详情可选字段缺失保留 Observed 状态，不为取得入口字段猜测响应值或补造身份。

POI 官方默认中文；langCode=en 属多语言高级服务，文档要求通过工单联系商务。
详情无法获取时官方亦指向商务/高级权限申请。两者都应列为**目标应用实际权限待控制台核**，
不能据文档推断 JT 已有或没有权限，更不在本轮申请。当前 zh 原中文名/地址保留，
英文仅解释状态并引用同一 provider ID；不冒充高德官方英文名/地址。
依据：[POI 的语言、详情权限说明](https://developer.amap.com/api/webservice/guide/api-advanced/search)。

walking/driving 选定切片仅支持显式 at_query_time；指定过去/未来出发时间仍拒绝，
不会悄悄改为现在。路线数值是查询时估算，不保证未来交通。驾车当前未收车牌/车型等条件，
需要这些条件的真实结论必须保持待核。此处的实现子集范围不因文档存在其他可选参数而扩张。
依据：[路径规划与条件](https://developer.amap.com/api/webservice/guide/api/direction/)、
[现 PLACE 消费约定](README.md)。

## 本轮待补的非秘密资料

这些是文本元数据/授权范围，不是 key、token、账号密码或证照原件。未知项不填猜测值。
材料页如含 key/手机号等内容，应只摘录所需非秘密字段或完整遮盖，不转发整页秘密。

| 资料 | 当前已知 / 待提供内容 | 谁/哪里可确认 |
|---|---|---|
| 源 workspace | 已核路径 `/Users/jtsm5p/Documents/Codex/2026-10-21/cj-012-place`、branch/head 如上 | 本地 Git；这不是高德控制台 application |
| 目标服务环境 | 目标 workspace/项目/测试环境名、宿主/区域、原 owner；具体值 UNKNOWN | JT/Main 的已接受环境登记，不能临时造生产标签 |
| 高德 application | 已有地图 Key 的存在性已确认；目标高德应用真实名称、非秘密应用 ID/用途、绑定、所属环境及运营主体类别仍 UNKNOWN | 已脱敏记录或不展示秘密的目标应用元数据页；未定位安全入口，未登录/创建 |
| 开发者认证 | 实际未认证/个人认证/企业认证等类别、审核/有效状态；这里只需类别/状态 | 目标账号控制台；不收身份证/营业执照/认证密码 |
| Key 平台和安全模式 | 要求 Web 服务，实际平台尚未核；IP 白名单/数字签名模式及适用出口仍 UNKNOWN；只填模式/状态，不填 key/签名秘密 | 已有配置的非秘密资料，不能为核对而展示/复制 Key。现候选仅 key-only，若实际要求 sig，需原 owner 另做受审差额，不能关闭安全模式迁就代码 |
| 实际服务权限 | text、detail、walking、driving 分别是否获准；详情高级权限；英文权限是否有实际需要/已开通 | 目标应用控制台/已有官方回执，未读回则 UNKNOWN |
| 实际 quota/计费 | 每 API/服务组的 QPS、日/月限制（按实际界面适用项）、剩余量、共享池、有效期、超额行为、消费告警/费用上限和批准预算 | 目标应用控制台。当前全部 UNKNOWN，不复制通用表数字或以旧额度推算 |
| 首测城市 | JT 指定城市/区县及可核验 adcode、适用行程/日期范围 | JT 的范围选择；未定，不擅选城市 |
| 两个真实 POI | A/B 的真实中文名/地址、分店/入口选择和各自用户来源；正式 ID/GCJ-02 坐标只能来自后续获准查询/可核对原来源 | JT 的两个实际固定安排；当前 A/B 未给定，禁止用 synthetic 代替 |
| 时间条件 | 各安排唯一 item ID、真实当地日期/时区、开始/结束或时长、固定意图、从 A 离开到 B 到达的条件、mode、缓冲/休息及适用人 | 原 NEEDS 用户输入/纠正及版本；缺失/歧义显式保留，不从设备时区补造 |
| 实际调用范围 | 允许的目标应用/环境、四 API 中首测哪些、原 attempt/用量上限/期限、取消与未知结果核对责任 | 后续明确授权与已接受 AUTH/USAGE/RUN 接缝；本轮无真实调用授权 |

官方创建指引要求服务平台选择 **Web 服务**，此处是服务端 REST key；不能拿 Web端 JS API
或 iOS SDK 类别替代。此说明不授权创建新 key，未来地图 UI 的 SDK 身份也不自动加入当前范围。
依据：[创建应用和 Key](https://developer.amap.com/api/webservice/create-project-and-key)。

官方认证协议按实际主体/用途约束认证类别，不能把当前账户类别从项目名称推出来。
技术服务许可规则区分主体和使用目的；**App 首发免费不推出平台商用免费或无需许可**。
由实际运营方核对对应类别、许可与有效范围，本轮不替 JT 分类、申请、签约或付款。
依据：[认证协议](https://lbs.amap.com/pages/Account-authentication-protocol)、
[官方许可说明](https://lbs.amap.com/faq/advisory/authorization/43168)。

官方流量页把 QPS 指向控制台配额管理，公开价格/配额说明也有服务组和适用类别。
公开页面不能证明目标应用的实际权益；本清单不录任何通用配额/价格数字。
依据：[流量限制说明](https://developer.amap.com/api/webservice/guide/tools/flowlevel)、
[官方配额/计费入口](https://developer.amap.com/upgrade)。

## 秘密的官方安全交接单独处理

已有 Key 沿现有安全保管方式处理，不要求重新发送或另建。上表完成不代表需要把 key 发到聊天。
本轮不读取/输出/复制 Key，不调用 Keychain/环境秘密，不登录控制台、不创建资源。
后续若获准接入：由持有权限的人在官方控制台确认目标 application/平台/安全模式，
通过项目已批准的服务端秘密管理入口或官方凭据交接方式注入；若此入口尚未确定，
只记录“安全注入入口待定”，不临时使用聊天、仓库或明文文件替代。

唯一现有低层消费是 `ProviderCredentials(api_key, expires_at)` 的服务端逐次显式传入。
PreparedRequest、Source、普通结果/日志、App 和对外资料均不承载该秘密。
该类型不是已接受 dispatch context，也不提供新的调用权限；真实 `execute` 仍无条件
unavailable。若实际配置要求 sig/其他认证，不能通过随意追加参数或伪造 guard 绕过。
依据：[传输边界](HTTPS-TRANSPORT.md)、[当前关闭入口](../../backend/place/cj_place/gaode.py)。

## 五张 GitHub Issue 的真实最小链

下列 **# 为 GitHub Issue 号**，不是 CJ 序号；旧 Issue 正文的“开发未开始/收费待定”
属于规划历史，本轮执行授权/首发免费选择按 JT 当前指令，不据旧正文回退授权。

| GitHub / CJ | 最小交付与接入关系 |
|---|---|
| [#14 / CJ-013 NEEDS](https://github.com/JTCAO515/Go2China/issues/14) | 原需求入口接收 A/B 两个真实固定安排，用户可纠正；保留 source、item_id、当地日期/时区、固定意图及原 needs_id/version。消费现 Snapshot/Revision，不新增一套 PLACE 需求 wire；“用户说已订”不等于查证订单。 |
| [#13 / CJ-012 PLACE](https://github.com/JTCAO515/Go2China/issues/13) | 目标应用权限/安全交接/预算与受保护出口就绪后，实际 search→选中正确分店/入口→detail 核同 ID→walking/driving 查询。保留原查询、ID、GCJ-02、Source、m/s、状态和适用时间；中英引用同一地点。真实调用/无结果/限流/失败分别记，不用 loopback 当实际来源。 |
| [#18 / CJ-035 FEASIBILITY](https://github.com/JTCAO515/Go2China/issues/18) | 将 #14 原版本 A/B 与 #13 实际路线/来源组合，核时间窗、交通+缓冲、固定/未选中保护；区分可行、已证明冲突、证据不足、超时。无需正式 Trip、完整 AI 草稿或完整地图 UI；需要原 owner 的真实消费与解释证据。 |
| [#34 / CJ-031 商店/隐私](https://github.com/JTCAO515/Go2China/issues/34) | 以真正被接受的版本/环境制作中英素材与隐私说明，准确写城市/模式/时间边界、原中文地址与英文解释、来源归属/许可；不能展示未接通的官方英文/导航能力。地图材料可先准备，但真实截图、包与处理范围仍须核实际版本。 |
| [#35 / CJ-033 首发验收](https://github.com/JTCAO515/Go2China/issues/35) | 汇总当前候选的真实账号/隔离/用量/取消/恢复、#13/#14/#18 组合、中英实际设备/目标网络、费用和支持/删除/运行证据；按全部适用 v1/I 门槛作 GO/NO-GO。以上地图最小链不能单独关闭全票或授权发布。 |

特别避免编号混淆：#18 不是 CJ-018；#14 不是 CJ-014 草稿；#34 不是 CJ-034 FACT；
#35 不是 CJ-035 FEASIBILITY。

最小操作顺序是：先固定 A/B 用户原输入与版本 → 获准实际地点身份/路线 → 原 CJ035
核来源适用性并给出解释 → 将真实能力/处理范围交材料 owner → 当前候选整体验收。
现选定路线只支持 query-time estimate：若 A/B 为未来时间或依据已过期，必须保留不适用 /
待核，不能把当前预计耗时包装成未来精确证明；所谓冲突/可行须由原 CJ035 按其证据规则判定。
这不是本 owner 新建的路由、数据库动作、求解器规则或第二正式 API。
来源：[NEEDS 消费约定](../needs/README.md)、上述五个 Issue、[PLACE 语义](README.md)。
这里的 NEEDS 名称来自本固定源码快照；实际接线须固定原 NEEDS owner 最新被接受版本，
不能把旧候选文案当作新正式 wire 或绕过其受保护入口。

给 #34 的隐私资料至少要据实际调用确认：关键词/城市或 POI ID、起终点 GCJ-02 坐标、
mode/必要参数发送给高德；服务端请求还涉及其凭据和出口网络信息。当前请求结构没有
完整聊天、完整 NEEDS、账号 token/护照/订单号字段；实际 root 抽取/接线尚未运行，须验证
只发最小必要查询，不把这些资料经 keyword 绕送，也不把未来时间塞入无该能力的接口。
实际宿主区域、处理方/许可、日志、留存/清理/缓存与用户说明由对应 owner 核实；本文件不
填默认留存或凭域名推断处理地域。地图截图/商店素材只描述已验能力；无实际地图 UI 可先
做有来源地点/路线说明，不能合成截图冒充真实产品。此段是待核对的数据路径清单，非已完成
隐私披露/商店法律审查。来源：[实际请求参数](../../backend/place/cj_place/gaode.py)、
[#34](https://github.com/JTCAO515/Go2China/issues/34)。

## 本轮结果与未运行项

本轮完成：公开官方文档与源码对应检查、五票编号/最小链核对、非秘密资料与秘密注入分离。
路线无尾斜线入口首次超时；同一官方带尾斜线页面成功读回（页面更新日期 2026-02-02）；
POI 页更新日期 2026-07-15。未把旧优势页的配额示例或公开表当目标账户实值。

未改产品源码、测试或任何被拦对象，未新增代理/线程；只写当前 PLACE 契约目录。
未重跑已过 TLS、原敏感探针、解析器或旧域套件；既有证据按其原 head/范围保留。
本文件只做链接/编号/差额检查，不能称双审/CI/真实集成 PASS。
账号/目标 application/认证类别/实际权限 quota/城市/A/B 时间资料目前仍 UNKNOWN；
真实 provider 调用、密钥交接、数据库、付费、root 接线、真实设备、商店材料验收与发布均 UNRUN。
原 accepted dispatch-context/current AUTH/shared claim-cancel/trusted receipt 接缝和独立门禁仍须
由原 owner/Main 处理，本文件不定义签名、不放行 `execute`，也不恢复 DEFERRED Review 轮。

元数据续作的安全边界：在已知 `/Users/jtsm5p/Documents/Codex/2026-10-21` 做文件名定位，
并检查本仓库已知无秘密的工程说明/清单；命中为实现、fixture 和清单，未定位到明确的地图
目标 App 脱敏元数据记录。未读不相干的脱敏数据库记录或未知聊天，也未猜测/打开可能展示
秘密的 Key 列表页。因此停止在已有可见资料边界，不能填入“Web Service 已确认”、认证类别、
应用绑定、安全模式或权限/quota 数值。具体缺口是：已有脱敏记录的准确位置，或确定不展示
Key 的目标应用元数据页面定位及可见字段；只需这些非秘密资料，不需 Key 内容或密钥验证。
本次仅更正此清单，未读取新秘密、发业务请求、重跑旧测试/受拦轮或修改产品源码；存在性
已确认与权益 UNKNOWN 分开保留，不计新增源码编码。
