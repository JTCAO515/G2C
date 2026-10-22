# Canonical typed clear settlement — SessionLifecycle 最小公开增量

base `6fe045cf9c6851eb4076a31da20eea0eb6aed10c`，旧 Message/Memory/Trip 用途字节不变。
依据 CJ006 固定反例 `3ff9a15f72d7b26ad2fb0288d3b238eb7bf9a138` 的
contracts/ui/evidence/sdk-clear-same-tuple/REPORT.md 与独立 Testing
CJ-006-clear-lifetime/REPORT.md。same verifier tuple / shell generation 不能判断
原 clear 的所有权；旧错误同名与正常退休 token 均不能替代 canonical 结果。

## 已实现公开签名

```swift
public enum SessionClearSettlement: Equatable, Sendable {
    case cleared
    case failed(SessionFailure)
    case replaced
}
// SessionLifecycle 是 @MainActor；方法同步执行。
public func clearWithSettlement() -> SessionClearSettlement
```

分类直接发生在既有 clearAndBlock 回调前捕获的私有 clearing generation/current
比较处；不暴露私有代次、凭据或新增 host authority。

- `.cleared`：原 clear 本身完成，lifecycle 原代次进入 cleared。
- `.failed(canonicalFailure)`：原 clear 仍拥有结算，实际存储失败；状态 blocked。
  包含真实原失败恰好名为 `.staleOperation`，不能再按此枚举名字当作 replaced。
- `.replaced`：回调期间另一个 lifecycle 操作接替；无论外部回调成功还是抛错，
  旧 clear 不改新状态。B 可能 saved，也可能自己失败 blocked；结果不证明 B 有效、
  不采纳 B、不提供业务许可或新的 namespace/verification 绑定。

CJ006 应在既有 UI/verification guards 下 switch 此结果：仅 cleared 结算原成功，
仅 failed 结算原故障；replaced 退休旧 UI bookkeeping，不修改或自动采纳替换存储。
不要再用 ownsOperation(old)==false、error 字符串/同名 staleOperation、UI tuple
相等或公开 state snapshot 猜 clear 结算。callback 返回后若 host 还有其他外部调用，
仍需原有 host 回写检查；该结果只说明本次 canonical clear 边界的结算。

## 兼容

旧 `clear() throws` 保持公开签名，并从同一个实现映射：cleared 正常返回、
failed 抛原 canonical failure、replaced 抛 SessionFailure.staleOperation。
因此旧调用/抛错行为不变，也有意保留旧接口不可区分同名错误的历史限制；需要
区分者必须消费新 typed API，而非私用字段。未改 SDK bridge/host 的既有 presentation
结果或自动启用新 API。没有第二套 clear 实现、wrapper 模块或状态权威。

## 验证

新 ClearSettlementTests6项：正常成功、原 storageUnavailable/staleOperation/Keychain
错误、任意错误 canonicalization、same-identity saved replacement（外部成功/抛错）、
replacement 自己 blocked（外部成功/抛错）、旧 throws API 兼容。复用同一 lifecycle/
namespace，不用 verifier/UI tuple 变化规避反例。全相关 Session/bridge 原用例同时运行：
6新 + 9 SessionStore + 4 ownership + 8 adjacent + 4 save + 10 bridge = **41/41 PASS**。
原 UI 反例失败证据仍在原 owner，未冒称本轮修复 CJShell 或独立双审通过。

普通 import CJSession 的 ExternalClearSettlementConsumer.swift 另以
`-package-name CJ007ExternalClearConsumer` 单独 typecheck PASS，无 @testable 或
package-private 权限。证据 evidence/typed-clear-settlement-tests.txt、
evidence/typed-clear-external.txt。

只改原 CJSession 一个生产源文件与相应测试/契约/证据；Package、默认关闭、已有
密钥用途/编码、backend、CJShell、签名/权限均未改。无真实 Keychain/网络/资源动作。
消费者 pin 新 head；本结果不是完整 Auth、平台持久性或新 B 的授权验收。
