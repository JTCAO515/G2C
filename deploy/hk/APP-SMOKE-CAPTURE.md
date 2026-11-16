# 普通 Home 冒烟采集（B-only）

这是 #1048 门禁的采集组件，尚不是完整冒烟执行器或香港 ACTIVE 资格。
App 沿普通入口生成 MID 并提交；不注入固定 MID、不改 journal、不走实验 RPC。
C 对同一组 App 原件判定，不另发一套 API 消息。

```text
普通 Home POST → 原 AUTH / MESSAGE / RUN / 费用账户资格
  worker 的原 registrations_for_run 回调
    匹配冻结的下一输入槽 → 持久记录真实 MID/CID/generation/RUN/sequence
    返回原注册表 → 原模型/工具/Meter/唯一费用出口
  run_worker.run_once 返回 + 原 ACK → producer-return 观察记录
```

## 冻结与文件权限

B 为每轮生成一个 `G2C-App-smoke-capture.1` 的 0600 策略文件。它绑定：

- window_id、精确 server source、A 的 App source、C计划SHA、起止时间（最长90分钟）；
- 原 ledger_id / producer_id、恰好两个既有 C 主体；构造时只读核其原 scope_sublimit 归属 C；
- 每主体4个冒烟槽、最多2个准备槽，总8条冒烟、最多4条准备；
- 有序 slot_id / nonce / subject / locale / protocol / text_sha256 / setup，以及
  conversation_mode（new/default/continuation）和 prior_slot_id；
- 已存在的0700 claims目录及device/inode、0600 evidence_manifest路径及SHA；
  既有 ToolEvidence v4 的同source、同两个主体、model+tool、同截止时间和0700 artifact目录device/inode。

App source只是待与A实包交叉核对的pin，服务器不把配置中的SHA当作App证明。
输入槽只存正文SHA；不得把邀请码、Bearer或模型密钥放入策略。

目录由B显式预建，内含0600 `claims.lock` 和 `claims.json`；后者初始内容为
`{version: "G2C-App-smoke-claims.1", policy_sha256: <策略原字节SHA>, claims: []}`。
组件不自动创建、恢复或清空这些控制文件。每轮用全新目录；旧UNKNOWN、claim和pending文件保留。
文件锁互斥；原子写通过O_EXCL的claims.pending、fsync、replace和目录fsync发布。
残留pending是待核原动作，不覆盖后重放。重启读取同一原claim，同MID/绑定不新增槽。

## 准入与原件

仅在原已受理RUN中、任何固定回答/Memory/模型之前登记。wrong owner、窗口过期、
目录替换、策略变化、输入/语言/顺序不符、超额或改绑都在新provider注册前拒绝。
其他主体仍用原注册表，不扩大其采集范围。new槽核原生成CID和sequence1；
continuation必须接同一已登记prior槽的CID/generation和下一sequence。

**legacy的两种摘要必须分开。** 1/2原路径持久化的是demo_dialogue_input_sha256和
canonical MESSAGE raw_input/input_sha256；它没有持久化完整outer bytes或可唯一识别的outer版本。
采集保存 `input_sha256`（原outer摘要）和 `canonical_sha256`（原MESSAGE摘要），明确为legacy execution origin。
C须用A实际INTENT原字节重算outer SHA并核原MID、解析实际普通协议；不能从默认源码、
配置pin或canonical摘要重构outer bytes。原生3/4必须走另外资格，不能替普通Home过门禁。

## 结束与费用边界

只有实际run_worker.run_once返回、原RUN终态和delivery ACK核同后才写producer-return；
该记录不来自空队列推断。这个组合未传background_jobs，但现有Memory原件和操作仍须全部核对。
记录的 `cost_coverage=NOT_ASSERTED`：它不是完整费用PASS、不是供应商已结算、也不释放任何hold。
后续受保护reader必须核全部前后台原操作、native Meter、financial原行及生产者闭合，缺件为UNKNOWN。
观察记录写失败只发固定ALERT并让冒烟缺证；不重写原终态、不重放、不影响其他用户的原请求。

worker入口为 `worker --app-smoke-manifest <B的0600路径>`，与旧固定MID collector和
实验runtime-manifest互斥；旧路径保留。新组合与脚本都须独审、精确CI、实像/资源核同、
原账/空在途和正式新lease后才可安装或派发。当前文件不签发资格、不放开真实请求。
