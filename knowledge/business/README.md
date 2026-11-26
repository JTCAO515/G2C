# 商务场景知识条目

事实数据线维护；首批为 #1759（W5-6）的广州四条：广交会境外采购商预登记、琶洲交通、签证渠道、展馆付款。

- `guangzhou.v1.json`（`g2c-business-knowledge.1`）：每条有 `id`、`topic`、中英文标题和正文、官方来源 `source_urls`、核对日 `checked_on`、复核期限 `expires_on`。商务场景包（`backend/cj_api/scene_packs/business.json`，S 线）的 `knowledge` 按 `id` 引用这些条目，`verified_on` / `review_by` 分别对应 `checked_on` / `expires_on`。
- `validate.py`：严格校验，包括未知或重复的键、主题、城市、中英文缺失、复核期限 1–90 天，以及来源必须是下面已批准 hostname 上的具体 https 页面。CI 由 `backend/tests/test_business_knowledge.py` 运行。校验不读系统时钟，到期提醒由 `scripts/fact_expiry.py`（#1757）负责。

## 口径

- 来源只用 S1（主办方、主管部门自己发布的内容），分级见 `knowledge/visitor/SOURCES.md`「来源分级」和 COLLECTION-STANDARD v0.2 §5。复核期限按 §8 与来源稳定程度两套分档取较早的日期（见 `knowledge/visitor/README.md`）。
- 广交会每届不同的日期、办证点时段、交通管制细节都不写进条目，写成「以当届官方通知为准」。
- 签证只给官方渠道，不判断签证种类、免签或过境免签。免签政策 2026-12-31 之后的安排一律写「以官方为准」并附国家移民管理局链接。

## 已批准的来源 hostname（只限广州商务条目）

| hostname | 机构 | 用途 |
|---|---|---|
| www.cantonfair.org.cn | 广交会官网（中国对外贸易中心） | 预登记、邀请函、采购商证件、馆内登记处 |
| hk.cantonfair.org.cn | 广交会驻香港办事处（同一主办方） | 邀请函可用于办理来华签证 |
| gaj.gz.gov.cn | 广州市公安局 | 展馆周边交通指引 |
| www.gz.gov.cn | 广州市人民政府 | 城市服务（付款、兑换） |
| www.nia.gov.cn | 国家移民管理局 | 签证、免签政策的官方渠道 |

批准出处：统筹 2026-11-26 按 JT 预授权决定，前 4 个 hostname 新增，`www.nia.gov.cn` 沿用原有批准（#843）。登记和使用限制写在 `knowledge/visitor/SOURCES.md`「2026-11-26 广州商务来源」一节。

## 改条目

先重读官方来源，再改 JSON，`checked_on` 写重读当天。在仓库根目录运行 `python3 -B knowledge/business/validate.py`，然后在 `reviews/` 下记录逐条依据。
