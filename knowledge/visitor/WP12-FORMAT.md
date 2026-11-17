# WP12 内容格式与消费约定

父票 #922，H 子票 #935；消费者 L #847 / C WP9 #932。以下是本地内容文件约定，不冻结或修改 FACT wire。

## 目录和兼容性

| 目录 / 格式 | 内容 | 读取入口 |
|---|---|---|
| `entries/*.json`，旧八字段 | 原有 12 条须知 | `load_entries` / `validate.py`，原接口和默认复核命令保持 |
| `entries-v2/*.json`，`visitor-entry.2` | 1 条场馆条件，2 条官方渠道指引 | `load_entries_v2` / `validate_v2.py` |
| `names/*.json`，`visitor-name.1` | 7 组 JT 已核对的 Wikidata 中英文标签、QID | `load_names` / `validate_names.py` |
| `examples/*.json` | 合成正例，只验证格式 | 禁止作真实知识检索 |

L 现有 `FACT-query.2/result.2` 和 `cj_fact.visitor.Entry.parse` 仅接受旧八字段及五主题。H 保留旧目录的八字段结构，避免让现有整包读取失败；#935 交付未改旧条目，后续实际复核仅在原格式内维护。
新目录须由 L 显式选择，追加 wire/消费版本并验证后使用，不能让旧 `.2` 解码器静默接受额外字段。兼容保留的退出条件是 L 确认旧消费者已迁移、已保存结果可读、回退验证完成；本次不删除旧路径。

## visitor-entry.2

每个文件仍是非空数组。记录保留原八字段，严格新增下面四项；不接受额外键。

| 字段 | 规则 |
|---|---|
| `format_version` | 固定 `visitor-entry.2` |
| `entry_kind` | `fact` 或 `official_channel` |
| `subject` | `fact` 必须有 `{key,name_zh,name_en,wikidata_qid}`；官方渠道必须为 `null` |
| `conditions` | 下表五键必须全部出现，未知用 `null` |

`subject.key` 是维护者的稳定地点键，小写字母/数字以点或连字符分段。`wikidata_qid` 可为 `null`，有值时必须是合法 `Q` 编号。
字段作用于这个具体地点的常规散客基本参观，不扩展到整座城市、团队、特展或临时活动。L/C 必须核对实际站点身份与适用范围，不能仅凭城市或模糊名称套用。
Wikidata 名称和政府来源中的译名可以不同；名称目录不证明两套供应商 POI 已完成身份映射。

| conditions 字段 | 机器语义 |
|---|---|
| `reservation_required` | `true` 明确需要预约；`false` 明确常规散客无需强制预约；`null` 未知。可选预约渠道存在不等于必须预约 |
| `closed_weekdays` | `null` 未知；`[]` 来源明确没有常规每周闭馆日；非空数组为无重复 ISO 周几，周一=1、周日=7。`[]` 不保证没有临时闭馆 |
| `closed_weekdays_public_holiday_exception` | 每周闭馆未知时必须 `null`；已知时必须布尔值。`true` 表示国家法定节假日例外，不能把普通周末或调休工作日一概当作法定节假日；空闭馆数组配 `false` |
| `advance_booking_days` | 非负整数或 `null`；必须与下项一起解释，未知不写 `0` |
| `advance_booking_rule` | `window_max`＝最多可提前多少天预约；`minimum_lead`＝至少须提前多少天预约；天数未知时规则也必须 `null`。最少提前要求仅在 `reservation_required=true` 时有效 |

实例：重庆体育博物馆政府公开指引区分了试营业与正式开放。常规散客免预约，周一例行闭馆但法定节假日例外；仍可选用最多提前 7 天的预约渠道。因此本条为 `false / [1] / true / 7 / window_max`，不能生成“必须提前七天预约”。
本条保留政府页的“正式开放后”常规范围；团体和临时活动需另查，不能由格式校验推断现场当前可用性。

## 免签与入境

新增主题 `visa_entry`，仅允许 `entry_kind=official_channel`，`subject=null`、五个条件全为 `null`；来源仅取已确认的国家移民管理局或外交部 hostname。
当前两条分别指向国家移民管理局政策解读栏目和官方首页，只有查询及向主管机关确认的指引。没有国籍清单、免签天数、入境材料或个体资格结论。
校验检查结构与官方来源边界，不把文本规则检查当成法律正确性证明。§0.6 所要求的模型路由、禁止凭印象补答案和无命中行为由 L 接入并测试，H 本次只交内容。

## visitor-name.1

严格字段为 `format_version,id,place_key,wikidata_qid,name_zh,name_en,cities,source_urls,checked_on,expires_on,license`。
版本固定 `visitor-name.1`，许可固定 `CC0-1.0`。`name_zh` 和 `name_en` 保留同一实体的原始 `zh` / `en` 标签；缺标签不自译、不补造，不做繁简或坐标转换。
来源必须恰为 `https://www.wikidata.org/wiki/<同一QID>`。同批 `id`、`place_key`、QID 均唯一；坐标、经纬度及其他未定义字段被拒绝。
核对与人工确认记录、7 个实体和查询用量见 [NAMES.md](NAMES.md)。此目录不承载营业、预约、价格或地理坐标事实。

## 校验和 30 天复核

```sh
uv run --locked python -B -m unittest discover -s knowledge/visitor -p 'test_*.py' -v
uv run --locked python -B knowledge/visitor/validate.py knowledge/visitor/entries/*.json
uv run --locked python -B knowledge/visitor/validate_v2.py knowledge/visitor/entries-v2/*.json
uv run --locked python -B knowledge/visitor/validate_names.py knowledge/visitor/names/*.json
uv run --locked python -B knowledge/visitor/review_due.py knowledge/visitor/entries/*.json
uv run --locked python -B knowledge/visitor/review_due.py --format v2 knowledge/visitor/entries-v2/*.json
uv run --locked python -B knowledge/visitor/review_due.py --format names knowledge/visitor/names/*.json
```

复核窗口仍含第 30 天，排序和失败传播保持；过期、缺字段或损坏数据退出 1，不输出部分成功。v2 报告保留完整条件和地点，名称报告保留中英名/QID/许可，均有来源和核对/失效日期。
旧默认命令仍只接受旧格式，不做格式猜测或自动降级。所有文件入口共享仓库原严格 JSON 解析器、日期校验和过期拒绝；边界内已验证值不重复检查。

| 内容组 | 数量 | 失效日（日初，北京时间） | 最迟内容复核 |
|---|---|---|---|
| 场馆条件 | 1 | 2026-11-23 | **2026-11-22 18:00** |
| 官方渠道指引 | 2 | 2026-12-16 | 2026-12-15 18:00 |
| Wikidata 名称 | 7 | 2027-02-11 | 2027-02-10 18:00 |

2026-11-25 前的常规复核已于 **2026-11-16**完成：旧格式 10 条、v2 3 条重新读取原政府来源后更新日期，内容/条件不变；另 9 条不满足本轮筛选条件，保留日期。见 [复核记录](reviews/2026-11-16.md)。以上为手工维护约定，没有创建自动任务。

## visitor-entry.3：九城追加格式（#1056）

旧八字段、visitor-entry.2、visitor-name.1 的字段及城市/主题接受集合不变，原22条保留；后续内容复核可更新正文、来源和日期，不改条目ID或旧字段结构。新增文件在 `entries-v3/*.json`，只通过 `load_entries_v3` / `validate_v3.py` 显式读取，不递归混入旧目录。它是本地内容版本，不冻结或启用任何 FACT wire。

键集合与 v2 相同，`format_version` 固定 `visitor-entry.3`；新增城市键 `taizhou-zhejiang` / `suzhou-anhui`，分别指浙江台州/安徽宿州，拒绝裸 `taizhou` / `suzhou`，不得绑定江苏城市。主题在 v2 基础上允许 `seasonal_holiday`。

五个 conditions 字段及其 `null`、周几、假日例外、`window_max` / `minimum_lead` 语义完全沿用。地点事实仍要求 exact subject 四键；**城域通用事实可 `subject=null`，但五条件必须全null**，不能把通用铁路指引套作整座城市的景区免预约或闭馆规则。
`official_channel` 仅用于 `visa_entry` 或 `seasonal_holiday`，subject及五条件全null。免签/入境仍仅允许已批 NIA/MFA 官方渠道，禁止生成资格事实。

三个新增来源批准仅在新版本生效：`www.zjtz.gov.cn` 限浙江台州场馆规则，`www.ahsz.gov.cn` 限安徽宿州场馆规则（主题passport_booking、单城且有subject）；`www.gov.cn` 限seasonal_holiday。子域和其他网站拒绝。清单与批准证据见 SOURCES.md。

```sh
uv run --locked python -B knowledge/visitor/validate_v3.py knowledge/visitor/entries-v3/*.json
uv run --locked python -B knowledge/visitor/review_due.py --format v3 knowledge/visitor/entries-v3/*.json
```

复核输出沿用v2的完整subject/conditions字段，不做格式猜测。首批五条补两城五主题，核对2026-11-16；三条30天指引12-16日初失效，手机卡2027-01-15、紧急号码2027-02-14。原7城旧目录不重复写入新城市。
L需显式追加城市/主题及新格式消费者，C按实际subject与时效使用；旧FACT .2不直接接受新数据。旧路径退出仍须L核迁移/已保存结果/回退，本次不删旧路径。覆盖和票据见 ACCEPTANCE-COVERAGE.md。

最初由JT在#702逐批确认的政府部门、公共文博机构及限定景区官方经营机构来源继续保留。后续JT明确授权H代批正确、正常的信息源；本Goal可在#702记录核验依据后，将范围明确的公开商业指南、媒体或平台资料加入SOURCES.md。来源批准不等于字段正确，仍须逐条核对、独立R及精确CI，未知核心条件不计补齐；正文注明真实发布方和证据局限，不将商业资料写成景区官方政策。免签/入境的官方渠道限制及Wikidata名称授权不变。

新增来源在验证器绑定对应城市、passport_booking主题和非空subject；机构host按已批准范围接受，较窄的单篇或平台资料仅接受精确URL，不扩大整站、子域、其他查询或主题。原三格式不采用这些新来源，不改变FACT wire或消费者权限。候选www.szmuseum.com实为江苏苏州博物馆，仍从本Goal清单及验证器排除。

## 来源与证据边界

新政府材料均在 #843/6818584957 已确认范围内：

- [国家移民管理局政策解读](https://www.nia.gov.cn/n741440/n741577/index.html)：2026-11-16 复核；只采用渠道信息。
- [国家移民管理局官方入口](https://www.nia.gov.cn/index.html)：2026-11-16 复核；不复制政策、收费或统计内容。
- [重庆体育博物馆参观指南](https://www.cq.gov.cn/zwgk/zfxxgkml/zdlyxxgk/ggwh/wh/zxdt/202507/t20250714_14813861.html)：2025-07-14 发布，2026-11-16 复核；采用 8 月 1 日正式开放后的常规规则，不把试营业预约要求带入。短失效期不等于保证场馆没有临时调整。

在 #935 的 2026-11-13 收集时，北京候选页面多次返回 403，未采用其搜索摘要作为已核对条件，也未换路径/身份绕过。国家移民管理局最初读取遇压缩内容解码错误，后按响应压缩格式正确读取同一获批公开站点；没有放宽 TLS 或权限检查。
网页核对、离线格式测试、L 现有旧格式消费、新格式工具接线和 C 提醒生成分别计证；新格式接线、真实模型回答、提醒效果与现场办理均尚未验证。
