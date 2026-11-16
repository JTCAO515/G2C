# 真实基础链路冒烟执行器（#1048）

这是 C 的串行调度与联合判定入口。七项、中英各一次，共 14 项；输入和预算来自
`docs/quality/m4-stage0-1048/basic-chain-smoke.v1.json`。该文件继续保留为阶段 0
设计原件，实际执行授权来自 JT 本轮 Goal 和 #495/6907095660，不能把设计改成执行成绩。

每次香港部署、每个 App 构建交 JT 前，各用新 run ID 和实际 App/服务端候选。
首个 FAIL/UNKNOWN 停新、保留原始输出、通知 A/L 修复；后续项 UNRUN。只有同一候选
的 14 项全部真实 PASS，才允许在 #702 写「可以请 JT 测试」。本工具不部署、不发版、
不修改原账，也不关闭 #815/#32 的其他门槛。

## 操作

App pin、旧对话和 host 配置由 A/B 的实际交付装配为本机 owner-only 文件；不入库、
不在命令行传 token。普通 Home 自己分配 MID，plan 的 null MID 是待绑定状态，
绝不是 collector 通配符。

```sh
uv run --locked python -B -m eval.basic_chain prepare \
  --app "$APP_PIN" --old-chats "$OLD_CHATS" --output "$NEW_PLAN"
uv run --locked python -B -m eval.basic_chain run --execute \
  --plan "$NEW_PLAN" --host "$QUALIFIED_HOST" --output-directory "$NEW_PRIVATE_RUN"
```

`prepare` 不联网、不占额度。首次没有旧合成对话时加 `--first-setup`，增加每语言两条
普通 App 消息，第二条必须续同一 CID。新目录必须不存在；实际产物目录 0700、文件
0600，不覆盖旧原件或 FAIL/UNKNOWN。不自动重试任何 UI 提交或 reader 失败。

运行在每项 UI 动作前检查北京时间，23:00–08:00 不启动新动作。夜间如需核对原动作，
使用 B 单独授权的原件读取流程，不通过重跑本脚本重新提交。供应商发票未取得时实付
为 UNKNOWN，不把它算成零；foreground/background 覆盖或原 usage 缺失则整项 UNKNOWN。

**当前真实执行仍 UNRUN。** 仓库实现不授予实际窗口；必须先拿到 B 受审查的有界
App claim、受保护原件 reader 和完整生产者/会计证据，以及 A 经验证的合成账号隔离
和普通 Home UI/真机入口。未交付时不得用本地 fixture、Debug 页面或 server-only
第二份 POST 替代。单元测试的控制分数不登记为真实成绩。

## A/B adapter ABI（候选接口；实际资格另交付）

host `version=LIO-basic-chain-host.1` 包含：`evidence_layer=L2+L3`、`synthetic_only=true`、
`app`、`candidate`、中英 `subjects`、`native_authority_ref`、`ledger_anchor_ref`、`pricing`，
以及 `programs.app/backend`。每个程序是 operator-owned、不允许组/其他人写入的绝对
入口，含实际 `sha256` 和资格证据 `qualification_ref`；单进程无 shell，stdin/stdout
为单个 JSON。入口及其依赖的资格由 A/B 负责，不能用自制常量 PASS 程序冒充交付。

App pin 字段为 `build/source_sha/artifact_sha256/protocol`：
`source_sha` 值是实际完整 Git source SHA（40 位），`artifact_sha256` 是产物
SHA-256；四项逐字匹配 A 的候选，不从 main 推定已安装。服务端 candidate 字段为
`source/image/schema/qualification_sha256`；subject 每语言单独固定。协议用普通
Home 实际版本，不切 native4 或临时宽权限路径代过。

每项依次调用：

1. B `action=preflight`：输入 `run_id/plan_sha256/step/context`；返回
   `LIO-basic-chain-preflight.1`、相同候选/subject/App、相同 run/plan/nonce、
   `starts_at/ends_at`（带时区）、`status=ACTIVE`、实际 `admission_ref`、
   `available_cny/required_remaining_hold_cny`，及实际核验的
   `authority_verified/bounded_app_claims_verified/idle_verified/capture_ready`。
   标准窗最长 60 分钟，首次最长 90 分钟；这些字段只表达现有原生资格，不创建授权。
2. A `action=one_gate`：同一输入加实际 admission 引用。只执行一项普通 Home UI
   操作，返回原始 UI facts；可以由 A 已验证的真机步骤驱动，但须逐项返回，不先跑完
   8 条再统一评分。未具备隔离/安全装配则拒绝，不碰 JT journal。
3. B `action=observe_original`：同一输入加 A 原始 facts。返回
   `LIO-basic-chain-observation.1`；`ui` 必须与 A 输出逐字结构相等，附同次原生 facts。
4. 首次失败 B `action=stop_new`：只停新/登记，不取消或重放原动作；失败也保留，C
   自身不再调下一项。B 不可用时保留 stop-new UNKNOWN，并人工交接。

完整、可执行的字段检查在 `runner.preflight`、`judge.judge` 和 `cost.costs`。
缺字段、错候选/owner/nonce、缺原件或超时都 UNKNOWN；实际明确错误优先 FAIL。
两个 producer 必须提供非空 `artifacts=[{path,sha256}]`；C 再读取 owner-only 原件核
哈希，stdout/stderr 和请求也保留在私有目录。不把历史报表里手写 PASS 当原件。

写入项关联：A 实际 outer UTF-8 JSON → B 同 MID 的 outer `input_sha256`；原生
canonical MESSAGE hash → inventory；原模型/工具 wire hash → 原 Meter/fee。
三种哈希分别核对，legacy1/2 不凭空声称服务端保存了未保存的 outer/protocol 字节。
`native_origin_verified` 必须由实际 App/原路由/typed claim 证据推导。实际 receipt、
RUN、正文、UI 展示来源都要关联，server completed 单独不足。SM07 还要三天实际地点、
原行程对象和展开/回看：legacy2 完整预览不计自动保存 PASS；native3/4 或声称保存时
要求同原动作持久版本/历史，不编日期或人数。普通问答不写 Trip 或 Saved Memory。

读取项须无新 MESSAGE、无新付费操作、Trip/Memory 不变，旧/新 CID、历史及草稿
由 A UI 与 B 原件联合核验。恢复项不插新欢迎语；后台与锁屏返回均要覆盖。

时间使用 A 实际单调时钟：`first_progress_ms/first_body_ms/complete_ms`；未发进度
用 null + `progress_status=NOT_EMITTED`，不能伪造 0。正文/完成须在现行 90 秒上限内。
本门禁不替代 #32 的 p95/其他性能门槛。

## 费用与输出

按原账每个 `ledger_id/attempt_id` 去重，要求完整 foreground/background 及实际
生产者关闭原件。`run_once.returned`、空在途和 foreground completed 单独不证明
全部费用闭合。INTENT/UNKNOWN 保留原 hold；错 model/endpoint/region 或原 usage
不完整，不伪造 token 成本。新增收费工具未注册则拒绝计为免费。

`report.json` 固定分母 14，含每项状态/理由/时间、费用三栏、已知费用小计、实际
候选和 release_allowed。未完整覆盖的总费用为 null，已核到的原小计单独保留。
预计标准 8 MESSAGE、46 model allowance、10 tool，保守 56、请求额度 60 元；首次
12 MESSAGE、66 model allowance、10 tool，保守 76、请求额度 80 元。
每语言工具 SM02=1、SM05/SM06=0、SM07=4，双语共 10。预计 token/tool 成本标准
0.371504 元、首次 0.519984 元；均是报价，不是实际成本，也不替代原生准入。

真实结果摘要写 #1048，首失败原件交 A/L；全过后才写 #702。C 既有子额度不调整。

## 本地检查

```sh
uv run --locked python -B -m pytest -q eval/tests/test_basic_chain.py
uv run --locked python -B scripts/test.py
```

测试只验证执行器的停派、双哈希/费用/owner/候选边界及语义正反例，不发真实调用。
