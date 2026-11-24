# TAXI.1 · 打车信息

`POST /v1/tools/taxi/estimate`、`POST /v1/tools/taxi/link` 和 `POST /v1/tools/taxi/search`（地点搜索，见下文）。使用现有 App Bearer 和已批准的内部测试账号名单。香港的供应商验证完成前，路由统一关闭。有 Bearer 格式的请求返回 `403 not_enabled`。客户端用现有 `X-Request-ID` 关联请求。

## 请求

估价和链接均接收以下 JSON。经纬度使用有限 JSON 数字，地名可以省略。地名为 1–120 个字符、去空白后非空，不得含控制字符（C0、DEL、C1）、代理项、行/段分隔符或双向控制字符（U+061C、U+200E、U+200F、U+202A–U+202E、U+2066–U+2069），否则 `400 invalid_request`；零宽连接符、软连字符等其他格式字符允许。链接可另外带单个 `vehicle_category`，值来自估价车种。当前授权下该字段不发送给滴滴，客户端不得把返回链接展示为已选择车型。未知字段拒绝。

```json
{
  "version": "TAXI.1",
  "origin": {"lat": 39.9, "lng": 116.4, "coordinate_system": "WGS-84", "name": "北京西站"},
  "destination": {"lat": 40.05, "lng": 116.3, "coordinate_system": "GCJ-02"}
}
```

坐标系标记仅接受 `WGS-84`、`GCJ-02`。发布版本使用本地大陆地图单元先检查两端，再将标记为 `WGS-84` 的点转换为 `GCJ-02`。出境或不在服务范围内的点返回 `422 out_of_service_area`，在调用滴滴前完成。估价使用供应商按坐标逆地理返回的中文 `display_name` 或 `formatted_address`。客户端地名供本机展示，无法核实地名时返回 `422 coordinate_unverified`。发给供应商的估价与链接坐标为 6 位小数字符串。 [京沪同点验证](https://github.com/JTCAO515/G2C/issues/1309#issuecomment-7090786405)

| 操作 | 200 字段 |
| --- | --- |
| 估价 | `version`、`vehicles[].{category,name,currency,price_display}`、`observed_at`（ISO 8601）。`category` 和 `price_display` 分别保留滴滴 `productCategory` 与 `priceText`。客户端可按车型代码本地化名称。供应商给出可核实区间和距离时，可附 `price_min_minor`、`price_max_minor`（CNY 分）和 `distance_m`。可附 `trace_id`。区间和距离缺失时省略。 |
| 链接 | `version`、`url`、`link_type=https`。已验证的供应商 `appLink` 使用 `https://v.didi.cn/XvYQEWe`，只接收与本轮起终点一致的四个坐标查询参数。真机落地以 [阶段 0](https://github.com/JTCAO515/G2C/issues/1309) 为准。 |

错误示例为 `{"error":"quota_exceeded"}`。非法坐标、身份字段或未知字段返回 `400 invalid_request`。缺少有效登录为 `401 sign_in_required`。非内测账号为 `403 not_enabled`。超过 4 KiB 为 `413 request_too_large`。达到单项每日 50 次为 `429 quota_exceeded`，供应商限流为 `429 rate_limited`。滴滴 `-32001` 触发一次退避重试，仍限流则返回 `429 rate_limited`。`-32002` 记录固定告警并返回 `502 supplier_unavailable`。`-32010` 返回 `400 invalid_request`。`-32021` 只重新估价一次，链接可用同一请求参数继续一次。`-32050` 返回 `502 supplier_unavailable`。超时为 `504 supplier_timeout`，本地依赖不可用为 `503 unavailable`。

Asia/Shanghai 每日分别统计每个账号的估价和链接调用次数。鉴权通过且请求有效后，在供应商分发前持久预留一次，包括结果未知的请求。价格或链接重试在对应操作另外预留，链接过期引发的补估价使用原估价额度。逆地理调用记到同账号的独立计数。滴滴只接收工具所需的坐标与地点名称。账户、手机号、App 凭据及原始请求均不进入供应商载荷或计数记录。只支持信息型工具。

## 地点搜索

`POST /v1/tools/taxi/search` 供起点、终点输入框按城市搜索地点。鉴权、内测名单、4 KiB 上限和 `Cache-Control: no-store` 与估价相同。未知字段拒绝。

```json
{"version": "TAXI.1", "query": "天安门", "city": "北京", "near": {"lat": 39.9, "lng": 116.4, "coordinate_system": "WGS-84"}}
```

- `query`：1–100 个字符，去掉首尾空白后非空，字符规则同上文地名，否则 `400 invalid_request`。
- `city`：中文城市名（2–24 个汉字），或英文别名 `Beijing`、`Shanghai`、`Chengdu`（大小写不敏感）。先去掉「中国」「中國」前缀；不以「市」「自治州」「地区」「盟」结尾时补「市」。其他文字（含拉丁字母、数字）为 `400 invalid_request`。香港、澳门及台湾地区的城市名（以香港、澳门/澳門、台湾/臺灣、台北、新北、桃园、台中、台南、高雄、基隆、新竹、嘉义、花莲、台东、屏东、宜兰、苗栗、彰化、南投、云林、澎湖、金门、马祖等繁简写法开头，或英文别名 `Hong Kong`、`HongKong`、`Macau`、`Macao`、`Taipei`、`Taiwan`）不补「市」，返回 `422 out_of_service_area`，不调用滴滴。福建连江等同名大陆地名照常处理。
- `locale`：可选，`zh`（默认）或 `en`，其他值为 `400 invalid_request`。只有 `en` 才补英文字段，见下文。
- `near`：可选，与估价的坐标对象相同（`name` 规则同 `query`）。只用作滴滴结果排序参考点，先做大陆服务范围检查并转为 `GCJ-02`；范围外返回 `422 out_of_service_area`，不调用滴滴；越界或非数字坐标为 `400 invalid_request`。

滴滴只收到 `keywords`、`city`，以及有 `near` 时的 `location`（`lng,lat`，6 位小数）。调用不重试。

200 返回 `{"version": "TAXI.1", "items": [...]}`，最多 20 项，按滴滴顺序：

| 字段 | 说明 |
| --- | --- |
| `name_zh` | 滴滴 `display_name`，非空字符串，1–120 个字符，字符规则同上文地名 |
| `address_zh` | 滴滴 `address`，缺失时用 `address_all`；为空、超过 240 个字符或含上文地名规则禁止的字符时为 `null` |
| `city` | 规范化后的请求城市 |
| `lat`、`lng` | 有限数字；供应商给 JSON 数字（实测）或纯十进制字符串时都接受 |
| `coordinate_system` | 固定 `GCJ-02` |
| `name_en` | 可选，仅 `locale=en`：`name_zh` 的英文译名，1–200 个字符，字符规则同地名且不含汉字 |
| `address_en` | 可选，仅 `locale=en`：`address_zh` 的英文译文，规则同 `name_en`；`address_zh` 为 `null` 时一定省略 |

英文字段（M4 授权条目 9 增补，#1457）：服务端用调用者自己的登录凭据，经香港翻译中转，把本次结果中尚未缓存的名称和地址按行合成一段文字（每行前加 `[序号]`），做一次千问文字翻译（`TRANSLATION.1`，`qwen-mt-flash`，中译英）。这次翻译计入调用者「每人每天文字 300 次」与翻译子额度，鉴权、名单和计费由翻译中转负责。合成文字最多 1500 个字符，放不下的条目本次不翻译（若已有缓存仍返回缓存译文）。译文必须逐行带回相同序号，行被合并、拆分或换序时整批放弃，不猜配对。译文按 `(name_zh, address_zh)` 缓存在服务端进程内（有界），命中缓存不再计次。以下情况都只省略对应英文字段，状态码和中文字段不变，不会因翻译返回 429 或 502：翻译不可用、超时（约 12 秒）、额度用尽、翻译名单外、返回行数与送出行数不符、译文为空或超长、含不可见字符或汉字（含 CJK 扩展区、兼容区与全角标点）。给司机看的仍是中文。

结果行的城市（规范化后）与请求不同，或坐标不在大陆服务范围内，则跳过。全部结果都被这样跳过，或滴滴无结果时返回空 `items`。结果行缺字段、`display_name` 或 `city` 不是字符串、坐标非数字、名称不合规等无法投影时跳过；没有任何可用行且至少有一行无法投影时返回 `502 supplier_unavailable`。

错误：`400 invalid_request`、`401 sign_in_required`、`403 not_enabled`、`413 request_too_large`、`422 out_of_service_area` 同上。每账号每日（Asia/Shanghai）搜索路由 50 次，超出 `429 quota_exceeded`。鉴权与请求校验通过后先持久预留路由一次，再在调用滴滴前预留 `didi:maps_textsearch` 一次（上限 50）；城市或 `near` 在服务范围外时只占路由次数。超时（`504 supplier_timeout`）、传输失败与无法解析的结果（`502 supplier_unavailable`）照计次数，不退回。滴滴 `-32001` 不重试，直接 `429 rate_limited`；`-32010` 为 `400 invalid_request`；`-32002`（固定告警）、`-32021`、`-32050` 及其他错误为 `502 supplier_unavailable`。错误正文只有 `error` 代码，不回显供应商消息。

本地服务范围数据来自 [Natural Earth v5.1.2 的 1:10m CHN map unit](https://github.com/nvkelso/natural-earth-vector/releases/tag/v5.1.2)。转换公式来源及许可见 [coordtransform](https://github.com/wandergis/coordtransform)。
