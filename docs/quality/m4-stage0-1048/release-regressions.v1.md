# #1048 发版故障本地回归

按 [JT 部署决定](https://github.com/JTCAO515/G2C/issues/495#issuecomment-6972695033)
和 [回答优先、写入从严](https://github.com/JTCAO515/G2C/issues/495#issuecomment-6972760640)
核对修复候选。下列用例使用隔离的本地账号、私有 PG 或模拟传输。
[原回归集](regressions.v1.json)、[阶段 0 冒烟设计](basic-chain-smoke.v1.json)及各评测分母保持原版本。

## 锁等待 / Timeline reads during provider response

原件见 [构建 47 两次 timeline 503](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-6968815874)。
两次读取均在 MESSAGE 锁等待超时后失败；历史持锁事务及与两条 RUN 的逐条映射仍 UNKNOWN。
[进件](https://github.com/JTCAO515/G2C/pull/1170)和[普通讨论](https://github.com/JTCAO515/G2C/pull/1174)
各有独立的本地红绿对照。

- 先在同一会话留一轮完整原件。分别在 `model.lio_intake.9` 与
  `model.lio_discussion.0` 已发出请求、响应被夹具暂停时，从同一账号读 timeline。
  每次读取应在释放模拟响应前实际返回 HTTP 200，并保留旧回答。放行后核同一原 RUN、
  一次上游发送、同一计量链及 Trip 零写入（讨论）。保留普通问答与跨 owner 负例。
- 本地组件检查覆盖两条路径的发送交接及原计量保护。签名 PG 投影组另查真实争锁时的
  原 503 保护、无锁的队列读取以及 owner、RUN、原参考绑定。该负例的 503 应继续成立。
  候选还需用同一 worker/PG 和暂停响应覆盖实际读写重叠，组件检查单独通过不能填这一格。
- 进件、讨论的原组合执行回执分别为
  [503→200](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-6968967148)和
  [正常响应及缺 DONE](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-6969237889)。
  后续改动以候选本身的并发用例为准。

```sh
CJ_ENV=local uv run --locked python -B -m pytest -q \
  backend/agent/tests/test_provider.py backend/cj_api/tests/test_m4_real_services.py
uv run --locked python -B scripts/pg_suites.py lio_projection
```

## 格式、来源与流完整性 / Reply and write separation

原 [#994](https://github.com/JTCAO515/G2C/issues/994) 的两条模型回执实际被进件格式或
来源绑定拒绝，用户没收到回答。原输出未捕获，具体坏字段未知；只用新合成坏值回放。
构建 47 另一原 RUN 的供应商原因仍 UNKNOWN，在本地分别构造缺 DONE、usage 或模型身份，
不把任一夹具结果当该原 RUN 的归因。

- 中英分别注入非法进件格式和不匹配的用户原文引用，验证现有预算允许时有实际的普通
  对话正文、原坏值无执行权限、无 NEEDS 或 Trip 写入。预算拒绝应发生在下次出站前；
  原拒绝与账务保留。对合法输入，继续核实际规划和原固定项。
- 单独注入结构化草稿的重复项 ID。用实际 timeline 核到可读的候选正文和未保存提示，
  核原校验失败、Trip 零写入。基础冒烟的三日规划还须核每一天的实际安排。
- 流完结信号、usage 或模型身份缺失时，完整正文和明确截断分别造对照。
  前者应可见，后者不展示为完整回答。两者均核同一原 attempt、财务 UNKNOWN 和原 hold，
  不因展示发放写入权限、不重派。现有供应商测试覆盖谨慎结算、INTENT 及无重派；
  完整正文展示及截断对照须在 B 的候选中实测，旧测试的无正文断言不能代替新验收。

```sh
CJ_ENV=local uv run --locked python -B backend/cj_api/tests/lio_cross_language_pg.py
CJ_ENV=local uv run --locked python -B backend/cj_api/tests/lio_rejected_capture_fallback_pg.py
```

## 上一轮失败后继续 / Follow-up after an unsuccessful turn

在同一中英会话中用夹具使原轮失败或 UNKNOWN，再提交新的、独立的用户消息。
实际验证首轮用户数据进入下一轮、原未决动作不重派、原轮无写入授权、后续应答可见。
覆盖 Demo 与非 Demo 的原日期边界；对话继续不能继承旧的规划执行授权。
真实测试仍在首个 FAIL 或 UNKNOWN 后停止派发。

```sh
uv run --locked python -B scripts/pg_suites.py lio_failed_history
```

## 登录前置 / Sign-in prerequisite

见 [原登录回归](login-prerequisite-regressions.v1.md)与 [#1124](https://github.com/JTCAO515/G2C/issues/1124)。
本地入口为 [check_lio_signin.py](../../../ios/App/Acceptance/check_lio_signin.py)。
分别用 `--language zh-Hans`、`--language en` 和各自新的 `--output`、`--build-dir`
目录运行已授权的本机模拟器夹具。有效签发后应进同一账号 Home，冷启动保留原对话与草稿，
不要求旧 starter，也无新业务消息。使用 `--scenario malformed` 核无效响应应安全拒绝，
保留诊断而不创建会话。实际香港短码登录与真机七项另记其原件。

## 复核记录

运行前沿仓库既有方式安装锁定依赖。PG 用例使用本地 PostgreSQL 17 的 bin 目录，
通过 `CJ_PG_BINDIR` 指定。PR 回执登记候选 SHA、执行入口和实际结果。
真实冒烟以 [#1048 当前判定](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-6972969188)
和候选原件为准。本地用例不改变已记录的真实失败、未知、费用或释放条件。
