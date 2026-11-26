# App 内同意界面：范围、对照与文案（W4-3 #1747，替代 #714 的 2026-11-09 草稿）

- 状态：**范围与四个选择已批准**（统筹 2026-11-27 按 JT 预授权）；文案待 Opus 红线审查后交 A 线实现。本文件只定范围和文案，不改代码。
- 依据：已公开的隐私政策 1.0（[go2china.space/privacy](https://go2china.space/privacy)，源文件 `docs/privacy/privacy-policy.md`）；[#225 正式法律相关意见](https://github.com/JTCAO515/G2C/issues/225#issuecomment-6735366219)；[#1748 定位决定](https://github.com/JTCAO515/G2C/issues/1748#issuecomment-7182096789)；老票 [#714](https://github.com/JTCAO515/G2C/issues/714)（2026-11-09，按当时的旧主体和旧方案写）。
- **原则**：文案里的接收方、处理地、数据类别，一律照抄政策原文；政策没有的承诺不写。政策一改，本文件对应处同步改。
- 开关：整张同意界面放在新开关后，默认关（#1747 票面「开关后默认关」）。开关名由 A 线按命名规则定，建议 `G2CConsentEnabled`。
- **设计依据《个人信息保护法》第 16 条**：个人不同意处理其个人信息的，不能因此拒绝提供产品或服务，处理属于提供服务所必需的除外。所以「数据存放在香港」（账号相关功能必需）是必须同意的；「AI 处理」不是必需，**不同意也能进 App**，只是 AI 功能关闭。

## 1. 范围

| 项 | 首次启动 | 可否撤回 | 在哪里撤回 | 不同意会怎样 |
|---|---|---|---|---|
| **数据存放**：账号、对话、行程、记忆存在中国香港的服务器，每日备份在香港 | **必须同意**（首启页，按钮「同意…」） | 不能单独撤回 | 注销账号（「我的」里，政策 §8） | **停在本页**：说明账号相关功能需要这一项；可读完整政策；提供「退出」。不发送任何数据 |
| **AI 处理**：对话文字、行程内容、翻译的文字语音图片、菜单照片，以及打车、酒店、地铁周边搜索结果里的地点名和地址、路书里的地点名、营业时间和地铁站名，从香港发到北京的阿里云百炼 | **二选一，不预选**（同一页）：「开启 AI 处理」/「暂不开启」 | **可以**，也可以之后再开 | 「我的」→「隐私」（新入口，A 线加） | **照样进 App**，AI 功能关闭，见下表 |
| **记忆**：Lio 根据对话提出可记住的偏好，点「记住」后才成为记忆 | **不在首启**。第一次要生成记忆候选之前单独询问，不预勾选 | **可以** | 「我的」→ 记忆（现有记忆页，加开关） | 不生成候选、不保存；其他功能照常。AI 处理没开时不弹这一页 |
| **定位** | **不在首启**，首启页只写一句「位置和记忆用到时另行询问」。已有单独页（#1853），第一次用打车「当前位置」或「附近」时弹出 | 可以 | 「我的」→「位置」，或 iOS 设置 | 手动输入地点，其他功能照常（#1748 决定） |
| 真人服务、官网真人服务请求表、App 内问题反馈 | 不适用（未开放，政策 §12「开放后适用」）；开放时各自单独征得同意 | — | — | — |

### 1.1 AI 处理关闭后，哪些功能停、哪些照常（统筹 2026-11-27 批准）

规则：凡是把内容发给阿里云百炼的功能都停；不走模型的照常。

| 停用 | 原因 |
|---|---|
| Lio 对话、行程规划 | 对话文字和行程内容发百炼 |
| 记忆建议 | 为生成候选，对话内容发百炼 |
| AI 翻译（文字、语音、图片） | 发百炼 |
| 点餐（菜单照片识别与解释） | 菜单照片发百炼 |
| 地点英译（打车、酒店、地铁周边的英文地名）、路书的地点补充内容 | 发的是供应商返回的地点名和地址，地点名本身公开，但**用户查了哪些地点会暴露他的行程**，所以和其他发百炼的功能一起停（统筹 2026-11-27 定）。关闭后这些地方只显示中文名。政策 §5 百炼那一行把这两类补上（PR #1962，待合并；#1962 先合，本文再合） |

| 照常 | |
|---|---|
| 出示卡、商务常用语、离线资料、地图、打车（中文地名）、附近、航班、火车、酒店、汇率、景点预约与提醒 | 不把用户内容发给百炼 |

停用的位置都显示一句：中「已关闭 AI 处理，可在「我的」→「隐私」里重新开启。」／ EN "AI processing is off. You can turn it back on under Me → Privacy."

撤回的效果：撤回后不再向百炼发送新内容；**已经发出的无法在传输途中召回，但我们会依法协助删除**（政策 §8）。撤回确认页要写这一句。

## 2. 与 #714 的对照

| #714 验收项 | 现状（main，2026-11-27） | 在本方案里怎么处理 |
|---|---|---|
| 服务方主体改为营业执照全称，UI 测试断言新主体 | 隐私摘要 `PrivacySummary.swift`（#1890）已写「广州创竞科技有限公司」。`docs/ui.md:286` 还写着 Context Jump LLC | 首启页第 1 条用同一句。`docs/ui.md:286` 在政策 PR 里一并改掉（见 §4） |
| 修正 6 处与实况不符的文案（香港服务器、邀请码登录、日志 90 天、离线 14 天、删 IAP、删 30+30 承诺） | 旧文案已被 #1890 的摘要替换，代码里已无「Context Jump」「新加坡」「30 天加 30 天」 | **不重复**。首启页只放同意所需的几条，其余指向完整政策和「隐私摘要」 |
| 首次发送消息前显示 AI 许可（接收方、处理地、内容与用途），拒绝后不发送，设置里可撤回 | **没有**。App 里目前没有 AI 许可界面 | 并入首启页的「AI 处理」选择（首启就问，发送前不再弹）。拒绝后不发送，AI 功能关闭但 App 可用；撤回入口「我的」→「隐私」 |
| 首次生成记忆候选前取得主动选择，不预勾选，说明跨会话复用和关闭、编辑、删除方法 | **没有**。记忆候选现在直接生成 | 单独的「记忆」询问页，见 §3.3 |
| 中英文在模拟器上完整走一遍：同意、拒绝、稍后撤回 | — | 沿用，A 线实现后补；按加速期放 58 真机回归 |
| 最终中英文案经 JT 批准 | #714 草稿 11-09 起未批 | 统筹按 JT 预授权审定 |
| #714 草稿里的定位段（「用完即丢弃，不会上传」） | **与事实不符**：位置会发到香港服务，再转滴滴或高德 | **作废**，由 #1853 的定位同意页取代（见 §3.4，已实现） |
| #714 草稿里的记忆段（「点『记住』后才会保存」「健康、宗教……不会被保存」） | 政策写的是：候选随账号保存在服务器，点「记住」后才成为记忆；对「敏感类不进候选」目前没有证据 | 改写（§3.3）：写候选会保存；敏感类写成「请不要」，不写成承诺 |
| #714 草稿里的留存段（备份 30 天等） | 政策 §7 已有逐项期限 | 不放进同意页，只链接政策 §7 |

## 3. 文案

> 带 `〔 〕` 的是对政策原文的引用，用来逐字核对；界面上不显示括号。

### 3.1 首次启动页

**标题**：中「先看看你的数据怎么处理」／英 "How your data is handled"

**第 1 条 谁在运营**
- 中：Go2China 由广州创竞科技有限公司运营。联系：hello@go2china.space。
- EN: Go2China is operated by Guangzhou Chuangjing Technology Co., Ltd. Contact: hello@go2china.space.
- 〔政策 §1：运营主体：广州创竞科技有限公司 / Operator: Guangzhou Chuangjing Technology Co., Ltd.；联系：hello@go2china.space〕

**第 2 条 存在哪里（需要你同意才能使用账号相关功能）**
- 中：你的账号、对话、行程和记忆存放在我们位于中国香港的服务器，每日备份存放在中国香港的对象存储。
- EN: Your account, chats, trips and memories are stored on our servers in Hong Kong, China, with daily backups in object storage in Hong Kong.
- 〔政策 §6 第一句，逐字〕

**第 3 条 AI 处理（你来选，不开启也能使用 App）**
- 中：Go2China 用阿里云百炼（通义千问）生成回答、翻译和识别菜单。你的对话文字和行程内容，翻译的文字、语音和图片，菜单照片，打车、酒店、地铁周边搜索结果里的地点名和地址，以及路书里的地点名、营业时间和地铁站名，会从我们在中国香港的服务发到中国大陆北京的阿里云百炼处理。不开启 AI 处理也能使用 App，只是聊天、行程规划、记忆建议、翻译和点餐不可用，地点名只显示中文。你可以随时在「我的」→「隐私」里开启或关闭。
- EN: Go2China uses Alibaba Cloud Model Studio (Qwen) to generate replies, translate and read menus. Your chat text and trip content, the text, voice and images you translate, menu photos, place names and addresses in taxi, hotel and metro-nearby search results, and place names, opening hours and station names in roadbooks are sent from our service in Hong Kong to Alibaba Cloud Model Studio in Beijing, mainland China, for processing. You can use the app without AI processing; chat, trip planning, memory suggestions, translation and the menu helper will not be available, and place names show in Chinese only. You can turn it on or off at any time under Me → Privacy.
- 〔政策 §5 表「阿里云百炼（通义千问）/ Alibaba Cloud Model Studio (Qwen)｜中国大陆北京 / Beijing, mainland China｜对话文字和行程内容；翻译的文字、语音、图片；菜单照片（#1962 合并后再加：打车、酒店、地铁周边搜索结果里的地点名和地址；路书里的地点名、营业时间和地铁站名）｜生成回答、翻译、识别菜单（#1962 合并后再加：生成地点英文名和路书地点说明）」；§6 第二条「生成回答、翻译、识别菜单时，相关内容从香港发到北京的阿里云百炼」；「撤回入口」政策**目前没有**，见 §4 第 1 条〕
- 不写百炼是否用输入内容训练或保留多久（政策没有这项承诺，#225 记为未核实）。

**第 4 条 我们不做什么**
- 中：我们不出售你的个人信息，也不用于广告。请不要在对话或翻译里填写健康、证件、宗教等敏感信息，或可识别他人的信息。
- EN: We do not sell your personal information or use it for advertising. Please do not enter health, ID or religious information, or information that identifies other people, in chats or translation.
- 〔政策 §3 末段，「申请表」一词去掉（这里是 App）〕

**第 5 条 另行询问**
- 中：位置和记忆不在这里同意，用到时我们会单独问你。
- EN: Location and memory are not part of this consent. We ask you separately when they are needed.
- 〔#1748 决定：总同意只写「定位另行询问」。记忆的另行询问是本方案新增，见 §3.3〕

**第 6 条 你的选择**
- 中：你可以随时在「我的」里查看、修改和删除记忆，或注销账号。撤回不影响撤回前已进行的处理；已经发出的请求无法在传输途中召回，但我们会依法协助删除。完整政策：go2china.space/privacy。
- EN: You can view, edit and delete memories, or close your account, under Me at any time. Withdrawing does not affect processing before withdrawal. Requests already sent cannot be recalled in transit, but we will help delete them as the law requires. Full policy: go2china.space/privacy.
- 〔政策 §8〕

**按钮（三个，都不预选）**
- 中「同意，并开启 AI 处理」／ EN "Agree and turn on AI processing"：同意数据存放，开启 AI 处理，进入 App。
- 中「同意，暂不开启 AI 处理」／ EN "Agree, but keep AI processing off"：同意数据存放，AI 功能关闭，进入 App。
- 中「不同意」／ EN "Don't agree"：见下。

**点「不同意」后（停在本页）**
- 中：账号、对话、行程等功能需要把数据存放在我们位于中国香港的服务器。不同意就无法使用这些功能。你可以先读完整政策，也可以退出。
- EN: Account, chat and trip features need your data to be stored on our servers in Hong Kong, China. Without this you cannot use them. You can read the full policy first, or leave.
- 按钮：中「看完整政策」「退出」／ EN "Read the full policy" "Leave"。「退出」回到登录页，不在程序里结束 App（统筹 2026-11-27 定，iOS 不建议强制结束）。

### 3.2 开关 AI 处理（「我的」→「隐私」）

- 开关标题：中「AI 处理」／ EN "AI processing"；开启时副标题：中「已开启：你的对话、翻译内容和查到的地点名会发到北京的阿里云百炼处理。」／ EN "On: your chats, translation content and the place names you look up are sent to Alibaba Cloud Model Studio in Beijing for processing."
- 关闭时的副标题：中「已关闭 AI 处理，可在这里重新开启。」／ EN "AI processing is off. You can turn it back on here."
- 关闭时的确认：
  - 中：关闭后，聊天、行程规划、翻译和点餐会停用，不再向阿里云百炼发送新的内容。已经发出的请求无法在传输途中召回，但我们会依法协助删除。其他功能照常使用，地点名只显示中文。
  - EN: Chat, trip planning, translation and the menu helper will stop, and no new content will be sent to Alibaba Cloud Model Studio. Requests already sent cannot be recalled in transit, but we will help delete them as the law requires. Everything else keeps working; place names show in Chinese only.
  - 按钮：中「关闭 AI 处理」「取消」／ EN "Turn off AI processing" "Cancel"
- 重新开启：不再出现首启那样的整页，只确认接收方和处理地一次：中「开启后，你的对话和翻译内容会发到中国大陆北京的阿里云百炼处理。」／ EN "Once on, your chats and translation content are sent to Alibaba Cloud Model Studio in Beijing, mainland China, for processing."；按钮「开启」「取消」／ "Turn on" "Cancel"。

### 3.3 记忆（第一次要生成候选之前）

**标题**：中「要让 Lio 记住你的偏好吗？」／ EN "Let Lio remember your preferences?"

- 中：开启后，Lio 会根据对话提出可以记住的偏好与事实（为此，对话内容会发给 AI 模型）。这些建议会随你的账号保存在服务器上；你点「记住」后才成为记忆，用于以后的对话。你可以随时查看、修改和删除记忆，或在「我的」里关闭。请不要让它记住健康、证件、宗教等敏感信息，或可识别他人的信息。
- EN: Once on, Lio suggests preferences and facts it could remember from your chats (the chat content goes to the AI model for this). These suggestions are stored on our servers with your account; they become memories used in later chats only when you tap Remember. You can view, edit and delete memories at any time, or turn this off under Me. Please do not let it remember health, ID or religious information, or information that identifies other people.
- 〔政策 §3「记忆」行：Lio 会根据对话提出可以记住的偏好与事实（为此对话内容会发给 AI 模型）。这些候选随你的账号保存在服务器上；你点「记住」后才成为记忆、用于以后的对话；政策 §7「记忆候选：随账号保存，注销账号时删除」〕
- **按钮**：中「开启记忆」「暂不开启」／ EN "Turn on memory" "Not now"（不预选）
- AI 处理没开时不弹这一页（记忆建议依赖 AI）。
- 对比 #714 草稿：删去「点『记住』后才会保存」（候选其实会保存）和「健康、宗教、同行人、证件、私人地址和行踪不会被保存」（这是 #225 的要求，不是已验证的事实，改成「请不要」）。若 B 线之后做出了敏感类过滤并有证据，再改回承诺。

### 3.4 位置（已实现，不重复）

#1853 已有单独页（`LioLocationConsentView.swift`），#1748 已批。逐项对政策 §4：用途、何时（用时才读、不后台）、去向（精确位置发到香港服务；打车转滴滴；附近降到约 100 米后发高德）、留存（不和账号一起保存）、撤回（「我的」→「位置」，或 iOS 设置）、不同意（手动输入）都一致。本方案**不改它**。

## 4. 上线前要同步的事

1. **政策**：§8 要加「撤回 AI 处理」入口，§12 要把「App 内同意界面与定位单独询问页」里已上线的部分改成正文。政策 §12 写明「开放时我们会先更新本政策」。**开关打开前，先开政策 PR（#1962）并走红线审查，再合并，再开开关；#1962 先于本文合并，因为本文首启页 AI 条列的数据类别以 #1962 合并后的政策 §5 为准**（统筹要求：必须在开关打开前合并；58 上传完成前都不合并）。
2. **服务端同意记录**：#714 范围明确不含服务端记录同意或拦截未授权请求，另开 B 线子票。58 内测期间同意记录只在本机（和位置同意一致：按账号存本机、退出登录保留、注销账号删除）。对外部测试者开放前须有服务端拦截（#33 放行清单 5.2），不由本方案解决。
3. **#225 外部测试前置**：首次把真实内容发给模型前的明确许可（Apple §5.1.2(i)）由 §3.1 第 3 条的选择承担；首次提取记忆前的肯定选择由 §3.3 承担。对外部开放前仍须 #33 放行清单 5.8 的补充法律意见。
4. **遗留**：`docs/ui.md:286` 仍写 Context Jump LLC（在政策 PR #1962 里一并改）。UI 测试已断言新主体（`DevelopmentBetaUITests`、`ShellStructureUITests`），#714 点名的那两处已不存在。
5. **英文品牌拼写**：定位页写 "Amap"，政策写 "AMap"，建议 A 线统一为政策写法。

## 5. 已批准的选择（统筹 2026-11-27 按 JT 预授权）

1. **一页**。
2. **撤回 AI 处理后**：凡是把内容发给百炼的功能都停（Lio 对话、行程规划、AI 翻译；地点英译走百炼，一起停）；不走模型的工具照常（出示卡、打车、地图、离线资料、商务常用语）。停用处写「已关闭 AI 处理，可在设置里重新开启」（§1.1）。
3. **不同意的两种情况**：不同意「AI 处理」，照样进 App，AI 功能关闭（《个人信息保护法》第 16 条）；不同意「数据存放在香港」，停在本页，说明账号相关功能需要这一项，同时提供「退出」。
4. **记忆的询问放在第一次生成候选之前**（#225）。

## 回滚

只涉及文档。revert 本 PR 即可。
