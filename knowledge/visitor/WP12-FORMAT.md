# WP12 内容格式与消费约定

父票 #922，H 子票 #935；消费者 L #847 / C WP9 #932。以下是本地内容文件约定，不冻结或修改 FACT wire。

## 目录和兼容性

| 目录 / 格式 | 内容 | 读取入口 |
|---|---|---|
| `entries/*.json`，旧八字段 | 原有 12 条须知 | `load_entries` / `validate.py`，原接口和默认复核命令保持 |
| `entries-v2/*.json`，`visitor-entry.2` | 1 条场馆条件，2 条官方渠道指引 | `load_entries_v2` / `validate_v2.py` |
| `names/*.json`，`visitor-name.1` | 7 组 JT 已核对的 Wikidata 中英文标签、QID | `load_names` / `validate_names.py` |
| `examples/*.json` | 合成正例，只验证格式 | 禁止作真实知识检索 |

L 现有 `FACT-query.2/result.2` 和 `cj_fact.visitor.Entry.parse` 仅接受旧八字段及五主题。H 保留旧目录的全部内容字节，避免让现有整包读取失败。
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
| 新场馆条件 | 1 | 2026-11-20 | **2026-11-19 18:00** |
| 新官方渠道指引 | 2 | 2026-12-13 | 2026-12-12 18:00 |
| Wikidata 名称 | 7 | 2027-02-11 | 2027-02-10 18:00 |

原 12 条的常规复核仍须在 2026-11-25 前完成，本次明确为 **2026-11-24 18:00 前**；原核对日期及失效日期未机械延长。以上为手工维护约定，没有创建自动任务。

## 来源与证据边界

新政府材料均在 #843/6818584957 已确认范围内：

- [国家移民管理局政策解读](https://www.nia.gov.cn/n741440/n741577/index.html)：2026-11-13 核对；只采用渠道信息。
- [国家移民管理局官方入口](https://www.nia.gov.cn/index.html)：2026-11-13 核对；不复制政策、收费或统计内容。
- [重庆体育博物馆参观指南](https://www.cq.gov.cn/zwgk/zfxxgkml/zdlyxxgk/ggwh/wh/zxdt/202507/t20250714_14813861.html)：2025-07-14 发布，2026-11-13 核对；采用 8 月 1 日正式开放后的常规规则，不把试营业预约要求带入。短失效期不等于保证场馆没有临时调整。

北京候选页面本次多次返回 403，未采用其搜索摘要作为已核对条件，也未换路径/身份绕过。国家移民管理局最初读取遇压缩内容解码错误，后按响应压缩格式正确读取同一获批公开站点；没有放宽 TLS 或权限检查。
网页核对、离线格式测试、L 现有旧格式消费、新格式工具接线和 C 提醒生成分别计证；新格式接线、真实模型回答、提醒效果与现场办理均尚未验证。
