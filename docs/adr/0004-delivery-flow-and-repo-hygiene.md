# ADR-0004：交付流程收敛与仓库卫生

- 状态：**accepted**（JT 于 2026-10-27 逐项确认，见“JT 决定”一节；技术效果仍按各 Issue 验证）
- 日期：2026-10-27
- 依据：main `8fac0dff5e50ce08c277b65f7322a4ea64d77e65` 的静态审查；未运行 pytest / swift test（UNRUN）
- 关联：[ADR-0002](0002-runtime-candidates.md)、[ADR-0003](0003-state-and-recovery.md)、[CJ-005](https://github.com/JTCAO515/G2C/issues/5)、[交接](../handoff.json)、[P0 派工单](../dispatch/P0-repo-hygiene.md)

## 背景（仓库证据）

10/21–10/26 共 383 次提交、约 25 万行新增，但尚无用户可用的端到端链路：

- 已登记迁移只有 `backend/migrations/0001_foundation.sql`（仅 `cj.schema_migrations`）；7 个领域 `sql/candidate.sql` 均为候选，`scripts/check-empty-db-init.py` 固定 `apply: BLOCKED`。
- 真实模型调用 UNRUN；Agent 运行时只在 `spikes/runtime`。OpenAPI 31 个端点，无 SSE 流式端点。
- iOS 主 target 仍为 `ProbeView`；四 Tab `ShellView` 在独立 package `ios/Modules/CJShell`，未接入 App。
- 2877 个文件中 1837 个位于 `evidence/`（约 48MB，含 `.log/.txt/.xz/.mp4`）；618 个文件含本机路径 `<local>`，仓库为 PUBLIC 且无许可证。
- `backend/cj_api/composition.py::_pinned_modules` 在运行时校验同仓兄弟模块文件 sha256；任何领域改动都需同步 `*_pins.json` 与 `PIN-UPDATE`，产生大量 Integrate 提交。
- 根 `pyproject.toml` 外另有十余个领域级 `pyproject`/`uv.lock`；`scripts/` 有 49 个独立 check/build 脚本；无 `.github/` CI。
- README 仍写“尚无产品工程、可运行 API、schema”；AGENTS.md / engineering.md 指向另一台机器的本地 HANDOFF 与旧仓库 `Go2China` Issue 链接，仓库内无 `docs/handoff.json`。

## 决定（提议）

1. **交接回仓库**：`docs/handoff.json` 为机器权威源，`HANDOFF.md` 由其生成。本机 HANDOFF 可继续作为 Main 的工作笔记，但不再是唯一入口；两者冲突时以仓库 + Git + Issue 实况为准。
2. **CI 是唯一的“绿”**：新增最小 GitHub Actions（pytest、OpenAPI 校验与生成一致性、PG16 迁移 up/down、macOS `swift build/test`）。作者自报 PASS 只作补充，不替代 CI。
3. **证据出仓**：新增运行日志、进程记录、压缩包、录屏不再入库，改为 CI artifact 与 PR 描述中的 PASS / FAIL / UNRUN / UNKNOWN 表；仓库只保留精简 `evidence/INDEX.md`。**不改写 Git 历史、不 force push**；既有证据文件的清理另行确认。
4. **公开仓库去本机路径**：本机绝对路径替换为占位（如 `<local-handoff>`、`<repo>`）。
5. **（P1）删除同仓 hash pin**：合并为单一 Python package `cj` + 单一 `pyproject`/`uv.lock`，由契约测试与 CI 保证组合一致；Git commit 即不可变 pin。
6. **（P1）流程精简**：一个 PR 对应一个 Issue 切片，CI 绿 + 一次独立 Review 即合并；trunk-based，不再经 `cj/integration-c0` 中转。STOP 规则、UNKNOWN 纪律、未知写入先读回保持不变。
7. **路线**：P0 仓库卫生 → P1 结构收敛 → P2 walking skeleton（CJ-007→009→010→014→015 + 011 最小记忆，单城市、中英、真机）→ P3 加厚至内测。P2 期间暂停新领域铺宽（离线、手动编辑、反馈、清理进度、用量展示）。

## 已确认 / 证据 / 待决 / 推断

- **已确认用户决策**：ADR-0001 全部内容；本 ADR 第 1–7 条及下节 JT 决定；`qwen3.8-flash` 与北京端点（见 `spikes/runtime/REPORT.md`）；JT 授权本 PR（handoff.json、ADR-0004、P0 派工单）并直接合并 main。
- **仓库证据**：“背景”各条，均可在上述 main commit 复核。
- **Claude 推断（待验证）**：交付慢的主因是流程与组合开销而非技术难度；竖切 walking skeleton 能显著提升可验收产出。

## JT 决定（2026-10-27）

1. 仓库可见性：**保持 PUBLIC**。因此去本机路径（第 4 条）为必做项；许可证与产品法律条款仍待定，公开不等于授予开源许可。
2. **接受**第 3 条（证据出仓）与第 5 条（删除同仓 hash pin）。既有已跟踪证据的清理与 pin 删除一并在 P1 执行（pin 删除后 hash 约束随之解除），仍不改写 Git 历史。
3. **接受** P2 范围值：单城市 **北京**、主登录 **邮箱一次性登录（OTP）**、最低 **iOS 17**。真实可达性、SDK 能力与设备覆盖仍按 CJ-004/007/026 验证。
4. **接受**第 6 条流程精简。

## 实施记录

- **P0（PR #141，2026-10-27）**：仓库内交接、最小 CI、文档对齐、清理本机路径、.gitignore。
- **P1（2026-10-27）**：
  - 删除同仓 sha256 pin：`cj_api` 直接 import（`MODULE_SETS`），删除 `*_pins.json`、`prepare-*-deps`、`check-*-wire.sh` 和 loopback HTTP+PG harness。去掉 pin 后暴露出两处真实漂移（aead cursor 测试嵌套 history context；cleanup 测试清单落后于 storage registry），均已修正。
  - 单一发行包：根 `pyproject.toml` 加 `uv.lock`，由 hatchling 打包各领域。**实施细节**：保留原 import 名（`cj_auth` 等），没有改名为 `cj.*` 子包，以免大规模重写 import；发行包名为 `cj`。
  - 统一入口：`scripts/test.py`（无数据库）、`scripts/pg_suites.py`（私有集群）、`scripts/migrate.py`、`scripts/check.sh`；CI 的 python / postgres / swift 三个 job 全部阻塞。
  - 迁移：10 版有序链，每版有 down 和 sha256，CI 跑 up → down → up。领域表暂留 public schema，`cj` schema 只放迁移台账；角色、授权、RLS 未定。
  - 证据出仓：1836 个文件移出跟踪，归档在 tag `evidence-archive-2026-10-27`（见 [evidence](../evidence.md)）；evaluation 的 golden 报告移到 `fixtures/`。
  - 修复 `ProbeView` 的 `enum State` 遮蔽 SwiftUI `@State` 的问题。
  - 已知未覆盖：真实 uvicorn + 生成 Swift 客户端的 loopback 端到端随 harness 一起删除，留到 P2 在迁移链上重建；`scripts/check-generated-*.sh` 和 iOS 模块中 pin 时代的准备脚本（`ios/Modules/*/scripts/prepare_*`、`check_pin.py`，依赖已出仓的 evidence）尚未纳入 CI 或清理。

## 取舍

- 失去逐文件 hash 的运行时防篡改；以 CI、分支保护与 Review 代替。若需供应链完整性，应针对外部依赖（`uv.lock` 哈希）而非同仓源码。
- 证据出仓后，历史审计依赖 CI 保留期与 PR 记录；长期需保留的产物进 Release 或私有存储。
- 暂停铺宽会推迟部分 Issue，但每个已做领域都能更早被真实链路验证。

## 回滚

本 ADR 与 P0 仅改文档、交接与 CI 配置，`git revert` 对应合并提交即可；不涉及数据、凭据或外部资源。
