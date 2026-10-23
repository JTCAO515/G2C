# 宿主 Observation 同步重入 P2：作者返修

源码固定 `22650bb21eaa388abeb2df8aac4b647477d5138f`，parent
`c57e78d68178f0b34167eafaaa70b836c870ae24`。最终候选 HEAD 为后续证据提交。
原租约，仅修改 NeedsContainerHost.swift 与相关 Harness 测试/本目录证据；
不改 FEAS client、Memory host、ShellState、peer、API/Auth/root，不启用传输。

## 原问题与修复

Testing 原新探针及 FAIL 在 `cj-testing/CJ-035-feasibility-host`，只读收取后保全为
[testing-original-ObservationOpenProbe.swift.txt](testing-original-ObservationOpenProbe.swift.txt)、
[testing-original-observation-open-probe.log](testing-original-observation-open-probe.log)、
[testing-original-observation-open-exit.json](testing-original-observation-open-exit.json)。

同一原探针加入作者现有 Harness，在未修改产品的 c57e78d 上复现：
[observation-open-before.log](observation-open-before.log) exit1，
外层返回后 getter 的实际 presentation ID 与通知内新建 ID 不一致。
原7函数16场景 PASS 和本 FAIL 同时保留，不将前者称覆盖本缺陷。

根因：宏生成 `evaluation` setter 在赋值前发送 Observation willSet；
原 epoch 核查位于 setter 调用前，观察者同步重入后外层仍完成旧赋值。

修复：将 presentation 的存储与通知边界明确为 computed
`feasibilityPresentation` 的 `access(keyPath:)` 和 `withMutation(keyPath:)`。
底层 storage 用 @ObservationIgnored，**通知继续由真实 Observation registrar 发送**；
在 withMutation 闭包内、willSet 观察者已返回而实际 storage 尚未写入时核查原 epoch。
同样保护 invalidateFeasibility 的清除，避免旧 dismiss/leave 清掉通知内新开呈现。
没有通过 getter 合成/替换 ID，没有排队延迟、关闭通知或修改原探针断言。
旧操作通知发出后可被新操作取代；open 的 true 仍表示其来源检查已接受，
不保证其呈现最终仍是当前值，不赋予评估/网络/保存授权。

## 验证结果

- PASS：原 Testing 同一探针，[observation-open-after.log](observation-open-after.log)。
- PASS：必要相邻回归，[observation-regression.log](observation-regression.log)：
  10函数、21展开场景 = 原16 + 原Observation探针1 + 已有呈现替换/关闭/离场重入3
  + 真实通知保持1。包含最终 getter 确认真实新ID保留、旧ID关闭无效，
  正常发布和清除的观察者均实际触发；未删除/改弱原16断言。
- PASS：iOS Simulator generic arm64/x86_64 局部静态编译，
  [observation-ios.log](observation-ios.log)，Xcode27.1/Swift6.4，无签名/运行。
- PASS：git diff --check、独占路径及源码hash；见
  [observation-executed-source.json](observation-executed-source.json)。

原 inputs.json、tests-final.log 及原失败日志保持原样；本次实际准备图见
[observation-inputs.json](observation-inputs.json)。复现准备仍使用原
`python3 scripts/prepare_feasibility_host.py`，脚本会生成当前 inputs.json；本证据保留其
当前输出为 observation-inputs.json 后恢复原 inputs.json，以免覆盖历史证据。
未改变 fixed client/shared/SDK/Auth/NEEDS pins，SDK仍单dc29，不全重跑原client47。

定向复现/修后命令：

```sh
python3 scripts/prepare_feasibility_host.py
swift test --package-path contracts/ui/evidence/feasibility-host/.prepare/Modules/CJShell --force-resolved-versions --skip-update --filter testingObservedOpenMustNotOverwriteReentrantPresentation
swift test --package-path contracts/ui/evidence/feasibility-host/.prepare/Modules/CJShell --force-resolved-versions --skip-update
```

编译命令仍为原报告中从 `.prepare/Modules/CJShell` 执行的 xcodebuild generic Simulator。
本轮是 synthetic ShellFacts + 实际宿主源码的局部图，与原证据相同层级。
client 独立错绑定 P2 仍 HOLD；未用此宿主修复冒客户端或完整 App 通过。
正式 cohost/全App统一图、实际 root/session 组合、独立复审/Testing、真实服务/设备、
CI/PR/merge/deploy 均未在本返修放行。未发送外部消息，由 Main 官方读取固定结果。
