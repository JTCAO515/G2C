# 外国游客常用 App 与工具候选池（全部“待核实”）

本目录存放**尚未核实**的常用 App/工具候选，服务对象是来华外国游客，覆盖支付、地图、打车、铁路、城市公共交通、翻译、通信上网、住宿/行程预订及其他实用工具。

与正式内容的边界：

- 本目录任何记录都**不是已确认事实**，不得直接进入 Lio 回答、FACT wire、GitHub Pages 事实快照或任何消费者。
- 本目录与 `entries/`、`entries-v2/`、`entries-v3/`、`names/` 物理分开；不改变既有格式、校验器、来源白名单或消费者权限。
- 本目录与 2026-11-18 城市/场馆候选批次（`knowledge/visitor/candidates/`，PR #1195）分开维护：那一批使用以城市、地点和主题为核心的 `visitor-candidate.1`；本批需要记录工具中英文名、工具分类、支持语言、使用前准备和官方下载入口，字段不同，因此另立 `visitor-tool-candidate.1`，避免修改 #1195 正在使用的文件。

## 文件

| 文件 | 内容 |
|---|---|
| `README.md` | 本说明：边界、格式、校验、晋级流程 |
| `2026-11-18-apps-and-tools.json` | 本批 24 条候选，非空 JSON 数组，格式 `visitor-tool-candidate.1` |
| `2026-11-18-apps-and-tools.md` | 供人工浏览和复核的表格、缺口与冲突摘要；JSON 是唯一数据源 |
| `../validate_tool_candidates.py` | 只读格式校验器，不联网、不抓取、不写记录 |
| `../test_validate_tool_candidates.py` | 校验器单元测试 |

## 格式 `visitor-tool-candidate.1`

每个记录严格包含下列字段，不接受额外键：

| 字段 | 规则 |
|---|---|
| `format_version` | 固定 `visitor-tool-candidate.1` |
| `id` | `tool-candidate.<收集日期>.<slug>`；小写字母/数字，以点或连字符分段；日期段必须等于 `collected_on`；全批次唯一 |
| `name_zh` | 非空中文名 |
| `name_en` | 非空英文名 |
| `category` | `payment`、`map`、`taxi`、`rail`、`city_transport`、`translation`、`communication`、`booking`、`other` 之一 |
| `purpose_zh` | 非空中文用途概括，最多 600 字；写“能解决什么问题”，不复制整段原文 |
| `cities` | 非空数组；全国性用 `nationwide`，城市特定用现有城市键（如 `shanghai`、`beijing`、`guangzhou`） |
| `languages` | 非空数组；已知语言逐项写，不确定写“待核实”或“未知”，不编造 |
| `preparation` | 非空数组；使用前可能需要准备的手机号、证件、银行卡、设备或网络条件；不确定写“待核实” |
| `official_links` | 数组，可为空；每项 `{name,url,type}`，`type` 为 `official_site`、`official_store`、`official_help`；没有找到官方入口时留空并在 `missing` 写“官方入口待补充” |
| `sources` | 非空数组；每项 `{name,url,type,language,published_on,valid_until}`；至少一个来源，URL 优先 https，官方页仅有 http 时按原样记录（无片段/账号密码）；`published_on` 只在来源页明确标注发布日期时填写；`valid_until` 只在来源页明确给出有效期时填写；未知用 `null` |
| `collected_on` | 固定 `YYYY-MM-DD`；本批为 `2026-11-18`；不能晚于校验当天 |
| `status` | 固定 `待核实` |
| `missing` | 字符串数组，列出未知或缺少的关键信息（可为空数组） |
| `notes` | `null` 或非空字符串；写适用范围、证据局限、来源口径差异 |
| `conflicts` | 字符串数组，记录与其他来源或既有条目的明显冲突（可为空数组） |
| `related_entries` | 字符串数组，可能相关/重复的既有正式条目 id（以 `visitor.` 开头，可为空数组），供后续查重 |

来源类型：`official_government`（政府）、`official_operator`（交通/通信等运营方）、`official_tool`（工具/平台官方站点或帮助页）、`official_store`（官方应用商店页面）、`official_media`（官方媒体/政府新闻）、`commercial_platform`（商业平台）、`other_public`（其他公开来源或机构身份未核实）。**来源类型只是如实标注，不代表已批准或已核实。**

## 校验

沿用仓库锁定环境；在仓库根目录运行：

```sh
uv run --locked python -B -m unittest discover -s knowledge/visitor -p 'test_*.py' -v
uv run --locked python -B knowledge/visitor/validate_tool_candidates.py knowledge/visitor/tool-candidates/*.json
```

校验检查字段集合、id/日期、枚举、URL 形状、来源发布日期和重复项；任一文件失败退出 1，不输出部分成功。它不是内容正确性证明，也不联网。

## 2026-11-18 批次

- 共 **24 条**候选：支付 3、地图 3、打车 1、铁路 1、城市公共交通 4、翻译 3、通信上网 4、预订 2、其他 3。
- 覆盖 `nationwide` 19 条；城市特定 5 条（北京 2、上海 1、广州 1、深圳 1）；全国性工具不自动展开到具体城市。
- 按条目主来源统计：政府/官方媒体 11 条、运营方/工具官方 8 条、官方应用商店 2 条、商业平台 3 条；辅助来源含政府、工具官方、应用商店和商业平台多类。
- 24 条均至少列出一项 `missing`；6 条记录到明显冲突或口径差异；所有条目 `status=待核实`。
- 地方面：除上海 Metro 大都会、北京亿通行、广州地铁外，本批补入**深圳地铁国际银行卡拍卡过闸**（官方公告，2026-09-22）与**北京英文地图 Beijing Map**；原“百度地图 / Beijing Map 英文版”合并条目已拆成两条独立候选，避免把两个不同产品混为一条。
- 采集方式为公开网页只读访问和检索定位；未登录、未填表、未购票、未调用站点接口/小程序、未使用付费服务；原件、网页快照和运行日志未入库。
- **本批未做全面查重、未统一纠错、未逐条事实复核**；重复、冲突和未知均原样保留。

## 晋级为正式事实（后续轮次）

1. 人工复核：打开官方入口和来源页，确认工具主体、当前功能、支持语言、使用前准备、下载渠道和时效；官方应用商店页与商业平台说明不自动等同官方政策。
2. 查重：与既有 `entries*/`、`candidates/` 及同批候选比对，处理重复与冲突；冲突保留证据，不静默合并。
3. 来源批准：按 #702/#843 既有流程在 `SOURCES.md` 记录来源范围（本目录的收集不构成批准）。
4. 写入正式格式：工具条目与现有以地点为核心的 `visitor-entry.2/3` 不同，晋级前需由内容维护者与 L 决定是否新增工具条目格式及消费者；不得直接把本目录 JSON 塞进现有条目或 FACT wire。
5. 晋级后从候选池删除或标注去向，避免同一内容两处维护。

本目录不保存抓取原件、网页快照或运行日志；来源只留 URL 和概括。
