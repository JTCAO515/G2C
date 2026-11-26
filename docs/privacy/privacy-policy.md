# Go2China 隐私政策 / Privacy Policy（草稿）

<!--
状态：草稿，待 JT 批准；未对外发布。Issue #1746（W4-2，总票 #1714）。
同源：本文件是官网与 App 隐私政策的唯一文本来源。官网页（web/，W0-4 之后由官网线接入）与 App 内隐私页（替换 PublicInformation.swift 的内测说明，W4-3 #1747）都从本文件生成，不各自手写。生成方式在接入票里定。
方括号【待 JT】处是主体信息或需要 JT 决定的内容，起草时不填。
每节中文在前、英文在后，两种语言内容一致；不一致时以【待 JT：哪种语言为准】为准。
不写尚未实装的功能或未经验证的期限（#225 正式法律相关意见「文案」一节）。
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
| 真人服务 | 称呼、电话号码、服务时间与地点、会面信息、备注 | 安排陪同，见第 6 节 | 请求真人服务时必需 |
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
| In-person services | Name to address you by, phone number, service time and place, meeting details, notes | Arranging a companion, see section 6 | Required to request a service |
| Usage and diagnostics | Usage counts, error records | Quotas, troubleshooting | Required |
| Feedback | What you choose to submit | Handling the issue | Optional |

**我们不收集**：护照号等证件号码、支付卡号、你的通讯录。只有在你使用打车或附近、并单独同意后，我们才读取设备位置；每次只读一次，不在后台持续定位，也不把位置写入记忆或发给 AI 模型。

**We do not collect**: passport or other ID numbers, payment card numbers, or your contacts. We read your device location only when you use Taxi or Nearby and have given separate consent. We read it once each time, never track you in the background, and never put your location into memory or send it to the AI model.

<!-- 【发布前提】位置相关的写法对应统筹 2026-11-26 按 JT 预授权决定的边界（#1833：打车坐标只用于该次请求、不记日志不落盘不进缓存键；附近降到 3 位小数），以及 #1832（定位用途说明与隐私清单申报）、#1747（同意界面单列定位）。这三张票落地前，本节与现状不符，不能对外发布。 -->

我们不出售你的个人信息，也不用于广告。

We do not sell your personal information or use it for advertising.

## 4. 我们与谁共享 / Who we share with

我们只把完成你所用功能需要的信息发给下列接收方；发给它们的请求不带你的账号、邮箱或手机号。【待核对：各接收方的签约主体全称】

We send each recipient only what the feature you use needs. Requests to them do not include your account, email or phone number. [To verify: each recipient's contracting entity]

| 接收方 / Recipient | 所在地 / Location | 收到什么 / What they receive | 用途 / Purpose |
|---|---|---|---|
| 阿里云百炼（通义千问）/ Alibaba Cloud Model Studio (Qwen) | 中国大陆北京 / Beijing, mainland China | 对话文字和行程内容；翻译的文字、语音、图片；菜单照片 / Chat text and trip content; text, voice and images for translation; menu photos | 生成回答、翻译、识别菜单 / Replies, translation, menu reading |
| 高德地图开放平台 / AMap (Gaode) | 中国大陆 / Mainland China | 地点和路线查询词、城市；附近功能的约 100 米精度位置 / Place and route queries, city; location at about 100 m for Nearby | 地点、路线、天气、附近 / Places, routes, weather, Nearby |
| 滴滴出行 / DiDi | 中国大陆 / Mainland China | 打车搜索词、上车点（可为设备精确位置）、目的地 / Taxi search terms, pickup (may be precise device location), destination | 估价、生成叫车链接；你在滴滴 App 里下单付款 / Estimates and ride links; you book and pay in the DiDi app |
| 飞常准 / VariFlight | 中国大陆 / Mainland China | 航班号、机场、日期 / Flight number, airports, date | 航班查询 / Flight lookup |
| 阿里云（香港）/ Alibaba Cloud (Hong Kong) | 中国香港 / Hong Kong, China | 服务器与备份上的全部数据 / All data on our servers and backups | 代我们托管 / Hosting on our behalf |
| 真人服务陪同人员 / In-person companions | 广州 / Guangzhou | 见第 6 节 / See section 6 | 提供你请求的服务 / Providing the service you requested |

**你点开的第三方链接**：打开 Trip.com（酒店、火车、机票、景点）、Klook、12306、高德地图或 Apple 地图时，链接里会带上你查询的城市、酒店、日期、人数或目的地坐标，由对方按其隐私政策处理。App 内地图由 Apple MapKit 显示。

**Third-party links you open**: When you open Trip.com (hotels, trains, flights, attractions), Klook, 12306, AMap or Apple Maps, the link carries the city, hotel, dates, number of guests or destination coordinates you searched for, and that service handles them under its own policy. In-app maps are shown by Apple MapKit.

## 5. 存放地点与跨境 / Where data is stored and cross-border transfers

你的账号、对话、行程、记忆和服务请求存放在我们位于中国香港的服务器（阿里云中国香港），每日备份存放在中国香港的对象存储。

- 生成回答、翻译、识别菜单时，相关内容会从香港发送到中国大陆北京的阿里云百炼处理。
- 使用地点、路线、打车、附近、航班工具时，查询条件会从香港发送到位于中国大陆的高德、滴滴、飞常准。
- 你在中国大陆使用 App 时，你的信息会从大陆传到香港。
- 你请求真人服务时，第 6 节所列信息会从香港提供给广州的陪同人员；陪同的服务纪要会传回香港。

在首次把你的对话发送给 AI 模型前，以及首次使用位置、请求真人服务前，我们会在 App 内单独征得你的同意。【待 JT：出境所需的标准合同、认证或评估，按 #225 路径在对外开放前落实，并在此写明】

Your account, chats, trips, memories and service requests are stored on our servers in Hong Kong, China (Alibaba Cloud Hong Kong), with daily backups in object storage in Hong Kong.

- For replies, translation and menu reading, the relevant content goes from Hong Kong to Alibaba Cloud Model Studio in Beijing, mainland China.
- For places, routes, taxi, nearby and flight tools, your search terms go from Hong Kong to AMap, DiDi and VariFlight in mainland China.
- When you use the app in mainland China, your information is transferred from the mainland to Hong Kong.
- When you request an in-person service, the information in section 6 is provided from Hong Kong to the companion in Guangzhou, and the companion's service notes come back to Hong Kong.

We ask for your separate consent in the app before we first send your chats to the AI model, and before you first use location or request an in-person service. [JT: cross-border mechanisms (standard contract, certification or assessment) to be put in place under #225 before external launch and stated here]

## 6. 真人服务 / In-person services

部分服务由真人提供，首个是广州的中英商务陪同。提交前，确认页会列出将与陪同人员共享的信息，并写明服务由真人提供、陪同人员称呼、到场时间、取消规则和由谁退款。你单独同意后我们才会提交。

陪同人员受我们委托提供服务，按服务协议只为本次服务使用你的信息、服务结束后删除、不得转交他人。陪同只能看到完成本次服务需要的信息（称呼、语言、时间地点、会面信息、当天联系的电话号码），从服务安排好到服务结束后 24 小时内可见；看不到你的账号、对话、行程全文、记忆和报价。服务状态在 App 内更新。

陪同服务按次收费，在 App 外付款，不通过 Apple App 内购买。【待 JT：收款方式与收款主体】

请只填写陪同需要知道的内容，不要在备注里填写健康、证件或宗教信息；如需填写会面对象的信息，请只填称呼和公司名。

Some services are provided by real people. The first is an English–Chinese business companion in Guangzhou. Before you submit, the confirmation page lists the information we will share with the companion and states that the service is provided by a person, the companion's name, arrival time, cancellation rules and who handles refunds. We only submit after you give separate consent.

Companions act on our behalf. Under their service agreement they use your information only for this service, delete it afterwards and do not pass it on. A companion sees only what is needed for this service (how to address you, language, time and place, meeting details, and a phone number for that day), from when the service is arranged until 24 hours after it ends. They cannot see your account, chats, full trips, memories or the price. Service status is updated in the app.

Companion services are paid per service, outside the app, not through Apple in-app purchase. [JT: payment method and receiving entity]

Please include only what the companion needs to know. Do not put health, ID or religious information in the notes. If you mention the people you are meeting, include only their name and company.

## 7. 保存多久 / How long we keep it

【按 #225 意见逐类核对后定稿，不沿用旧内测文案的 30/30/30/180 天。以下为已确认或已实装的口径：】

- 记忆、对话、行程：保存到你删除或注销账号；系统不会因长期未使用而删除（ADR-0006）。【待 JT：按 PIPL 第 19、47 条逐类审核是否有持续必要】
- 运行日志与诊断：政策目标 90 天【待核对实际清理任务覆盖范围】。
- 备份：按对象创建时间滚动 30 天；恢复时先重放删除标记，已删除的数据不会因恢复而重新出现。
- 离线行程：最后一次成功同步起最多 14 天可读，到期停止读取。
- 真人服务：请求、状态与凭据在服务完成后 12 个月删除；服务纪要 90 天删除。

- Memories, chats and trips: kept until you delete them or close your account; we do not delete them for inactivity (ADR-0006). [JT: review each category for continued necessity]
- Operational logs and diagnostics: 90-day policy target [to verify against the actual cleanup jobs].
- Backups: rolling 30 days from object creation; restores replay deletions first, so deleted data does not come back.
- Offline trips: readable for up to 14 days after the last successful sync, then reading stops.
- In-person services: requests, status and records are deleted 12 months after the service; service notes after 90 days.

## 8. 你的权利 / Your rights

你可以查阅、更正、删除你的信息，撤回同意，注销账号，并要求解释本政策。【按实际构建写入口：哪些在 App 内可做、哪些发邮件】请发邮件到 hello@go2china.space，我们会在【待 JT：时限】内回复。撤回同意不影响撤回前已进行的处理；已经发出的请求无法在传输途中召回，但我们会依法协助删除。持续断网的设备无法被远程清除，会在下次联网时清理。

You can access, correct and delete your information, withdraw consent, close your account, and ask us to explain this policy. [In-app paths per the actual build] Email hello@go2china.space and we will reply within [JT: time limit]. Withdrawing consent does not affect processing before withdrawal. Requests already sent cannot be recalled in transit, but we will help delete them as the law requires. A device that stays offline cannot be wiped remotely; it is cleaned up the next time it connects.

## 9. 未成年人 / Children

Go2China 面向成年人。我们不会在知情的情况下收集未满【待 JT：年龄】周岁者的个人信息。

Go2China is for adults. We do not knowingly collect personal information from anyone under [JT: age].

## 10. 安全 / Security

传输加密；服务密钥只放在服务器，不在 App 里；真人服务上线后，员工按名单登录运营台，查看留审计；陪同人员只看到最少必要信息。

Data is encrypted in transit; service keys are kept on our servers, never in the app; once in-person services launch, staff sign in to the operations console from an approved list and every view is logged; companions see only the minimum they need.

## 11. 政策更新 / Changes

我们会在本页公布新版本和生效日期。涉及处理目的、接收方或跨境的重大变化，会在 App 内提示，需要时重新征得你的同意。

We post new versions and their effective dates on this page. For material changes to purposes, recipients or cross-border transfers, we notify you in the app and ask for consent again where required.
