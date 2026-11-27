# 自有收录库（places）

行程与收录库线维护（#1985 F-3）。收景点、餐饮、购物、酒店、交通枢纽，只收适合外国游客的地点。**数据由 AI 起草，必须校验后再导入，人审之后才进库。** 流程照 `knowledge/attractions`：JSON 唯一数据源 → validate → generate → 服务端副本和 App 副本 → CI 逐字节比对。

## 文件

| 路径 | 作用 |
|---|---|
| `<城市>.v1.json` | **唯一数据源**。城市取 `beijing shanghai guangzhou shenzhen chengdu chongqing`。只放人审通过的条目 |
| `placelib.py` | 字段规则（草稿和库两种形态） |
| `validate.py` | 校验全部城市文件，并比对副本；`--write` 规范化源文件并重写副本 |
| `generate.py` | 生成服务端副本和 App 精简版；`validate.py` 调用，也可单独运行 |
| `import/import_drafts.py`、`import/amap.py`、`score.py` | 导入 Codex 草稿、高德补坐标、打分、审核表（#1986） |
| `candidates/<城市>.cand.json` | 候选（待审、已决定的都在这里；不是库） |
| `review/<城市>.review.csv`、`.md` | 给 JT 的审核表 |
| `SOURCES.md` | 数据来源条款核对结论 |
| `placeimages.py`、`images/check_images.py`、`images/manifest.v1.json` | 图片清单：生成、校验（#1987） |

生成物（不要手改）：
- 服务端副本 `backend/fact/cj_fact/places_<城市>.v1.json`，与源文件**逐字节一致**，读取入口 `cj_fact.places`（`load_city`、`by_id`、`by_category`、`match_name`）。
- App 精简版 `ios/Modules/CJShell/Sources/CJLioUser/Resources/LioPlaces.v1.json`：只有 id、城市、类别、`kind`、等级、排名、中英名、别名、GCJ-02 坐标、amap_id、酒店的 `price_band` / `star` / `accepts_foreigners`（其他类别为 null，「住」按它们筛选并与高德结果取交集）、一句话简介、缩略图文件名。App 在问服务端之前就能显示的就这些。
- CI：`backend/tests/test_places_pipeline.py` 与 `backend/fact/tests/test_places_copy.py`。数据改了却没重新生成，`python` job 失败。App 副本也在 Python job 里比对（只改 `knowledge/` 的 PR 不跑 Swift job）。
- 一个城市文件被删除时，它的副本也算过期，`--write` 会一并删掉。

## 与 Codex 草稿的关系

Codex 产出放在 `codex-inbox/C1`（景点）、`C7`（枢纽）、`C8`（餐饮、购物、酒店），字段名和类型就是 `coord/codex/` 里的格式，**库的字段是它的超集**，不需要转换：

| 草稿 | 库 |
|---|---|
| `external_signals`（评分、排名） | **不进库**。留在候选文件里，仅内部用于决定收不收、排第几 |
| 不带坐标（有坐标即判错） | 加 `location`：`gcj02.lat/lng`、`amap_id`、`amap_name`、`method`、`geocoded_on` |
| — | 加 `rank`（同城同类别内排名，不重复，可为 null）和 `review`（`status`、`reviewer`、`reviewed_on`、`note`） |
| 缺的字段可省略 | 库里每个字段都在，没把握就是 `null`；需要非空的见下 |

草稿检查（`placelib.check_draft`）：必须有 id、city、category、中英文名、sources、checked_on、confidence；多出的字段只警告并丢弃；有错的条目不导入，进拒绝清单。

## 库里的规则（validate 强制）

- **id** `pl_<缩写>_<短名>`，缩写 bj sh gz sz cd cq 必须和城市一致，小写加下划线，全库唯一。
- **来源**：`sources`、`hours_source`、`official_url`、`ticket.booking_url` 必须是 https 网页；点评、攻略、聚合站（Tripadvisor、携程、马蜂窝、大众点评、小红书、百科、订房站等）一律拒绝，列表在 `placelib.THIRD_PARTY_HOSTS`。是不是官方，仍由审核人判断。每条至少 1 个来源，写 `checked_on`。
- **坐标**：GCJ-02，最多 6 位小数，必须落在该城的范围框里（防止高德匹配到外地同名地点）；`(0,0)` 过不了。`method` 为 `amap-*` 时必须有 `amap_id`；`manual` 可以没有。
- **文字**：单行、无首尾空格。字数限制：`intro_short_zh` ≤ 40、`intro_short_en` ≤ 90、`intro_long_zh` ≤ 200、`intro_long_en` ≤ 450。简介必须是我们自己写的，不复制原文。
- **名称唯一**：同一城市里，中英文名和别名不能重复（实体链接靠它匹配，歧义宁可不收）。
- **`ticket.closed_weekdays`**：ISO 星期，1 = 周一，7 = 周日；`null` 表示来源没写，`[]` 表示没有固定闭馆日。
- **预约规则只认 `knowledge/attractions/booking-rules.v1.json`**：同一景点（名称或别名精确匹配）在这里写的预约要求或闭馆日和那张表矛盾，validate 报错，先解决矛盾再入库。`ticket` 只用于地点页展示。
- **景点 `subcategory`**：`history museum park street landmark experience`；餐饮、购物、酒店的 `subcategory` 是小写短词（如 `international_brand`），由收录时统一。
- **酒店**：必须 `accepts_foreigners: true` 并附 `foreigner_signals.evidence`（不收民宿、短租）；`price_band` 取 `<500 500-1000 1000-2000 >2000`。
- **枢纽**：`hub_type` 为 `airport` 或 `rail`，必须有 `code`；没有简介字段。
- **库里只放 `review.status` 为 `approved` 或 `retired` 的条目**；候选和被拒绝的留在 `candidates/`。`places` 按 id 排序，源文件必须是 `validate.py --write` 写出的规范格式（稳定 diff，副本才能逐字节一致）。
- 校验不读系统时钟；到期提醒由 `scripts/fact_expiry.py` 负责（后续接入）。

## 改库

1. 条目经审核表确认（#1986 的 `import/` 生成审核表，人审之后才合入）。
2. 在仓库根目录运行 `python3 -B knowledge/places/validate.py --write`：校验、规范化、重写副本。
3. 把源文件和全部副本一起提交。改到 App 副本的 PR 受 `coord/main-freeze.md` 的 `ios/**` 约束。

## 导入 Codex 草稿（#1986）

```bash
# 离线：只校验、打分、出审核表（不查高德）
python3 -B knowledge/places/import/import_drafts.py --inbox ../codex-inbox --today 2026-11-29
# 联网：用高德补 GCJ-02 坐标和 amap_id（key 只从环境变量读，不进日志、不进文件）
CJ_AMAP_WEB_KEY=… python3 -B knowledge/places/import/import_drafts.py --inbox ../codex-inbox --today 2026-11-29 --live
```

- 读 `C1/*.json`（景点）、`C7/hubs.json`（枢纽）、`C8/*.json`（餐饮、购物、酒店），每个文件是一个条目数组。**校验不过的条目进 `candidates/rejected-<日期>.json`，不导入**；已在库里的 id 跳过；同城同中文名只警告。
- 高德匹配分四档：`exact`（名称或别名一致）、`close`（互相包含且长度占 60% 以上）、`weak`（只是第一条结果，审核人必须核对）、`none`；POI 没找到再用地址地理编码（`address-only`，没有 amap_id）。结果不在该城范围框内的丢弃，防止匹配到外地同名地点。高德临时错误只标这一条，key 无效或额度用完则整次中止。
- 打分只用来排审核顺序（主档在前，再按分数），不决定收不收；构成见 `score.py`。**外部评分和排名默认不计分**，要等统筹按 Codex G3 的条款结论决定后才加 `--use-external-signals`。
- 审核表：`review/<城市>.review.csv`（Excel 可直接打开，批次 25 条，空的 `decision` 列填 accept / reject / edit，另有 `rank`、`note` 列）和 `.md`（逐条卡片）。表里以 `= + - @` 开头的单元格会加引号前缀，避免草稿里的公式在表格软件里执行。
- 重跑安全：已有决定的条目保持不变，待审的刷新，从收件箱里消失的待审条目保留。
- 高德应答缓存在 `<收件箱>/.amap-cache`（仓库之外），只用于避免重复计费，不提交。

## 图片（#1987）

地点图是 AI 生成的**示意插画**（JT 2026-11-27 定），地点页和气泡卡都标「示意图」，不使用第三方图片。大图 1600×1200、缩略图 512×512 的 PNG 太大，不进 git，存放位置由服务端线的图片存储登记决定；进仓库的是 `images/manifest.v1.json`：每张图的文件名、实测尺寸、SHA-256、`license`、`label_zh`/`label_en`、生成提示词、模型、日期。

```bash
# Codex 交付 codex-inbox/C2（manifest.json + PNG）后：实测尺寸和哈希、拒绝不合规条目、写清单
python3 -B knowledge/places/images/check_images.py build ../codex-inbox/C2 --today 2026-11-30
# 校验清单；--files 同时核对图片文件；--release 要求每张图对应库里的地点、每个主档景点都有图
python3 -B knowledge/places/images/check_images.py check --files ../codex-inbox/C2 --release
```

- `license` 只能是 `ai-generated`，`label_zh` 必须是「示意图」、`label_en` 是 Illustration，尺寸必须精确，缩略图不能是同一个文件；不合规的条目被**拒绝而不是修**，退回 Codex 重做。
- 图里不许有文字、Logo、水印、能认出脸的人物，这一点脚本看不出来，由审核表上的人工抽查负责。
- 清单是 `validate.py` 的一部分，CI 每次校验；App 精简版的 `thumb` 字段取自清单。App 副本一旦生成，`Package.swift` 要声明 `Resources/LioPlaces.v1.json`（有测试守着）。

## 开发用数据包（未经人审，只给开发用）

JT 审核要一天一批，库会空一阵，而实体链接（对话线 D-1）、地点页（App 线 D-4）、行程画布都要拿数据开发。所以由 `candidates/` 里所有待审候选生成一份**开发用数据包** `dev/places-dev-pack.v1.json`：库的字段形态，但每条 `review.status` 都是 `unreviewed`，`rank` 为空，坐标等高德跑完才有（之前为 null）。**它不是库，也不是事实**。

- 生成与校验：`validate.py --write` 重新生成，`validate.py` 检查与候选一致；被 accept 的条目离开开发包（进了正式库），被 reject 的不在里面。校验拒绝任何看起来已审核的条目。
- **生产不读**：不在 `backend/fact/cj_fact/` 里（不进服务端镜像），不是 App 的打包资源，也不在任何部署文件里；`test_places_devpack.py` 逐项守着。
- 服务端：`cj_fact.places_dev`，**两个环境变量都设了才放行**：`CJ_PLACES_DEV_ENABLED=1` 和 `CJ_PLACES_DEV_PACK=<包的路径>`；否则一律 `FactFailure('places_dev_disabled')`。香港环境永远不设这两个变量（测试扫 deploy、.github、tooling 里的文件）。
- App：`LioDevPlacesPack`（`#if DEBUG`，Release 和 Beta 编译里整个文件都没有），从启动参数 `--places-dev-pack <路径>` 或环境变量 `G2C_PLACES_DEV_PACK` 读；读不到、版本不对、有任何已审核条目就当没有。用到开发数据的界面必须标明这是开发数据。
- JT 审核完、数据进了正式库，开发包自动缩小直至没有（没有待审候选时 `validate.py --write` 删除它）。

## 审核结果入库（#1988）

JT（或指定的人）在 `review/<城市>.review.csv` 的 `decision` 列填 `accept`、`reject` 或 `edit`（edit 必须在 `note` 写要改什么），可在 `rank` 列写同类别内的名次。然后：

```bash
python3 -B knowledge/places/import/apply_review.py beijing --reviewer JT --on 2026-11-30
python3 -B knowledge/places/validate.py --write     # 重写副本，并与预约规则表交叉核对
```

- `accept` 的条目拿候选里的草稿字段（去掉 `external_signals`）加高德坐标、`rank`、审核记录（审核人、日期、备注）进库；没有坐标（高德没找到）的不能 accept。
- 整个城市文件先用 `validate.py` 同一套规则试校验，**有一条不过就整城都不写**并列出全部问题（常见的是同城名称重复）。
- `reject` 留在候选文件里标 `rejected`，不进库；`edit` 保持待审，修完草稿重新导入。
- 只有**待审**的候选能被决定；候选已经 accepted / rejected 的再填 decision 会被拦下并说明（改主意：先在候选文件里把它的 `status` 改回 `pending`）。reject 一个已进库的 id 也会被拦：库里的条目要在库文件里下架。
- 库里已有的 id 再 accept 默认被拦（旧条目带着原审核人、日期、名次）；确实要改审，加 `--replace`（只用于候选已是 accepted 的条目），汇总会逐个列出被替换的 id。上一次运行写完库文件、没来得及改候选状态就被中断时，用同样的 `--reviewer`、`--on` 和答案再跑一遍就行（同一个答案得到同一个条目，只补上候选状态，不需要 `--replace`）。
- 库文件和候选文件都是先写同目录临时文件再改名，写到一半被杀或磁盘满，旧文件原样还在；表头缺 `id` 或 `decision` 列、候选文件结构坏了，都是一条清楚的失败，不写任何文件。
- 库里只有人点过 accept 的条目：这是「人审之后才进库」的唯一入口。
