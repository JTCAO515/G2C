# 外国游客须知条目

父票 #841；格式与候选来源 #843；首批收集 #846；事实工具接入由 L 在 #847 完成。
H 线只拥有 `knowledge/visitor/**`。JT 已在 [#843](https://github.com/JTCAO515/G2C/issues/843#issuecomment-6818584957) 确认 H1 来源范围。
首批 **12 条**中英条目于 2026-11-12 核对，覆盖七城 × 五主题共 35 个覆盖格；具体范围和限制见 [COVERAGE.md](COVERAGE.md)。

## 文件与格式

- `SOURCES.md`：JT 已确认的来源范围；不据首页地址推断具体事实。
- `examples/format.json`：3 条**合成格式样例**，正文和日期均为测试数据，不是已核对的游客须知，禁止接入检索。
- `entries/*.json`：正式内容文件，每个文件为非空 JSON 数组；`mainland-basics.json` 为 5 条全国适用基础指引，`city-services.json` 为 7 条城市专有事项。目录中的“正式”区分合成样例，不代表已上线。
- `validate.py` / `test_validate.py`：只读本地格式检查与测试；不联网、不抓取、不写条目。
- `review_due.py` / `test_review_due.py`：列出未来 30 天内失效条目，含第 30 天；`test_content.py` 检查七城五主题覆盖与来源 hostname。
- `FACT-ASSESSMENT.md`：现有 FACT@1.0 的适配差异与 L 的交付边界。

每个条目严格包含下列字段，不接受额外字段：

| 字段 | 类型与规则 |
|---|---|
| `id` | 非空稳定标识，`visitor.` 开头，其后为小写字母、数字、点或连字符；全批次唯一 |
| `topic` | `payment`、`passport_booking`、`transport`、`internet`、`emergency` 五选一 |
| `cities` | 非空且无重复的城市代码数组：`beijing`、`chengdu`、`xian`、`shanghai`、`hangzhou`、`chongqing`、`shenzhen`；列出每个实际适用城市，不使用“全国”自动展开 |
| `text_zh` | 非空中文正文；自己的话概括，不整段复制原文 |
| `text_en` | 非空英文正文；与中文等义，不增加来源没有的承诺，不标作官方翻译 |
| `source_urls` | 非空、无重复的 HTTPS 网址数组；引用获批范围内实际支持正文的具体公开页面，无用户名、密码或片段 |
| `checked_on` | 维护者实际核对日期，严格 `YYYY-MM-DD`，不能晚于检查当天 |
| `expires_on` | 严格 `YYYY-MM-DD`，必须晚于核对日期；该日 **Asia/Shanghai 00:00 起失效**，当日即拒绝 |

`checked_on` 是维护者核对日期，不是网站发布日期；`expires_on` 是本库的复核期限，不是官方政策终止日。
两者都不能冒充原网页的声明。语言由 `text_zh` / `text_en` 明确为中文 / 英文，适用范围由 `cities` 与正文中的限制条件共同表达。日期检查按北京时间日历；运行时应使用可信服务端时间。
一条同时适用多个城市时可显式列出，但必须有来源支持每个城市；仅写城市入口不等于覆盖已验收。

3 条完整示例见 [format.json](examples/format.json)，分别展示单城支付、多城交通及单城上网的字段形状。
示例网址只是格式占位引用，正文无真实规则；核对日期不代表实际访问。样例只在固定测试日检查，过期后不延长来假装新鲜。

## 本地验证

沿用根项目锁定环境，严格 JSON 复用仓库 `cj_strict_json.reject_duplicates`，不复制解析器：

```sh
uv sync --locked
uv run --locked python -B -m unittest discover -s knowledge/visitor -p 'test_*.py' -v
uv run --locked python -B knowledge/visitor/validate.py --as-of 2026-11-12 knowledge/visitor/examples/format.json
# 正式内容检查：省略 --as-of 使用当前北京时间
uv run --locked python -B knowledge/visitor/validate.py knowledge/visitor/entries/*.json
uv run --locked python -B knowledge/visitor/review_due.py knowledge/visitor/entries/*.json
```

格式检查拒绝缺字段、空正文、未知主题或城市、重复 id/JSON 键、无效网址、错误或非规范日期、未来核对日及已失效条目。
退出码 0 为通过，1 为无效数据；任一文件失败不会输出整批 PASS。脚本不读取网址内容。
`--as-of` 只用于可重复的本地测试，不能用历史日期为生产条目延寿。
这些测试尚未接入根 `scripts/test.py`；本线无该文件写权，PR 单独记录实际执行结果，不能把现有 CI 冒充本套测试。

## 内容核对与维护

格式通过不能证明来源已批准、网页可达、内容准确或双语等义。首批由 H 线 Codex 逐条对照公开页面概括并检查覆盖，未经过 JT 的逐条人工审阅；没有实际办理支付、手机卡、景区预约或乘车，也未完成 L 的事实工具接入。
签证和入境只给官方渠道指引，不概括政策、资格或适用天数。会变的价格、余票、时刻和政策数字优先不写；
确需写时附核对日并设短复核期限，不能当成实时信息。对无明确支持的条目保留缺口，不编造成功。

维护者每周一、内容合并前及 L 接入前运行上述两个命令；这是一项手工维护约定，没有创建自动任务。
首批下一次内容复核应在 **2026-11-25 18:00（北京时间）之前**完成，先检查八达岭和三峡博物馆两条；其失效时刻为 2026-11-26 00:00。其他分组复核时间见 COVERAGE.md。
到期前重新读获批页面；只有实际复核后才更新 `checked_on` 和 `expires_on`，不机械延长日期。
`review_due.py` 输出 id、主题、城市、核对日、失效日和来源，按失效日/id 排序；截至 2026-11-12，未来 30 天内应复核 10 条。
该脚本沿用原严格校验：发现已失效条目或格式错误时退出 1，不输出部分清单。先根据报错定位并复核对应条目，再重新运行；不能把失败当作“没有待复核条目”。
失效条目停止返回，不因旧回答或缓存继续使用。`review_due.py` 不修改文件，也不授予过期条目的展示权。
来源新增或跨 hostname 先在 #843 请 JT 确认。正文只保存必要概括与网址，抓取原件和日志不入库。
