# Go2China 隐私政策 / Privacy Policy（草稿）

<!--
状态：草稿，待 JT 批准；未对外发布。Issue #1746（W4-2，总票 #1714）。
同源：本文件是官网与 App 隐私政策的唯一文本来源。官网页（web/，W0-4 之后由官网线接入）与 App 内隐私页（替换 PublicInformation.swift 的内测说明，W4-3 #1747）都从本文件生成，不各自手写。生成方式在接入票里定。
方括号【待 JT】处是主体信息或需要 JT 决定的内容，起草时不填。
每节中文在前、英文在后，两种语言内容一致；不一致时以【待 JT：哪种语言为准】为准。
不写尚未实装的功能或未经验证的期限（#225 正式法律相关意见「文案」一节）。

【发布前提】本稿描述的是下列各项落地后的状态。对外发布（官网或 App 内对外可见）前，逐项确认已落地并与文字核对；任一项未落地，对应段落要删去或改写成现状。首次对外公开另须 JT 本人确认（统筹转达）。
- 第 3、4 节的位置写法：#1833（打车坐标只用于该次请求、不记日志不落盘不进缓存键；附近发给高德的坐标转换、周边搜索、逆地理三类请求都降到 3 位小数）、#1832（定位用途说明与隐私清单申报）、#1748（定位单独成页、需要时才弹出，撤回入口「我的 → 位置」；统筹 2026-11-26 按 JT 预授权决定）。三张票都落地前，这些写法与实际行为不一致。总同意（#1747）里只写一句「定位另行询问」。
- 第 3、5 节的单独同意：AI 模型、记忆在 #1747（总同意界面，其中只写一句「定位另行询问」）；位置在 #1748（单独成页、需要时才弹出）；真人服务在 #1772（确认页，分项勾选）。出境告知随各项同意一起给出：AI 模型在 #1747、位置在 #1748、真人服务在 #1772。
- 第 6 节真人服务：#1768（契约）、#1769（存储与清理）、#1771（运营台）、#1772（确认页）、#1775（陪同服务协议含委托处理条款，JT 负责）。
- 第 7 节真人服务 12 个月 / 90 天：#1769 的清理钩子落地并验证。
- 第 3、6 节官网接单入口：#1862（W10-3，开关 `SERVICE_REQUEST_ENABLED` 默认关）把去向从只写日志的替身换成服务线的服务请求后端（W9，#1768），并在官网 `/privacy` 公开本政策（JT 本人确认）；官网表单的同意方式见 PIPIA 增补「官网渠道」一节。
- 第 4、5 节 Vercel 函数区域与 Jotform 实际 API 区域：按控制台配置核对后填写。
- 第 5 节出境机制：按 #225 落实后填写。
- 第 6 节：PIPIA 增补第 11 节第 9 项（用户在聊天里主动说出的时间地点、会面对象会随聊天发给百炼）对外部用户的处理方式由 JT 本人定，定了以后在此补告知。
-->

- 版本：【待 JT：版本号】　生效日期：【待 JT】
- Version: [JT: version]　Effective date: [JT]

<!-- 首次对外公开（官网或 App 内对外可见）须 JT 本人确认，由统筹转达。公开首发（M5）前另请法律意见复核本文。 -->

## 1. 我们是谁 / Who we are

Go2China（以下简称「我们」）是帮助外国人在中国办事的本地助手 App 与网站 go2china.space。运营主体：【待 JT：营业执照全称、英文名称、注册地址】。如有疑问，请联系 hello@go2china.space。

Go2China ("we") is a local assistant app and website (go2china.space) that helps foreigners get things done in China. Operator: [JT: full legal name, English name, registered address]. Questions: hello@go2china.space.

## 2. 适用范围 / Scope

本政策适用于 Go2China iOS App、官网 go2china.space，以及你通过它们请求的真人服务。你通过我们跳转到第三方平台（例如滴滴、Trip.com、Klook、12306）后，由该平台按其隐私政策处理你的信息。

This policy covers the Go2China iOS app, the website go2china.space, and any in-person services you request through them. When we link you to a third-party platform (for example DiDi, Trip.com, Klook or 12306), that platform handles your information under its own privacy policy.

## 3. 我们处理哪些信息、为什么 / What we process and why

<!-- 事实来源：docs/privacy/outbound-dataflow.md（#1743）。随登记表更新。 -->

| 功能 | 信息 | 目的 | 必需或可选 |
|---|---|---|---|
| 账号 | 邀请码、账号标识；登录凭据保存在你设备的钥匙串里 | 登录、区分账号 | 必需 |
| 和 Lio 对话 | 你发送的文字；Lio 的回答；你保存的行程 | 生成回答、规划行程 | 使用该功能时必需 |
| 记忆 | 你同意保存的偏好与事实 | 跨对话记住你 | 可选，单独同意 |
| 翻译 | 你输入的文字、录下的语音、拍摄或选择的图片（上传前去掉照片里的位置等元数据） | 翻译、朗读 | 使用该功能时必需 |
| 点餐 | 菜单照片 | 识别并解释菜品 | 使用该功能时必需 |
| 打车 | 搜索词、上车点和目的地；选「当前位置」时为设备精确位置 | 查询地点、估价、生成滴滴叫车链接 | 使用该功能时必需；位置单独同意 |
| 附近 | 设备位置（发给地图服务前降到约 100 米精度） | 查找附近的地点 | 使用该功能时必需；位置单独同意 |
| 其他工具 | 城市、地点名、航班号、日期等你输入的查询条件 | 查询地点、路线、航班、火车、酒店 | 使用该工具时必需 |
| 真人服务 | 称呼、联系方式（App 内为电话号码，官网入口为邮箱）、服务时间与地点（官网入口只收日期，城市固定广州）、会面信息、备注；报价与支付状态、服务状态与凭据、服务纪要、你的评价 | 安排陪同、回复你的请求，见第 6 节 | 请求真人服务时必需 |
| 官网抢先体验申请 | 称呼、邮箱、得知渠道、所在国家、计划出行时间、目的地、需求、备注 | 处理你的抢先体验申请 | 申请时必需（备注等可选） |
| 用量与诊断 | 用量计数、错误记录 | 额度控制、排查故障 | 必需 |
| 问题反馈 | 你主动提交的内容 | 处理问题 | 可选 |

| Feature | Information | Purpose | Required or optional |
|---|---|---|---|
| Account | Invite code, account identifier; sign-in credentials stay in your device keychain | Sign-in, keeping accounts apart | Required |
| Chatting with Lio | Text you send; Lio's replies; trips you save | Replies and trip planning | Required to use the feature |
| Memory | Preferences and facts you agree to save | Remembering you across chats | Optional, separate consent |
| Translation | Text you type, voice you record, photos you take or choose (location and other metadata removed before upload) | Translating and reading aloud | Required to use the feature |
| Menu | Menu photos | Reading and explaining dishes | Required to use the feature |
| Taxi | Search terms, pickup and destination; your precise device location when you choose "Current location" | Finding places, fare estimates, DiDi ride links | Required to use the feature; location needs separate consent |
| Nearby | Your device location (reduced to about 100 m before it goes to the map service) | Finding places near you | Required to use the feature; location needs separate consent |
| Other tools | City, place names, flight numbers, dates and other search terms you enter | Places, routes, flights, trains, hotels | Required to use the tool |
| In-person services | Name to address you by, contact details (phone number in the app, email on the website form), service time and place (the website form takes only a date; the city is fixed to Guangzhou), meeting details, notes; quote and payment status, service status and records, service notes, your rating | Arranging a companion and replying to your request, see section 6 | Required to request a service |
| Website early access application | Name, email, how you heard of us, country, planned travel time, destinations, needs, notes | Handling your early access application | Required to apply (notes and some fields optional) |
| Usage and diagnostics | Usage counts, error records | Quotas, troubleshooting | Required |
| Feedback | What you choose to submit | Handling the issue | Optional |

**我们不收集**：护照号等证件号码、支付卡号、你的通讯录。只有在你使用打车或附近、并单独同意后，我们才读取设备位置。位置的同意单独询问，在你第一次需要时才弹出，不在首次启动时一并勾选。每次只读一次，不在后台持续定位。

- 去向：精确位置发到我们的香港服务；打车时转给滴滴；查找附近时降到约 100 米精度后发给高德。
- 不和你的账号一起保存，不写入记忆，也不发给 AI 模型。
- 撤回：在「我的 → 位置」里关闭，或在系统设置里关闭 Go2China 的定位权限。
- 你的定位同意记录按账号保存在本机，同一台设备上的其他账号读不到；退出登录时保留，注销账号时删除。

**We do not collect**: passport or other ID numbers, payment card numbers, or your contacts. We read your device location only when you use Taxi or Nearby and have given separate consent. We ask for location consent on its own, the first time you need it, not as part of the consent at first launch. We read it once each time and never track you in the background.

- Where it goes: your precise location goes to our service in Hong Kong; for Taxi it is passed to DiDi; for Nearby it is reduced to about 100 m before it goes to AMap.
- It is not stored with your account, not saved to memory, and not sent to the AI model.
- To withdraw: turn it off in Me → Location, or turn off location access for Go2China in system Settings.
- Your location consent is stored on this device per account, and other accounts on the same device cannot read it. It is kept when you sign out and deleted when you close your account.

<!-- 位置相关的写法以文首「发布前提」第一条为准：#1833（打车坐标只用于该次请求、不记日志不落盘不进缓存键；附近发给高德的坐标转换、周边搜索、逆地理三类请求都降到 3 位小数）、#1832（定位用途说明与隐私清单申报）、#1748（定位单独成页、需要时才弹出、撤回入口）。三张票都落地前，本节与现状不符，不能对外发布。 -->

我们不出售你的个人信息，也不用于广告。

We do not sell your personal information or use it for advertising.

## 4. 我们与谁共享 / Who we share with

我们只把完成你所用功能需要的信息发给下列接收方。发给百炼、高德、滴滴、飞常准的请求不带你的账号、邮箱或手机号。【待核对：各接收方的签约主体全称】

We send each recipient only what the feature you use needs. Requests to Model Studio, AMap, DiDi and VariFlight do not include your account, email or phone number. [To verify: each recipient's contracting entity]

| 接收方 / Recipient | 所在地 / Location | 收到什么 / What they receive | 用途 / Purpose |
|---|---|---|---|
| 阿里云百炼（通义千问）/ Alibaba Cloud Model Studio (Qwen) | 中国大陆北京 / Beijing, mainland China | 对话文字和行程内容；翻译的文字、语音、图片；菜单照片 / Chat text and trip content; text, voice and images for translation; menu photos | 生成回答、翻译、识别菜单 / Replies, translation, menu reading |
| 高德地图开放平台 / AMap (Gaode) | 中国大陆 / Mainland China | 地点和路线查询词、城市、酒店搜索的地标、火车出发日期；附近功能的约 100 米精度位置 / Place and route queries, city, landmarks for hotel search, train departure date; location at about 100 m for Nearby | 地点、路线、天气、酒店、火车、附近 / Places, routes, weather, hotels, trains, Nearby |
| 滴滴出行 / DiDi | 中国大陆 / Mainland China | 打车搜索词、上车点（可为设备精确位置）、目的地 / Taxi search terms, pickup (may be precise device location), destination | 估价、生成叫车链接；你在滴滴 App 里下单付款 / Estimates and ride links; you book and pay in the DiDi app |
| 飞常准 / VariFlight | 中国大陆 / Mainland China | 航班号、机场、日期 / Flight number, airports, date | 航班查询 / Flight lookup |
| 阿里云（香港）/ Alibaba Cloud (Hong Kong) | 中国香港 / Hong Kong, China | 服务器与备份上的全部数据 / All data on our servers and backups | 代我们托管 / Hosting on our behalf |
| 真人服务陪同人员 / In-person companions | 广州 / Guangzhou | 见第 6 节 / See section 6 | 提供你请求的服务 / Providing the service you requested |
| Vercel | 【待核对：函数区域，未配置时按 Vercel 默认】/ [To verify: function region; Vercel default if not set] | 官网页面访问，以及你在官网提交的表单内容（转发时不保存原文）/ Website visits and the forms you submit on the website (forwarded, not stored as text) | 代我们托管官网和表单接口 / Hosting the website and its form endpoints on our behalf |
| Jotform | 【待核对：美国或欧盟，按实际 API 区域】/ [To verify: US or EU, by the API region in use] | 抢先体验申请的全部字段 / All fields of the early access application | 代我们保存和管理抢先体验申请 / Storing and managing early access applications on our behalf |

**你点开的第三方链接**：打开 Trip.com（酒店、火车、机票、景点）时，链接里会带上你查询的城市、酒店、日期和人数；打开高德地图或 Apple 地图导航时，链接里带目的地坐标；打开 Klook、12306 的链接不带你的信息。打开后由对方按其隐私政策处理。App 内地图由 Apple MapKit 显示。

**Third-party links you open**: Trip.com links (hotels, trains, flights, attractions) carry the city, hotel, dates and number of guests you searched for. Navigation links to AMap or Apple Maps carry the destination coordinates. Links to Klook and 12306 carry none of your information. Once opened, that service handles your information under its own policy. In-app maps are shown by Apple MapKit.

## 5. 存放地点与跨境 / Where data is stored and cross-border transfers

你的账号、对话、行程、记忆和服务请求存放在我们位于中国香港的服务器（阿里云中国香港），每日备份存放在中国香港的对象存储。

- 生成回答、翻译、识别菜单时，相关内容会从香港发送到中国大陆北京的阿里云百炼处理。
- 使用地点、路线、打车、附近、航班工具时，查询条件会从香港发送到位于中国大陆的高德、滴滴、飞常准。
- 你在中国大陆使用 App 时，你的信息会从大陆传到香港。
- 你在官网提交表单时，内容先到 Vercel 的接口：真人服务请求再转到我们在香港的服务；抢先体验申请转到 Jotform。【待核对：Vercel 函数区域与 Jotform API 区域】
- 你请求真人服务时，第 6 节所列信息会从香港提供给广州的陪同人员；陪同的服务纪要会传回香港。

在首次把你的对话发送给 AI 模型前，以及首次使用位置、请求真人服务前，我们会在 App 内单独征得你的同意。【待 JT：出境所需的标准合同、认证或评估，按 #225 路径在对外开放前落实，并在此写明】

Your account, chats, trips, memories and service requests are stored on our servers in Hong Kong, China (Alibaba Cloud Hong Kong), with daily backups in object storage in Hong Kong.

- For replies, translation and menu reading, the relevant content goes from Hong Kong to Alibaba Cloud Model Studio in Beijing, mainland China.
- For places, routes, taxi, nearby and flight tools, your search terms go from Hong Kong to AMap, DiDi and VariFlight in mainland China.
- When you use the app in mainland China, your information is transferred from the mainland to Hong Kong.
- When you submit a form on the website, it first reaches our endpoint on Vercel: in-person service requests then go on to our service in Hong Kong, and early access applications go to Jotform. [To verify: Vercel function region and Jotform API region]
- When you request an in-person service, the information in section 6 is provided from Hong Kong to the companion in Guangzhou, and the companion's service notes come back to Hong Kong.

We ask for your separate consent in the app before we first send your chats to the AI model, and before you first use location or request an in-person service. [JT: cross-border mechanisms (standard contract, certification or assessment) to be put in place under #225 before external launch and stated here]

## 6. 真人服务 / In-person services

部分服务由真人提供，首个是广州的中英商务陪同。提交前，确认页会列出将与陪同人员共享的信息，并写明服务由真人提供、陪同人员称呼、到场时间、取消规则和由谁退款。你单独同意后我们才会提交。

陪同人员受我们委托提供服务，按服务协议只为本次服务使用你的信息、服务结束后删除、不得转交他人。陪同只能看到完成本次服务需要的信息（称呼、语言、时间地点、会面信息、当天联系的电话号码），从服务安排好到服务结束后 24 小时内可见；看不到你的账号、对话、行程全文、记忆和报价。服务状态在 App 内更新。

陪同服务按次收费，在 App 外付款，不通过 Apple App 内购买。【待 JT：收款方式与收款主体】【待 JT：PIPIA 增补第 11 节第 9 项的告知】

请只填写陪同需要知道的内容，不要在备注里填写健康、证件或宗教信息；如需填写会面对象的信息，请只填称呼和公司名。

**通过官网提交**：你也可以在 go2china.space 的「需要真人帮忙」表单里提出广州中英商务陪同请求，填写称呼、邮箱、日期和说明（选填），并同意本政策。表单提交到同一网站的 `/api/service-request`，再转到我们自己的服务请求后端（与 App 内请求是同一套），不经过任何第三方表单服务；这个接口由 Vercel 代我们托管（见第 4 节）。我们通过邮件回复你，通常在 1 个工作日内（北京时间）。【待核对：回复邮件使用的邮件服务商】

Some services are provided by real people. The first is an English–Chinese business companion in Guangzhou. Before you submit, the confirmation page lists the information we will share with the companion and states that the service is provided by a person, the companion's name, arrival time, cancellation rules and who handles refunds. We only submit after you give separate consent.

Companions act on our behalf. Under their service agreement they use your information only for this service, delete it afterwards and do not pass it on. A companion sees only what is needed for this service (how to address you, language, time and place, meeting details, and a phone number for that day), from when the service is arranged until 24 hours after it ends. They cannot see your account, chats, full trips, memories or the price. Service status is updated in the app.

Companion services are paid per service, outside the app, not through Apple in-app purchase. [JT: payment method and receiving entity] [JT: notice for PIPIA addendum section 11 item 9]

Please include only what the companion needs to know. Do not put health, ID or religious information in the notes. If you mention the people you are meeting, include only their name and company.

**Requests from the website**: You can also request the Guangzhou English–Chinese business companion through the "Need a person to help" form on go2china.space, giving your name, email, date and an optional note, and agreeing to this policy. The form posts to `/api/service-request` on the same website and goes on to our own service request backend (the same one the app uses), not through any third-party form service. Vercel hosts this endpoint on our behalf (see section 4). We reply by email, usually within 1 business day (Beijing time). [To verify: the email provider used for replies]

## 7. 保存多久 / How long we keep it

【按 #225 意见逐类核对后定稿，不沿用旧内测文案的 30/30/30/180 天。以下为已确认或已实装的口径：】

- 记忆、对话、行程：保存到你删除或注销账号；系统不会因长期未使用而删除（ADR-0006）。【待 JT：按 PIPL 第 19、47 条逐类审核是否有持续必要】
- 运行日志与诊断：政策目标 90 天【待核对实际清理任务覆盖范围】。
- 备份：按对象创建时间滚动 30 天；恢复时先重放删除标记，已删除的数据不会因恢复而重新出现。
- 离线行程：最后一次成功同步起最多 14 天可读，到期停止读取。
- 真人服务：请求、状态与凭据在服务完成后 12 个月删除；服务纪要 90 天删除。官网提交的请求进同一套后端，按同样期限删除。
- 抢先体验申请：【待 JT：保存期限】

- Memories, chats and trips: kept until you delete them or close your account; we do not delete them for inactivity (ADR-0006). [JT: review each category for continued necessity]
- Operational logs and diagnostics: 90-day policy target [to verify against the actual cleanup jobs].
- Backups: rolling 30 days from object creation; restores replay deletions first, so deleted data does not come back.
- Offline trips: readable for up to 14 days after the last successful sync, then reading stops.
- In-person services: requests, status and records are deleted 12 months after the service; service notes after 90 days. Requests from the website go into the same backend and follow the same periods.
- Early access applications: [JT: retention period]

## 8. 你的权利 / Your rights

你可以查阅、更正、删除你的信息，撤回同意，注销账号，并要求解释本政策。【按实际构建写入口：哪些在 App 内可做、哪些发邮件】请发邮件到 hello@go2china.space，我们会在【待 JT：时限】内回复。撤回同意不影响撤回前已进行的处理；已经发出的请求无法在传输途中召回，但我们会依法协助删除。

You can access, correct and delete your information, withdraw consent, close your account, and ask us to explain this policy. [In-app paths per the actual build] Email hello@go2china.space and we will reply within [JT: time limit]. Withdrawing consent does not affect processing before withdrawal. Requests already sent cannot be recalled in transit, but we will help delete them as the law requires.

## 9. 未成年人 / Children

Go2China 面向成年人。我们不会在知情的情况下收集未满【待 JT：年龄】周岁者的个人信息。

Go2China is for adults. We do not knowingly collect personal information from anyone under [JT: age].

## 10. 安全 / Security

传输加密；服务密钥只放在服务器，不在 App 里；真人服务上线后，员工按名单登录运营台，查看留审计；陪同人员只看到最少必要信息。

Data is encrypted in transit; service keys are kept on our servers, never in the app; once in-person services launch, staff sign in to the operations console from an approved list and every view is logged; companions see only the minimum they need.

## 11. 政策更新 / Changes

我们会在本页公布新版本和生效日期。涉及处理目的、接收方或跨境的重大变化，会在 App 内提示，需要时重新征得你的同意。

We post new versions and their effective dates on this page. For material changes to purposes, recipients or cross-border transfers, we notify you in the app and ask for consent again where required.
