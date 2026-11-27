# Go2China 隐私政策 / Privacy Policy

<!--
同源：本文件是官网 go2china.space/privacy 与 App 内隐私页的唯一文本来源，两处都从这里生成，不各自手写。
原则：只写已经上线的事。尚未开放的能力放在第 12 节「开放后适用」，开放前不对外承诺。
事实来源：出站数据流登记表 docs/privacy/outbound-dataflow.md；PIPIA 增补 docs/privacy/pipia-service-request.md；#225 正式法律相关意见。
发布：JT 本人定 2026-12-01 正式公开（统筹转达）。公开首发（App Store 上架）前另请法律意见复核本文。
运营主体出处：JT 2026-11-09 更正为广州创竞科技有限公司（#225 正文「JT 2026-11-09 事实更正 · 运营主体」、docs/scope.md「处理方与地域」行）；此前 #159 与构建 57 App 内说明写的 Context Jump LLC 是主体假设。#225 正式意见以美国主体为前提的段落是否需补充意见，见 #33 放行清单「需要 JT 确认」第 3 项。
营业执照信息：JT 本人 2026-11-26 提供（统筹转达）。英文名称 JT 原写「Guangzhou Chuangjing Technology Co.LTd」，按通行写法规范为「Guangzhou Chuangjing Technology Co., Ltd.」，只是格式规范，不是改名。
公开页不出现占位（官网生成器 `scripts/build_privacy_page.cjs --strict`）。
依赖（统筹 2026-11-26 按 JT 预授权决定，随 12-01 一起上线）：
- 第 5、6 节 Vercel 香港区域：#1872（`web/vercel.json` 固定 `/api/*` 到 hkg1）须在公开前合并。
- 第 6 节抢先体验申请的境外处理勾选：#1878（政策页与勾选框）随政策一起合并。
- 第 4 节位置精度：#1875（#1833）已随源提交 47c89be1 在香港上线（切换 2026-11-26 09:43Z；S 线读回证据在 [#1833 评论](https://github.com/JTCAO515/G2C/issues/1833#issuecomment-7188449226)：现网镜像 `COARSE_DECIMALS = 3`，三类高德请求和缓存键都是 3 位小数，附近冒烟通过，香港容器日志里没有精确坐标）。
锚点按生成器写法写在对应行的行尾（生成器只给英文版写 id，所以第 12 节中英两条都写）：recipients（第 5 节，避免生成器按节号默认给第 5 节 cross-border）、cross-border（第 6 节）、in-person-services、website-requests（第 12 节）。
-->

- 版本：1.0　生效日期：2026 年 12 月 1 日
- Version: 1.0　Effective date: 1 December 2026
- 中英文如有不一致，以中文版为准。/ If the Chinese and English versions differ, the Chinese version prevails.

## 1. 我们是谁 / Who we are

Go2China（以下简称「我们」）是帮助外国人在中国办事的本地助手，包括 Go2China iOS App 和网站 go2china.space。运营主体：广州创竞科技有限公司，注册地址：广州市天河区黄埔大道西100号富力盈泰广场A座410A室。联系我们：hello@go2china.space。

Go2China ("we") is a local assistant that helps foreigners get things done in China, made up of the Go2China iOS app and the website go2china.space. Operator: Guangzhou Chuangjing Technology Co., Ltd., registered at Room 410A, Tower A, R&F Yingtai Plaza, No. 100 Huangpu Avenue West, Tianhe District, Guangzhou, China. Contact: hello@go2china.space.

## 2. 适用范围与当前状态 / Scope and current status

本政策适用于 Go2China iOS App 和官网 go2china.space。

- App 目前只通过 Apple TestFlight 向受邀测试者提供，还没有在 App Store 上架。
- 官网目前提供产品介绍和「抢先体验」申请表。
- 你通过我们跳转到第三方平台（例如滴滴、Trip.com、Klook、12306、景点官网）后，由该平台按其隐私政策处理你的信息。

This policy covers the Go2China iOS app and the website go2china.space.

- The app is currently offered only to invited testers through Apple TestFlight. It is not yet on the App Store.
- The website currently offers product information and an early access application form.
- When we send you to a third-party platform (for example DiDi, Trip.com, Klook, 12306 or an attraction's official site), that platform handles your information under its own privacy policy.

## 3. 我们处理哪些信息、为什么 / What we process and why

| 功能 | 信息 | 目的 |
|---|---|---|
| 账号 | 邀请码、账号标识；登录凭据保存在你设备的钥匙串里 | 登录、区分账号 |
| 和 Lio 对话、规划行程 | 你发送的文字；Lio 的回答；你保存的行程 | 生成回答、规划和保存行程 |
| 记忆 | Lio 会根据对话提出可以记住的偏好与事实（为此对话内容会发给 AI 模型）。这些候选随你的账号保存在服务器上；你点「记住」后才成为记忆、用于以后的对话 | 跨对话记住你，你可以查看、修改和删除记忆 |
| 翻译 | 你输入的文字、录下的语音、拍摄或选择的图片（上传前去掉照片里的位置等元数据） | 翻译、朗读 |
| 点餐 | 菜单照片（服务器不保存照片） | 识别并解释菜品 |
| 打车 | 搜索词、上车点和目的地；选「当前位置」时为设备精确位置 | 查询地点、估价、生成滴滴叫车链接 |
| 附近 | 设备位置（发给地图服务前降到约 100 米精度） | 查找附近的地点、「我在哪」 |
| 其他工具 | 城市、地点名、酒店地标、航班号、出行日期等你输入的查询条件 | 查询地点、路线、天气、汇率、航班、火车、酒店 |
| 景点预约提醒 | 你选的景点和日期 | 在你的设备上按时提醒（本机通知，不发给我们的服务器） |
| 问题反馈 | App 内目前没有提交反馈的入口；受邀测试者在内部测试群里发截图、问题记录和发生时间 | 处理问题 |
| 用量与诊断 | 用量计数、错误记录 | 额度控制、排查故障 |
| 官网抢先体验申请 | 称呼、邮箱、得知渠道、所在国家、计划出行时间、目的地、需求、备注 | 处理你的申请、通过邮件联系你 |
| 和我们的邮件往来 | 你发给 hello@go2china.space 的邮件内容与邮箱地址 | 回复你 |

| Feature | Information | Purpose |
|---|---|---|
| Account | Invite code, account identifier; sign-in credentials stay in your device keychain | Sign-in, keeping accounts apart |
| Chatting with Lio, planning trips | Text you send; Lio's replies; trips you save | Replies, planning and saving trips |
| Memory | Lio suggests preferences and facts it could remember from your chats (the chat content goes to the AI model for this). These suggestions are stored on our servers with your account; they become memories used in later chats only when you tap Remember | Remembering you across chats; you can view, edit and delete memories |
| Translation | Text you type, voice you record, photos you take or choose (location and other metadata removed before upload) | Translating and reading aloud |
| Menu | Menu photos (our server does not keep them) | Reading and explaining dishes |
| Taxi | Search terms, pickup and destination; your precise device location when you choose "Current location" | Finding places, fare estimates, DiDi ride links |
| Nearby | Your device location (reduced to about 100 m before it goes to the map service) | Finding places near you, "Where am I" |
| Other tools | City, place names, hotel landmarks, flight numbers, travel dates and other search terms you enter | Places, routes, weather, exchange rates, flights, trains, hotels |
| Sight booking reminders | The sight and date you choose | Reminders on your device (local notifications, not sent to our servers) |
| Feedback | There is no way to submit feedback in the app yet; invited testers share screenshots, the issue record and the time in the internal testing group | Handling the issue |
| Usage and diagnostics | Usage counts, error records | Quotas, troubleshooting |
| Website early access application | Name, email, how you heard of us, country, planned travel time, destinations, needs, notes | Handling your application and contacting you by email |
| Emails with us | The content of emails you send to hello@go2china.space and your email address | Replying to you |

**我们不收集**护照号等证件号码、支付卡号和你的通讯录；App 内不付款。我们不出售你的个人信息，也不用于广告。请不要在对话、翻译或申请表里填写健康、证件、宗教等敏感信息，或可识别他人的信息。

**We do not collect** passport or other ID numbers, payment card numbers, or your contacts, and nothing is paid for in the app. We do not sell your personal information or use it for advertising. Please do not enter health, ID or religious information, or information that identifies other people, in chats, translation or application forms.

## 4. 位置 / Location

- 只有在你使用「打车」或「附近」时，App 才通过 iOS 系统权限读取设备位置；每次只读一次，不在后台持续定位。
- 去向：位置先发到我们在香港的服务。打车时，上车点的精确位置只在这一次请求里发给滴滴，我们自己不写日志、不保存；用来让搜索结果更靠近你的位置降到约 100 米。查找附近时，位置降到约 100 米精度后再发给高德。
- 位置不和你的账号一起保存，不写入记忆，也不发给 AI 模型。查找附近时，服务器会在内存里按降精度后的位置短暂缓存查询结果（约 1 分钟），不与账号关联。
- 撤回：在 iOS「设置」里关闭 Go2China 的定位权限，或者不用这两个功能；其他功能照常可用，打车时可以手动选上车点。

- The app reads your device location through the iOS permission only when you use Taxi or Nearby. It reads it once each time and never tracks you in the background.
- Where it goes: your location first goes to our service in Hong Kong. For Taxi, the precise pickup location is sent to DiDi in that one request only, and we do not log or store it ourselves; the location used to bring search results closer to you is reduced to about 100 m. For Nearby, your location is reduced to about 100 m before it goes to AMap.
- Your location is not stored with your account, not saved to memory, and not sent to the AI model. For Nearby, our server briefly caches results in memory by the reduced location (about 1 minute), not linked to your account.
- To withdraw: turn off location access for Go2China in iOS Settings, or don't use these two features. Everything else keeps working, and for Taxi you can choose the pickup point by hand.

## 5. 我们与谁共享 / Who we share with {#recipients}

我们只把完成你所用功能需要的信息发给下列接收方。发给阿里云百炼、高德、滴滴、飞常准的请求不带你的账号、邮箱或手机号。

We send each recipient only what the feature you use needs. Requests to Alibaba Cloud Model Studio, AMap, DiDi and VariFlight do not include your account, email or phone number.

| 接收方 / Recipient | 所在地 / Location | 收到什么 / What they receive | 用途 / Purpose |
|---|---|---|---|
| 阿里云（中国香港）/ Alibaba Cloud (Hong Kong) | 中国香港 / Hong Kong, China | 服务器与每日备份上的全部数据 / All data on our servers and daily backups | 代我们托管 / Hosting on our behalf |
| 阿里云百炼（通义千问）/ Alibaba Cloud Model Studio (Qwen) | 中国大陆北京 / Beijing, mainland China | 对话文字和行程内容；翻译的文字、语音、图片；菜单照片；打车、酒店、地铁周边的搜索结果里的地点名和地址（用于生成英文名）；路书里的地点名、营业时间和地铁站名 / Chat text and trip content; text, voice and images for translation; menu photos; place names and addresses in taxi, hotel and metro-nearby search results (to produce English names); place names, opening hours and station names in roadbooks | 生成回答、翻译、识别菜单、生成地点英文名和路书地点说明 / Replies, translation, menu reading, English place names and roadbook place descriptions |
| 高德地图开放平台 / AMap (Gaode) | 中国大陆 / Mainland China | 地点和路线查询词、城市、酒店地标、火车出发日期；附近功能降到约 100 米精度的设备位置 / Place and route queries, city, hotel landmarks, train departure dates; your device location reduced to about 100 m for Nearby | 地点、路线、天气、酒店、火车、附近 / Places, routes, weather, hotels, trains, Nearby |
| 滴滴出行 / DiDi | 中国大陆 / Mainland China | 打车搜索词、上车点（可为设备精确位置）、目的地 / Taxi search terms, pickup (may be your precise device location), destination | 估价、生成叫车链接；你在滴滴 App 里下单付款 / Estimates and ride links; you book and pay in the DiDi app |
| 飞常准 / VariFlight | 中国大陆 / Mainland China | 航班号、机场、日期 / Flight number, airports, date | 航班查询 / Flight lookup |
| Vercel Inc. | 美国公司；官网接口运行在 Vercel 香港区域，静态页面与平台访问日志不受该区域设置控制 / A US company; website endpoints run in Vercel's Hong Kong region, while static pages and platform access logs are not bound to that region | 官网访问，以及你在官网提交的申请（我们的接口代码转发时不保存原文；Vercel 平台记录 IP、路径等访问信息）/ Website visits and applications you submit (our endpoint code forwards them without storing the text; the Vercel platform logs access details such as IP address and path) | 代我们托管官网和表单接口 / Hosting the website and its form endpoints on our behalf |
| Jotform Inc. | 美国 / United States | 抢先体验申请的全部字段 / All fields of the early access application | 代我们保存和管理抢先体验申请 / Storing and managing early access applications on our behalf |
| Spacemail（Spaceship 旗下邮箱服务）/ Spacemail (Spaceship's email service) | 服务商位于美国，邮件可能存储在中国境外 / Provider based in the United States; emails may be stored outside China | 你和 hello@go2china.space 之间的邮件 / Emails between you and hello@go2china.space | 收发邮件 / Sending and receiving email |
| Apple | 美国等 / United States and elsewhere | 通过 TestFlight 分发 App；你在 TestFlight 里提交的反馈和崩溃报告；App 内地图由 Apple MapKit 显示 / App distribution through TestFlight; feedback and crash reports you submit in TestFlight; in-app maps shown by Apple MapKit | 按 Apple 的隐私政策处理 / Handled under Apple's privacy policy |

**你点开的第三方链接**：打开 Trip.com（酒店、火车、机票、景点）时，链接里会带上你查询的城市、酒店、日期和人数；打开滴滴叫车链接时带上车点和目的地坐标；打开高德地图或 Apple 地图导航时带目的地坐标或站名；打开 Klook、12306 和景点官网的链接不带你的信息。打开后由对方按其隐私政策处理。

**Third-party links you open**: Trip.com links (hotels, trains, flights, attractions) carry the city, hotel, dates and number of guests you searched for. DiDi ride links carry the pickup and destination coordinates. Navigation links to AMap or Apple Maps carry the destination coordinates or station name. Links to Klook, 12306 and attraction sites carry none of your information. Once opened, that service handles your information under its own policy.

## 6. 存放地点与跨境 / Where data is stored and cross-border transfers {#cross-border}

你的账号、对话、行程和记忆存放在我们位于中国香港的服务器，每日备份存放在中国香港的对象存储。你的信息会在中国大陆与境外之间传输：

- 你在中国大陆使用 App 时，信息从大陆传到香港。
- 生成回答、翻译、识别菜单、生成地点英文名和路书地点说明时，相关内容从香港发到北京的阿里云百炼；使用地点、路线、打车、附近、航班工具时，查询条件从香港发到位于中国大陆的高德、滴滴、飞常准。
- 官网抢先体验申请先传到中国香港处理（官网接口由 Vercel 托管，运行在香港区域），再转给位于美国的 Jotform；你和我们的邮件由位于美国的 Spacemail 收发，可能存储在中国境外。
- 提交抢先体验申请前，请你勾选「同意传到中国大陆以外（中国香港和美国）处理」；不勾选无法提交。

**依据**：上述传输是为向你提供你请求的服务、履行与你之间的约定所必需（《个人信息保护法》第十三条第一款第二项）；向境外提供个人信息，我们按《促进和规范数据跨境流动规定》中为订立、履行个人作为一方当事人的合同所必需的情形处理，并向你告知接收方、目的、方式和信息种类（见第 5 节）。其中设备位置和记忆建议目前只对受邀内部测试账号开放；对外部用户开放前，我们会另行取得你的单独同意（见第 12 节）。这些依据将在公开首发前另请法律意见复核。

**你的权利**：你可以向我们或境外接收方行使查阅、更正、删除等权利，方式见第 8 节；对跨境提供有疑问，可以发邮件到 hello@go2china.space。

Your account, chats, trips and memories are stored on our servers in Hong Kong, China, with daily backups in object storage in Hong Kong. Your information moves between the Chinese mainland and places outside it:

- When you use the app in mainland China, your information goes from the mainland to Hong Kong.
- For replies, translation, menu reading, English place names and roadbook place descriptions, the relevant content goes from Hong Kong to Alibaba Cloud Model Studio in Beijing; for places, routes, taxi, nearby and flight tools, your search terms go from Hong Kong to AMap, DiDi and VariFlight in mainland China.
- Website early access applications are first transferred to Hong Kong, China for processing (the website endpoint is hosted by Vercel and runs in its Hong Kong region), then go to Jotform in the United States; emails between you and us go through Spacemail, a provider in the United States, and may be stored outside China.
- Before you submit an early access application, you tick "I agree to my information being processed outside mainland China (Hong Kong, China and the United States)". Without it, the application cannot be submitted.

**Basis**: These transfers are necessary to provide the services you ask for and to perform our arrangement with you (Article 13(1)(2) of the Personal Information Protection Law). For transfers outside the Chinese mainland we rely on the situation in the Provisions on Promoting and Regulating Cross-Border Data Flows where a transfer is necessary to conclude or perform a contract to which you are a party, and we tell you the recipients, purposes, methods and types of information (see section 5). Device location and memory suggestions are currently available only to invited internal test accounts; before they are offered to external users, we will ask for your separate consent (see section 12). These bases will be reviewed by legal counsel before public launch.

**Your rights**: You can exercise your rights to access, correct and delete your information with us or with the overseas recipients, as set out in section 8. For questions about cross-border transfers, email hello@go2china.space.

## 7. 保存多久 / How long we keep it

- 记忆、对话、行程：保存到你删除或注销账号；系统不会因为长期未使用而删除。
- 记忆候选：随账号保存，注销账号时删除。
- 运行日志与诊断：政策目标 90 天。
- 备份：按对象创建时间滚动保存 30 天；恢复时先重放删除记录，已删除的数据不会因恢复而重新出现。
- 离线行程：最后一次成功同步起最多 14 天可读，到期停止读取。
- 抢先体验申请：收集后 12 个月删除。
- 和我们的邮件往来：形成服务的，服务完成后 12 个月删除；没有形成服务的询问，最后一次往来后 6 个月删除。

- Memories, chats and trips: kept until you delete them or close your account; we do not delete them for inactivity.
- Memory suggestions: stored with your account and deleted when you close your account.
- Operational logs and diagnostics: 90-day policy target.
- Backups: rolling 30 days from object creation; restores replay deletions first, so deleted data does not come back.
- Offline trips: readable for up to 14 days after the last successful sync, then reading stops.
- Early access applications: deleted 12 months after collection.
- Emails with us: if they led to a service, deleted 12 months after the service is completed; other enquiries, 6 months after the last message.

## 8. 你的权利 / Your rights

你可以查阅、更正、删除你的信息，撤回同意，注销账号，并要求我们解释本政策。

- 在 App 内：在「我的」里查看、修改和删除记忆，或注销账号。
- 撤回 AI 处理（App 内同意界面开放后适用，见第 12 节）：在「我的」→「隐私」里关闭。关闭后，聊天、行程规划、翻译和点餐停用，不再向阿里云百炼发送新的内容，其他功能照常（打车、酒店、地铁周边的地点名只显示中文，路书不生成地点说明）；已经发出的请求无法在传输途中召回，但我们会依法协助删除。
- 其他请求（包括删除抢先体验申请、邮件往来）：发邮件到 hello@go2china.space。我们会先核对你就是当时提交信息时使用的邮箱或账号，在 15 个工作日内答复，最迟 30 天内处理完。
- 撤回同意不影响撤回前已进行的处理；已经发出的请求无法在传输途中召回，但我们会依法协助删除。

You can access, correct and delete your information, withdraw consent, close your account, and ask us to explain this policy.

- In the app: under Me, view, edit and delete memories, or close your account.
- Withdrawing AI processing (applies once the in-app consent screens launch, see section 12): turn it off under Me → Privacy. Once it is off, chat, trip planning, translation and the menu helper stop and no new content is sent to Alibaba Cloud Model Studio; everything else keeps working (place names in taxi, hotel and metro-nearby results show in Chinese only, and roadbooks have no generated place descriptions). Requests already sent cannot be recalled in transit, but we will help delete them as the law requires.
- Other requests (including deleting an early access application or emails with us): email hello@go2china.space. We first check that you are using the same email address or account you used when you gave us the information, reply within 15 business days, and complete the request within 30 days at the latest.
- Withdrawing consent does not affect processing before withdrawal. Requests already sent cannot be recalled in transit, but we will help delete them as the law requires.

## 9. 未成年人 / Children

Go2China 面向 18 周岁及以上的成年人。我们不会在知情的情况下收集未满 18 周岁者的个人信息；发现后会删除。

Go2China is for adults aged 18 and over. We do not knowingly collect personal information from anyone under 18, and we delete it if we find out.

## 10. 安全 / Security

传输加密；服务密钥只放在服务器，不在 App 里；照片上传前去掉位置等元数据；发给地图、打车、航班服务商的请求不带账号信息。

Data is encrypted in transit; service keys are kept on our servers, never in the app; location and other metadata are removed from photos before upload; requests to map, taxi and flight providers carry no account details.

## 11. 政策更新 / Changes

我们会在本页公布新版本和生效日期。涉及处理目的、接收方或跨境的重大变化，会在 App 内或通过邮件提示，需要时重新征得你的同意。

We post new versions and their effective dates on this page. For material changes to purposes, recipients or cross-border transfers, we notify you in the app or by email and ask for consent again where required.

## 12. 开放后适用 / Applies once launched

以下能力还没有开放。开放时我们会先更新本政策；需要你另行同意的，会先在 App 或官网上单独征得你的同意，再开始处理相关信息。

- **真人服务**（首个是广州中英商务陪同）：由真人提供，提交前确认页会列出将与陪同人员共享的信息并分项征得同意；陪同人员受我们委托、只看到完成本次服务需要的信息；按次收费，在 App 外付款。 {#in-person-services}
- **官网真人服务请求表**：在官网「广州中英商务陪同」表单提出请求，收集称呼、邮箱、日期和说明（选填），提交到我们自己的后端，由工作人员通过邮件跟进，不经过第三方表单服务；谈妥后再转成正式的服务请求。提交前请你确认已阅读本政策，并分三项征得你的同意：处理时间地点等行踪信息；提供给陪同人员；传到中国大陆以外（中国香港和美国）处理（官网接口由 Vercel 托管，运行在香港区域；App 服务在阿里云香港；回复邮件由美国的 Spacemail 收发）。具体时间、地点、会面对象和当天联系电话，我们在回复邮件里和你确认后再记录，在此之前陪同人员看不到你的任何联系方式。 {#website-requests}
- **App 内同意界面与定位单独询问页**：首次启动时先请你同意把数据存放在我们位于中国香港的服务器，并由你选择是否开启 AI 处理（不开启也能使用 App，只是聊天、行程规划、翻译和点餐不可用，可随时在「我的」→「隐私」里开启或关闭）；第一次要生成记忆建议之前，以及使用位置之前，另行单独询问；位置可在「我的 → 位置」撤回。
- **App 内问题反馈**：在 Lio 的回答下点「没帮上」并可选填补充说明，发到我们在香港的服务，按账号保存，注销账号时删除。开放前会先单独征得你的同意。
- **对话中的行程建议自动保存**：你和 Lio 聊到行程时，和这一趟有关的建议（新加的地点、Lio 草拟的日程、想去的地方）会自动保存到你当前的行程，存放位置和其他行程内容一样，在我们位于中国香港的服务器。每次保存后，回答下面会出现「已加入 · 撤销」：在 24 小时内，并且这一趟在这次保存之后还没有新的改动（你自己改过，或 Lio 又保存、撤销过），可以一键撤销这次保存；有了新的改动之后，这一次就不能再撤销，但你仍可以随时在行程里删掉 Lio 加的内容。你自己加过、改过或删掉的地点，Lio 不会修改、移动或再加回。为此我们会记录：每次保存和撤销来自哪条对话、哪个账号、什么时间；行程里每个地点是你还是 Lio 加的或改的；你删掉了哪些地点（用来不再自动加回）。撤销或删掉地点不会删除这些记录，它们随你的账号保存，注销账号时一起删除。这项不另设同意：它属于第 3 节「和 Lio 对话、规划行程」里规划和保存行程的用途；第一次自动保存时，App 会提示你一次。 {#trip-autosave}

The following are not launched yet. Before launching any of them, we will update this policy; where your separate consent is needed, we will ask for it in the app or on the website before processing the related information.

- **In-person services** (the first is an English–Chinese business companion in Guangzhou): provided by real people. Before you submit, a confirmation page lists the information to be shared with the companion and asks for separate consents. Companions act on our behalf and see only what this service needs. Paid per service, outside the app. {#in-person-services}
- **Website in-person service request form**: request a companion through the "A business companion in Guangzhou" form on the website by giving your name, email, a date and an optional note. It goes to our own backend, where our staff follow up by email, not through any third-party form service; once details are agreed, it becomes a formal service request. Before you submit, the form asks you to confirm you have read this policy and to give three separate consents: processing time and place information; sharing it with the companion; and processing outside mainland China (Hong Kong, China and the United States) (the website endpoint is hosted by Vercel and runs in its Hong Kong region; the app service runs on Alibaba Cloud Hong Kong; reply emails go through Spacemail in the United States). We confirm the exact time, place, who you are meeting and a phone number for the day with you by email before recording them; until then the companion cannot see any of your contact details. {#website-requests}
- **In-app consent screens and a separate location prompt**: at first launch we first ask you to agree to your data being stored on our servers in Hong Kong, China, and let you choose whether to turn on AI processing (you can use the app without it; chat, trip planning, translation and the menu helper will not be available; you can turn it on or off at any time under Me → Privacy). We ask separately before memory suggestions are first generated and before location is used; location can be withdrawn under Me → Location.
- **In-app feedback**: tap "Didn't help" under a Lio answer and optionally add a note. It goes to our service in Hong Kong, is stored with your account and is deleted when you close your account. We will ask for your separate consent before it launches.
- **Trip suggestions saved automatically from chat**: when you talk with Lio about a trip, suggestions for that trip (places it adds, days it drafts, places you want to visit) are saved to your current trip automatically, stored like the rest of your trips on our servers in Hong Kong, China. After each save, "Added · Undo" appears under the answer. You can undo that save with one tap within 24 hours, as long as the trip has not changed since (you edited it, or Lio saved or undid something); once it has, that save can no longer be undone, but you can still remove the items Lio added from the trip at any time. Lio does not change, move or bring back places you added, edited or removed yourself. To do this we record which chat, which account and what time each save and undo came from; whether each place in the trip was added or changed by you or by Lio; and which places you removed (so they are not added back automatically). Undoing a save or removing a place does not delete these records; they are kept with your account and deleted when you close your account. This needs no separate consent: it falls under planning and saving trips in "Chatting with Lio, planning trips" in section 3; the app tells you once, the first time a trip suggestion is saved automatically. {#trip-autosave}
