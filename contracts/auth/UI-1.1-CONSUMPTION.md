# CJ007 对 UI@1.1 固定候选的差额消费确认

UI 固定 head：`a9d0a9da13ec507882939e7c13114acda348e509`，差额 base
`e722befc9adf53e07dfb508198ff49710ab91b01`；只读源 `cj-006-ui`。
AUTH 差额 base：`64f48cf4f502b7e984f31ae59e3430cd02b0c762`。
状态：CJ007 对以下新展示边界作**有界消费确认**，不是 UI/AUTH 冻结、
独立审验或真实集成通过。UI@1.1 是源码破坏性候选，不沿用 UI@1.0 全面兼容结论。

## 固定源码核对与结论

只读 `git diff <base> <head>` 的 contracts/ui、ShellState.swift、ShellView.swift、
ShellStateTests.swift，并 `git show <head>:...` 读取 AssistantShell.swift；
按固定提交检索 Demo 的新调用。没有读取未归档 runtime 内容作证据。

| 项目 | UI@1.1 固定源码行为 | CJ007 消费结论 |
|---|---|---|
| host 清理入口 | @MainActor invalidateIdentity 先轮换 generation，再清 draft、memoryPath、presentation；默认 presentation 清两引用/正文/三页面状态，保留语言与 tab | 旧“无清理 hook”缺口在本地源码层已补齐；未来 host 必须实际调用，尚无真实映射证据 |
| 外部正文 | 删除 ShellView(state:assistantBody:)；正文改经 generation-checked apply 写入私有(set) presentation，再由 ShellView 读取 | 旧外部正文旁路在此模块已移除；未来 host 不得另建无屏障正文 renderer，外部缓存仍由 host 清理 |
| 旧 token / 另一实例 | ShellGeneration 内部 UUID、构造受限；apply 先比较当前 token，失败不写；每个实例/重置新 token | 接受 UI-local 防晚到语义；不是服务端身份/会话证明，不得重新取当前 token 给旧结果贴标 |
| 语言与身份 | selectLanguage 不改 generation/presentation；对应 Swift 测试含该断言 | 接受同一身份下的语言保留语义；不得以 locale 重建 host 或触发登录/退出 |
| 路由/展示 | 账号仍在记忆内；draft/memoryPath 仍为同步本地 UI binding | 不可将异步私有结果绕过 apply 写这些 binding；受限数据不能由页面状态授予权限 |
| sheet/focus | AssistantShell 观察 generation 变化关闭历史 sheet 和输入焦点 | 源码已接观察；实际渲染时序、键盘/设备行为 UNRUN，不声称同步视觉清理验收 |

UI 作者新增的 Swift 测试源码覆盖全字段清理、A 晚到、B 显示后 A 晚到、另一实例、
语言保留。这里只读核对断言，未运行该 Swift 测试，也未据此声称测试 PASS。
双横线绘制/键盘完成入口不改变 AUTH 消费语义，不扩大为 UI 视觉验收。

## AUTH 草案的必要接入规则

1. 未来 host 在工作开始前一起捕获 AUTH 的 instance/generation/principal/session
   revision 与 UI 的 generation，保留原值。每次 await 后先复核 AUTH 绑定与资格，
   再用原 UI token 调 apply；false 丢弃，不用当前 token 重标旧 payload。
2. 退出、切号、明确失效或新登录生命周期开始时，host 应同步失效旧 AUTH 绑定并
   调 UI invalidateIdentity，再接新身份工作。外部缓存、订阅、任务与凭据由相应
   owner 独立处理；UI 清理不证明远端撤销/取消/删除。
3. UI generation 与 AUTH generation 不是同一个 ID，不能互换，也不要求把
   principal 暴露给 UI。仅 UI token 匹配不能通过资格/资源授权；仅 AUTH 匹配不能
   向已替换的 ShellState 写入。
4. 网络 unknown/offline 不触发身份失效或删凭据。AUTH-draft.1 目前保守隐藏私有
   展示/阻止新业务：未来 host 可用当前有效 UI token 投影默认空私有内容及 unknown
   展示，不能以旧内容作新验证成功。离线草稿/缓存政策仍待产品决定，不能宣称本地
   invalidateIdentity 是网络失败的通用恢复方案。
5. 同一身份中会话 revision 更新或资格变化也须由 AUTH 重新判断；UI token 未变
   不代表旧回调仍可接受。当前 UI 没有凭据/资格职责，这是正确职责分离，不是缺陷。

责任：CJ006 拥有 UI@1.1 源码/展示边界；CJ007 拥有未来验证与绑定语义；真实 host
adapter 的文件写权仍需 Main 分配；CJ005 负责唯一来源/真实 C2 接缝。当前不新增
Swift adapter、协议、API、数据库或假身份生产入口。

## 合成差额证据

命令：`python3 -B contracts/auth/check_ui.py`，macOS/Python 3.9.6，8/8 PASS。
原 4 项入口/语言/清理遗漏/unknown 规则仍执行；新增 4 项双重屏障反例：旧 UI token、
另一实例、用新 token 包装旧账号结果、相同 UI token 下 AUTH 未知或 revision 变化。
清理样例中的 body 是抽象投影；UI@1.1 已改为 presentation 内部值，不再声称外部。

这些测试只执行 AUTH 目录的合成规则，不执行 UI@1.1 Swift，不是 host 实现；UI 源码
结论来自上述固定提交核对。原 AUTH model.py/check.py 未变，复用原 12 项证据。

剩余 PENDING：真实 host 映射、外部私有状态清理、双方最终版本发布与消费确认。
正式登录/受邀策略/C2 未定；真实账号、SDK、API/数据库隔离、真机、部署 UNRUN。
Issue #8 不关闭，AUTH@1.0 不冻结。本次未发现要求 CJ006 立刻返修的新增 AUTH 接缝
源码缺陷；以上 host 义务不能因本次消费确认被省略。
