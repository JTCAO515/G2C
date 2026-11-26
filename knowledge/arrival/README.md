# 入境规则（唯一来源）

事实数据线维护；#1730（W5-2）。

- `arrival-rules.v1.json`：唯一数据源（免签政策、国家与过境免签、入境卡、官方兜底渠道）。`checked_at` 是实际重读官方来源的日期，`review_every_days` 是复核期限。
- `sync_copies.py`：把源文件逐字节写成两份副本：App 随包的 `ios/Modules/CJShell/Sources/CJLioUser/Resources/LioArrivalRules.v1.json`，以及香港后端读取的 `backend/fact/cj_fact/arrival_rules.v1.json`（随 `cj_fact` 包打进镜像，读取入口是 `cj_fact.arrival.load_rules`）。两份副本都不要手改。
- CI：`backend/fact/tests/test_arrival_rules.py` 比对三份文件逐字节一致，不一致时 `python` job 失败。

改规则：先重读官方来源（国家移民管理局、外交部领事服务网），再改本文件，在仓库根目录运行 `python3 -B knowledge/arrival/sync_copies.py`，把三个文件一起提交。改到 App 副本的 PR 受 `ios/**` 合并冻结约束，以 `coord/main-freeze.md` 为准。
免签政策 2026-12-31 之后：查不到官方延续公告时写成「以官方为准」并给官方链接，不推断延续与否（统筹 2026-11-26 按 JT 预授权决定）。
