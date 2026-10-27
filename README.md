# G2C

面向外国来中国旅游的游客：记住已授权的事实、经历与偏好，提供有来源的旅行建议，并在持续修改中保护已经确认的安排。App 名为 **G2C**，Web 品牌为 **go2china.space**，后端为 **CJ Agent 系统**。

**当前状态（2026-10-27）：** #149、#150 已审查、返修并合并。当前候选接入 DEBUG 模拟器开发会话：真实 UI 完成中英提案接受、显式确认和正式详情读取；拒绝、结果未知后的离线重启/原动作对账、跨用户隔离及 Release 不组装验证通过。后端是私有本地 PG、强制签名入口和 FakeProvider，不是云或真实模型验收。按 JT 最新指令，本轮经独立 Codex 审查、全部 CI 通过后正常合并，核验 main CI 后暂停；MESSAGE 写入仍未实现。复现见 [App README](ios/App/README.md)，当前状态与唯一下一步见 [HANDOFF.md](HANDOFF.md)（由 [docs/handoff.json](docs/handoff.json) 生成）。

## 已确认的产品边界

- 中英同时首发；先少量受邀外国游客内测，再准备公开首发。
- 四 Tab 顺序：助手 / 行程 / 插件 / 记忆；账号、设置、退出与注销放在记忆内。
- 首批完整长记忆，覆盖跨会话和不同旅行；Muse 风格布局按规格实现。
- 插件 v1 明确占位；语音、附件、礼物/referral 是视觉入口，不据此增加后端能力。
- 使用全新账号与数据，不继承旧账号、行程、订阅或权益；此次不迁移或删除旧数据。

## 文档导航

| 阅读目的 | 入口 |
|---|---|
| 首版交付与排除项、待决事项 | [范围](docs/scope.md) |
| 已确认与推荐的区别、决策理由 | [ADR 索引](docs/adr/README.md) |
| 模块职责、信任与数据流 | [架构](docs/architecture.md) |
| API、事件、版本、幂等与错误语义 | [契约设计约定](docs/contracts.md) |
| 长记忆完整生命周期 | [记忆规格](docs/memory.md) |
| Muse 布局与双语交互 | [UI 规格](docs/ui.md) |
| 协作、测试、环境与后续初始化 | [工程说明](docs/engineering.md) |
| 本轮证据、开工与后续放行清单 | [Readiness](docs/readiness.md) |

工作清单及 H/C/I 依赖的唯一入口为 [CJ-005 / GitHub #5](https://github.com/JTCAO515/G2C/issues/5)。35 项 CJ 编号与 GitHub Issue 号不同，本文不复制全量依赖图。Issue 管范围和任务依赖，ADR 管决策理由，规格管行为；变更时共同核对，冲突显式报告，不悄悄以旧讨论覆盖新确认。

## 模块与开工方式

客户端展示与收集操作；CJ API 校验身份、版本和业务写入；单主 Agent 提出建议；地点/事实/求解工具提供证据；业务库保存正式状态；内部记忆组件提供受控派生检索。详见[模块边界](docs/architecture.md#模块职责)。客户端与模型均不能直接改正式旅程。

## 本地检查（与 CI 一致）

```bash
uv sync --locked
uv run --locked python -B scripts/test.py        # 无数据库的全部套件
uv run --locked python -B scripts/pg_suites.py   # PostgreSQL 套件与迁移 up/down/up，需 CJ_PG_BINDIR 或 pg_config
```

后端入口与约定见 [backend/README.md](backend/README.md)，迁移见 [backend/migrations/README.md](backend/migrations/README.md)；CI（[`.github/workflows/ci.yml`](.github/workflows/ci.yml)）全部阻塞，是唯一的“绿”。历史证据已出仓，见 [docs/evidence.md](docs/evidence.md)。开发授权不包含付费调用、云资源、权限/凭据变更、外联、公开发布或删除旧数据。

交接更新：先改 `docs/handoff.json`，再运行 `python3 -B scripts/handoff.py render` 和 `python3 -B scripts/handoff.py check`。检查已进入 CI 的 python job，不依赖本机技能或 npm。四个 job（python、postgres、swift、ios-app）全部阻塞，合并还需 Claude 独立审查或 JT 明确同意。

GitHub 当前可见性为 PRIVATE（2026-10-27 只读核实）；许可证和产品法律条款仍待定。ADR 的可见性修订由 #144 单独处理，本切片不修改已接受 ADR。P2 范围为北京、邮箱 OTP、最低 iOS 17。
