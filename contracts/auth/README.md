# AUTH 语义草案（CJ-007 / Issue #8）

版本标识：`AUTH-draft.1`；目标 `AUTH@1.0` **尚未发布/冻结**。
协议无关规范子范围候选：[AUTH-SEMANTICS@0.1.0-rc.1](SEMANTICS.md)，
当前待独立审验及 Main 决定发布范围；不等同完整 AUTH@1.0。
执行 owner：Main 指派的 CJ007 独立执行聊天（本候选作者）；不兼任 Main。
输入：r3 Issue #8 本地已验证快照、固定 base
`00769d7f793566887a8e192a6ca7b35d8c5fb46a` 的 BASE@1.0 与 docs/contracts.md。
UI@1.1 仍为候选；当前固定版本消费确认见 [UI-1.1-CONSUMPTION](UI-1.1-CONSUMPTION.md)。
本地展示清理与 token 屏障已在候选源码提供；真实 host/Auth 映射仍 **PENDING**。
不沿用 UI@1.0 的完整兼容性，不授予下游正式 Auth 实现权限。

本目录只含协议无关语义、正负样例和内存合成检查。没有 endpoint、JWT
声明、provider 配置、SDK adapter、凭据、数据库或 RLS；不得导入生产。
唯一正式 API 来源仍为 `contracts/api/openapi.json`，本草案不是第二 API。
领域语义经 owner/消费者确认后，由 CJ-005 共享契约 owner 纳入唯一来源，
再生成消费者；届时本目录的合成记法不得作为并行 wire schema 长期维护。

新增本地 Swift 流程候选与 Google/Apple 接入准备见 [SDK-BOUNDARY](SDK-BOUNDARY.md)。
缺配置的入口明确不可用；官方 SDK 本地编译/拦截 transport 差额见
[SDK-ADAPTER](../../ios/Modules/CJAuth/SDK-ADAPTER.md)，不代表真实 OAuth/账号已接通。

服务端独立实现候选：[接口/准入](SERVER-INTERFACE.md)、[JWT adapter 与验证](../../backend/auth/README.md)。
这不代表正式 API、真实权限提供者或实时撤销已经接通。

CJ005 的 Bearer 输入/注入契约、候选 HTTP/BASE 映射及显式 Supabase profile 见
[API-COMPOSITION](API-COMPOSITION.md)；仍无公开路由或自动权限提供者。

## 已确认的首版账号方式

邮箱＋密码、自助注册、邮箱验证及找回密码；JT 管理受邀名单，未受邀不能使用模型。
具体来源、状态正负样例与新环境最小待决见 [EMAIL-DECISION](EMAIL-DECISION.md)。
这项产品决策不代表环境或权限已开通，也不冻结 AUTH。

## 身份与授权边界

- **principal**：服务端在新 CJ 环境验证真实会话后得到的内部身份；不能从请求
  owner/user_id、客户端账号显示值、请求追踪 ID、模型文本或邀请标志取得。
  旧产品凭据/缓存/权益没有隐式映射或导入。
- **session revision**：服务端可信的会话有效性版本/撤销屏障的语义占位，
  不规定 JWT claim、表或 SDK 实现。刷新、过期、撤销是否改变该值，由真实
  SDK 与服务端验证方案共同定案；不得把客户端代次当作服务端撤销机制。
- **client generation**：本机账号生命周期屏障；每次显式登录尝试、退出、
  切账号、明确失效均轮换。重新登录同一 principal 也不能复用旧代次。
  重启须有新实例标识，不能只把计数归零后接受旧任务。
- **eligibility**：服务端对该 principal 的受邀资格检查，独立于身份验证；
  `allowed / denied / unknown` 为概念状态。验证身份成功不自动获准内测。
  资格未知/被拒绝均不得访问受限业务或派发模型任务。客户端隐藏按钮不算门禁。
- 每次资源读写、引用、事件/恢复、后台上下文、结果返回和正式副作用提交均
  在相应权威边界检查当前身份、有效会话、资格和实际资源归属。全部引用都要查，
  不仅检查外层 Trip。异步等待后在提交/派发前重查，不以入队时快照代替。
  数据库必须另行执行其权限检查；本模型只证明规则样例，不证明数据库隔离。
- 他人资源与不存在的资源对外同样拒绝，不暴露存在性。合成检查中的内部拒绝
  原因只用于本地测试，不是可返回给客户端的错误详情。

## 客户端状态与晚到行为

`anonymous → checking → eligible / restricted / unknown`，明确失效进入
`invalid`。这些是草案概念，不是已冻结 UI 枚举；账号入口位于记忆内。

1. 启动/恢复默认不授权私有操作；通过正式 SDK 验证后再建立身份与资格。
   凭据只能由 SDK/平台安全存储管理；本目录只用布尔值表示其存在。
2. 每个异步身份请求捕获实例、client generation 与唯一操作序号。仅当前
   未消费操作可回写；重复回调和较旧刷新回调不能覆盖较新结果。
3. 每个私有请求捕获实例、代次、principal、session revision；每次 await 后，
   在显示、缓存、持久化、订阅事件、派生子任务前检查完整绑定及当前资格。
   取消是优化，绑定检查才是正确性屏障。失去资格也清除可见私有内容。
4. 退出/切账号立即轮换代次、取消本地活动、清空可见内容、去除旧安全凭据的
   自动恢复资格，并使旧缓存不可读；不能等待远端退出 ACK 才清除。
   远端撤销 `unknown` 与本机已退出并存；不声称其他设备已退出、不自动盲重发。
   本地安全存储删除失败必须显式报告并阻止自动恢复；实际 SDK 验证待做。
5. 网络中断、超时、验证服务不可用都为 `unknown`，保留既有凭据，不报账号
   无效、不把本地退出扩大为服务端全局撤销。草案合成模型保守隐藏私有内容、
   阻止新业务；离线缓存可见期限尚待产品决策，不能把此模型当最终离线策略。
6. 只有与当前请求绑定的权威身份失效结果才清除当前身份；旧账号的失效回调
   不能登出新账号。单一资源拒绝不是会话失效，资格拒绝也不删除有效凭据。
7. 已发出的业务写入响应丢失须保留原动作的恢复语义；账号切换仅阻止污染新账号，
   不证明服务端回滚、停止任务或全域物理删除。MESSAGE/RUN/CLEANUP 负责具体恢复。

## 双语状态意图与 BASE 的接缝

| 语义 | 中文意图 | English intent | 凭据与恢复 |
|---|---|---|---|
| checking | 正在确认会话 | Checking your session | 禁止新私有操作 |
| identity invalid | 登录已失效，请重新登录 | Your session is no longer valid. Sign in again. | 当前权威失效才清除 |
| network unknown | 暂时无法确认会话，请检查网络后重试 | Unable to verify your session. Check your connection and try again. | 保留凭据；只安全重试验证读取 |
| eligibility denied | 当前账号尚无内测资格 | This account does not have beta access yet. | 保留身份；阻止受限业务 |
| eligibility unknown | 暂时无法确认内测资格 | Unable to confirm beta access right now. | 保留身份；阻止受限业务 |
| logout remote unknown | 已退出本机，远端会话撤销尚未确认 | Signed out on this device. Remote session revocation is not confirmed. | 不恢复旧会话，不报全局成功 |
| resource denied | 无法访问此内容 | This content is not available. | 不泄露他人资源，不自动登出 |

这些是语义样例，正式中英文案需 CJ006 消费确认。未来 HTTP 错误须使用 BASE
现有 ErrorResponse/request_id；网络无响应时不得伪造服务端 request_id。
本轮不指定 HTTP code/category 或新增机器错误码。读取未知可安全重新验证；
有副作用的未知（建号、退出撤销、业务写入）必须先核原操作，不能笼统标可重试。

## 敏感数据与清理职责

凭据/密码/邀请秘密不得进入本目录、日志、普通缓存或模型上下文。诊断仅留必要
脱敏操作关联；principal 也不是公开日志标签。客户端私有缓存须按环境与身份隔离，
退出立即不可见，具体清理失败与重启恢复防线待实现。CJ007 负责会话/本机身份清理；
CJ009/010/011/015 负责各域绑定与晚到；CJ024 负责完整删除；CJ005 负责统一存储登记。
本轮无新增持久存储，未改统一登记，也不实现注销或删除旧产品数据。

## 最小待决与消费门槛

| 输入/确认 | 决策/执行 owner | 仅阻塞的后续部分 |
|---|---|---|
| 登录方式与 JT 管理邀请已确认；名单权威绑定/撤销、链接与会话生命周期仍待定 | JT / CJ001；CJ007 实现 | 真实登录、准入与对应 SDK 负例 |
| 新 CJ C2 隔离环境、可信验证方案与失效传播、安全存储、HTTPS/数据库权限 | CJ005 + CJ007，资源授权由 JT | SDK/server/DB 实现与两个新账号验收 |
| 记忆内账号入口、双语状态、退出/切号事件与清理消费 | CJ006 + CJ007 | 真实 UI@1.1 host 绑定与最终消费确认 |
| 离线可见范围、留存/清理、处理方与用户说明 | JT / CJ001；CJ024、CJ007 | 离线显示与持久存储策略 |
| principal/会话屏障与各域异步提交、恢复的接缝 | CJ008/009/010/011/015/024 等实际消费者 + CJ007 | CJ009 固定语义已核对；本新子版本消费及各域真实接入未完成 |
| 纳入唯一 API 来源、版本与错误映射、固定版本消费确认 | CJ005 + CJ007 + 实际消费者 | AUTH@1.0 冻结/发布 |

不要求上述所有决策先完成才审本草案；但未经确认不能把草案当 AUTH@1.0。

## 可执行合成检查

在仓库根运行（Python 3.9+ 标准库，无网络、无安装、无真实写入口）：

```sh
python3 -B contracts/auth/check.py
python3 -B contracts/auth/check_email.py
```

`model.py` 是测试专用内存语义模型，`examples.json` 是明确标记的假身份数据。
验证器输入是合成可信裁决，不解析/验证真实凭据；绝不可用它签发或接受身份。
检查覆盖服务端规则正负例、退出/切号/同账号重登/重启晚到、重复及乱序刷新、
网络未知与明确失效、资格拒绝及服务端撤销/资格变化后再次校验。
实际 SDK、跨用户 API/数据库、真机、CI、部署、独立 Review/Testing 均未由此证明。
Issue #8 保持未完成。独立审验应固定提交 head；内容变化后补受影响检查。
