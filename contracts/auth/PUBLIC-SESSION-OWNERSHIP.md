# SessionLifecycle 公开只读归属查询 — 最小消费增量

base b24cc77c307bbb1dd9c552aeb92a148213534541。原 SessionBridge1e 与 Memory key
purpose 保留。本轮只将既有 ownsOperation 从 package 改为 public，函数逻辑不变：

```swift
@MainActor
public func ownsOperation(_ operation: SessionOperation) -> Bool
```

返回该 operation 是否仍为此 SessionLifecycle 实例/当前 generation/当前 operation
的原操作。一个 lifecycle 的 persistence/namespace 由可信 host 绑定；此函数不读取
或重新认证 namespace，不证明账号/凭据/权限，不接受 caller namespace 覆盖。
同 namespace 的另一 lifecycle 实例也不拥有此 token。

| 情况 | ownsOperation | isCurrent |
|---|---|---|
| 当前正常原操作 | true | true |
| 原操作自身真实存储失败而 blocked | true | false |
| 被新 operation 或 B 代次替代 | false | false |
| clear 已开始（成功或失败） | 原 token 为 false | 原 token 为 false |
| 来自另一 lifecycle 实例 | false | false |

CJ006 的 load/save catch 可在重新核原 UI 绑定后，用 ownsOperation(original) 区分
“应显示原操作存储失败”与“旧错误不应污染新 B”。它不能替代使用/回写前的 isCurrent，
不能据 true 解除 blocked、重试写入、恢复会话或授业务权限。调用外部回调后仍须
重新核对应绑定。clear 会主动废弃原 operation，故不能用 clear 前 token 的 false
单独推断新 B 已替换；继续使用已接受的 clear/UI 代次收尾规则和结构化结果，
不按错误字符串猜测。具体 host 改动由 CJ006 在原写权实施。

验证：普通 import CJSession 的 PublicOwnershipTests4项 + 原 SessionStore9项，
13/13 PASS；另用 `-package-name CJ007ExternalOwnershipConsumer` 单独 swiftc
类型检查 ExternalOwnershipConsumer.swift，exit0，无 @testable、无同 package 权限。
证据：CJAuth/evidence/public-ownership-tests.txt、public-ownership-external.txt。
原 bridge31/keypurpose 等行为未改，证据复用，不重复后端/SDK/Keychain测试。

没有公开代次写入、材料读取或新 wrapper；不改 Package、默认策略、权限/access
组、后端或失败 probe。版本字符串与方法签名参数不变；消费者 pin 新固定 head。
