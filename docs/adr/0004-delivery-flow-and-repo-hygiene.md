# ADR-0004：交付流程收敛与仓库卫生

- 状态：**proposed**（Claude 架构审查提议；第 4 节决策点需 JT 逐项确认后改为 accepted）
- 日期：2026-10-27
- 依据：main `8fac0dff5e50ce08c277b65f7322a4ea64d77e65` 的静态审查；未运行 pytest / swift test（UNRUN）
- 关联：[ADR-0002](0002-runtime-candidates.md)、[ADR-0003](0003-state-and-recovery.md)、[CJ-005](https://github.com/JTCAO515/G2C/issues/5)、[交接](../handoff.json)、[P0 派工单](../dispatch/P0-repo-hygiene.md)

## 背景（仓库证据）

10/21–10/26 共 383 次提交、约 25 万行新增，但尚无用户可用的端到端链路：

- 已登记迁移只有 `backend/migrations/0001_foundation.sql`（仅 `cj.schema_migrations`）；7 个领域 `sql/candidate.sql` 均为候选，`scripts/check-empty-db-init.py` 固定 `apply: BLOCKED`。
- 真实模型调用 UNRUN；Agent 运行时只在 `spikes/runtime`。OpenAPI 31 个端点，无 SSE 流式端点。
- iOS 主 target 仍为 `ProbeView`；四 Tab `ShellView` 在独立 package `ios/Modules/CJShell`，未接入 App。
- 2877 个文件中 1837 个位于 `evidence/`（约 48MB，含 `.log/.txt/.xz/.mp4`）；618 个文件含本机路径 `/Users/jtsm5p`，仓库为 PUBLIC 且无许可证。
- `backend/cj_api/composition.py::_pinned_modules` 在运行时校验同仓兄弟模块文件 sha256；任何领域改动都需同步 `*_pins.json` 与 `PIN-UPDATE`，产生大量 Integrate 提交。
- 根 `pyproject.toml` 外另有十余个领域级 `pyproject`/`uv.lock`；`scripts/` 有 49 个独立 check/build 脚本；无 `.github/` CI。
- README 仍写“尚无产品工程、可运行 API、schema”；AGENTS.md / engineering.md 指向另一台机器的本地 HANDOFF 与旧仓库 `Go2China` Issue 链接，仓库内无 `docs/handoff.json`。

## 决定（提议）

1. **交接回仓库**：`docs/handoff.json` 为机器权威源，`HANDOFF.md` 由其生成。本机 HANDOFF 可继续作为 Main 的工作笔记，但不再是唯一入口；两者冲突时以仓库 + Git + Issue 实况为准。
2. **CI 是唯一的“绿”**：新增最小 GitHub Actions（pytest、OpenAPI 校验与生成一致性、PG16 迁移 up/down、macOS `swift build/test`）。作者自报 PASS 只作补充，不替代 CI。
3. **证据出仓**：新增运行日志、进程记录、压缩包、录屏不再入库，改为 CI artifact 与 PR 描述中的 PASS / FAIL / UNRUN / UNKNOWN 表；仓库只保留精简 `evidence/INDEX.md`。**不改写 Git 历史、不 force push**；既有证据文件的清理另行确认。
4. **公开仓库去本机路径**：本机绝对路径替换为占位（如 `<local-handoff>`、`<repo>`）。
5. **（P1，待确认）删除同仓 hash pin**：合并为单一 Python package `cj` + 单一 `pyproject`/`uv.lock`，由契约测试与 CI 保证组合一致；Git commit 即不可变 pin。
6. **（P1，待确认）流程精简**：一个 PR 对应一个 Issue 切片，CI 绿 + 一次独立 Review 即合并；trunk-based，不再经 `cj/integration-c0` 中转。STOP 规则、UNKNOWN 纪律、未知写入先读回保持不变。
7. **路线**：P0 仓库卫生 → P1 结构收敛 → P2 walking skeleton（CJ-007→009→010→014→015 + 011 最小记忆，单城市、中英、真机）→ P3 加厚至内测。P2 期间暂停新领域铺宽（离线、手动编辑、反馈、清理进度、用量展示）。

## 已确认 / 证据 / 待决 / 推断

- **已确认用户决策**：ADR-0001 全部内容；`qwen3.8-flash` 与北京端点（见 `spikes/runtime/REPORT.md`）；JT 授权本 PR（handoff.json、ADR-0004、P0 派工单）并直接合并 main。
- **仓库证据**：“背景”各条，均可在上述 main commit 复核。
- **待 JT 决定**：见下节。
- **Claude 推断（待验证）**：交付慢的主因是流程与组合开销而非技术难度；竖切 walking skeleton 能显著提升可验收产出。

## 待 JT 决定（operatorActions）

1. 仓库可见性：保持 PUBLIC 或改 PRIVATE（建议许可证未定前改 PRIVATE）。
2. 是否接受第 3 条（证据出仓）与第 5 条（删除 hash pin）——两者修改既有组合/证据流程。
3. P2 范围值：城市、主登录方式、最低 iOS。建议：单城市北京、邮箱 OTP、iOS 17（均为候选）。
4. 是否接受第 6 条流程精简。

## 取舍

- 失去逐文件 hash 的运行时防篡改；以 CI、分支保护与 Review 代替。若需供应链完整性，应针对外部依赖（`uv.lock` 哈希）而非同仓源码。
- 证据出仓后，历史审计依赖 CI 保留期与 PR 记录；长期需保留的产物进 Release 或私有存储。
- 暂停铺宽会推迟部分 Issue，但每个已做领域都能更早被真实链路验证。

## 回滚

本 ADR 与 P0 仅改文档、交接与 CI 配置，`git revert` 对应合并提交即可；不涉及数据、凭据或外部资源。
