# 出站数据流登记表

- Issue：[#1743](https://github.com/JTCAO515/G2C/issues/1743)（W4-1，总票 [#1714](https://github.com/JTCAO515/G2C/issues/1714)）
- 依据代码：`origin/main` `27388ea7`（逐行核对）；已复查到 `81a47879`，之间的提交没有新增出站主机（新增的 `*.gov.cn` 链接只是入境规则数据里的来源引用，不是网络调用）。行号指 `27388ea7`。
- 方法：只读代码；没有运行任何调用外部服务的脚本。「未核实」表示只看代码无法确认，原因写在条目里。
- 用途：隐私政策（[#1746](https://github.com/JTCAO515/G2C/issues/1746)）、PIPIA（`docs/privacy/pipia-service-request.md`，[#1745](https://github.com/JTCAO515/G2C/issues/1745)）、App Store 隐私标签和同意界面（[#1747](https://github.com/JTCAO515/G2C/issues/1747)）的事实来源。
- 状态：本表记录**现状**，不是放行结论。现状里有超出 [#225 正式法律相关意见](https://github.com/JTCAO515/G2C/issues/225#issuecomment-6735366219)首轮边界的地方，见第 2 节，对外部测试者开放前须先处理。

## 0. 维护规则

1. 新接入供应商、新增发出字段、或改变精度和留存的 PR，**在同一个 PR 里更新本表**（总表一行 + 附录一节），并在 PR 描述写明「已更新出站数据流登记表」。
2. 本表与 `backend/storage-registry.json` 互相对照：凡是服务端会保存供应商请求或返回的地方（缓存、账本、证据目录、日志），都应在 storage-registry 登记；目前的缺口见第 3 节乙表第 10 行。
3. 新的数据流（例如真人服务请求、健康信息）先登记本表和 PIPIA，再对外部用户开放（ADR-0010 第 4 节）。

## 1. 总表

个人信息类别缩写：**原文**=用户输入原文（对话/搜索词/地标文字）；**媒体**=照片/语音；**GPS**=设备精确坐标；**POI**=供应商或内置地点坐标；**城市**=城市级；**日期**=出行/入住日期；**无**=不含个人信息。所有服务端调用均不带用户/设备/邮箱/手机号标识（App 直接打开的外链会暴露用户自己的 IP/浏览器信息，下表不重复写）。

| # | 供应商 | 方式 | 主机 | 触发 | 发出的个人信息类别 | 代码依据 |
|---|---|---|---|---|---|---|
| 1 | 阿里云百炼 DashScope | 服务端 API | `dashscope.aliyuncs.com`（北京） | Lio 对话/规划/记忆抽取 | 原文（对话）、行程内容、POI、日期 | `backend/agent/cj_agent/provider.py:325-345, 570-600`；`backend/cj_api/real_services.py:658` |
| 1a | 同上 | 服务端 API | 同上 + `dashscope-result-bj.oss-cn-beijing.aliyuncs.com`（TTS 结果下载） | 翻译插件（文字/语音/图片/TTS） | 原文、媒体（语音、照片，已去 EXIF） | `backend/cj_api/translation.py:30, 47-49, 304-421` |
| 1b | 同上 | 服务端 API | 同上 | 点餐（OCR + 解释） | 媒体（菜单照片）、OCR 文字 | `backend/cj_api/lio_menu.py:298-330` |
| 1c | 同上 | 服务端 API | 同上 | 路书 | 无（公开地点名/营业时间/地铁站） | `backend/cj_api/lio_roadbook.py:255-258, 343-380` |
| 1d | 同上 | 服务端 API | 同上 | 打车/附近/酒店/地铁周边英文名 | 无（供应商返回的 POI 名称地址） | `backend/cj_api/taxi_tools.py:301-345` |
| 2 | 高德 Web 服务 | 服务端 API | `restapi.amap.com` | Lio 管线、行政区、天气、路书、**附近**、酒店、地铁周边、城际火车 | **GPS**（附近：坐标转换/周边/逆地理）、原文（Lio 检索词、酒店地标）、POI、城市、日期（火车） | `backend/cj_api/nearby_tools.py:206-270`；`backend/place/cj_place/gaode*.py`；`lio_hotel_search.py:287-330`；`lio_transport_rail.py:34-50` |
| 3 | 滴滴 | 服务端 MCP | `mcp.didichuxing.com` | 打车搜索/预估/叫车链接 | **GPS**（起点、搜索偏置）、原文（搜索词）、POI | `backend/cj_api/didi_mcp.py:45-55`；`taxi_tools.py:252-415` |
| 3a | 滴滴 | 链接跳转（App 打开） | `v.didi.cn` → 滴滴 App；`apps.apple.com` | 叫车 | **GPS**（链接参数中的起点坐标）、POI | `taxi_tools.py:30-34, 230-249`；`LioTaxiEntry.swift:20-27` |
| 4 | 和风天气 QWeather | 服务端 API（需配置；App 未调用） | `<项目>.qweatherapi.com` | `/v1/tools/weather` | 城市或两位小数坐标（约 1 km） | `backend/cj_api/qweather_tools.py:31-45, 146-156` |
| 5 | 飞常准 VariFlight | 服务端 MCP | `c-gw.variflight.com` | 城际交通航班、`/v1/tools/flights` | 航班号/机场码、日期 | `backend/cj_api/variflight_tools.py:21, 31-57, 235-260` |
| 6 | 欧洲央行 ECB | 服务端 HTTPS GET | `www.ecb.europa.eu` | 汇率 | 无 | `backend/cj_api/currency_tools.py:20-45` |
| 7 | 国家移民管理局 | 服务端 HTTPS GET | `en.nia.gov.cn` | Lio 公告事实 | 无 | `backend/fact/cj_fact/live_source.py:26-28` |
| 8 | Supabase（新加坡，冻结） | 服务端 PostgreSQL | `aws-0-ap-southeast-1.pooler.supabase.com` | 取决于 `CJ_BETA_DB_TARGET`；运维冻结/演练脚本 | Supabase 目标下为**整库业务数据**；hk-local 下仅运维脚本 | `backend/cj_api/supabase_test_database.py:29`；`deploy/hk/configuration.py:135-139` |
| 9 | 阿里云 OSS 香港 | 服务端 SDK | `oss-cn-hongkong-internal.aliyuncs.com`，桶 `g2c-beta-backup` | 每日备份/恢复 | **整库导出**（全部用户数据），SSE-AES256，未见客户端加密 | `deploy/hk/oss_backup.py:12-75` |
| 10 | GitHub | 服务端只读 API；Actions runner 探测 | `api.github.com`；runner → `api-beta.go2china.space/health/*` | 发布门禁；可用性监测 | 无 | `deploy/hk/application_release.py:213`；`deploy/hk/readiness_monitor.py` |
| 11 | Let's Encrypt | Caddy ACME | `acme-v02.api.letsencrypt.org` | 证书 | 无（域名） | `deploy/hk/Caddyfile:10-11` |
| 12 | Docker / Debian 软件源 | 构建期下载 | `download.docker.com`、`deb.debian.org` | 主机准备/镜像构建 | 无 | `deploy/hk/host-prepare.sh:31, 41`；`deploy/Dockerfile:2` |
| 13 | 高德 iOS 地图 SDK | App SDK（仅 DEBUG + `G2C_AMAP_LOCAL`） | SDK 自定（未核实） | 行程地图「同意并加载高德地图」 | 可视区域、设备/网络信息（闭源，未核实）；不取定位 | `ios/Modules/CJShell/Sources/CJShell/AMapRecordedPlaceMap.swift:1-45` |
| 14 | Apple MapKit / Apple 地图 | 系统框架 + 链接跳转 | `maps.apple.com` 及系统地图服务 | 行程/路线/附近地图；导航 | 可视区域；POI 坐标（导航终点）；附近地图显示用户位置（系统本地，未核实是否上报） | `LioNearbyView.swift:157-165, 401-415`；`LioLocalSupportView.swift:340-358` |
| 15 | 高德地图 App | 深链 | `iosamap://path`、`iosamap://poi` | 附近/地铁导航 | POI 坐标或站名（不含当前位置） | `LioNearbyView.swift:404-407`；`LioMetroMap.swift:314-316` |
| 16 | Trip.com | 链接跳转（酒店经香港 302） | `www.trip.com` | 酒店、火车、机票、景点 | 城市、酒店名、**入住/离店日期、人数**、出行日期；无联盟 ID | `backend/cj_api/lio_hotel_search.py:144-195`；`deploy/hk/hotel_relay.py:109-126`；`lio_transport.py:376-389`；`LioAttractionBookingPartner.swift:41` |
| 17 | Klook | 链接跳转 | `www.klook.com` | 景点预约 | 无（内置景点英文名） | `LioAttractionBookingPartner.swift:42` |
| 18 | 12306 | 链接跳转 | `www.12306.cn` | 交通 | 无（首页链接） | `lio_transport.py:379`；`ios/.../LioTransport.swift:449` |
| 19 | 官方/政府/帮助类静态外链 | 链接跳转 | 故宫、上博、`english.beijing.gov.cn`、`s.nia.gov.cn`、财付通等 | 各信息页 | 无 | 第 19 节 |
| — | Airalo | 无 | — | eSIM 预览（无链接） | 无 | `LioESIMPreviewView.swift:64-70` |

## 2. 定位字段去向

### 2.1 现状（`27388ea7`）

- App 读设备定位的代码只有一处：`ios/Modules/CJShell/Sources/CJLioUser/LioTaxiPickupLocation.swift`（`requestWhenInUseAuthorization` + 一次性 `requestLocation`，WGS-84 原始精度，`:15-46`）。**打车**和**附近**两个功能复用它。
- **打车**：「当前位置」起点和搜索偏置 `near` → 香港 `/v1/tools/taxi/*` → 服务端转 GCJ-02、保留 6 位小数（约 0.1 米）、不降精度 → **滴滴 MCP**；滴滴返回的 `v.didi.cn` 叫车链接也带这组坐标，App 交给滴滴 App 打开。服务端不落盘、不写日志（`backend/cj_api/taxi_tools.py:252-261, 356-415`）。
- **附近**：设备坐标 → 香港 `/v1/tools/nearby/*` → **高德 Web**（坐标转换、周边搜索、逆地理），6 位小数；服务端进程内缓存 60 秒 / 32 条，**缓存键含精确坐标**（`backend/cj_api/nearby_tools.py:206-270`）。
- **没有**发现设备坐标进入百炼或任何模型、长期记忆、Trip.com、Klook、12306、飞常准、和风、ECB。
- 用户自己在对话、翻译、搜索框里输入的地址和地名，会作为原文发给百炼（对话、翻译）、滴滴（打车搜索词）、高德（酒店地标、Lio 检索词）。
- 两条 GPS 流都只对内部名单 G2C@01–99 开放（M4 授权条目 10、12）。
- App 侧声明不一致：`ios/App/Info.plist:61` 的定位用途说明只写了打车；`ios/App/PrivacyInfo.xcprivacy` 没有申报 Precise/Coarse Location。

### 2.2 与 #225 的关系和已定的边界

#225 正式意见写明首轮「将 GPS 或由 GPS 推出的可关联位置发给香港后端、北京百炼或高德，当前均未放行」。上面两条 GPS 流超出这一边界；对内部名单属于 M4 授权范围。对外部开放前**至少**须完成 [#1832](https://github.com/JTCAO515/G2C/issues/1832)、[#1833](https://github.com/JTCAO515/G2C/issues/1833)、[#1748](https://github.com/JTCAO515/G2C/issues/1748)；这三张票是必要条件，不是放行结论。

统筹 2026-11-26 按 JT 预授权决定的目标边界（由 #1833、#1748 落地，落地后本节改写为现状；三张票都落地前，下表写法与实际行为不一致）：

| 流向 | 目标边界 |
|---|---|
| 打车起点 → 滴滴 | 保留精确坐标，只用于该次请求；不写日志、不落盘、不进缓存键 |
| 附近 → 高德 | 发给高德前降到 3 位小数（约 100 米）；缓存键也用降精度后的坐标 |
| 两者 | 不进百炼，不进长期记忆，不和账号一起保存 |
| 同意与撤回（#1748） | 定位单独成页、需要时才弹出，不并进首次启动的总同意（总同意 #1747 只写「定位另行询问」）；撤回入口「我的 → 位置」或系统设置；同意记录按账号存在本机，其他账号读不到，退出登录时保留、注销账号时删除（统筹 2026-11-26 决定，取代此前「退出登录或注销时清除」的说法） |

目标边界落地后，与 #225 首轮边界**仍有差异**：

- 打车仍把设备精确坐标发到香港后端，再转给滴滴；#225 写的是香港后端首轮不收自动获取的 GPS 及其可关联衍生字段。
- 附近仍把由 GPS 推出的约 100 米坐标发给高德，并在香港进程内短暂缓存；#225 写的是高德即使取得书面许可也只接手选 POI、公开路线端点或城市，不带 GPS。
- #225 还要求：联网定位另开契约红线票，取得接收方书面条件，做出境评估和拒绝、撤回等负例验收；MapKit 的用户位置标记是否向 Apple 传送可推知位置的区域先核清；高德 Web 的外部使用另有书面许可门槛。

这些差异对外部测试者是否可以接受、要补哪些条件，见第 3.1 节第 6 项，交 JT 判断。

配套：#1832（A 线）把定位用途说明改为覆盖打车和附近，并在 `PrivacyInfo.xcprivacy` 申报精确位置；同意界面（#1747）把定位单列一项，写明会发给滴滴（打车）和高德（附近）。


## 3. 文档与代码的差异

对照对象：`docs/authorizations/M4.md`（条目 1–19）、`docs/architecture.md`、`backend/storage-registry.json`。表中「第 N 节」指本文附录的编号。

### 甲、文档提到但代码没调用（或只部分实现）

| # | 文档出处 | 文档说法 | 代码现状 | 依据 |
|---|---|---|---|---|
| 1 | M4 条目 8 | Wikidata 只读查询地点中英文名 | 无任何网络调用，只有来源类型标签 `wikidata` | `backend/trip/cj_trip/rich_source.py:31` |
| 2 | M4 条目 16 | Airalo 联盟/合作伙伴目录、服务端限额 | 无后端代码；App 只有无链接预览 | 第 21 节 |
| 3 | M4 条目 17 | Klook 联盟 + Data Feed/API，「玩乐」插件按城市只读展示 | 只有景点预约的公开搜索链接，无 API/Feed、无「玩乐」中转 | `LioAttractionBookingPartner.swift:36-49` |
| 4 | M4 条目 11 | 服务端生成**带联盟标识**的 Trip.com 链接；可能调联盟酒店接口 | 无联盟 ID、无 Trip.com API；仅公开链接（文档本身也写了「凭据交接前用不带联盟 ID 的链接」） | `lio_hotel_search.py:4-5, 144-159`；`lio_transport.py:376-389` |
| 5 | M4 条目 12 ② | 高德 iOS 地图 SDK 用于「附近」地图显示、进入内部 TestFlight | 「附近」地图用的是 **Apple MapKit**（`LioNearbyView.swift:2, 157-165`）；高德 SDK 只在 `DEBUG && G2C_AMAP_LOCAL` 真机编译的行程地图里 | `AMapRecordedPlaceMap.swift:1`；`TripPlaceMapView.swift:46` |
| 6 | M4 条目 9 | 图片原位翻译「含 qwen-mt-image 保留排版」 | 代码不用 `qwen-mt-image`；改为 `qwen-vl-ocr`（advanced_recognition 取文字框）+ `qwen-mt-flash` 逐行翻译，App 端自绘 | `translation.py:351-358, 512-520`；`translation_budget.py:20-23` |
| 7 | M4 条目 15 | 「天气」插件经香港只读查询 | 服务端路由与 QWeather 客户端已在（需配置才启用），但 **App 未调用**（天气页是静态预览） | 第 4 节 |
| 8 | M4 条目 14 | 「航班 / Flights」插件 | `/v1/tools/flights` 服务端存在，App 只经「交通」`/v1/tools/transport/search` 间接使用飞常准；无直接航班页调用 | 第 5 节 |
| 9 | architecture.md 流程图 | 身份服务候选 Supabase Auth | 后端用本方签发者 `https://local.g2c.invalid` + worker 签名密钥；JWKS 传输仅测试引用；App 打包 supabase-swift 但未配置 | 第 8 节 6–7 点 |
| 10 | architecture.md 流程图 | 持久执行候选 DBOS / AgentScope，记忆候选 ReMe | 后端/部署代码中无 `dbos`/`agentscope` 导入（只在 `scripts/provider_m4.py:216` 打印版本）；未发现 ReMe 导入（`git grep -w reme` 无命中）。均不涉及外部网络 | grep 结果 |
| 11 | storage-registry `external-processing` | `status: not_provisioned`，保留期 UNDECIDED、「activation blocked」 | 实际上百炼、高德、滴滴、飞常准、和风（可配）、ECB、OSS 均已在香港代码中启用调用 | 第 1–9 节 |
| 12 | M4 条目 3 | 「只用合成行程与合成查询，不发送真实用户内容」 | 代码开关 `CJ_M4_SYNTHETIC_ONLY=1` 只约束主体名必须形如 `m4-synthetic-*`；但 Demo 名单（`CJ_BETA_DEMO_SUBJECTS_JSON`）里的账号——`G2C@01–99`、`CJ_Tester@01–99` 两组短码和 `D1-` 长码——都被映射为 `m4-synthetic-demo-<后缀>`（`deploy/hk/demo_login.py:36-37, 69-77`），Lio 对话对整个 Demo 名单开放（`deploy/hk/configuration.py:350-358`），所以**Demo 名单 206 个账号（#1051）本人输入的对话原文会照常发给百炼，对话中提到的地名可能进入发给高德的检索词**；JT 2026-11-26 确认均为内部团队账号；不再使用的 `CJ_Tester@` 和 `D1-` 账号已由 S 线撤销登录资格（只撤登录、不删数据），撤销后可登录 104 个：`G2C@01–99` 共 99 个、`CJ_Tester@12`、4 个 `D1-` 长码；名单主体数仍为 206（S 线 2026-11-26 核对，[#1720 评论](https://github.com/JTCAO515/G2C/issues/1720#issuecomment-7182561865)）。「合成」是主体命名，不是内容保证 | `real_services.py:313-318, 351`；`demo_login.py:36-37, 69-77`；`configuration.py:350-358` |

### 乙、代码调用但文档没提（或未登记）

| # | 出站 / 存储 | 代码依据 | 文档缺口 |
|---|---|---|---|
| 1 | TTS 音频下载主机 `dashscope-result-bj.oss-cn-beijing.aliyuncs.com`（第二个北京主机） | `translation.py:30, 395-421` | M4 条目 9 只写「DashScope 北京端点」，未列该 OSS 结果主机 |
| 2 | 国家移民管理局 `en.nia.gov.cn` 固定公告页 | `cj_fact/live_source.py:26-28` | M4 条目 3 只泛称「公开权威事实页」，未点名站点 |
| 3 | 高德 `/v3/config/district` 行政区目录 | `lio_city.py:18-19` | M4 条目 3 列地点/路线/天气/公交/周边，未列行政区划接口（无用户数据） |
| 4 | 设备 GPS 精确坐标 → 滴滴 MCP（打车起点、搜索偏置 `near`） | `taxi_tools.py:252-261, 356-415`；`LioTaxiPickupLocation.swift` | M4 条目 10 列出了工具名，但未明说会发**设备实时坐标**；条目 12 只讲「附近」读定位 |
| 5 | Apple MapKit 地图 + 「附近」地图 `UserAnnotation` + 打开 Apple 地图（带 POI 坐标） | `LioNearbyView.swift:157-165, 401-415`；`LioLocalSupportView.swift:340-358` | M4 只把 Apple/MapKit 作为对照提及；Apple 作为数据接收方未登记 |
| 6 | 高德 App 深链 `iosamap://path`、`iosamap://poi`（POI 坐标/站名，`sourceApplication=Go2China`） | `LioNearbyView.swift:404-407`；`LioMetroMap.swift:314-316` | M4 未提 |
| 7 | 飞常准 MCP `initialize` 发送 `clientInfo={name:'Go2China'}` | `variflight_tools.py:240-242` | 未提（无个人信息，仅品牌名） |
| 8 | Let's Encrypt ACME、GitHub API（发布门禁）、GitHub Actions runner 探测健康检查、Docker/Debian 源 | 第 10 节 | 不在 M4（运维出站，无用户数据）；`MONITORING.md` 记录了 runner 探测 |
| 9 | 旧 Supabase：代码默认 `CJ_BETA_DB_TARGET='supabase'`，运维脚本仍有远程分支；变量名 `CJ_SUPABASE_*_URI` 在本机 PG 模式下也沿用 | `deploy/hk/configuration.py:135-139`；`local_postgres.py:80-92`；`checkpoint.py:66-73`；`cloud_rehearsal.py:299-304` | architecture.md 仍画 Supabase Auth；storage-registry 未登记「新加坡冻结副本」这一物理位置 |
| 10 | **storage-registry 未登记的服务端存储**：`m4-outflows.sqlite`（预算账本，哈希/元数据）；ToolEvidence 0700 目录（**完整模型请求体与工具输入/输出原文**）；`plugin_call` SQLite 与 `/plugin-state/{weather,flights}.sqlite`（计次）；翻译/菜单/路书账本；进程内缓存（菜单 5000、路书 5000、附近 60 s 含精确坐标、酒店、英译 4096、天气 120 s、航班 60 s、Trip.com 句柄 24 h）；访问日志 `access-YYYY-MM-DD.jsonl`；OSS 每日整库备份 | `tool_evidence.py:120-180`；`authorization_budget.py:182-190`；`plugin_tools.py:33-56`；`deploy/hk/access_log.py:1-15`；`oss_backup.py` | storage-registry 只有 business / checkpoints / memory-derived / device-cache / cleanup-control / external-processing 六类，以上均无对应 objects |
| 11 | App `PrivacyInfo.xcprivacy` 未申报位置数据；`NSLocationWhenInUseUsageDescription` 只提打车 | `ios/App/PrivacyInfo.xcprivacy`；`ios/App/Info.plist:61` | 「附近」也读定位且坐标上传香港再转高德 |
| 12 | 酒店服务端回包 `affiliate_links` 缺省按 `true` 显示推广披露，但代码无联盟 ID | `LioHotelOffers.swift:346, 423`；`lio_hotel_search.py:4-5` | 口径不一致（未核实服务端实际回填值） |
| 13 | 服务端生成的高德公开链接 `uri.amap.com/navigation`（路线起终点坐标）与 `uri.amap.com/marker`（单个地点坐标），随工具结果返回 | `backend/cj_api/real_services.py:1000-1011` | 未登记。坐标来自 POI 或行程地点，不是设备 GPS，但可能反映用户行程；主对话界面是否渲染成可点链接未核实 |

### 3.1 需要统筹 / JT 判断的事项

1. **「合成」只约束账号名，不约束内容**（甲表第 12 行）：Demo 名单里 `G2C@`、`CJ_Tester@` 两组短码和 `D1-` 长码账号都被映射为 `m4-synthetic-demo-*` 主体，他们自己输入的对话原文会照常发给百炼，提到的地名可能进入高德检索词。M4 条目 3、4 写的是「不发送真实用户内容」。统筹已判断属于授权文档写法与事实不一致，更正稿见 PR #1842（待 JT 本人批准）；持有者身份：JT 2026-11-26 确认均为内部团队账号；不再使用的 `CJ_Tester@` 和 `D1-` 账号已由 S 线撤销登录资格（只撤登录、不删数据），撤销后可登录 104 个：`G2C@01–99` 共 99 个、`CJ_Tester@12`、4 个 `D1-` 长码；名单主体数仍为 206（S 线 2026-11-26 核对，[#1720 评论](https://github.com/JTCAO515/G2C/issues/1720#issuecomment-7182561865)）。仍可登录的 `CJ_Tester@12` 和 4 个 `D1-` 账号是否撤销，待统筹决定。
2. **storage-registry 漏登的服务端存储**（乙表第 10 行），其中 ToolEvidence 目录能保存完整模型请求体和工具原文，附近缓存键含精确坐标。建议开票给 S 线补登或说明，并同 PR 交付清理钩子（ADR-0009 第 6 条）。
3. **旧 Supabase 是否仍在被连**：代码默认 `CJ_BETA_DB_TARGET='supabase'`，实际值在服务器 `common.env`，仓库看不到（附录第 8 节）。
4. **ToolEvidence 在香港是否开启、对哪些主体开启**：由运维 manifest 决定，代码只说明能力（附录 1.1 第 5 点）。
5. **高德 iOS SDK 与 Apple MapKit 实际上报的设备和位置信息**：闭源 SDK 与系统行为，未核实；TestFlight 构建是否带 `G2C_AMAP_LOCAL` 也需核对。
6. **定位边界与 #225 的剩余差异**（第 2.2 节）：#1833 落地后，打车精确坐标仍到香港和滴滴、附近约 100 米坐标仍到高德。对外部测试者开放前，是改 #225 的边界（须 JT 本人），还是进一步收紧（例如打车只在 App 内用、不经香港；附近改为手选地点），由 JT 判断。

## 4. 只到本方服务的新数据流（不出站）

不发给任何第三方或模型、但属于新收集的数据，也在这里登记，供隐私政策和 App 隐私标签核对。

| 功能 | 触发 | 发出的字段 | 接收方 | 开关与状态 | 出处 |
|---|---|---|---|---|---|
| 回答下的反馈入口（W4-9 [#1753](https://github.com/JTCAO515/G2C/issues/1753)） | 用户在一条 Lio 回答下点「没帮上」，可选填「补充说明」 | 复用现有 `POST /v1/feedback`，请求体固定为 `action_id`（客户端生成的提交编号）、`problem`、`expectation`、`references`（该回答的服务端 message id，可带匹配的 run id）。A 线提供的内容：固定文案「这条回答没帮上忙 / This answer didn't help.」与用户选填的补充说明（≤500 字，输入框提示不要填写个人信息），分别落在 `problem`、`expectation` 哪一个以 #1753 代码为准。不发聊天原文、位置、设备信息 | 只到本方香港服务，不转第三方或模型。服务端凭登录凭据识别账号，**按账号**存入香港 PostgreSQL `cj_feedback_action`：原始请求字节及其 sha256、提交时间，以及从被引用消息读出的会话、generation、sequence、run 编号、原始输入哈希和读取时的 run 状态；不复制对话原文或工具内容。无自动保留期，只在注销（删除）账号时由 `FeedbackHook` 删除；没有删除单条反馈的入口 | 开关 `G2CAnswerFeedbackEnabled`，默认关；**#1753 合并前不生效**，合并后按代码核对本行 | A 线 2026-11-26 提供；统筹 2026-11-26 按 JT 预授权决定。代码依据：`backend/cj_api/feedback_routes.py:53-65`、`backend/cj_api/FEEDBACK-WIRE.md`、`backend/feedback/cj_feedback/postgres.py:101`、`backend/feedback/cj_feedback/lifecycle.py:36-55`、`backend/storage-registry.json:220-232` |

同一张票加的 AI 提示「由 AI 生成，可能有误，重要信息请自行确认」（开关 `G2CAIDisclosureEnabled`，默认关）不产生数据，不登记。

## 附录：逐供应商明细

编号沿用底稿：第 2 节高德放在第 3 节滴滴之后；第 11–20 节为 App 侧；A–C 为定位逐跳细节（结论已汇总到正文第 2 节）。

### 1. 阿里云百炼 DashScope（北京端点）

总体：主机 `dashscope.aliyuncs.com`（北京，`region='cn-beijing'` 写在元数据里，`backend/agent/cj_agent/provider.py:860`）；另有 TTS 结果下载主机 `dashscope-result-bj.oss-cn-beijing.aliyuncs.com`（见 1.2）。全部为服务端 API，密钥只在香港服务端。下面按功能分小节。

#### 1.1 Lio 对话 / 规划 / 记忆抽取（Chat Completions，OpenAI 兼容模式）

1. 接入：服务端 HTTPS，`POST /compatible-mode/v1/chat/completions`，流式 SSE。固定 `M4_BASE='https://dashscope.aliyuncs.com/compatible-mode/v1'`、`M4_MODEL='qwen3.8-flash'`（`provider.py:210-211`）。生产路径用手写 h11 连接直连 `dashscope.aliyuncs.com:443`（`provider.py:325-345`）；`DashScopeProvider.stream`（`provider.py:172-180`，httpx，`CJ_MODEL_API_BASE_URL` 可配）是旧通用路径，`from_environment` 读三项环境变量（`provider.py:113-118`）。
2. 触发功能：Lio 对话回答（`model.answer`）、草稿/工具轮（`model.draft`/`model.tool_turn`）、规划需求理解 intake.1–9、探索式对话（`model.lio_exploration.1`）、记忆抽取（`memory.lio_extract.1`）、运行时反思（`model.runtime_reflection.1`）。注册表见 `backend/cj_api/real_services.py:398-420`，唯一调用点 `real_services.py:658`。
3. 发出字段：请求体 `model, messages, stream, stream_options, enable_thinking=false, max_tokens`，可选 `tools / tool_choice / parallel_tool_calls / response_format`（`provider.py:570-600`）。`messages` 包含：
   - 系统提示（代码内置）；
   - **用户输入原文**：对话文本（`messages` 中 role=user 的内容），不做截断/脱敏（未见任何脱敏代码）；
   - 正式行程上下文 `FORMAL_TRIP_CONTEXT_V1`：行程标题、所选日/项目的条目（地点名、时间等）、来源；引用值含内部 `conversation_id / generation / message_id / run_id`（`backend/message/cj_message/trip_reference.py:140-158`，`travel_reference.py:38-39`）——是内部不透明 ID，不含账户 scope；
   - 工具结果：以 `UNTRUSTED TOOL DATA` 前缀作为 user 消息回灌（`provider.py:536-539`），内容为高德/事实源返回的地点名、地址、**POI 坐标**（来自供应商数据，不是用户设备 GPS）、天气等；
   - **位置**：未发现设备 GPS 坐标进入模型请求的路径（设备定位只在打车起点用，见「定位字段去向」）；地点以 POI/城市名形式出现。
   - **标识**：请求体无 user/账户/设备/邮箱/手机号字段（`provider.py` 全文无 `user_id/account/email/phone/device`，见 grep）；HTTP 头只有 Host、Authorization、Content-Type、Accept 等（`provider.py:335-338`）。
   - 日期时间：行程日期随行程上下文发出；无请求时间戳字段。
4. 鉴权：`Authorization: Bearer <CJ_MODEL_API_KEY>`，密钥服务端从 `CJ_MODEL_API_KEY` 或 `CJ_MODEL_API_KEY_FILE`（须 0600）读取（`real_services.py:340-355`）。App 不持有。
5. 服务端记录：
   - 预算账本 `~/.local/share/g2c/m4-real-services/m4-outflows.sqlite`，只存 `attempt id / kind / input_sha / state / receipt`（哈希与计量元数据，不存正文）（`backend/usage/cj_usage/authorization_budget.py:182-190`）；
   - 审计日志 `cj_usage.audit` / `cj_provider.audit` 只记 `attempt_sha256`、时延、状态码、字符数，代码注释明确「Never log exception text, provider IDs, prompts, deltas or keys」（`provider.py:868-931`）；
   - **ToolEvidence（运维选择性开启）**：`record_model_input` 会把「发送前完整 HTTP 请求体」原文 `wire_input_utf8` 写入 0700 目录下的 JSON，`_record_model` 写模型输出原文 `result_utf8` 与输入原文 `input_utf8`（`backend/cj_api/tool_evidence.py:120-160`）。仅对 manifest 选中的合成主体、在截止时间前生效（`tool_evidence.py:95-104`），由 `app_smoke_capture.py:97`、`runtime_simulator_host.py:135`、`runtime_worker_bindings.py:196` 加载。
   - `backend/storage-registry.json`：**没有**对应条目。唯一相关的是 `external-processing`（`status: not_provisioned`，保留期 UNDECIDED），未列预算账本或 ToolEvidence 目录。
6. 代码依据：`backend/agent/cj_agent/provider.py:172-180, 210-211, 325-345, 412-437, 535-600, 860-931`；`backend/cj_api/real_services.py:306-420, 658`。
7. 开关/限制：`RealServices.from_environment` 要求 `CJ_M4_SYNTHETIC_ONLY=1`，否则抛错（`real_services.py:351`）；主体必须匹配 `m4-synthetic-[a-z0-9-]{1,80}` 且在 `invited.json` 中（`real_services.py:313-318, 352`）；截止日后只允许 Demo 主体（`real_services.py:323-336`）。香港部署 `deploy/hk/common.env.example:3`、`deploy/hk/secret_setup.py:73` 固定写入 `CJ_M4_SYNTHETIC_ONLY=1`。授权：M4.md 条目 4（对话/规划管线）、条目 18（路书 flash 档）、条目 19（点餐）。

#### 1.2 翻译插件：文字翻译 / 语音识别 / 图片 OCR / 图片原位翻译 / 语音合成

1. 接入：服务端 HTTPS → `dashscope.aliyuncs.com`：`/compatible-mode/v1/chat/completions`（文字翻译 `qwen-mt-flash`、语音识别 `qwen3-asr-flash`）与 `/api/v1/services/aigc/multimodal-generation/generation`（OCR `qwen-vl-ocr`、TTS `qwen3-tts-flash`）（`backend/cj_api/translation.py:47-49`；模型名 `backend/usage/cj_usage/translation_budget.py:20-23`）。TTS 返回音频 URL 后，服务端再 `GET` 下载 WAV，限定主机 `dashscope-result-bj.oss-cn-beijing.aliyuncs.com`（`translation.py:30, 395-421`），请求只带 `Accept: audio/wav`，无密钥。
2. 触发：App「插件 → 翻译」（路由 `/v1/tools/translate`、`/v1/tools/translate/image-layout`、`/v1/tools/tts`，`translation.py:25-29`）；香港中继 `deploy/hk/translation_relay.py:262`。点餐（1.3）复用其 OCR。
3. 发出字段：
   - 文字：**用户输入原文**整段（≤4000 字符，`translation.py:39, 191-195`），`translation_options.source_lang/target_lang`（`translation.py:314-321`）；
   - 语音：**用户语音**（App 上传的音频，服务端转 16 kHz WAV，≤60 秒）base64 作为 `input_audio`，`asr_options.language`（`translation.py:44-45, 197-201, 314-320`）；识别出的文本再逐行发给 `qwen-mt-flash`；
   - 图片：**用户照片**（PNG/JPEG，≤约 3 MB）以 data URI 发给 `qwen-vl-ocr`（`translation.py:38, 202-210, 305-312`；原位翻译 `351-358`），OCR 出的每行文本再逐行发 `qwen-mt-flash`（≤24 行，`translation.py:40, 512-533`）；服务端只校验格式与尺寸；App 端上传前统一经 `LioTranslationImageEncoder.jpeg` 从 CGImage 缩略图（长边 ≤2048）重新编码，且未传入任何元数据属性，因此相册原图的 EXIF/GPS 不会随图上传（`ios/Modules/CJShell/Sources/CJLioUser/LioTranslationImageEncoder.swift:6-29`；调用点 `LioTranslationView.swift:615`、`LioMenuOrderView.swift:127`）；
   - TTS：待朗读文本（≤280 字符）、固定音色 `Cherry`、语言（`translation.py:31, 378-382`）；
   - 位置：无。标识：请求体无用户/设备标识；App 生成的 `request_id`（UUID）只用于本方计量，不发往 DashScope（`translation.py:304-322` 请求体中没有它）。
4. 鉴权：`Authorization: Bearer CJ_MODEL_API_KEY`，服务端环境变量（`translation.py:273-274`；`deploy/hk/translation_relay.py:262`）。
5. 服务端记录：`TranslationBudget` 写入香港授权账本，**只存元数据**（scope、request_id、模态、阶段、模型、供应商 request_id、用量），模块文档串即「Metadata-only translation attempts」（`backend/usage/cj_usage/translation_budget.py:1, 89-140`）；失败日志只记 reason 与 HTTP 码（`translation.py` `G2C_TRANSLATION_ASR_FAILURE` / `TTS_AUDIO_FAILURE`）。不缓存原文或结果。storage-registry：无对应条目（仅 `external-processing` 未开通占位）。
6. 代码依据：`backend/cj_api/translation.py:24-52, 165-215, 251-460, 462-557`；`deploy/hk/translation_relay.py:25-39, 255-275`；`deploy/hk/plugin_roster.py`。
7. 限制：准入经 `account_checker_for` + 名单 `configured_translation_subjects`——固定 G2C@01–99 共 99 个邀请主体，外加 2 个哈希锁定的额外主体（`deploy/hk/plugin_roster.py:5-6, 26-39`）；TTS、图片原位翻译分别受 `TRANSLATION_TTS_ENABLED`、`TRANSLATION_IMAGE_LAYOUT_ENABLED` 开关（`translation_relay.py:270-271`）；日限额 text 300 / speech 1800 秒 / image 50 / tts 200（`translation_budget.py:19`）。授权：M4.md 条目 9。

#### 1.3 「工具 → 点餐」菜单解释（MENU.1）

1. 接入：服务端 HTTPS → `dashscope.aliyuncs.com`。两步：①`qwen-vl-ocr` 识别照片（复用 1.2 的 `DashScopeTranslation`，计入翻译图片额度）；②`qwen3.8-flash` 经 `/compatible-mode/v1/chat/completions` 解释菜品，每份菜单最多 2 次、每次 15 行（`backend/cj_api/lio_menu.py:39-52, 298-330`；模型 `backend/usage/cj_usage/menu_budget.py:30`）。
2. 触发：App「工具 → 点餐」拍照或从相册选图，路由 `/v1/tools/menu/explain`；香港中继 `deploy/hk/menu_relay.py`。
3. 发出字段：
   - 第一步：**用户拍摄/相册菜单照片**（App 端已重编码为 ≤2048 px 的 JPEG、不带 EXIF/GPS，见 1.2；服务端转 data URI，`lio_menu.py:107-124`）；
   - 第二步：OCR 识别出的菜单行文字，JSON 数组 `{"i": 行号, "text": 行文字}`，已在本地去掉行尾价格，每行 ≤60 字符（`lio_menu.py:43, 57, 126-153, 224-226`）+ 固定系统提示 `RULES`；
   - 模块文档串明确：模型看不到用户的饮食需求、账户或位置，只看到识别出的菜单文字（`lio_menu.py:7-8`）。位置：无。标识：无。
4. 鉴权：`Authorization: Bearer CJ_MODEL_API_KEY`（`lio_menu.py:313`），服务端环境变量。
5. 服务端缓存/记录：
   - 进程内 `MemoryMenuCache`：键 = 归一化行文字 + 提示词版本，值 = 已校验的菜品解释，LRU 上限 5000（`lio_menu.py:197-221`）；注释称「public dish knowledge only, never photos or user data」。进程重启即失。
   - 照片只在内存处理、不存不记（`lio_menu.py:9`）；计量写 `MenuBudget` / `TranslationBudget` 账本（元数据）。
   - storage-registry：无对应条目（内存缓存未登记）。
6. 代码依据：`backend/cj_api/lio_menu.py:1-12, 38-53, 107-226, 298-420`；`deploy/hk/menu_relay.py:33-43, 215-242`。
7. 限制：名单 `MENU_INTERNAL_SUBJECTS` 必须是 G2C@01–99 的非空子集（`menu_relay.py:217-228`）；未配置时路由停用（`disabled=raw is None`，`menu_relay.py:242`）。授权：M4.md 条目 19（+ 条目 9 的图片识别）。

#### 1.4 「工具 → 路书」地点内容补充（ROADBOOK.1，模型部分；高德部分见 2.4）

1. 接入：服务端 HTTPS → `dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`，模型 `qwen3.8-flash`，每个地点中、英各 1 次（`backend/cj_api/lio_roadbook.py:55-56, 343-380`；`backend/usage/cj_usage/roadbook_budget.py:29-31`）。
2. 触发：App「工具 → 路书」，路由 `/v1/tools/roadbook/places`（`lio_roadbook.py:39`）；香港中继 `deploy/hk/roadbook_relay.py:188-214`。
3. 发出字段（发给模型）：只有 `name`（地点名，来自高德）、`opening`（高德营业时间）、`metro`（最近 ≤2 个地铁站名 + 距离米数）+ 固定系统提示（`lio_roadbook.py:255-258`）。`_facts` 明确剔除电话和评分（`lio_roadbook.py:222-253`）。模块文档串：「Nothing about the traveller is sent: only public place names and the city」（`lio_roadbook.py:9`）。用户输入原文：无（地点名由 App 从行程带来，但模型看到的是高德返回的名称）。位置：无坐标发给模型。标识：无。
4. 鉴权：`Bearer CJ_MODEL_API_KEY`（`roadbook_relay.py:201`）。
5. 缓存/记录：进程内 `MemoryRoadbookCache`（容量 5000，键 `v{PROMPT_VERSION}:poi:<高德POI>` 或 `name:<城市>:<中文名>`），注释称「public place content (no account data)… a Postgres table replaces it later」（`lio_roadbook.py:182-207`）；审计日志 `ROADBOOK_PLACE_UNAVAILABLE` 记 App 的 `request_id`、序号、语言、原因（`lio_roadbook.py:335-337`）；计量 `roadbook.1` 账本（元数据）。storage-registry：无条目。
6. 代码依据：`backend/cj_api/lio_roadbook.py:1-12, 38-60, 134-207, 222-258, 343-470`；`deploy/hk/roadbook_relay.py:3-4, 30-38, 188-214`。
7. 限制：名单 `ROADBOOK_INTERNAL_SUBJECTS`（须为 G2C@01–99 子集，`roadbook_relay.py:188-199`），未配置则停用；每日 60 地点 / 5 本，模型子上限 ¥300，80% 后仅用缓存（`roadbook_budget.py:23-29`）。授权：M4.md 条目 18。

### 3. 滴滴 MCP（`mcp.didichuxing.com`）+ 滴滴打车链接（`v.didi.cn`）

（编号说明：第 2 节留给高德，因其子用途最多，写在后面。）

1. 接入：服务端 MCP（JSON-RPC 2.0 over HTTPS `POST https://mcp.didichuxing.com/mcp-servers?key=<KEY>`），固定 4 个工具：`maps_textsearch`、`maps_regeocode`、`taxi_estimate`、`taxi_generate_ride_app_link`（`backend/cj_api/didi_mcp.py:12-21, 45-55`）。返回的打车链接为 `https://v.didi.cn/XvYQEWe?slng=…&slat=…&dlng=…&dlat=…`，服务端校验主机/路径/坐标后交给 App（`backend/cj_api/taxi_tools.py:30-34, 230-249`）；App 只在装了滴滴（`OneTravel://` 可打开）时用 `UIApplication.open` 打开，否则打开 App Store `apps.apple.com/app/id554499054`（`ios/Modules/CJShell/Sources/CJLioUser/LioTaxiEntry.swift:20-27`）。
2. 触发：App「插件 → 打车」：地点搜索 `/v1/tools/taxi/search`、价格预估 `/v1/tools/taxi/estimate`、生成叫车链接 `/v1/tools/taxi/link`（`taxi_tools.py:27-29`）。
3. 发出字段：
   - `maps_textsearch`：`keywords` = **用户输入的搜索词原文**（≤100 字符，仅 strip），`city` = 城市名，可选 `location` = `near` 偏置点（`taxi_tools.py:147-165, 356-363`）。App 端 `near` 取自上车点坐标，若上车点是「当前位置」则即**设备 GPS 精确坐标**（`ios/.../LioTaxiView.swift:94, 483-484`；`LioTaxiWire.swift:117-127`）。
   - `maps_regeocode`：`location` = 起点/终点坐标（`taxi_tools.py:367-373`）。
   - `taxi_estimate`：`from_lat/from_lng/to_lat/to_lng` + `from_name/to_name`（名称由 regeocode 得来）（`taxi_tools.py:385-389`）。
   - `taxi_generate_ride_app_link`：`from_lat/from_lng/to_lat/to_lng`（`taxi_tools.py:405-415`）。
   - **位置**：起点可以是**设备 GPS（CoreLocation，WGS-84）精确坐标**（`LioTaxiPickupLocation.swift:41-46`），服务端本地 WGS→GCJ 转换后保留 6 位小数（约 0.1 m 精度）发给滴滴，**不做模糊化**（`taxi_tools.py:252-261`）；终点为用户搜索选中的 POI、行程地点或最近使用地点。服务端检查坐标在中国大陆服务区内（`taxi_tools.py:254-259`）。
   - 标识：请求体无用户/设备/邮箱/手机号；JSON-RPC `id` 固定为 1（`didi_mcp.py:47-48`）。
   - 日期时间：无。
4. 鉴权：MCP Key 放在 URL 查询串 `?key=`（服务端环境变量 `DIDI_MCP_KEY`，`deploy/hk/taxi_runtime.py:15, 44`）；异常处理刻意不外泄 endpoint（`didi_mcp.py:93-95`）。App 不持有。
5. 记录：`PluginCalls` SQLite 表 `plugin_call(day, owner=sha256(issuer,subject), operation, used)`，只计次数（`backend/cj_api/plugin_tools.py:33-56`）；日志仅 `ALERT didi_key_rejected`（`taxi_tools.py:74`）。英译结果进程内缓存 `ENGLISH_CACHE_CAPACITY=4096`，键为（中文名, 中文地址）（`taxi_tools.py:265, 280-298`）。App 端在本地保存「最近使用地点」（`LioTaxiRecentPlaces(directory:)`，`LioTaxiEntry.swift:28`）——只记录用户选的目的地，不含当前位置（见附录 C1 第 5 点）。storage-registry：无条目。
6. 代码依据：`backend/cj_api/didi_mcp.py:1-95`；`backend/cj_api/taxi_tools.py:1-35, 98-165, 230-420`；`deploy/hk/taxi_runtime.py:15-66`；App `LioTaxiEntry.swift`、`LioTaxiPickupLocation.swift`、`LioTaxiView.swift`、`LioTaxiWire.swift`。
7. 限制：模块文档串「HK stays disabled until provider verification」（`taxi_tools.py:1`）；需同时配置 `DIDI_MCP_KEY` 与 `TAXI_INTERNAL_SUBJECTS`，名单必须恰为 G2C@01–99（`configured_plugin_subjects`，`deploy/hk/plugin_roster.py:13-23`；`taxi_runtime.py:44-51`）；每人每天每操作 50 次（`taxi_tools.py:31`）。授权：M4.md 条目 10（信息型，只用 `maps_*`、`taxi_estimate`、`taxi_generate_ride_app_link`）。
8. 附带：英文模式下搜索结果的中文名/地址会经本方翻译中继发给 DashScope `qwen-mt-flash` 英译（见 1.2，`taxi_runtime.py:24-40`；`taxi_tools.py:301-345`）——发出的是滴滴返回的 POI 名称与地址，不是用户输入。

### 2. 高德 Web 服务（`restapi.amap.com`，服务端 API）

共通：服务端 HTTPS GET，密钥 `key=<CJ_AMAP_WEB_KEY>` 拼在查询串（各模块均同，如 `backend/cj_api/nearby_tools.py:94`、`backend/place/cj_place/https_transport.py:220`），密钥只在香港服务端/worker。所有模块都检查响应是否回显密钥。请求不带任何用户/设备标识（参数都由代码固定白名单构造）。计量账本只存 scope 哈希、request_id、操作名、日期、响应 sha256（如 `backend/usage/cj_usage/nearby_budget.py:38-67`），不存坐标或原文。storage-registry：各子用途均**无条目**。M4.md 授权：条目 3（地点/路线/天气/公交/周边）、条目 12（①附近 ③酒店 ④火车 ⑤车站周边 + 坐标转换 + 逆地理）、条目 18（路书）。

#### 2.1 Lio 对话/规划管线：地点搜索、详情、周边、路线、公交

1. 端点：`/v3/place/text`、`/v3/place/detail`、`/v3/direction/walking|driving`、`/v3/direction/transit/integrated`、`/v5/place/text|around|detail`（`backend/place/cj_place/https_transport.py:20-23, 199, 298, 386`；`gaode.py:94-108`；`gaode_v2.py:69-79`；`rich_routes.py:52-60`）。
2. 触发：Lio 模型工具调用 `place_search` / `place_route` 及规划管线（`backend/cj_api/real_services.py:385-420`，`lio_poi2_tool.py:63`，`lio_route_tool.py:60`）。
3. 字段：`keywords`（模型从对话生成的检索词——**可能包含用户在对话里写的地名/地址**，属间接用户输入）、`city/region`、`id`（高德 POI）、`location`（周边中心：**POI 坐标**）、路线 `origin/destination`（**POI 坐标** + POI id）、`city`（公交）、`langCode/extensions/show_fields` 等固定值（`gaode.py:93-110`；`gaode_v2.py:69-79`；`rich_routes.py:56-59`）。`request_ref/started_at` 只进本地绑定哈希，不发出（`gaode_v2.py:81-84`）。设备 GPS：无（Lio 管线不接触 CoreLocation）。
4. 记录：`AuthorizationBudget`（`m4-outflows.sqlite`，只存 input_sha）；ToolEvidence 开启时，`record` 会保存工具输入原文 `input_utf8` 与结果原文 `result_utf8`（`backend/cj_api/tool_evidence.py:95-113`）。
5. 限制：同 1.1——`CJ_M4_SYNTHETIC_ONLY=1` + `m4-synthetic-*` 主体（`real_services.py:313-352`）。

#### 2.2 行政区划目录 `/v3/config/district`

- 固定参数 `keywords=100000, subdistrict=3, extensions=base`，不含任何用户数据（`backend/cj_api/lio_city.py:18-19, 150-165`）；城市名比对在本地完成（`real_services.py:446-488`）。仅 `national_subjects` 可触发（`real_services.py:455-458`）。

#### 2.3 天气（Lio 事实源）`/v3/weather/weatherInfo`

- 参数 `key, city=<adcode>, extensions=all`（`backend/fact/cj_fact/live_source.py:27, 113-125`）——城市级行政编码，无坐标、无标识。由 `real_services.py:29` 引入，属 Lio 管线，同 1.1 的合成主体限制。

#### 2.4 路书（ROADBOOK.1）高德部分

- 端点 `/v5/place/detail`（`id=<App 传来的 POI id>`）或 `/v5/place/text`（`keywords=<地点中文名>, region=<城市>`），再 `/v5/place/around`（`location=<该 POI 坐标>`, 餐饮|地铁站, 1000 m）（`backend/cj_api/lio_roadbook.py:417-436`；`backend/usage/cj_usage/roadbook_budget.py:37-41`）。地点名/城市来自 App 行程（`PlaceRequest`，`lio_roadbook.py:134-160`）。无设备位置、无标识。上限 2000 次（`roadbook_budget.py:41`）。名单与开关见 1.4。

#### 2.5 「附近 / Nearby」（NEARBY.1/2）——**设备 GPS 精确坐标外发**

1. 端点：`/v3/assistant/coordinate/convert`（`coordsys=gps`）、`/v5/place/around`、`/v3/geocode/regeo`（`backend/usage/cj_usage/nearby_budget.py:16-20`）。路由 `/v1/tools/nearby/search`、`/v1/tools/nearby/reverse`（`nearby_tools.py:27-28`）。
2. 字段：`locations`/`location` = **设备 GPS 坐标**，App 用 CoreLocation 取得（`ios/.../LioNearbyView.swift:15-19` → `LioTaxiPickupLocation.pickup()`），以 WGS-84 原精度上传香港，服务端格式化为 6 位小数（`nearby_tools.py:214, 268`），WGS-84 时先发给高德做坐标转换（`nearby_tools.py:206-210`），再用转换后坐标做周边搜索或逆地理；`types`/`keywords=行李寄存`、`radius`（500/1000/3000）、`sortrule`（`nearby_tools.py:212-235`）。无标识、无时间。
3. 缓存：进程内 60 秒、32 条，**键含精确坐标**（`nearby_tools.py:38-39, 218-227, 258-262`）——不含用户标识，但在内存中短暂保存坐标→结果；未登记 storage-registry。日志 `G2C_NEARBY_POI_PROJECTION` 只记行数与原因。
4. 限制：每人每天 100 次、总计 3000 次（`nearby_budget.py:21-22`）；名单变量 `CJ_NEARBY_INTERNAL_SUBJECTS_JSON`（`deploy/hk/configuration.py:47`；`deploy/hk/nearby_relay.py:31-32` 引用 `generate_plugin_subjects`，即 G2C@01–99 范围）。授权：M4.md 条目 12 ①（含逆地理编码）。

#### 2.6 酒店搜索（HOTEL.2）高德部分

- 端点：`/v3/geocode/geo`（`address=<用户输入的地标/附近文字>`, `city`）、`/v5/place/around`（`location=<地理编码得到的坐标>`, 酒店类型）或 `/v5/place/text`（`region=<城市>`），再 `/v5/place/around` 查最近地铁站（`backend/usage/cj_usage/hotel_budget.py:20-27`；`backend/cj_api/lio_hotel_search.py:287-330`）。
- 用户输入原文：`near` 地标文字（App `LioHotelOffers.swift:273-291` 的 `near.query`）。设备 GPS：无（App 请求只有 city/near 文本/日期/人数/价格/语言，`LioHotelOffers.swift:277-291`）。入住日期等**不发给高德**（只用于 Trip.com 链接，见第 9 节）。
- 缓存：进程内 `self.cache`，键含城市与 near 文本（`lio_hotel_search.py:345-368`，键构成**未逐字核实**）。英文名经翻译中继 → DashScope（`lio_hotel_search.py:368-371`）。授权：M4.md 条目 12 ③、条目 9。

#### 2.7 地铁站周边（METRO-NEARBY.1）

- `/v5/place/around`，`location` = App 内置地铁图生成的**车站坐标**；App 只发 `city_id + station_id`，模块文档串明言「this route can never receive the traveller's location」（`backend/cj_api/metro_nearby.py:1-9, 130-133`；`backend/usage/cj_usage/metro_nearby_budget.py:20-21`）。结果按车站+类别缓存 1 天、全账户共享。授权：M4.md 条目 12 ⑤。

#### 2.8 城际火车（TRANSPORT.1 rail）

- `/v3/direction/transit/integrated`（跨城），参数 `origin/destination` = 代码内置的**城市中心坐标**、`city/cityd` = 城市中文名、`date` = 用户选的出发日期、`time=08:00`（`backend/cj_api/lio_transport_rail.py:34-50`；城市表 `lio_transport.py:65-77`）。无用户位置、无标识。每人每天 30 次、总计 1500 次（`lio_transport.py` 文件头常量）。授权：M4.md 条目 12 ④。

### 4. 和风天气 QWeather（项目专属主机 `*.qweatherapi.com`）

1. 接入：服务端 HTTPS GET `https://<weather_host>/weather/v1/current|hourly|daily` 与 `/weatheralert/v1/current`，路径末尾拼 `/<lat>/<lng>`（`backend/cj_api/qweather_tools.py:20-24, 146-156`）。主机名不写死，由 `/control/travel-providers.json` 的 `weather_host` 提供，代码只校验正则 `[a-z0-9-]{4,50}(\.yun)?\.qweatherapi\.com`（`qweather_tools.py:20, 132-134`；`deploy/hk/travel_runtime.py:23, 99`）——实际主机名**未核实**（配置文件不在仓库）。传输用 `travel_provider.ProviderClient`（无重定向、不读环境代理、不记 URL，`backend/cj_api/travel_provider.py:112-133`）。
2. 触发：服务端路由 `/v1/tools/weather`（`qweather_tools.py:17`）。**App 在 27388ea7 未调用此路由**：`ios/**` 无 `tools/weather` 引用，`LioWeatherPreviewView.swift` 是静态预览，不联网（grep 结果）。
3. 字段：位置二选一——城市枚举 `beijing/chengdu/shanghai` 映射到代码内置坐标，或 App 传 `lat/lng`；服务端统一**截断为 2 位小数（约 1 km，城市街区级）**后放进 URL 路径（`qweather_tools.py:31-45`）；`lang`、`localTime=true`、`hours=24`/`days=7`（`qweather_tools.py:146-150`）。无用户输入原文、无标识、无日期。
4. 鉴权：请求头 `X-QW-Api-Key`（`qweather_tools.py:156`），服务端环境变量 `CJ_QWEATHER_KEY`（`deploy/hk/configuration.py:57`）。
5. 缓存/记录：`ShortCache(120)` 进程内 120 秒，键 =（类别, 语言, 两位小数坐标），注释「Only projected public data … never an owner or raw response」（`travel_provider.py:68-69`；`qweather_tools.py:137-143`）；调用计数 `/plugin-state/weather.sqlite`（`travel_runtime.py:114`，结构同 PluginCalls 推定，**未逐行核实**）。storage-registry：无条目。
6. 代码依据：`backend/cj_api/qweather_tools.py:1-160`；`deploy/hk/travel_runtime.py:90-122`。
7. 限制：需 `weather_host` 与 `CJ_QWEATHER_KEY` 同时存在才注册，否则注册为停用（`travel_runtime.py:111-122`）；名单固定 G2C@01–99（`travel_runtime.py:102`）；每人每天 200 次（`qweather_tools.py:18`）。授权：M4.md 条目 15（「只发送城市或经纬度，不发送用户身份」）。

### 5. 飞常准 VariFlight MCP（`c-gw.variflight.com`）

1. 接入：服务端 MCP（Streamable HTTP，JSON-RPC）`POST https://c-gw.variflight.com/chat_message/mcp/api`（`backend/cj_api/variflight_tools.py:21`）。先 `initialize`（`clientInfo={name:'Go2China', version:'1'}`）、`notifications/initialized`，再 `tools/call`，只允许 `getFlightList`、`getFlightStatus`（`variflight_tools.py:23, 235-260`）。会话头 `Mcp-Session-Id`、`MCP-Protocol-Version`。
2. 触发：`/v1/tools/flights`（FLIGHTS.1）与「交通」`/v1/tools/transport/search` 的航班模式（`backend/cj_api/lio_transport.py:392-400, 449`）。App 端调用的是 `v1/tools/transport/search`（`ios/.../LioTransportRelay.swift:49`）；**App 未发现直接调用 `/v1/tools/flights`**。
3. 字段：`getFlightStatus{fnum, date}` 或 `getFlightList{dep, arr, date}`（`variflight_tools.py:31-57`）；交通模式下 `dep/arr` 为代码内置城市的机场三字码（逗号分隔，最多 3 个），「codes come from CITIES, never from input」（`lio_transport.py:392-400`）。用户输入：航班号或机场码（格式受正则限制）、出行日期。无位置、无标识。客户端名 `Go2China` 会发给供应商。
4. 鉴权：`Authorization: Bearer <CJ_VARIFLIGHT_MCP_KEY>`（`variflight_tools.py:235`；`deploy/hk/configuration.py:58`）。
5. 缓存/记录：`ShortCache(60)`，键 =（工具名, 参数）（`variflight_tools.py:208-217`）；计数 `/plugin-state/flights.sqlite`（`travel_runtime.py:129-131`）；遇 402 写 `flights.payment-hold` 停用（`travel_runtime.py:126-131`）。storage-registry：无条目。
6. 代码依据：`backend/cj_api/variflight_tools.py:1-60, 200-265`；`backend/cj_api/lio_transport.py:1-30, 392-470`；`deploy/hk/travel_runtime.py:124-160`。
7. 限制：需 `CJ_VARIFLIGHT_MCP_KEY` 且 `/control/travel-providers.json` 中 `flights_enabled` 或 `transport_enabled` 为 true（`travel_runtime.py:128-160`）；名单 G2C@01–99；每人每天合计 50 次（`variflight_tools.py:20`）。授权：M4.md 条目 14。

### 6. 欧洲央行 ECB 参考汇率（`www.ecb.europa.eu`）

1. 接入：服务端 HTTPS `GET /stats/eurofxref/eurofxref-daily.xml`，请求头只有 `Accept: application/xml`（`backend/cj_api/currency_tools.py:20-21, 33-45`）。公开数据，无鉴权。
2. 触发：App「汇率」调用本方 `/v1/tools/currency/rates`（`ios/.../LioCurrencyRelay.swift:25, 42`，请求体只有 `{"version":"CURRENCY.1"}`），服务端读取并缓存 ECB 数据。App 侧有构建开关 `G2CCurrencyEnabled`（`ios/App/Info.plist:15`）。
3. 字段：无任何用户数据、位置、标识（固定 GET）。ECB 只能看到香港服务器出口 IP。
4. 鉴权：无。
5. 缓存：缓存 ECB 快照（模块文档串「Read and cache the ECB's published euro reference rates」，`currency_tools.py:1`）；配额状态文件要求私有（`deploy/hk/currency_runtime.py:41`）。storage-registry：无条目（公开数据，影响小）。
6. 代码依据：`backend/cj_api/currency_tools.py:1-60`；`deploy/hk/currency_runtime.py:1-45`。代码里的 `http://www.ecb.int/...` 只是 XML 命名空间常量（`currency_tools.py:23`），不是网络请求。
7. 限制：「Closed-by-default」，需 `CJ_ECB_INTERNAL_SUBJECTS_JSON` 名单（`currency_runtime.py:1, 30`；`deploy/hk/configuration.py:59`）。授权：M4.md 条目 13。

### 7. 国家移民管理局英文公告页（`en.nia.gov.cn`）

1. 接入：服务端 HTTPS GET 固定页面 `https://en.nia.gov.cn/n147418/n147463/c183412/content.html`（免签/入境政策公告），DNS 解析后按 IP 钉住连接（`backend/fact/cj_fact/live_source.py:26-28, 60-110`；`backend/fact/cj_fact/https_transport.py:80-110`）。
2. 触发：Lio 工具 `fact`（公告事实源），`backend/cj_api/real_services.py:29, 806-827`。
3. 字段：只有固定 URL 与 `Host/Accept/Accept-Encoding/Connection` 头（`https_transport.py:105-108`），无用户数据、位置、标识。
4. 鉴权：无。
5. 记录：结果进入 Lio 工具结果（ToolEvidence 开启时保存原文，见 1.1）；budget 账本只记哈希。storage-registry：无条目。
6. 限制：同 Lio 管线（`CJ_M4_SYNTHETIC_ONLY=1`、合成主体）。授权：M4.md 条目 3「公开权威事实页」。
- 附注：M4.md 条目 8（Wikidata）在代码中**没有网络调用**；`backend/trip/cj_trip/rich_source.py:31` 只有来源类型标签 `wikidata`。

### 8. 旧 Supabase 新加坡项目（ref `sajkhvjpllldfyfryalx`，`aws-0-ap-southeast-1.pooler.supabase.com`）

结论先行：**代码仍保留完整的 Supabase 连接路径，是否真的在连，取决于服务器 `common.env` 中 `CJ_BETA_DB_TARGET` 的值——该值不在仓库，未核实。** 代码默认值是 `'supabase'`（`deploy/hk/configuration.py:135-139`），切到本机 PG 需显式设 `hk-local`（`deploy/hk/README.md:459-470` 说明为「已批准的 (b2) 切换」）。

1. 接入：PostgreSQL 协议（不是 HTTP），会话模式 pooler，`sslmode=verify-full` + CA 指纹钉扎（`backend/cj_api/supabase_test_database.py:1-31, 53-90`）。
2. 触发 / 角色：
   - API、worker 运行时数据库：`CJ_SUPABASE_RUNTIME_URI`（`deploy/hk/configuration.py:26-27, 296-300`）。`hk-local` 时，同名变量被改写为本机 Unix socket `/run/g2c-pg` 的连接串（`deploy/hk/local_postgres.py:80-92`；`supabase_test_database.py:31, 61-70`）——**变量名仍叫 SUPABASE，但目标已是本机**，登记表需注意别被名字误导。
   - 运维角色 migrate / recovery / rehearsal / backup / checkpoint：`CJ_SUPABASE_OPERATOR_URI`（`configuration.py:28-33`；`deploy/hk/checkpoint.py:66-73`——同一文件里既有本机 socket 分支 `decode_hk_socket_uri`，也有远程 `decode_uri` + `CJ_SUPABASE_CA_FILE` 分支）。
   - 清理：`CJ_SUPABASE_CLEANUP_URI`（`configuration.py:60, 422-457`；`backend/cj_api/supabase_cleanup.py`）。
   - 云端恢复演练 `deploy/hk/cloud_rehearsal.py:1, 299-304`（文档串「real Supabase recovery rehearsal」）——显式写 Supabase。
   - 冻结：`deploy/hk/local_postgres.py:48-77` `freeze_supabase` 冻结源库应用登录与默认读写，归档名 `b2-supabase-frozen`。
3. 字段：在 Supabase 目标下，**整个业务数据库**（消息、行程、记忆、用量等，即 storage-registry 的 `business` / `checkpoints` / `memory-derived` / `cleanup-control` 各表）都经此连接读写；在 `hk-local` 目标下，只有显式调用 Supabase 的运维脚本（冻结、云端演练、远程分支 checkpoint）才会连。
4. 鉴权：连接串内含角色密码，服务端 0600 secret 文件（`configuration.py:62-70` `load_secret_environment`）。
5. storage-registry：`business` 等存储条目描述的是数据本身，未单独标注「旧 Supabase 新加坡冻结副本」这一物理位置（`backend/storage-registry.json` 中无 `supabase` 字样，grep 结果）。
6. **JWKS**：`backend/auth/cj_auth/https_jwks_transport.py` 的 `HTTPSJWKSTransport` 只被 `backend/auth/tests/` 引用，生产代码无引用（git grep）；`backend/c2-preparation/resource-request.json:58` 中 `jwks_url: null`。香港后端签发者是本方 `ISSUER='https://local.g2c.invalid'`（`backend/cj_api/local_app.py:44`），由 worker 持有签名私钥 `CJ_BETA_SIGNING_PRIVATE_B64`（`configuration.py:27`；`deploy/hk/demo_login.py:1`）。→ **鉴权不调用 Supabase JWKS**。
7. **App 侧**：`ios/Modules/CJAuth` 依赖 `supabase-swift 2.55.4` 的 `Auth`（`ios/Modules/CJAuth/Package.swift:11, 18`），`CJShell/AccountHost.swift:5-6` 引入，但：默认 `AccountHost(shell:)` 用 `UnconfiguredSDKAdapter`（`AccountHost.swift:97-99`）；Supabase 适配器要求显式 `authURL/publicKey`，默认 fetch 直接抛 `notConnectedToInternet`，「No URL/key defaults」（`ios/Modules/CJAuth/Sources/CJAuthSupabase/SupabaseSDKAdapter.swift:5-18, 42-64`）；`ios/App` 中无 Supabase URL/Key。Beta App 登录走本方 `https://api-beta.go2china.space`（`ios/App/DemoBetaConfiguration.swift:11, 23, 34`）。→ **App 不连 Supabase**（SDK 被打进包但未配置）。
8. 授权：M4.md 条目 6（Supabase 测试项目补充操作）、条目 5（香港 ECS/OSS）。

### 9. 阿里云 OSS 香港（桶 `g2c-beta-backup`，`oss-cn-hongkong-internal.aliyuncs.com`）

1. 接入：服务端 SDK `alibabacloud_oss_v2`，区域 `cn-hongkong`，**内网端点** `https://oss-cn-hongkong-internal.aliyuncs.com`，签名 v4，禁止重定向（`deploy/hk/oss_backup.py:7, 12, 17-21`）。
2. 触发：每日备份 systemd 定时器 `g2c-beta-backup.timer` → `deploy/hk/daily-backup.sh` → `deploy/hk/backup.py`（「Daily checkpoint + original OSS object reconciliation」）；恢复 `deploy/hk/recovery.py` 下载。
3. 字段：对象键 `backups/<UTC时间戳>-<sha256>/database.dump`（≤64 MiB）与 `manifest.json`（≤1 MiB）（`oss_backup.py:24-27`）。`database.dump` 是**整库导出**，包含全部用户数据（对话原文、行程、记忆、账户等）。元数据 `sha256`。传输与存储：服务端加密 `server_side_encryption='AES256'`、ACL `private`、`forbid_overwrite`（`oss_backup.py:59-75`）；checkpoint 用 Ed25519 签名（`deploy/hk/checkpoint.py:34-44`），**未见客户端加密**（grep `checkpoint.py` 无 encrypt/AES 调用；结论为「未见」，非穷尽证明）。
4. 鉴权：RAM 用户 AccessKey，`OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET` 环境变量（`EnvironmentVariableCredentialsProvider`，`oss_backup.py:20`；`deploy/hk/configuration.py:32-33` backup 角色）。
5. storage-registry：未登记 OSS 备份副本的位置与保留期（`backend/storage-registry.json` 无 `oss` 字样）；保留/删除规则需另查 `deploy/hk/oss_quota.py`（**未核实**）。
6. 授权：M4.md 条目 5（OSS `g2c-beta-backup` 香港私有、RAM 用户 `g2c-backup`）。

### 10. 部署与运维出站

| 目标 | 方式 | 发出内容 | 依据 | 备注 |
|---|---|---|---|---|
| GitHub API `api.github.com/repos/<REPOSITORY>/…` | 服务器上的发布脚本 `urlopen`，无 token | 只读请求仓库路径（CI 结果、PR 审查等发布门禁证据），不发用户数据 | `deploy/hk/application_release.py:213`；`deploy/hk/application_release_host.py:218-229` | 运维元数据，无用户数据 |
| GitHub Actions 托管 runner → `https://api-beta.go2china.space/health/live`、`/health/ready` | 工作流 `hk-readiness.yml` 调 `deploy/hk/readiness_monitor.py` | 只 GET 两个健康检查路由，UA `G2C-readiness-monitor/1`，不鉴权（`readiness_monitor.py:1, 9-10, 33-37`） | `deploy/hk/MONITORING.md:8-21` | 目标是本方域名；GitHub 可见结果（状态码/时延）。需仓库变量 `HK_READINESS_MONITOR_ENABLED=true` 才启用，2027-01-01 后跳过 |
| Let's Encrypt ACME `acme-v02.api.letsencrypt.org` | Caddy 自动签证书 | 域名 `api-beta.go2china.space`、ACME 账户 | `deploy/hk/Caddyfile:10-11` | 不含用户数据；Caddyfile 全文未配置 ACME 联系邮箱，也无 `log` 指令（Caddy 默认不写访问日志） |
| Docker CE 软件源 `download.docker.com`、Debian 源 `deb.debian.org` | 主机准备与镜像构建 | 软件包下载 | `deploy/hk/host-prepare.sh:31, 41`；`deploy/Dockerfile:2` | 构建期，无用户数据 |
| 本机健康检查 `127.0.0.1:8765` | 容器内 | — | `deploy/hk/healthcheck.py:4`；`deploy/healthcheck.py:4` | 非外部 |
| 告警 | 代码中告警为写 stderr 的 `ALERT …` 行（如 `translation_relay.py:266`、`taxi_runtime.py:61`） | — | — | **未发现**任何外部告警渠道（邮件/IM/Webhook/Sentry），grep `smtp`、`webhook`、`feishu`、`dingtalk`、`sentry` 在 deploy/backend 代码中无命中 |
| `169.254.169.254` | — | — | 只出现在测试与 SSRF 拒绝清单（`backend/fact/cj_fact/local_source.py:72` 等） | **不是**出站调用 |

---

**App 侧（`ios/**`）**

### 11. App 的 URLSession：只连本方后端

- 所有非测试 URLSession 客户端（`CJMessageHTTP/Transport.swift:638-655`、`CJRunClient/RunCancellationTransport.swift:55-63`、`CJManualPreviewClient/ScopedTransport.swift:23-32`、`LioCurrencyRelay.swift:100-106`、`LioHotelOffers.swift:513-519`、`LioMenuOrderRelay.swift:219`、`DemoInviteClient.swift:22-54` 等）都用注入的 `baseURL`，Beta 固定为 `https://api-beta.go2china.space`（`ios/App/DemoBetaConfiguration.swift:11`），均为 ephemeral 配置并拦截重定向。
- 在 `ios/**/*.swift`（不含测试/验收/Demo）中未发现指向第三方主机的 URLSession 请求。`restapi.amap.com` 在 App 中只作为**校验/展示白名单字符串**出现（`CJMessageHTTP/LioPublicDisplay.swift:8-10`、`CJTripClient/PlaceResultV1.swift:242`），不是请求。
- 「附近」结果里的高德图片 URL 会被解析（`LioNearbyRelay.swift:109-130, 196, 223-228`，限 `*.autonavi.com`/`*.amap.com`），但 grep 未发现视图里使用 `.photo` 或 `AsyncImage` 加载它——**判断为未加载**（未在真机验证）。
- 「Supabase」：见第 8 节第 7 点，SDK 打包但未配置、不联网。

### 12. 高德 iOS 地图 SDK（MAMapKit / AMapFoundationKit）

1. 接入：App SDK，地图瓦片等由 SDK 自行联网（主机由 SDK 决定，**未核实**）。
2. 触发：行程地点地图 `TripPlaceMapView` 的「显示高德地图」，需用户点「同意并加载高德地图」（`ios/Modules/CJShell/Sources/CJShell/TripPlaceMapView.swift:39-58`）。
3. 发出：界面文案称「高德会处理查看区域及设备、网络信息…不申请你的位置」（`TripPlaceMapView.swift:44`）。代码设置 `showsUserLocation=false`、`analysisAgree=false`、`enableHTTPS=true`、隐私弹窗已展示/已同意（`AMapRecordedPlaceMap.swift:32-45`）。SDK 实际上报的设备信息字段**未核实**（闭源 SDK）。
4. 鉴权：**iOS 平台 Key 在 App 包内**（`AMapLocalKey.plist`，按 Bundle ID 校验，`AMapRecordedPlaceMap.swift:17-20`；`LocalAMapConfiguration.swift`）。
5. **开关：只在 `DEBUG && G2C_AMAP_LOCAL && canImport(MAMapKit) && 真机` 时编译**（`AMapRecordedPlaceMap.swift:1`；`TripPlaceMapView.swift:46`）。SDK 不在 Swift Package 依赖里，由 `ios/App/Acceptance/prepare_m4_amap.py` 本地注入。→ 普通 Release/TestFlight 构建**不包含**高德 SDK（据编译条件判断；TestFlight 构建是否带 `G2C_AMAP_LOCAL` **未核实**）。授权：M4.md 条目 1、条目 12（SDK 进入内部 TestFlight、Key 可随 App 分发）。

### 13. Apple MapKit / Apple 地图

- MapKit 视图：`LioItineraryTimelineView`、`LioRouteMap`、`LioTripsView`、`LioNearbyView`、`TripPlaceMapView`（`import MapKit`，grep 结果）。文案：「查看地图会向 Apple 发送查看区域，不申请你的位置」（`TripPlaceMapView.swift:44`）。发出：地图可视区域（由 MapKit 决定）。
- 打开 Apple 地图 App/网页：
  - 附近导航：`https://maps.apple.com/?daddr=<POI 纬度,经度>&q=<地名>`（`LioNearbyView.swift:401-415`）——**目的地 POI 坐标**，不含当前位置；
  - 地铁站导航：`?q=<城市+站名>`，无坐标（`LioMetroMap.swift:312-320`）；
  - 使领馆：`MKMapItem.openInMaps()` 用使领馆坐标，或 `?q=<名称 地址>`（`LioLocalSupportView.swift:340-358`）。
- 无鉴权。App 内无请求日志。

### 14. 高德地图 App 深链 `iosamap://`

- 附近导航 `iosamap://path?sourceApplication=Go2China&dlat=<POI纬度>&dlon=<POI经度>&dname=<地名>&dev=0&t=0`（`LioNearbyView.swift:404-407`）——终点 POI 坐标；起点由高德 App 自行定位，**不由本 App 传出当前位置**。
- 地铁站 `iosamap://poi?sourceApplication=Go2China&name=<城市+站名>&dev=0`（`LioMetroMap.swift:314-316`）。
- 注意 `Info.plist` 的 `LSApplicationQueriesSchemes` 只登记了 `OneTravel`（`ios/App/Info.plist:27`），代码对 `iosamap` 直接 `open` 并以返回值判断，不做 `canOpenURL` 探测。

### 15. 滴滴 App / 网页链接

- 见第 3 节：`v.didi.cn` 链接含起终点 GCJ-02 坐标（起点可能是设备 GPS），App 仅在 `canOpenURL("OneTravel://")` 为真时打开（`LioTaxiEntry.swift:20-25`）；否则打开 App Store 滴滴页 `apps.apple.com/app/id554499054`（`LioTaxiEntry.swift:26-27`）。

### 16. Trip.com（链接跳转）

1. 酒店：服务端生成 `https://www.trip.com/hotels/list?cityId=…&searchWord=<酒店名>&checkin=<日期>&checkout=<日期>&crn=1&adult=<人数>&curr=CNY&locale=en-US`，或首页 `https://www.trip.com/hotels/`（`backend/cj_api/lio_hotel_search.py:64-65, 144-159`）；存进进程内 `HandoffStore`（不透明句柄，24 小时、≤10000 条，重启即失，`lio_hotel_search.py:161-195`），App 打开 `https://api-beta.go2china.space/v1/tools/hotel/out/<handle>`，香港服务器 302 跳转到 Trip.com（`deploy/hk/hotel_relay.py:109-126`；App `LioHotelOffers.swift:271, 537`）。Trip.com 收到：城市、酒店名、**入住/离店日期、成人数**，以及用户浏览器自身的 IP/Cookie。无本方用户标识，**无联盟 ID**（文档串「without an affiliate ID until JT hands over the Trip.com credentials」，`lio_hotel_search.py:4-5, 148-150`）。
2. 火车/航班：`https://www.trip.com/trains/china/route/<城市>-to-<城市>/`、`https://www.trip.com/flights/showfarefirst?dcity=…&acity=…&ddate=<日期>&triptype=ow&class=y&quantity=1`（`backend/cj_api/lio_transport.py:376-389`），经 `wrap_link`（默认原样，`lio_transport.py:421-422`）返回 App。发出：城市代码、**出行日期**。
3. 景点：`https://www.trip.com/things-to-do/list?keyword=<景点英文名>`（App 端静态拼接，`LioAttractionBookingPartner.swift:36-49`），关键词来自内置表，不含用户输入。
4. 授权：M4.md 条目 11（Trip.com 联盟，酒店链接）。`affiliateLinks` App 端景点为 `false`（`LioAttractionBookingPartner.swift:20`）；酒店由服务端回包 `affiliate_links` 决定，缺省按 `true` 显示披露（`LioHotelOffers.swift:346, 423`）——与「暂无联盟 ID」并存，属文案/开关口径差异，**未核实**服务端实际回填值。

### 17. Klook（链接跳转）

- `https://www.klook.com/search/result/?query=<景点英文名>`（`LioAttractionBookingPartner.swift:42`），与 Trip.com 景点链接同一逻辑：关键词来自内置表，无用户数据、无联盟参数。只有服务端/App 的静态链接，**没有任何 Klook API/Data Feed 调用**。授权：M4.md 条目 17。

### 18. 12306（链接跳转）

- `https://www.12306.cn/en/index.html`（服务端，`lio_transport.py:379`）与 App 端 `https://www.12306.cn/index/` / `/en/index.html`（`ios/.../LioTransport.swift:449`）。纯首页链接，不带任何参数。

### 19. 其他静态外链（无用户数据）

- 景点官方预约站（故宫 `ticket.dpm.org.cn`、上博 `reservation.shanghaimuseum.net`、八达岭、慕田峪、熊猫基地、陕历博等）、政府/新闻页（`english.beijing.gov.cn`、`s.nia.gov.cn/ArrivalCardFillingPC/` 入境卡、`www.gd.gov.cn` 等）、微信/财付通帮助页（`LioPaymentGuide.swift:33`）、高德隐私政策 `lbs.amap.com/pages/privacy/`、Apple 地图法律页、使领馆目录（`bmeia.gv.at` 等）。均为 SwiftUI `Link` 打开的固定 URL，不附加用户参数（grep 汇总结果；逐条未逐行核对）。

### 20. 系统框架

- **CoreLocation**：见下节。
- **麦克风 / 相机 / 相册**：用于翻译与点餐（`ios/App/Info.plist:64-66`）；录音/图片只发往本方后端，再由后端转 DashScope（第 1.2、1.3 节）。
- **Speech / Vision 框架：未使用**（grep `import Speech|import Vision|SFSpeechRecognizer|VNRecognizeText` 无命中）；识别全部在服务端（DashScope）。
- **AVFoundation**：录音、播放 TTS（`LioRelayVoiceInput.swift`、`LioSpokenPreviewButton.swift`、`LioTranslationPCM.swift` 等），本地处理。

---

**定位字段去向逐跳细节**（结论见正文第 2 节）

### A. App 是否读取设备定位

- **是，只有一处**：`ios/Modules/CJShell/Sources/CJLioUser/LioTaxiPickupLocation.swift`。`CLLocationManager.requestWhenInUseAuthorization()` + 一次性 `requestLocation()`，12 秒超时，拿到后立即 `stopUpdatingLocation`（`LioTaxiPickupLocation.swift:15-31, 57-76`）。产出 `LioTaxiPlace(nameZH:"当前位置", coordinate: WGS-84 原始经纬度)`，**不降精度**（`:41-46`）。
- 全仓 `CLLocationManager` 只此一处（grep `CLLocationManager|requestLocation|startUpdatingLocation`）。高德 SDK `showsUserLocation=false`（`AMapRecordedPlaceMap.swift:45`），MapKit：只有「附近」地图用了 `UserAnnotation()`（`LioNearbyView.swift:159`），即在 Apple 地图上画出用户当前位置——由系统 MapKit 本地使用定位权限绘制；Apple 是否因此收到位置属系统行为，**未核实**。其他 MapKit 视图未见 `showsUserLocation`/`UserAnnotation`。
- 权限说明 `NSLocationWhenInUseUsageDescription` 只写了「打开打车时使用你的位置设置起点」（`ios/App/Info.plist:61`），**但「附近」也会调用同一定位**（见 C2）——文案与实际用途不一致，值得登记表标注。
- `PrivacyInfo.xcprivacy` 申报的数据类型只有 UserID、DeviceID、OtherUserContent、CustomerSupport，**没有 PreciseLocation / CoarseLocation**（`ios/App/PrivacyInfo.xcprivacy`，grep 结果）——与「设备精确坐标上传到本方服务器再转给高德/滴滴」的事实不一致，需人工复核。

### B. 两个调用方

| 调用方 | 代码 | 用途 |
|---|---|---|
| 打车 | `LioTaxiEntry.swift:13-16` `currentPickup` | 起点「当前位置」；也作为地点搜索偏置 `near`（`LioTaxiView.swift:94, 483-484`） |
| 附近 | `LioNearbyView.swift:15-19` `currentLocation` | 周边搜索中心 / 逆地理「我在哪」 |

其余功能（Lio 对话/规划、酒店、路书、地铁周边、交通、天气、翻译、点餐）**都不读设备定位**：酒店只发城市+地标文字（`LioHotelOffers.swift:277-291`）；地铁周边只发 `city_id+station_id`（`backend/cj_api/metro_nearby.py:4-5`）；天气路由 App 未调用。

### C. 坐标流向（逐跳）

#### C1. 打车（设备 GPS → 香港 → 滴滴；→ 滴滴 App）
1. App → 香港 `/v1/tools/taxi/estimate`、`/v1/tools/taxi/link`：`origin{lat,lng,coordinate_system:"WGS-84"}`；`/v1/tools/taxi/search`：`near`（当城市匹配时）（`LioTaxiWire.swift:74, 117-127`；`backend/cj_api/taxi_tools.py:98-122, 147-152`）。
2. 香港服务端：WGS-84→GCJ-02 本地转换，格式化 6 位小数，检查在中国大陆内（`taxi_tools.py:252-261`）；**不落盘**（`PluginCalls` 只计次数，`plugin_tools.py:33-56`；访问日志不记 body/query，`deploy/hk/access_log.py:1-15`）。
3. 香港 → 滴滴 MCP：`maps_regeocode{location}`、`taxi_estimate{from_lat,from_lng,…,from_name}`、`taxi_generate_ride_app_link{from_lat,…}`、`maps_textsearch{location}`（`taxi_tools.py:356-415`）。
4. 滴滴返回的 `v.didi.cn` 链接 `slat/slng` 即该坐标；App 交给系统打开滴滴 App（`LioTaxiEntry.swift:20-25`）。
5. 本地存储：「最近地点」只记录用户选的**目的地**（`LioTaxiView.swift:96-102`、`LioTaxiPlaces.swift:96-110`），不存当前位置。
6. 英译：滴滴返回的 POI 名/地址（不是坐标）→ 翻译中继 → DashScope（`taxi_tools.py:301-345`）。

#### C2. 附近（设备 GPS → 香港 → 高德）
1. App → 香港 `/v1/tools/nearby/search`、`/v1/tools/nearby/reverse`：`center{lat,lng,coordinate_system:"WGS-84"}`（`LioNearbyRelay.swift:59-74, 270-274`）。
2. 香港 → 高德 `/v3/assistant/coordinate/convert?locations=<lng,lat 6 位>&coordsys=gps`，再 `/v5/place/around?location=…` 或 `/v3/geocode/regeo?location=…`（`backend/cj_api/nearby_tools.py:206-270`）。
3. 服务端进程内缓存 60 秒/32 条，键含精确坐标（`nearby_tools.py:218-262`）；计量账本无坐标（`nearby_budget.py:38-67`）。
4. 之后导航：App 只把**目的地 POI 坐标**放进 `iosamap://path` / `maps.apple.com?daddr=`（`LioNearbyView.swift:401-415`），不带当前位置。

#### C3. 未发现的流向
- **百炼 / 任何模型**：未发现设备坐标进入模型请求。Lio 对话管线不接触 CoreLocation；路书模型只收地点名/营业时间/地铁站（`lio_roadbook.py:255-258`）；点餐模型只收菜单文字（`lio_menu.py:7-8`）；翻译只收用户主动提交的文字/语音/图片（图片已去 EXIF，见 1.2）。
- **Trip.com / Klook / 12306 / 飞常准 / 和风 / ECB**：不收设备坐标。
- 唯一需要注意的「间接位置」：用户在对话、翻译、搜索框里**自己输入**的地址/地名，会原文发给百炼（对话、翻译）、滴滴（打车搜索词）、高德（酒店 `near` 地标、Lio 检索词）。

（C3 已完整，以上为定位专节全部内容。）

---

### 21. Airalo（eSIM）——代码里**无出站**

- `backend/**`、`deploy/**`：无任何 Airalo/Impact 主机、密钥变量或路由（`git grep -i airalo` 只命中 iOS 一个文件）。
- `ios/Modules/CJShell/Sources/CJLioUser/LioESIMPreviewView.swift`：静态「上网卡」预览页，点「在 Airalo 查看」只弹出提示「示例套餐没有购买链接」（`:64-70, 93`），**不打开任何 URL、不发请求**。
- 结论：M4.md 条目 16 已批准但未实现；当前不向 Airalo 发送任何数据。
