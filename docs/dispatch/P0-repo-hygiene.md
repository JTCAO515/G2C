# Codex 派工单：P0 仓库卫生与最小 CI

- 派工方：Claude（架构/审查）；执行方：Codex
- 依据：[ADR-0004](../adr/0004-delivery-flow-and-repo-hygiene.md)（proposed）、[交接](../handoff.json)
- base：main（以开工时 `git rev-parse origin/main` 为准并写入 PR）
- 分支：`chore/p0-repo-hygiene`，经 PR 合并；禁止直推 main、force push、改写历史

## 目标

让任何新 agent 只靠本仓库即可安全续作，并让“绿”由 CI 而非自报决定。**不改业务行为。**

## 反目标

- 不改 `backend/**`、`ios/**`、`spikes/**`、`contracts/**` 的源码、测试、SQL、pins 或 OpenAPI。
- 不删除、移动既有 `evidence/` 文件（是否清理既有证据待 JT 决定）。
- 不删除 hash pin 机制（P1，待 JT 决定）。
- 不调用付费 provider、不创建云资源、不配置或读取任何秘密。

## 强制阅读顺序

1. `HANDOFF.md`（由 `docs/handoff.json` 生成）
2. `docs/adr/0004-delivery-flow-and-repo-hygiene.md`
3. 本派工单
4. `README.md`、`AGENTS.md`、`docs/engineering.md`
5. `pyproject.toml`、`uv.lock`、`backend/tests/test_api.py`、`scripts/check-composition.sh`

## 冻结项

现有 OpenAPI（`contracts/api/openapi.json`）、全部领域代码与 `*_pins.json`、已登记迁移 `backend/migrations/manifest.json`、ADR-0001。

## 允许修改

- `README.md`、`AGENTS.md`、`docs/**`（不改 ADR-0001~0003 的决定正文，只可修正失效链接）
- `.gitignore`
- `.github/workflows/**`（新建）
- 非源码文本中的本机绝对路径替换（`*.md`、`evidence/**` 内 `.json/.txt/.log` 的路径字符串，只替换路径，不改其他内容）

## 禁止修改

`backend/**`、`ios/**`、`spikes/**`、`contracts/**` 下的 `.py/.swift/.sql/.json` 源与 pins（evidence 子目录内路径替换除外）、`pyproject.toml`、`uv.lock`、`Package.swift/.resolved`、Xcode 工程。

> 注意：若某 pins 或 hash 文件覆盖了含本机路径的 evidence 文件，替换路径会导致 hash 失配——此类文件**跳过不改**，在 PR 中列出清单。

## 任务

1. **文档对齐现实**：README / AGENTS.md / engineering.md 中“尚无可运行 API/schema”等陈述改为现状；`JTCAO515/Go2China` Issue 链接改为 `JTCAO515/G2C`；本机 HANDOFF 路径改为指向 `HANDOFF.md` / `docs/handoff.json`。
2. **去本机路径**：`/Users/jtsm5p/...` 替换为 `<local>/...` 占位（遵守上方 hash 注意）。
3. **.gitignore**：新增忽略 `**/evidence/**/*.log`、`**/evidence/**/*.xz`、`**/evidence/**/*.gz`、`**/evidence/**/*.mp4`、`.deps/`；已跟踪文件不受影响。
4. **最小 CI**（`.github/workflows/ci.yml`，push main + pull_request）：
   - `python` job（ubuntu）：`uv sync --frozen`，`CJ_ENV=local uv run pytest -q backend/tests backend/cj_api/tests`；以实际能通过的最小集合起步，失败用例逐条记录在 PR，不跳过不删断言。
   - `contracts` job：用已有依赖校验 `contracts/api/openapi.json`（openapi-spec-validator），执行 `scripts/check-composition.sh` 若其离线可跑。
   - `swift` job（macos）：`swift build` + `swift test` 于 `ios/Modules/CJShell`（若依赖准备脚本需要本机 sibling checkout 无法在 CI 跑，则记录为 UNRUN 并说明，不伪造通过）。
   - PG16 迁移 up/down 留到 P1（迁移未定），本次不加。
5. **刷新交接**：更新 `docs/handoff.json` 的 `changedFiles`、`verification`、`nextAction`，重新渲染：`node ~/.claude/skills/jtcoding-skills/scripts/handoff.js render --project .`（无该脚本时手工同步并在 PR 说明）。

## 验收命令

```bash
grep -rIl '/Users/jtsm5p' . --exclude-dir=.git | wc -l   # 期望 0，或仅剩 PR 中列明的 hash 受保护文件
git diff --stat origin/main -- backend ios spikes contracts pyproject.toml uv.lock   # 期望仅 evidence 内路径替换
python3 -m json.tool docs/handoff.json > /dev/null
gh pr checks <PR>   # CI 全绿，或失败项逐条在 PR 记录原因
```

## 完成条件

- PR 已开，CI 至少 `python` 与 `contracts` job 运行并有结果；PR 描述含 PASS / FAIL / UNRUN / UNKNOWN 表与精确 base/head。
- 业务源码零改动（验收命令第 2 条）。
- `docs/handoff.json` 与 `HANDOFF.md` 同步。
- 由 Claude 按固定 head 独立审查后合并；Codex 不自批。

## 仍需 JT 决定（不在本单执行）

仓库可见性；既有证据是否清理；是否删除 hash pin（P1）；P2 城市/登录/最低 iOS；流程精简。

## 唯一下一步

完成本单 P0 PR → Claude 审查合并 → 根据 JT 决策派 P1（结构收敛）。
