# 七城 POI 候选库 · 第二轮（2026-11-18）

第二轮在第一轮 4043 条基线上补缺口、补细字段。所有记录仍为 **待复核**，是候选资料，不进入正式事实、GitHub Pages 数据或 Lio 正式回答。

## 目录

| 文件 | 内容 |
|---|---|
| `AUDIT.md` | 第一轮基线盘点：城市 × 区县 × 品类、城市 × 二级品类、缺口与已知来源限制 |
| `audit_district_category.csv` | 区县 × 一级品类逐格计数（715 行，含第一轮/第二轮新增/状态） |
| `audit_subcategory.csv` | 城市 × 二级品类逐格计数（336 行，含第一轮/第二轮新增/状态） |
| `audit_district_subcategory.csv` | 区县 × 二级品类全交叉（6864 行，含空档格与「仍空档/本轮已补」状态） |
| `<city>-new.csv` | 本轮新增 POI，表头与第一轮一致；`row_id` 从第一轮同城最大号顺延 |
| `<city>-enrich.csv` | 原条目补细，按第一轮 `row_id` 关联，长表格式 |
| `all-cities-new.csv` / `all-cities-enrich.csv` | 七城新增与补细合并表 |
| `ROUND2-SUMMARY.md` | 七城基线 / 新增 / 补细 / 剩余缺口汇总 |
| `<city>-SUMMARY.md` | 每城短汇总：新增分布、补细、目录、缺口 |

## 新增 POI 表

表头与第一轮 34 列完全相同（`row_id`…`tags`），规则沿用第一轮 README：

- `row_id`：同城顺延第一轮最大号，不复用、不改旧号。
- 每个新增地点至少一个能支持其身份的直接来源页；目录页覆盖多条时 `source_name` 写目录名 + 条目名/序号。
- 英文名四类标记；`官方英文`/`来源已有英文` 必须附 `name_en_source_url`；机器翻译/拼音转写留空并在 `name_en_note` 说明。
- 缺地址、分店、菜系等写“未知”或留空，不猜测。

## 补细表（长表）

列为：`row_id, city, field, old_value, new_value, source_name, source_type, source_url, collected_on, notes`。

- `row_id` 必须存在于第一轮 CSV；`city` 与基线一致。
- `field` 只允许：`district`、`subcategory`、`address_zh`、`branch_name`、`brand_or_parent`、`attraction_level`、`cuisine`、`signature_dishes`、`accommodation_type`、`venue_type`、`nearest_metro`、`official_website`、`name_en`、`name_en_type`、`name_en_source_url`、`name_zh_alt`、`notes`。
- `old_value` 必须与第一轮该字段完全一致；`new_value` 非空且与旧值不同；同一 `row_id + field` 只能出现一次。
- 每条补细必须有支持该字段的 `source_url`；不能拿支持名称的页面冒充地址来源。

## 校验

```sh
uv run --locked python -B -m unittest knowledge/visitor/test_poi_round2.py -v
uv run --locked python -B knowledge/visitor/validate_poi_round2.py \
  --baseline knowledge/visitor/place-candidates/seven-cities-2026-11/{beijing,shanghai,guangzhou,shenzhen,chengdu,chongqing,guilin}.csv \
  --new knowledge/visitor/place-candidates/seven-cities-2026-11/round2/*-new.csv \
  --enrich knowledge/visitor/place-candidates/seven-cities-2026-11/round2/*-enrich.csv
```

校验器检查：新增行沿用第一轮的列/城市/品类/英文/来源规则，`row_id` 不得与基线冲突；补细行 `row_id` 必须存在于基线、`old_value` 必须匹配、字段受控、来源 URL 有效、同一记录同一字段不重复。不联网，不证明内容正确。

## 合并方向

第二轮不覆盖第一轮 CSV。后续统一复检时：

1. 以第一轮 CSV 为底，把 `<city>-new.csv` 追加到同城末尾（`row_id` 已顺延，无冲突）。
2. 按 `row_id` 把 `<city>-enrich.csv` 的 `new_value` 应用到对应字段，并保留 `source_url` 到 `address_source_url` / `extra_source_urls` 或 `notes`。
3. 合并后再做全库查重与冲突裁决（本轮不做）。
