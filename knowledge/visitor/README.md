# 外国游客须知条目

父票 #841；格式与候选来源 #843；首批收集 #846；事实工具接入由 B 在 #847 完成。
H 线只拥有 `knowledge/visitor/**`。当前正式条目为 **0**，来源清单待 JT 确认。

## 文件与格式

- `SOURCES.md`：待确认来源范围；不是线上抓取许可或事实证据。
- `examples/format.json`：3 条**合成格式样例**，正文和日期均为测试数据，不是已核对的游客须知，禁止接入检索。
- `entries/*.json`：#846 确认来源后才创建的正式数据；每个文件为非空 JSON 数组。
- `validate.py` / `test_validate.py`：只读本地格式检查与测试；不联网、不抓取、不写条目。
- `FACT-ASSESSMENT.md`：现有 FACT@1.0 的适配差异与 B 的交付边界。

每个条目严格包含下列字段，不接受额外字段：

| 字段 | 类型与规则 |
|---|---|
| `id` | 非空稳定标识，`visitor.` 开头，其后为小写字母、数字、点或连字符；全批次唯一 |
| `topic` | `payment`、`passport_booking`、`transport`、`internet`、`emergency` 五选一 |
| `cities` | 非空且无重复的城市代码数组：`beijing`、`chengdu`、`xian`、`shanghai`、`hangzhou`、`chongqing`、`shenzhen`；列出每个实际适用城市，不使用“全国”自动展开 |
| `text_zh` | 非空中文正文；自己的话概括，不整段复制原文 |
| `text_en` | 非空英文正文；与中文等义，不增加来源没有的承诺，不标作官方翻译 |
| `source_urls` | 非空、无重复的 HTTPS 网址数组；引用获批范围内实际支持正文的具体公开页面，无用户名、密码或片段 |
| `checked_on` | 人工实际核对日期，严格 `YYYY-MM-DD`，不能晚于检查当天 |
| `expires_on` | 严格 `YYYY-MM-DD`，必须晚于核对日期；该日 **Asia/Shanghai 00:00 起失效**，当日即拒绝 |

`checked_on` 是维护者核对日期，不是网站发布日期；`expires_on` 是本库的复核期限，不是官方政策终止日。
两者都不能冒充原网页的声明。日期检查按北京时间日历；运行时应使用可信服务端时间。
一条同时适用多个城市时可显式列出，但必须有来源支持每个城市；仅写城市入口不等于覆盖已验收。

3 条完整示例见 [format.json](examples/format.json)，分别展示单城支付、多城交通及单城上网的字段形状。
示例网址只是格式占位引用，正文无真实规则；核对日期不代表实际访问。样例只在固定测试日检查，过期后不延长来假装新鲜。

## 本地验证

沿用根项目锁定环境，严格 JSON 复用仓库 `cj_strict_json.reject_duplicates`，不复制解析器：

```sh
uv sync --locked
uv run --locked python -B -m unittest discover -s knowledge/visitor -p 'test_*.py' -v
uv run --locked python -B knowledge/visitor/validate.py --as-of 2026-11-12 knowledge/visitor/examples/format.json
# #846 创建正式条目后：省略 --as-of 使用当前北京时间
uv run --locked python -B knowledge/visitor/validate.py knowledge/visitor/entries/*.json
```

格式检查拒绝缺字段、空正文、未知主题或城市、重复 id/JSON 键、无效网址、错误或非规范日期、未来核对日及已失效条目。
退出码 0 为通过，1 为无效数据；任一文件失败不会输出整批 PASS。脚本不读取网址内容。
`--as-of` 只用于可重复的本地测试，不能用历史日期为生产条目延寿。
这些测试尚未接入根 `scripts/test.py`；本线无该文件写权，PR 单独记录实际执行结果，不能把现有 CI 冒充本套测试。

## 内容核对与维护

格式通过不能证明来源已批准、网页可达、内容准确、双语等义或覆盖七城五主题；这些在 #846 逐条人工核对。
签证和入境只给官方渠道指引，不概括政策、资格或适用天数。会变的价格、余票、时刻和政策数字优先不写；
确需写时附核对日并设短复核期限，不能当成实时信息。对无明确支持的条目保留缺口，不编造成功。

到期前重新读获批页面；只有实际复核后才更新 `checked_on` 和 `expires_on`。
失效条目停止返回，不因旧回答或缓存继续使用。30 天内到期清单脚本及完整复核节奏留给 #846。
来源新增或跨 hostname 先在 #843 请 JT 确认。正文只保存必要概括与网址，抓取原件和日志不入库。
