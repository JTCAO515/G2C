# WP12 Wikidata 名称核对

任务 #935，规格 #922 §0.9；不含坐标、地图匹配或营业条件。
WP0 [PR940](https://github.com/JTCAO515/G2C/pull/940) 已于 2026-11-13 合并为 `6790174865efba17237224cf400e446c27cde8f7`，合并后的 M4 条目 8 限每日不超过 500 次、缓存、不批量镜像、使用不含个人邮箱的通用 User-Agent。
新增网站范围已由 JT 在 H 会话确认并记入 [#843/6848295860](https://github.com/JTCAO515/G2C/issues/843#issuecomment-6848295860)。7 组中英文标签及 QID 又经 JT 人工核对并同意入库，记录在 [#843/6850112735](https://github.com/JTCAO515/G2C/issues/843#issuecomment-6850112735)。

## 已确认的七组

`names/popular-places.json` 共 7 条，`checked_on=2026-11-13`、`expires_on=2027-02-11`。标签按源数据的 `zh` / `en` 原样保存，不自译或繁简转换。

| 维护者地点键 | 中文标签 | 英文标签 | Wikidata 来源 |
|---|---|---|---|
| `beijing.palace-museum` | 故宫博物院 | The Palace Museum | [Q2047427](https://www.wikidata.org/wiki/Q2047427) |
| `chengdu.panda-base` | 成都大熊猫繁育研究基地 | Chengdu Research Base of Giant Panda Breeding | [Q1067861](https://www.wikidata.org/wiki/Q1067861) |
| `xian.qin-mausoleum-museum` | 秦始皇帝陵博物院 | Emperor Qinshihuang's Mausoleum Site Museum | [Q122931722](https://www.wikidata.org/wiki/Q122931722) |
| `shanghai.the-bund` | 外滩 | The Bund | [Q125474](https://www.wikidata.org/wiki/Q125474) |
| `hangzhou.west-lake` | 西湖 | West Lake | [Q502371](https://www.wikidata.org/wiki/Q502371) |
| `chongqing.three-gorges-museum` | 重庆中国三峡博物馆 | Three Gorges Museum | [Q10872783](https://www.wikidata.org/wiki/Q10872783) |
| `shenzhen.window-of-the-world` | 世界之窗 | Window of the World | [Q2302764](https://www.wikidata.org/wiki/Q2302764) |

核对中排除了故宫院刊与北院区、外滩街道、其他国家的西湖、世界之窗地铁站和长沙同名公园等候选。秦始皇帝陵博物院按博物馆实体记录，不把其替换为兵马俑艺术品集合或整个陵墓区域。
城市是维护者按目标地点核对的归属，不是通过坐标计算得到。名称字典也不证明高德 POI 已与 QID 对齐；L/C 应按身份和来源显式映射，不能靠同名或同城自动绑定。

## 许可与查询用量

[Wikidata Licensing](https://www.wikidata.org/wiki/Wikidata:Licensing) 的原文已在授权后读取，结构化实体数据适用 CC0；其他命名空间的页面文字有不同许可。本库只存结构化标签及编号，记录 `license=CC0-1.0`，不复制许可页正文、图片或其他页面内容。

本批在 WP0 生效且来源范围确认后执行 7 次 `wbsearchentities` 名称搜索、1 次仅取 `labels` 的 `wbgetentities` 批量查询、2 次许可页读取。共按 **10 次**保守计入 2026-11-13 的每日上限，串行请求开始间隔至少 1 秒；本批自限不超过 20 次。
User-Agent 为 `G2C-VisitorKnowledge/1.0` 加公开项目链接，不含个人邮箱。已缓存只读结果并保存当日请求计数于仓库外；缓存、原始响应和查询日志不入 Git。没有查询 `query.wikidata.org` 或 Wikipedia，没有请求 claims/P625、坐标、图片、路线或其他实体属性。

`examples/names-format.json` 是合成语法示例，里面的 Q1 与合成标签不是实查结果，禁止加载进名称字典。只有 `names/*.json` 为本批已核对数据。

## 复核

常规复核仍在 **2026-11-24 18:00 前**完成，满足 11 月 25 日前的要求。名称的独立失效期限是 2027-02-11 日初，最迟于 2027-02-10 18:00 前再核对；不得据此延后常规内容复核。
复查必须继续遵守当时生效的 WP0 频率、来源与人工核对要求；许可或来源范围变化先核授权，不扩大到子域或其他网站。名称更改不赋予坐标或 POI 迁移权限。

```sh
uv run --locked python -B knowledge/visitor/validate_names.py knowledge/visitor/names/*.json
uv run --locked python -B knowledge/visitor/review_due.py --format names knowledge/visitor/names/*.json
```
