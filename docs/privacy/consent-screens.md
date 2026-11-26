# App 内同意界面：范围、对照与文案（W4-3 #1747，替代 #714 的 2026-11-09 草稿）

- 状态：**草稿，待统筹批准**，批准后交 A 线实现。本文件只定范围和文案，不改代码。
- 依据：已公开的隐私政策 1.0（[go2china.space/privacy](https://go2china.space/privacy)，源文件 `docs/privacy/privacy-policy.md`）；[#225 正式法律相关意见](https://github.com/JTCAO515/G2C/issues/225#issuecomment-6735366219)；[#1748 定位决定](https://github.com/JTCAO515/G2C/issues/1748#issuecomment-7182096789)；老票 [#714](https://github.com/JTCAO515/G2C/issues/714)（2026-11-09，按当时的旧主体和旧方案写）。
- **原则**：文案里的接收方、处理地、数据类别，一律照抄政策原文；政策没有的承诺不写。政策一改，本文件对应处同步改。
- 开关：整张同意界面放在新开关后，默认关（#1747 票面「开关后默认关」）。开关名由 A 线按命名规则定，建议 `G2CConsentEnabled`。

## 1. 范围

| 项 | 首次启动 | 可否撤回 | 在哪里撤回 | 不同意会怎样 |
|---|---|---|---|---|
| **隐私政策与数据存放**：账号、对话、行程、记忆存在中国香港的服务器，每日备份在香港 | **必须同意**（同一页，一个按钮） | 不能单独撤回 | 注销账号（「我的」里，政策 §8） | 停在本页；可读完整政策、联系我们；不发送任何数据 |
| **AI 处理**：对话文字、行程内容、翻译的文字语音图片、菜单照片，从香港发到北京的阿里云百炼 | **必须同意**（同一页，列为单独一条并写明接收方和处理地） | **可以** | 「我的」→「隐私」（新入口，A 线加） | 同上；已同意后撤回：聊天、翻译、点餐停用，地点、路线、航班、火车、酒店、汇率、景点提醒等不依赖百炼的功能照常 |
| **记忆**：Lio 根据对话提出可记住的偏好，点「记住」后才成为记忆 | **不在首启**。第一次要生成记忆候选之前单独询问，不预勾选 | **可以** | 「我的」→ 记忆（现有记忆页，加开关） | 不生成候选、不保存；其他功能照常 |
| **定位** | **不在首启**，首启页只写一句「位置和记忆用到时另行询问」。已有单独页（#1853），第一次用打车「当前位置」或「附近」时弹出 | 可以 | 「我的」→「位置」，或 iOS 设置 | 手动输入地点，其他功能照常（#1748 决定） |
| 真人服务、官网真人服务请求表、App 内问题反馈 | 不适用（未开放，政策 §12「开放后适用」）；开放时各自单独征得同意 | — | — | — |

撤回的效果：撤回 AI 处理后，不再向百炼发送新内容；**已经发出的无法在传输途中召回**（政策 §8）。App 里的撤回确认页要写这一句。

## 2. 与 #714 的对照

| #714 验收项 | 现状（main，2026-11-27） | 在本方案里怎么处理 |
|---|---|---|
| 服务方主体改为营业执照全称，UI 测试断言新主体 | 隐私摘要 `PrivacySummary.swift`（#1890）已写「广州创竞科技有限公司」。`docs/ui.md:286` 还写着 Context Jump LLC | 首启页第 1 条用同一句。`docs/ui.md:286` 另列为遗留（A 线 / 文档线改，不在本 PR） |
| 修正 6 处与实况不符的文案（香港服务器、邀请码登录、日志 90 天、离线 14 天、删 IAP、删 30+30 承诺） | 旧文案已被 #1890 的摘要替换，代码里已无「Context Jump」「新加坡」「30 天加 30 天」 | **不重复**。首启页只放同意所需的几条，其余指向完整政策和「隐私摘要」 |
| 首次发送消息前显示 AI 许可（接收方、处理地、内容与用途），拒绝后不发送，设置里可撤回 | **没有**。App 里目前没有 AI 许可界面 | 并入首启页的「AI 处理」条（不再另做「首次发送前」那一页：首启就同意，发送前不再弹）。撤回入口「我的」→「隐私」 |
| 首次生成记忆候选前取得主动选择，不预勾选，说明跨会话复用和关闭、编辑、删除方法 | **没有**。记忆候选现在直接生成 | 单独的「记忆」询问页，见 §3.3 |
| 中英文在模拟器上完整走一遍：同意、拒绝、稍后撤回 | — | 沿用，A 线实现后补；按加速期放 58 真机回归 |
| 最终中英文案经 JT 批准 | #714 草稿 11-09 起未批 | 本文件交统筹按 JT 预授权审定 |
| #714 草稿里的定位段（「用完即丢弃，不会上传」） | **与事实不符**：位置会发到香港服务，再转滴滴或高德 | **作废**，由 #1853 的定位同意页取代（见 §3.4，已实现） |
| #714 草稿里的记忆段（「点『记住』后才会保存」「健康、宗教……不会被保存」） | 政策写的是：候选随账号保存在服务器，点「记住」后才成为记忆；对「敏感类不进候选」目前没有证据 | 改写（§3.3）：写候选会保存；敏感类写成「请不要」，不写成承诺 |
| #714 草稿里的留存段（备份 30 天等） | 政策 §7 已有逐项期限 | 不放进同意页，只链接政策 §7 |

## 3. 文案

> 带 `〔 〕` 的是对政策原文的引用，用来逐字核对；界面上不显示括号。

### 3.1 首次启动页（必须同意）

**标题**：中「先看看你的数据怎么处理」／英 "How your data is handled"

**第 1 条 谁在运营**
- 中：Go2China 由广州创竞科技有限公司运营。联系：hello@go2china.space。
- EN: Go2China is operated by Guangzhou Chuangjing Technology Co., Ltd. Contact: hello@go2china.space.
- 〔政策 §1：运营主体：广州创竞科技有限公司 / Operator: Guangzhou Chuangjing Technology Co., Ltd.；联系：hello@go2china.space〕

**第 2 条 存在哪里**
- 中：你的账号、对话、行程和记忆存放在我们位于中国香港的服务器，每日备份存放在中国香港的对象存储。
- EN: Your account, chats, trips and memories are stored on our servers in Hong Kong, China, with daily backups in object storage in Hong Kong.
- 〔政策 §6 第一句，逐字〕

**第 3 条 AI 处理（需要你同意）**
- 中：Go2China 用阿里云百炼（通义千问）生成回答、翻译和识别菜单。你的对话文字和行程内容，翻译的文字、语音和图片，以及菜单照片，会从我们在中国香港的服务发到中国大陆北京的阿里云百炼处理。
- EN: Go2China uses Alibaba Cloud Model Studio (Qwen) to generate replies, translate and read menus. Your chat text and trip content, the text, voice and images you translate, and menu photos are sent from our service in Hong Kong to Alibaba Cloud Model Studio in Beijing, mainland China, for processing.
- 〔政策 §5 表「阿里云百炼（通义千问）/ Alibaba Cloud Model Studio (Qwen)｜中国大陆北京 / Beijing, mainland China｜对话文字和行程内容；翻译的文字、语音、图片；菜单照片｜生成回答、翻译、识别菜单」；§6 第二条「生成回答、翻译、识别菜单时，相关内容从香港发到北京的阿里云百炼」〕
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
- 中：你可以随时在「我的」里查看、修改和删除记忆，或注销账号；也可以在「我的」→「隐私」里撤回 AI 处理。撤回不影响撤回前已进行的处理，已经发出的请求无法在传输途中召回。完整政策：go2china.space/privacy。
- EN: You can view, edit and delete memories, or close your account, under Me at any time. You can also withdraw AI processing under Me → Privacy. Withdrawing does not affect processing before withdrawal, and requests already sent cannot be recalled in transit. Full policy: go2china.space/privacy.
- 〔政策 §8；「撤回 AI 处理」入口政策**目前没有**，见 §4 第 1 条〕

**按钮**：中「同意并继续」「不同意」／英 "Agree and continue" "Don't agree"（不预选；「不同意」后停在本页，只能读政策和联系我们）

### 3.2 撤回 AI 处理（「我的」→「隐私」）

- 开关标题：中「AI 处理」／ EN "AI processing"；开启时副标题：中「已开启：你的对话和翻译内容会发到北京的阿里云百炼处理。」／ EN "On: your chats and translation content are sent to Alibaba Cloud Model Studio in Beijing for processing."
- 关闭时的确认：
  - 中：关闭后，聊天、翻译和点餐会停用，不再向阿里云百炼发送新的内容。已经发出的请求无法在传输途中召回。其他功能照常使用。
  - EN: Chat, translation and the menu helper will stop, and no new content will be sent to Alibaba Cloud Model Studio. Requests already sent cannot be recalled in transit. Everything else keeps working.
  - 按钮：中「关闭 AI 处理」「取消」／ EN "Turn off AI processing" "Cancel"
- 「聊天、翻译、点餐停用」是依据登记表（`docs/privacy/outbound-dataflow.md` 附录 1.1–1.3）里发给百炼的功能；A 线实现时核对还有没有别的功能向百炼发内容（例如登记表 1d：打车、附近、酒店的地点名英译也经翻译中继到百炼），**待统筹确认**这类是否也停。

### 3.3 记忆（第一次要生成候选之前）

**标题**：中「要让 Lio 记住你的偏好吗？」／ EN "Let Lio remember your preferences?"

- 中：开启后，Lio 会根据对话提出可以记住的偏好与事实（为此，对话内容会发给 AI 模型）。这些建议会随你的账号保存在服务器上；你点「记住」后才成为记忆，用于以后的对话。你可以随时查看、修改和删除记忆，或在「我的」里关闭。请不要让它记住健康、证件、宗教等敏感信息，或可识别他人的信息。
- EN: Once on, Lio suggests preferences and facts it could remember from your chats (the chat content goes to the AI model for this). These suggestions are stored on our servers with your account; they become memories used in later chats only when you tap Remember. You can view, edit and delete memories at any time, or turn this off under Me. Please do not let it remember health, ID or religious information, or information that identifies other people.
- 〔政策 §3「记忆」行：Lio 会根据对话提出可以记住的偏好与事实（为此对话内容会发给 AI 模型）。这些候选随你的账号保存在服务器上；你点「记住」后才成为记忆、用于以后的对话；政策 §7「记忆候选：随账号保存，注销账号时删除」〕
- **按钮**：中「开启记忆」「暂不开启」／ EN "Turn on memory" "Not now"（不预选）
- 先于 AI 许可则不弹：没有同意 AI 处理，记忆询问页不出现。
- 对比 #714 草稿：删去「点『记住』后才会保存」（候选其实会保存）和「健康、宗教、同行人、证件、私人地址和行踪不会被保存」（这是 #225 的要求，不是已验证的事实，改成「请不要」）。若 B 线之后做出了敏感类过滤并有证据，再改回承诺。

### 3.4 位置（已实现，不重复）

#1853 已有单独页（`LioLocationConsentView.swift`），#1748 已批。逐项对政策 §4：用途、何时（用时才读、不后台）、去向（精确位置发到香港服务；打车转滴滴；附近降到约 100 米后发高德）、留存（不和账号一起保存）、撤回（「我的」→「位置」，或 iOS 设置）、不同意（手动输入）都一致。本方案**不改它**。

## 4. 上线前要同步的事

1. **政策**：§8 要加「在『我的』→『隐私』里撤回 AI 处理」，§12 要把「App 内同意界面与定位单独询问页」里已上线的部分改成正文。政策 §12 写明「开放时我们会先更新本政策」。**开关打开前，先开政策 PR 并走红线审查，再合并，再开开关。**
2. **服务端同意记录**：#714 范围明确不含服务端记录同意或拦截未授权请求，另开 B 线子票。58 内测期间同意记录只在本机（和位置同意一致：按账号存本机、退出登录保留、注销账号删除）。对外部测试者开放前须有服务端拦截（#33 放行清单 5.2），不由本方案解决。
3. **#225 外部测试前置**：首次把真实内容发给模型前的明确许可（Apple §5.1.2(i)）由 §3.1 第 3 条承担；首次提取记忆前的肯定选择由 §3.3 承担。对外部开放前仍须 #33 放行清单 5.8 的补充法律意见。
4. **遗留**：`docs/ui.md:286` 仍写 Context Jump LLC；`ios/App/Acceptance/*UITests.swift` 里断言旧主体的测试（#714 点名）。不在本 PR。
5. **英文品牌拼写**：定位页写 "Amap"，政策写 "AMap"，建议 A 线统一为政策写法。

## 5. 需要统筹批准的几点

1. **一页还是两页**：本方案把「隐私与数据存放」和「AI 处理」放在同一页、一个「同意并继续」；AI 处理单独成条、可单独撤回。备选：先后两页。建议一页，首启少一步。
2. **撤回 AI 处理后哪些功能停**：§3.2 的「聊天、翻译、点餐」，是否包括地点英译（打车、附近、酒店）。
3. **不同意后的行为**：停在本页，可读政策、联系我们。备选：允许进入但所有发数据的功能不可用。建议前者，简单且与「首次启动必须同意」一致。
4. **记忆询问时机**：「第一次要生成候选前」，而不是首启。依据 #225 的肯定选择要求。

## 回滚

只涉及文档。revert 本 PR 即可。
