# 外国游客候选资料池（全部“待核实”）

采集与核验流程参见 [H 线知识采集与核验标准](../COLLECTION-STANDARD.md)。

本目录存放**尚未核实**的候选资料，用来逐步扩大 G2C 外国游客知识库的城市与问题覆盖。它和 `entries/`、`entries-v2/`、`entries-v3/`、`names/` 里的正式内容**物理分开**，两者不能混读：

- 本目录任何记录都**不是**已确认事实，不得直接进入 L 的回答、FACT wire、GitHub Pages 事实快照或任何消费者。
- 正式条目（`entries*/`）仍按既有流程维护：来源批准、逐条核对、独立审查、精确 CI。晋级规则见文末。
- 本目录不改变任何既有格式、校验器、来源白名单或消费者权限。

## 为什么单独建这个池子

Lio 需要覆盖更多城市、更多问题（首次来华、城市景点、行程规划、签证官方渠道等）。如果每条都先走完整核实，收集速度会受限于复核人力。因此先按统一字段把候选批量收进来，如实标注来源类型、缺失项和冲突，供后续集中查重、复核和晋级；本轮不做全面查重、不统一纠错、不逐条复核。

## 文件

| 文件 | 内容 |
|---|---|
| `README.md` | 本说明：边界、格式、晋级流程 |
| `2026-11-18-*.json` | 2026-11-18 批次候选，按收集分组存放；每个文件是非空 JSON 数组 |
| `INDEX.md` | 本轮候选的维护索引（城市/主题覆盖、分组清单）；JSON 是唯一数据源 |
| `2026-11-18-gaps-and-conflicts.md` | 本批采集方式、来源缺口、明显冲突与后续复核重点 |

校验器在 `knowledge/visitor/validate_candidates.py`，测试在 `knowledge/visitor/test_validate_candidates.py`。校验只检查结构、日期、枚举与 URL 形状，不联网、不证明内容正确或来源已批准。

## 格式 `visitor-candidate.1`

每个记录严格包含下列字段，不接受额外键：

| 字段 | 规则 |
|---|---|
| `format_version` | 固定 `visitor-candidate.1` |
| `id` | `candidate.<收集日期>.<分组>.<slug>`，小写字母/数字，以点或连字符分段；日期段必须等于 `collected_on`；全批次唯一 |
| `title_zh` | 非空中文标题，概括候选主题 |
| `summary_zh` | 非空中文概括，最多 600 字；必须是自己写的概括，不整段复制原文 |
| `cities` | 非空数组；城市键见下；全国性内容用 `nationwide` |
| `place` | `null` 或 `{name_zh, name_en, address}`；`name_zh` 非空，后两项可为 `null`；不存坐标 |
| `audience` | 非空数组，简短中文描述适用人群（如“普通散客；首次来华游客”） |
| `themes` | 非空数组，见下方主题枚举 |
| `sources` | 非空数组，每项 `{name, url, type, language, published_on, valid_until}`；至少一个来源，URL 优先 https，来源页仅有 http 时按原样记录（无片段/账号密码）；`published_on` 只在来源页明确标注发布日期时填写；`valid_until` 只在来源页明确给出有效期时填写；两者未知用 `null` |
| `collected_on` | 固定 `YYYY-MM-DD`，本轮为 `2026-11-18`；不能晚于校验当天 |
| `status` | 固定 `待核实` |
| `missing` | 字符串数组，列出未知或缺少的关键信息（可空数组）；不确定的写“未知”，不编造 |
| `notes` | `null` 或非空字符串，写适用范围、证据局限（如“商业平台，非官方政策”“机构身份未独立核实”） |
| `conflicts` | 字符串数组，记录与其他来源或既有条目的明显冲突（可空数组） |
| `related_entries` | 字符串数组，可能相关/重复的既有正式条目 id（`visitor.` 开头，可空数组），供后续查重 |

城市键：`beijing`、`shanghai`、`guangzhou`、`shenzhen`、`chengdu`、`xian`、`hangzhou`、`chongqing`、`suzhou-jiangsu`（江苏苏州）、`nanjing`、`wuhan`、`changsha`、`guilin`、`xiamen`、`qingdao`、`harbin`、`kunming`、`zhangjiajie`、`luoyang`、`sanya`、`taizhou-zhejiang`（浙江台州）、`suzhou-anhui`（安徽宿州）、`nationwide`。注意 `suzhou-jiangsu` 与 `suzhou-anhui` 不可混用。

主题枚举：`payment`、`internet`、`transport`、`rail`、`passport_booking`、`emergency`、`arrival`、`attraction`、`trip_planning`、`accessibility`、`family`、`visa_entry`、`seasonal_holiday`。其中 `visa_entry` 只允许官方查询渠道，不写资格或法律判断。

来源类型：`official_government`（政府）、`official_venue`（场馆/景区官方）、`official_transport`（交通运营方）、`official_media`（官方媒体/政府新闻）、`intergovernmental`（政府间组织）、`commercial_platform`（商业平台，如携程/去哪儿/Trip.com/本地宝）、`map_platform`（地图平台）、`other_public`（其他公开来源或机构身份未核实）。**来源类型只是如实标注，不代表已批准或已核实。**

## 校验

沿用仓库锁定环境；在 `knowledge/visitor/` 目录下运行：

```sh
uv run --locked python -B -m unittest discover -s knowledge/visitor -p 'test_*.py' -v
uv run --locked python -B knowledge/visitor/validate_candidates.py knowledge/visitor/candidates/*.json
```

校验检查字段集合、id/日期、枚举、来源 URL 形状、过期状态；任一文件失败退出 1，不输出部分成功。它不是内容正确性证明，也不联网。

## 2026-11-18 批次

- 共 **75 条**候选，分 7 个文件：首次来华基础 14、华南与东南城市 12、华东城市 11、中西部城市 12、北方及其他城市 12、行程规划与官方渠道 12、人工补充的官方渠道 2。
- 覆盖 18 个城市、共 19 个城市键（北京、上海、广州、深圳、成都、西安、南京、苏州（江苏）、武汉、长沙、重庆、桂林、厦门、青岛、哈尔滨、昆明、张家界、洛阳）加 `nationwide`；13 个主题全部有内容。
- 来源类型：政府 35、场馆/景区官方 26、交通运营方 8、商业平台 3、其他公开来源 2、官方媒体 1（按条目主来源统计，另有少量条目含多来源）。
- 42 条来源页未标注发布日期；17 条记录到明显冲突或口径差异；全部条目 `missing` 均至少列出一项缺口（本批要求缺失即写“未知”，不编造补齐）。
- 采集方式为公开网页只读抓取 + 检索定位，未登录、未调用接口、未使用付费服务；原件与运行日志未入库。未做全面查重与逐条复核。

查阅：[INDEX.md](INDEX.md)（城市/主题索引与逐条清单）、[2026-11-18-gaps-and-conflicts.md](2026-11-18-gaps-and-conflicts.md)（缺口、冲突、复核顺序）。

## 晋级为正式事实（后续轮次）

1. 人工复核：打开候选的原始来源，确认机构身份、正文支持、中英含义与时效；商业平台资料不自动等同官方政策。
2. 查重：与既有 `entries*/` 及同批候选比对，处理重复与冲突；冲突保留证据，不静默合并。
3. 来源批准：按 #702/#843 既有流程在 `SOURCES.md` 记录来源范围（本目录的收集不构成批准）。
4. 写入正式格式：按 `entries-v3/`（visitor-entry.3）或后续版本落条目，附 `checked_on`/`expires_on`，走独立审查与精确 CI。
5. 晋级后从候选池删除或标注去向，避免同一内容两处维护。

本目录不保存抓取原件、网页快照或运行日志；来源只留 URL 和概括。
