# Lio Textual 渲染评估（#933 / #922 WP10）

结论：本轮不引入 Textual、不替换现有渲染，最低系统保持 iOS 17.0。WP10 的分段、问题组、画像与出口属于消息展示和普通发送交互，不以更换 Markdown 库为前提。依据 [JT 的 2026-11-13 决定](https://github.com/JTCAO515/G2C/issues/922#issuecomment-6848017500)，本文件只交评估报告。

## 考察范围与来源

核对日期：2026-11-13。固定考察上游正式发布的 [Textual 0.4.0](https://github.com/gonzalezreal/textual/releases/tag/0.4.0)，tag 指向 `b38f46ece8954c6c29eb4eadf679aae2da373549`；不是新增依赖声明，也不推断它是今后的最新版本。以下上游链接均固定到该提交。

| 项目 | 一手证据 | 对本次交付的含义 |
| --- | --- | --- |
| 最低系统与工具链声明 | [Package.swift](https://github.com/gonzalezreal/textual/blob/b38f46ece8954c6c29eb4eadf679aae2da373549/Package.swift)：Swift tools 6.0，iOS 18、macOS 15 | 考察版本的官方支持范围不包含 Go2China 必须保留的 iOS 17；本次不提高 App 的最低系统 |
| 行内、块级排版 | [README](https://github.com/gonzalezreal/textual/blob/b38f46ece8954c6c29eb4eadf679aae2da373549/README.md)：`InlineText`、`StructuredText`、标题/列表/表格样式与文本选择 | 提供较完整的展示能力；这些上游功能描述不等于已在 Lio 中通过中英、流式、选择或读屏验收 |
| 顶层许可 | [LICENSE 原文](https://github.com/gonzalezreal/textual/blob/b38f46ece8954c6c29eb4eadf679aae2da373549/LICENSE)：MIT，版权人为 Guille Gonzalez | 若未来分发该代码，需按许可保留版权及许可声明；本次未复制或分发该库 |
| 依赖与资源 | [Package.swift](https://github.com/gonzalezreal/textual/blob/b38f46ece8954c6c29eb4eadf679aae2da373549/Package.swift)：运行 target 使用 ConcurrencyExtras、SwiftUIMath，包含 Prism 资源；SnapshotTesting 用于测试 target | 不能将引入成本理解为只增加一个展示类型；未来须核对实际锁定的传递依赖、资源与包体 |
| 上游许可清单范围 | [LICENSE-3rdparty.csv](https://github.com/gonzalezreal/textual/blob/b38f46ece8954c6c29eb4eadf679aae2da373549/LICENSE-3rdparty.csv)列出 ConcurrencyExtras 与 SnapshotTesting | 该表不能代替实际解析出的全部依赖和资源许可核对；本报告不是完整传递依赖审计 |

## 与 Lio 现有实现的关系

代码基线为已合 main `e17e86ec797dfd9e796457e8788d48098a4496bc`。当前 [LioReplyMarkdown](https://github.com/JTCAO515/G2C/blob/e17e86ec797dfd9e796457e8788d48098a4496bc/ios/Modules/CJShell/Sources/CJLioUser/LioReplyMarkdown.swift)使用 Foundation 的 Markdown 解析结果，显式保留标题层级、列表标记和行内属性，再交 SwiftUI `Text`。链接和最终展示文本仍经过现有公开内容边界；[LioHome](https://github.com/JTCAO515/G2C/blob/e17e86ec797dfd9e796457e8788d48098a4496bc/ios/Modules/CJShell/Sources/CJLioUser/LioHome.swift)保留文本选择、回答气泡及失败提示。

[现有 Markdown 用例](https://github.com/JTCAO515/G2C/blob/e17e86ec797dfd9e796457e8788d48098a4496bc/ios/Modules/CJShell/Tests/CJLioUserTests/LioReplyMarkdownTests.swift)覆盖标题、列表、加粗、链接、纯文本前缀、嵌套列表续段、内部地址和显式执行信息拒绝。它们是后续 WP10 继续保留的检查，不是 Textual 的测试结果。

| WP10 需要的行为 | 本轮实现方向 |
| --- | --- |
| `segments` 按顺序显示气泡 | 由 #925 确定的消息结构驱动，沿现有渲染与展示边界绘制每段；不在 Markdown 文本里猜测交互结构 |
| 问题组选择后一起发送 | 使用原生可选择控件与「好了，继续」；精确字段、选项标识及合并发送编码等 #925 冻结，不让展示库承担发送状态 |
| 画像修改、提醒、出口和调整按钮 | 使用原生标签、气泡与按钮；修改画像通过普通文字消息，不新增直接画像写入权限 |
| 旧 `.1` / `.2` 消息与纯文本 | 保留现有版本的解码和渲染路径；新版本无效响应不能静默降级成旧版本成功，具体兼容用例随 #933 实现验收 |
| 读屏与中英 | 后续以真实 App 的标签、选择状态、合并发送、焦点顺序和完整 AX 证据验证；不以库宣传或此报告冒称通过 |

## 验证边界与后续条件

本次完成的是上游发布、平台声明、顶层许可、依赖声明与现有代码的只读核对。没有安装 Textual，没有修改 `Package.swift`、锁文件、部署目标或渲染代码，也没有建立 iOS 18 与 17 的双渲染路径。

Textual 在 Lio 中的编译、包体、长回答流式性能、中英浅深色、VoiceOver、完整 AX 与真机比较均为 **UNRUN**；不将上游展示例子或现有 Lio 的测试当作这些结果。当前 renderer 对 #933 完整新协议的兼容也要等实际字段与实现后验证。

如 JT 今后明确重新决定引入，再固定届时的确切版本及全部依赖、核对许可和最低系统支持，复用同一批中英合成输入比较长文本/流式追加/选择/链接与读屏表现，并保留旧消费者和失败记录。未经该决定，继续现有渲染，不用非官方移植或降低上游平台声明来替代本次结论。
