# #843：FACT@1.0 适配评估 → B #847

结论：**不能直接承载**。评估依据为 `contracts/fact/V1.md`、`README.md`、`TOOL-HOST-V1.md`，
基线 `0b3078552e66f726e00e444889285acb27432806`。此处只给 B 差异，不定义或冻结新 wire，不改 backend 或 contracts。

## 已有边界与差异

| 事项 | 现有 FACT@1.0 | 本库及 #847 所需 |
|---|---|---|
| 来源类型 | `data_origin=synthetic`，只接受固定 HTTPS 合成来源；明确要求真实来源采用新增版本 / policy | 人工整理的官方公开网页概括，必须显式标为人工整理，不得写成 synthetic 或官方原文 |
| 查询 | `fact_key`、单个 `region`、必填 `dates`、`conditions`；精确匹配，无地理或时区推断 | 按 `topic` 和城市检索；由 B 明确映射及新请求形状，不虚构旅行日期、身份或适用条件 |
| 正文 | `summary_zh/en` 是固定的适用性状态说明；`original_value` 保留原始 JSON literal | 返回 `text_zh/en` 的双语维护者概括；不能塞入原文或覆盖固定状态语义 |
| 证据 | 保存原文 base64、SHA256、精确 span，解码重解析原文与声明 | 本库不保存抓取原件，只有概括与多个具体来源 URL；不能伪造原文/span/hash 来满足旧版本 |
| 日期 | aware retrieval/evaluation timestamps；来源声明的覆盖日期和到期时刻 | `checked_on/expires_on` 是维护者日期；失效为北京时间日初，不能冒充来源发布日期或来源声明的到期日 |
| 结果 | synthetic producer、原始 request_ref、AUTH/RUN/Meter 关联、未知与取消边界 | B 需要新增显式本地知识库 producer / result 版本或独立 payload，并保留原关联与未知、取消、权限及费用不变量 |

## 交给 B 的最小要求

1. 仅新增版本；FACT@1.0、旧示例、decoder 和合成路径不变。由 B 决定新版本号并按红线流程附正负例。
2. 查询按五主题与七城显式匹配；只读取 `knowledge/visitor/entries/*.json`，不递归把 `examples/`、测试和文档当事实。
3. 只返回已人工核对且未失效的正式条目，带 `id/topic/cities/text_zh/text_en/source_urls/checked_on/expires_on`；
   新结果的证据类型明确是维护者概括，网址、日期留在内部结果中，不能因用户正文不显示依据而丢弃。
4. 在文件反序列化边界校验一次，使用可信当前时间检查到期；不能固定历史 `--as-of` 延寿。
   明确无命中、过期及格式错误的行为，不把格式错静默转换为成功或真实知识。
5. 无命中遵循 `docs/lio-voice.md` 第 6.2 节；用户正文不展示供应商或接口。签证/入境仍仅指向官方渠道。

本目录的格式是内容文件约定，不是新 FACT wire，也不授予服务端上线或抓取权。
B 接入须自行验证命中、无命中、失效、格式错误及本地签名链路中英问答。
截至 #843：正式条目 0，真实来源访问 0，线上接入及 L1 问答均 UNRUN。
