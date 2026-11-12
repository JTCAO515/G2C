/* Copy for go2china.space in six languages. Edit here; app.js only renders it.
   Chat-demo, redaction and footer strings come from the previous page version. */
window.G2C = {
 "T": {
  "en": {
   "nav": {
    "how": "How it works",
    "places": "Places",
    "privacy": "Privacy"
   },
   "heroTitle": "A personal agent for every day in China.",
   "heroLede": "Ask CJ Agent anything about getting around, paying, eating and booking. When a problem needs a phone call or a local check, JT Agent brings in a real person.",
   "heroNote": "Coming to iPhone first. We’re inviting travellers in small groups.",
   "howTitle": "How CJ Agent and JT Agent work together",
   "howLede": "CJ Agent is the one you talk to. JT Agent works in the background: it keeps an eye on your trip, opens a case when something goes wrong, and hands the steps AI can’t finish to a teammate.",
   "cjRole": "In your chat",
   "jtRole": "Behind the scenes",
   "cjList": [
    "Answers questions about payments, transport, food and tickets, with sources you can check.",
    "Plans your days around what it remembers about you, and keeps confirmed plans in place.",
    "Prepares bookings and changes, then waits for your yes before anything is paid or moved.",
    "Shows phrases and booking details in Chinese when you need to show someone.",
    "Speaks English and Chinese in the same conversation."
   ],
   "jtList": [
    "Follows your bookings, trains, flights and check-ins.",
    "Notices when something goes wrong, or when a question keeps going round in circles.",
    "Opens a case with only the details the next step needs.",
    "Passes calls and local checks to a teammate, and follows them through to the end.",
    "Sends the result back through CJ Agent, so everything stays in one chat."
   ],
   "scTitle": "What it looks like on the road",
   "tabs": [
    "The hotel can’t find your booking",
    "Your train is cancelled",
    "You need help fast"
   ],
   "laneChat": "In your chat",
   "laneBack": "Behind the scenes",
   "who": {
    "you": "You",
    "cj": "CJ Agent",
    "jt": "JT Agent",
    "mate": "Teammate"
   },
   "scenes": {
    "hotel": {
     "steps": [
      "The front desk says they can’t find my booking.",
      "Show them this card. I’m also asking a teammate to call the hotel.",
      "Booking not found at check-in. Handled as a trip disruption.",
      "Case opened with the hotel name, booking number and dates. Passport and account details stay out.",
      "Called the front desk in Chinese. The booking was filed under CLARKE EMMA.",
      "All sorted: it was under “CLARKE EMMA”. Your room is ready. A teammate called the hotel to confirm."
     ],
     "note": "If there had been no room, CJ Agent would show you nearby options with prices and book one only after you choose."
    },
    "train": {
     "steps": [
      "Status check: the 14:05 train to Xi’an is cancelled.",
      "Checks what depends on it: tonight’s hotel check-in and tomorrow’s 9:00 entry tickets.",
      "Your 14:05 train to Xi’an is cancelled. The 15:20 train arrives at 19:58 and keeps tonight’s hotel and tomorrow’s tickets. Book it?",
      "Yes, book the 15:20.",
      "Rebooked the ticket and told the hotel you’ll arrive around 20:30.",
      "Done. Your new ticket and updated plan are in your trip."
     ],
     "note": "Nothing was paid or changed until you said yes."
    },
    "sos": {
     "steps": [
      "I fell on the stairs and can’t stand on my ankle.",
      "If it’s serious, call 120 for an ambulance now. Show this to the driver or anyone nearby:",
      "Safety signal. Emergency steps went out straight away, without waiting for a case.",
      "On-call teammate alerted to help by message.",
      "A teammate is following up with you here. The nearest hospital with English-speaking staff is 2 km away."
     ],
     "note": "Emergency help is open to every user and covers guidance and message support. If you’re in danger, always call 110 (police), 120 (ambulance) or 119 (fire)."
    }
   },
   "watchTitle": "What JT Agent keeps an eye on",
   "cols": [
    "Situation",
    "For example",
    "What happens"
   ],
   "watch": [
    [
     "Your safety",
     "Injury, sudden illness, getting lost.",
     "Emergency numbers and phrases straight away, then a teammate helps by message."
    ],
    [
     "Documents and money",
     "A lost passport, a blocked card, a payment that won’t go through.",
     "Steps for reporting and replacing come first; a teammate checks the details."
    ],
    [
     "Disruptions",
     "A changed flight, a hotel that can’t find you, a closed attraction.",
     "Works out what else is affected, then proposes a fix."
    ],
    [
     "Changes you ask for",
     "Switch hotels, move a day, add a city.",
     "CJ Agent drafts options. Nothing changes until you confirm."
    ],
    [
     "When the AI gets stuck",
     "The same question going unanswered, a tool that keeps failing.",
     "A teammate sorts it out in the background and CJ Agent tells you the result."
    ]
   ],
   "rules": [
    [
     "You decide",
     "Nothing that costs money or changes your trip happens without your yes."
    ],
    [
     "You’ll know",
     "When a person helped, CJ Agent tells you what they did."
    ],
    [
     "Need to know",
     "Teammates see a case number and the few details the job needs, never your account."
    ]
   ],
   "placesTitle": "Where are you headed?",
   "placesLede": "Beijing to Kashgar, dim sum to hotpot. Ask about any of them in English or Chinese.",
   "privTitle": "Your details stay yours.",
   "eaTitle": "Apply for early access",
   "eaLede": "We’re inviting travellers in small groups, starting on iPhone. Tell us a little about your trip and we’ll email you when there’s a place for you.",
   "f": {
    "name": "Name",
    "email": "Email",
    "source": "How did you hear about G2C?",
    "sourcePh": "Choose one",
    "country": "Country or region",
    "optional": "optional",
    "when": "When will you visit China?",
    "dest": "Where would you like to go?",
    "other": "Somewhere else",
    "otherPh": "City or region",
    "needs": "What would help you most?",
    "note": "Anything else?"
   },
   "sending": "Sending…",
   "ok": "Thanks, you’re on the list. We’ll email you when your invitation is ready.",
   "bad": "Please add your name, a valid email and how you heard about G2C.",
   "fail": "We couldn’t send your application just now. Please try again in a minute, or email hello@go2china.space.",
   "failAlt": "You can also use the backup form.",
   "opt": {
    "source": [
     "Friend or family",
     "Search engine",
     "Instagram",
     "TikTok",
     "YouTube",
     "Xiaohongshu (RED)",
     "Reddit",
     "Event",
     "Other"
    ],
    "when": [
     "Within 3 months",
     "In 3–6 months",
     "In 6–12 months",
     "Not sure yet",
     "Already in China"
    ],
    "dest": [
     "Beijing",
     "Shanghai",
     "Xi’an",
     "Chengdu",
     "Guangzhou & Shenzhen",
     "Not sure yet"
    ],
    "needs": [
     "Payments",
     "Getting around",
     "Trip planning",
     "Booking",
     "Food",
     "Language",
     "Visa & entry"
    ]
   },
   "credits": "Photo credits",
   "online": "Your personal agent",
   "inputHint": "Ask anything about your trip…",
   "suggest": [
    "Paying in China",
    "3 days in Beijing",
    "Book a class"
   ],
   "chat": [
    {
     "t": "hello",
     "text": "Hi! I'm CJ, your personal agent for China. Ask me anything."
    },
    {
     "t": "user",
     "q": 0,
     "draft": "Do I need cash in Chi",
     "text": "How do I pay for things without cash?"
    },
    {
     "t": "bot",
     "text": "Most places use Alipay or WeChat Pay, and both accept foreign Visa and Mastercard. Set one up before you fly and I'll walk you through it.",
     "src": "Source: official Alipay & WeChat Pay guides"
    },
    {
     "t": "user",
     "q": 1,
     "draft": "Plan 3 days in Shang",
     "text": "Landing in Beijing on Friday for 3 days. Love food, hate crowds."
    },
    {
     "t": "bot",
     "text": "Lovely. I'll remember that for this trip and the next."
    },
    {
     "t": "mem",
     "text": "Remembered · loves food · avoids crowds"
    },
    {
     "t": "plan",
     "title": "3 days in Beijing",
     "tag": "DRAFT",
     "rows": [
      [
       "Fri",
       "Hutong breakfast walk, out before the tour buses"
      ],
      [
       "Sat",
       "Great Wall at Mutianyu, the quieter stretch"
      ],
      [
       "Sun",
       "Temple of Heaven at opening, then a dumpling class"
      ]
     ],
     "foot": "Sources: official opening hours · transit times"
    },
    {
     "t": "user",
     "q": 2,
     "text": "Book the dumpling class for two. Passport ",
     "secret": "E12345678",
     "ph": "<PASSPORT_1>"
    },
    {
     "t": "shield",
     "text": "Redacted before any model sees it"
    },
    {
     "t": "ask",
     "text": "Sunday 10:00, about ¥300 for two. Shall I go ahead?",
     "yes": "Confirm",
     "no": "Not now"
    },
    {
     "t": "sys",
     "text": "<b>JT Agent</b> · a teammate is confirming with the venue",
     "done": "<b>Confirmed</b> · Sun 10:00 is on your trip"
    }
   ],
   "redact": [
    [
     "Hi, I'm ",
     null
    ],
    [
     "Emma Clarke",
     "<NAME_1>"
    ],
    [
     ". Passport ",
     null
    ],
    [
     "E12345678",
     "<PASSPORT_1>"
    ],
    [
     ", call me on ",
     null
    ],
    [
     "+44 7700 900123",
     "<PHONE_1>"
    ],
    [
     ". I'm at ",
     null
    ],
    [
     "Gate 3, Hotel Lotus",
     "<LOCATION_1>"
    ],
    [
     ".",
     null
    ]
   ],
   "privLede": "Names, passport numbers, phone numbers, emails and exact locations are swapped for placeholders on our side before any model reads them.",
   "priv1": "Teammates see masked cases under a random case ID, never your account.",
   "priv2": "Revealing a field is limited to what the task needs, time-boxed and logged.",
   "priv3": "Your memory is yours: see it, correct it, delete it whenever you like.",
   "you": "You",
   "modelSees": "What the model sees",
   "footTag": "Your personal agent for China.",
   "companyName": "Guangzhou Chuangjing Technology Co., Ltd",
   "companyAddress": "Room 410, Tower A, R&F Yingtai Plaza, No. 100 Huangpu Avenue, Tianhe District, Guangzhou, China"
  },
  "zh": {
   "nav": {
    "how": "运作方式",
    "places": "目的地",
    "privacy": "隐私"
   },
   "heroTitle": "在中国的每一天，都有你的私人助理。",
   "heroLede": "出行、支付、吃饭、预订，有问题就问 CJ Agent。需要打电话或到当地核实时，JT Agent 会请真人来处理。",
   "heroNote": "首先登陆 iPhone，正在分批邀请旅行者体验。",
   "howTitle": "CJ Agent 和 JT Agent 如何配合",
   "howLede": "CJ Agent 负责和你对话。JT Agent 在后台工作：留意你的行程，出了状况就建立工单，把 AI 办不了的步骤交给团队成员。",
   "cjRole": "在对话里",
   "jtRole": "在后台",
   "cjList": [
    "回答支付、交通、餐饮和门票问题，并附上可以核对的来源。",
    "根据它记住的你来安排每天的行程，已确认的安排不会被打乱。",
    "准备好预订和改动，付款或调整前一定先等你同意。",
    "需要给别人看时，用中文显示短句和预订信息。",
    "同一段对话里，中英文随时切换。"
   ],
   "jtList": [
    "跟进你的预订、火车、航班和入住。",
    "发现出了问题，或同一个问题反复没解决。",
    "建立工单，只带下一步需要的信息。",
    "把电话和当地核实交给团队成员，并跟进到底。",
    "结果通过 CJ Agent 告诉你，一切都在同一个对话里。"
   ],
   "scTitle": "旅途中的真实场景",
   "tabs": [
    "酒店查不到你的预订",
    "你的火车停运了",
    "你需要紧急帮助"
   ],
   "laneChat": "你的对话",
   "laneBack": "后台",
   "who": {
    "you": "你",
    "cj": "CJ Agent",
    "jt": "JT Agent",
    "mate": "团队成员"
   },
   "scenes": {
    "hotel": {
     "steps": [
      "前台说查不到我的预订。",
      "把这张卡片给前台看。我也请团队成员给酒店打电话了。",
      "入住时查不到预订，按行程中断处理。",
      "建立工单，只包含酒店名、预订号和日期；护照和账号信息不在其中。",
      "用中文致电前台，预订登记在 CLARKE EMMA 名下。",
      "搞定了：预订登记在“CLARKE EMMA”名下，房间已经准备好。团队成员刚才打电话向酒店确认过。"
     ],
     "note": "如果没有房间，CJ Agent 会给你看附近的选择和价格，等你选好再预订。"
    },
    "train": {
     "steps": [
      "状态检查：14:05 开往西安的火车停运。",
      "检查受影响的安排：今晚的酒店入住、明天 9:00 的门票。",
      "你 14:05 去西安的火车停运了。15:20 那班 19:58 到，今晚的酒店和明天的门票都不受影响。要订吗？",
      "好，订 15:20 那班。",
      "已改签车票，并告诉酒店你大约 20:30 到。",
      "好了，新车票和更新后的安排都在你的行程里。"
     ],
     "note": "在你同意之前，没有付款，也没有任何改动。"
    },
    "sos": {
     "steps": [
      "我在楼梯上摔倒了，脚踝站不起来。",
      "如果情况严重，请马上拨打 120 叫救护车。把这段话给司机或身边的人看：",
      "安全信号：紧急步骤立即发出，不等工单。",
      "已通知值班团队成员，通过消息协助。",
      "团队成员会在这里继续跟进。最近有英语服务的医院在 2 公里外。"
     ],
     "note": "紧急协助向所有用户开放，提供指引和消息协助。遇到危险，请直接拨打 110（报警）、120（急救）或 119（火警）。"
    }
   },
   "watchTitle": "JT Agent 留意哪些情况",
   "cols": [
    "情况",
    "例如",
    "怎么处理"
   ],
   "watch": [
    [
     "人身安全",
     "受伤、突发疾病、走失。",
     "立即给出紧急电话和中文短句，再由团队成员通过消息协助。"
    ],
    [
     "证件与资金",
     "护照丢失、银行卡被冻结、付款失败。",
     "先给出报失和补办步骤，再由团队成员核实细节。"
    ],
    [
     "行程中断",
     "航班变动、酒店查不到预订、景点临时关闭。",
     "先弄清还影响哪些安排，再给出解决办法。"
    ],
    [
     "你提出的改动",
     "换酒店、调整某一天、加一个城市。",
     "CJ Agent 起草方案，你确认之前什么都不会变。"
    ],
    [
     "AI 卡住时",
     "同一个问题一直没解决、工具反复出错。",
     "团队成员在后台处理，CJ Agent 告诉你结果。"
    ]
   ],
   "rules": [
    [
     "由你决定",
     "花钱或改变行程的事，都要先得到你的同意。"
    ],
    [
     "让你知道",
     "如果有真人帮忙，CJ Agent 会告诉你他们做了什么。"
    ],
    [
     "只给必要的信息",
     "团队成员只看到工单号和完成任务所需的少量信息，看不到你的账号。"
    ]
   ],
   "placesTitle": "你想去哪里？",
   "placesLede": "从北京到喀什，从早茶到火锅，用中文或英文问都可以。",
   "privTitle": "你的信息，只属于你。",
   "eaTitle": "申请抢先体验",
   "eaLede": "我们正在分批邀请旅行者，首先在 iPhone 上开放。简单介绍一下你的旅行，有名额时我们会发邮件通知你。",
   "f": {
    "name": "名字",
    "email": "邮箱",
    "source": "你是怎么知道 G2C 的？",
    "sourcePh": "请选择",
    "country": "国家或地区",
    "optional": "选填",
    "when": "什么时候来中国？",
    "dest": "想去哪里？",
    "other": "其他地方",
    "otherPh": "城市或地区",
    "needs": "最需要哪方面的帮助？",
    "note": "还有什么想说的？"
   },
   "sending": "正在提交…",
   "ok": "谢谢！你已在名单上，邀请准备好后我们会发邮件给你。",
   "bad": "请填写名字、有效的邮箱，并选择你是怎么知道 G2C 的。",
   "fail": "暂时没能提交，请稍后再试，或发邮件到 hello@go2china.space。",
   "failAlt": "也可以使用备用表单。",
   "opt": {
    "source": [
     "亲友推荐",
     "搜索引擎",
     "Instagram",
     "TikTok",
     "YouTube",
     "小红书",
     "Reddit",
     "活动",
     "其他"
    ],
    "when": [
     "3 个月内",
     "3–6 个月",
     "6–12 个月",
     "还不确定",
     "已经在中国"
    ],
    "dest": [
     "北京",
     "上海",
     "西安",
     "成都",
     "广州和深圳",
     "还不确定"
    ],
    "needs": [
     "支付",
     "交通",
     "行程规划",
     "预订",
     "美食",
     "语言",
     "签证与入境"
    ]
   },
   "credits": "图片来源",
   "online": "你的私人助理",
   "inputHint": "问问关于行程的任何事…",
   "suggest": [
    "不带现金怎么付款",
    "北京 3 日游",
    "帮我预订"
   ],
   "chat": [
    {
     "t": "hello",
     "text": "你好！我是 CJ，你在中国的私人助理，想问什么都可以。"
    },
    {
     "t": "user",
     "q": 0,
     "draft": "在中国需要带现",
     "text": "没有现金，在中国怎么付款？"
    },
    {
     "t": "bot",
     "text": "大多数地方用支付宝或微信支付，两者都支持绑定境外 Visa / Mastercard。建议出发前开通，我一步步带你设置。",
     "src": "来源：支付宝与微信支付官方指引"
    },
    {
     "t": "user",
     "q": 1,
     "draft": "帮我规划上海",
     "text": "周五落地北京，玩 3 天。爱吃，怕人多。"
    },
    {
     "t": "bot",
     "text": "好的，这次和以后的旅程我都会记住。"
    },
    {
     "t": "mem",
     "text": "已记住 · 爱美食 · 避开人流"
    },
    {
     "t": "plan",
     "title": "北京 3 日",
     "tag": "草稿",
     "rows": [
      [
       "周五",
       "胡同早餐漫步，赶在旅行团之前"
      ],
      [
       "周六",
       "慕田峪长城，走人少的那一段"
      ],
      [
       "周日",
       "天坛开门即入，再去上饺子课"
      ]
     ],
     "foot": "来源：官方开放时间 · 交通时长"
    },
    {
     "t": "user",
     "q": 2,
     "text": "帮我订两人的饺子课。护照 ",
     "secret": "E12345678",
     "ph": "<PASSPORT_1>"
    },
    {
     "t": "shield",
     "text": "已脱敏，模型看不到原文"
    },
    {
     "t": "ask",
     "text": "周日 10:00，两人约 ¥300。要我继续吗？",
     "yes": "确认",
     "no": "暂不"
    },
    {
     "t": "sys",
     "text": "<b>JT Agent</b> · 团队成员正在与商家确认",
     "done": "<b>已确认</b> · 周日 10:00 已加入行程"
    }
   ],
   "redact": [
    [
     "你好，我是",
     null
    ],
    [
     "王小明",
     "<NAME_1>"
    ],
    [
     "，护照号 ",
     null
    ],
    [
     "E12345678",
     "<PASSPORT_1>"
    ],
    [
     "，电话 ",
     null
    ],
    [
     "138 0013 8000",
     "<PHONE_1>"
    ],
    [
     "，我在",
     null
    ],
    [
     "莲花酒店 3 号门",
     "<LOCATION_1>"
    ],
    [
     "。",
     null
    ]
   ],
   "privLede": "姓名、护照号、电话、邮箱和精确位置，在任何模型读取之前就已在我们这边替换为占位符。",
   "priv1": "团队成员只看到打码的工单和随机工单号，看不到你的账号。",
   "priv2": "揭示字段仅限任务所需，有时限，并全程留痕。",
   "priv3": "记忆归你所有：随时查看、更正或删除。",
   "you": "你",
   "modelSees": "模型看到的",
   "footTag": "你在中国的私人助理。",
   "companyName": "广州创竞科技有限公司",
   "companyAddress": "广州市天河区黄埔大道100号富力盈泰广场A座410室"
  },
  "ru": {
   "nav": {
    "how": "Как это работает",
    "places": "Места",
    "privacy": "Конфиденциальность"
   },
   "heroTitle": "Личный помощник на каждый день в Китае.",
   "heroLede": "Спрашивайте CJ Agent обо всём: как передвигаться, платить, где поесть и что забронировать. Если нужен звонок или проверка на месте, JT Agent подключает живого человека.",
   "heroNote": "Сначала на iPhone. Приглашаем путешественников небольшими группами.",
   "howTitle": "Как CJ Agent и JT Agent работают вместе",
   "howLede": "С CJ Agent вы общаетесь. JT Agent работает в фоне: следит за поездкой, открывает обращение, если что-то пошло не так, и передаёт сотруднику то, с чем ИИ не справится.",
   "cjRole": "В вашем чате",
   "jtRole": "За кадром",
   "cjList": [
    "Отвечает на вопросы об оплате, транспорте, еде и билетах и даёт проверяемые источники.",
    "Планирует дни с учётом того, что помнит о вас, и сохраняет подтверждённые планы.",
    "Готовит бронирования и изменения и ждёт вашего согласия, прежде чем что-то оплатить или перенести.",
    "Показывает фразы и данные брони по-китайски, когда их нужно кому-то показать.",
    "Говорит по-английски и по-китайски в одном чате."
   ],
   "jtList": [
    "Следит за бронированиями, поездами, рейсами и заселением.",
    "Замечает, когда что-то идёт не так или вопрос ходит по кругу.",
    "Открывает обращение только с теми данными, которые нужны для следующего шага.",
    "Передаёт звонки и проверки на месте сотруднику и доводит дело до конца.",
    "Возвращает результат через CJ Agent, и всё остаётся в одном чате."
   ],
   "scTitle": "Как это выглядит в поездке",
   "tabs": [
    "Отель не может найти бронь",
    "Ваш поезд отменён",
    "Нужна срочная помощь"
   ],
   "laneChat": "В вашем чате",
   "laneBack": "За кадром",
   "who": {
    "you": "Вы",
    "cj": "CJ Agent",
    "jt": "JT Agent",
    "mate": "Сотрудник"
   },
   "scenes": {
    "hotel": {
     "steps": [
      "На ресепшене говорят, что не могут найти мою бронь.",
      "Покажите им эту карточку. Я также попросил сотрудника позвонить в отель.",
      "Бронь не найдена при заселении. Обрабатывается как сбой в поездке.",
      "Открыто обращение: название отеля, номер брони и даты. Паспорт и данные аккаунта не передаются.",
      "Позвонил на ресепшен по-китайски. Бронь оформлена на CLARKE EMMA.",
      "Готово: бронь была на имя «CLARKE EMMA». Номер ждёт вас. Сотрудник позвонил в отель и всё подтвердил."
     ],
     "note": "Если бы мест не было, CJ Agent показал бы варианты поблизости с ценами и забронировал бы только после вашего выбора."
    },
    "train": {
     "steps": [
      "Проверка статуса: поезд в 14:05 до Сианя отменён.",
      "Проверяет, что от него зависит: заселение сегодня вечером и билеты на завтра на 9:00.",
      "Ваш поезд в 14:05 до Сианя отменён. Поезд в 15:20 прибывает в 19:58, отель и завтрашние билеты сохраняются. Бронировать?",
      "Да, бронируй на 15:20.",
      "Билет переоформлен, отель предупреждён, что вы приедете около 20:30.",
      "Готово. Новый билет и обновлённый план уже в вашей поездке."
     ],
     "note": "Ничего не оплачивалось и не менялось, пока вы не согласились."
    },
    "sos": {
     "steps": [
      "Я упал на лестнице и не могу наступить на ногу.",
      "Если всё серьёзно, сразу звоните 120, это скорая помощь. Покажите это водителю или людям рядом:",
      "Сигнал безопасности. Инструкции отправлены сразу, без ожидания обращения.",
      "Дежурный сотрудник подключён для помощи в переписке.",
      "Сотрудник продолжит помогать вам здесь. Ближайшая больница с англоговорящим персоналом в 2 км."
     ],
     "note": "Экстренная помощь доступна всем пользователям: подсказки и поддержка в переписке. При опасности всегда звоните 110 (полиция), 120 (скорая) или 119 (пожарные)."
    }
   },
   "watchTitle": "За чем следит JT Agent",
   "cols": [
    "Ситуация",
    "Например",
    "Что происходит"
   ],
   "watch": [
    [
     "Ваша безопасность",
     "Травма, внезапная болезнь, вы потерялись.",
     "Сразу номера экстренных служб и фразы по-китайски, затем сотрудник помогает в переписке."
    ],
    [
     "Документы и деньги",
     "Потерянный паспорт, заблокированная карта, платёж не проходит.",
     "Сначала шаги по заявлению и восстановлению, затем сотрудник проверяет детали."
    ],
    [
     "Сбои в поездке",
     "Изменённый рейс, отель не находит бронь, закрытая достопримечательность.",
     "Выясняет, что ещё затронуто, и предлагает решение."
    ],
    [
     "Изменения по вашей просьбе",
     "Сменить отель, перенести день, добавить город.",
     "CJ Agent готовит варианты. Ничего не меняется без вашего подтверждения."
    ],
    [
     "Когда ИИ застрял",
     "Вопрос остаётся без ответа, инструмент раз за разом даёт сбой.",
     "Сотрудник решает вопрос в фоне, а CJ Agent сообщает результат."
    ]
   ],
   "rules": [
    [
     "Решаете вы",
     "Ничего, что стоит денег или меняет поездку, не происходит без вашего «да»."
    ],
    [
     "Вы в курсе",
     "Если помогал человек, CJ Agent расскажет, что он сделал."
    ],
    [
     "Только нужное",
     "Сотрудник видит номер обращения и несколько нужных для дела данных, но не ваш аккаунт."
    ]
   ],
   "placesTitle": "Куда вы едете?",
   "placesLede": "От Пекина до Кашгара, от димсамов до хого. Спрашивайте о любом месте по-английски или по-китайски.",
   "privTitle": "Ваши данные остаются вашими.",
   "eaTitle": "Заявка на ранний доступ",
   "eaLede": "Мы приглашаем путешественников небольшими группами, начиная с iPhone. Расскажите немного о поездке, и мы напишем, когда для вас появится место.",
   "f": {
    "name": "Имя",
    "email": "Эл. почта",
    "source": "Откуда вы узнали о G2C?",
    "sourcePh": "Выберите",
    "country": "Страна или регион",
    "optional": "необязательно",
    "when": "Когда вы поедете в Китай?",
    "dest": "Куда хотите поехать?",
    "other": "Другое место",
    "otherPh": "Город или регион",
    "needs": "Что поможет вам больше всего?",
    "note": "Что-нибудь ещё?"
   },
   "sending": "Отправляем…",
   "ok": "Спасибо, вы в списке. Мы напишем, когда приглашение будет готово.",
   "bad": "Укажите имя, корректную почту и откуда вы узнали о G2C.",
   "fail": "Не удалось отправить заявку. Попробуйте через минуту или напишите на hello@go2china.space.",
   "failAlt": "Можно также воспользоваться запасной формой.",
   "opt": {
    "source": [
     "Друзья или семья",
     "Поиск",
     "Instagram",
     "TikTok",
     "YouTube",
     "Xiaohongshu (RED)",
     "Reddit",
     "Мероприятие",
     "Другое"
    ],
    "when": [
     "В ближайшие 3 месяца",
     "Через 3–6 месяцев",
     "Через 6–12 месяцев",
     "Пока не знаю",
     "Уже в Китае"
    ],
    "dest": [
     "Пекин",
     "Шанхай",
     "Сиань",
     "Чэнду",
     "Гуанчжоу и Шэньчжэнь",
     "Пока не знаю"
    ],
    "needs": [
     "Оплата",
     "Транспорт",
     "Планирование поездки",
     "Бронирование",
     "Еда",
     "Язык",
     "Виза и въезд"
    ]
   },
   "credits": "Авторы фотографий",
   "online": "Ваш личный помощник",
   "inputHint": "Спросите о поездке…",
   "suggest": [
    "Оплата в Китае",
    "3 дня в Пекине",
    "Забронировать занятие"
   ],
   "chat": [
    {
     "t": "hello",
     "text": "Привет! Я CJ, ваш личный помощник в Китае. Спрашивайте!"
    },
    {
     "t": "user",
     "q": 0,
     "draft": "Нужны ли наличные",
     "text": "Как платить без наличных?"
    },
    {
     "t": "bot",
     "text": "Чаще всего используют Alipay и WeChat Pay. Можно привязать иностранную Visa или Mastercard. Лучше настроить всё до вылета — помогу по шагам.",
     "src": "Источник: официальные инструкции Alipay и WeChat Pay"
    },
    {
     "t": "user",
     "q": 1,
     "draft": "План на три дня",
     "text": "Прилетаю в Пекин в пятницу на 3 дня. Люблю вкусно поесть, не люблю толпы."
    },
    {
     "t": "bot",
     "text": "Запомню это для этой и следующих поездок."
    },
    {
     "t": "mem",
     "text": "Сохранено · любит еду · избегает толп"
    },
    {
     "t": "plan",
     "title": "3 дня в Пекине",
     "tag": "ЧЕРНОВИК",
     "rows": [
      [
       "Пт",
       "Завтрак в хутунах до приезда групп"
      ],
      [
       "Сб",
       "Великая стена в Мутяньюй — тихий участок"
      ],
      [
       "Вс",
       "Храм Неба к открытию, затем урок пельменей"
      ]
     ],
     "foot": "Источники: часы работы · время в пути"
    },
    {
     "t": "user",
     "q": 2,
     "text": "Забронируй урок на двоих. Паспорт ",
     "secret": "E12345678",
     "ph": "<PASSPORT_1>"
    },
    {
     "t": "shield",
     "text": "Личные данные скрыты до передачи модели"
    },
    {
     "t": "ask",
     "text": "Воскресенье, 10:00, около ¥300 за двоих. Продолжить?",
     "yes": "Подтвердить",
     "no": "Не сейчас"
    },
    {
     "t": "sys",
     "text": "<b>JT Agent</b> · сотрудник уточняет бронь",
     "done": "<b>Подтверждено</b> · воскресенье, 10:00 добавлено в план"
    }
   ],
   "redact": [
    [
     "Здравствуйте, я ",
     null
    ],
    [
     "Анна Иванова",
     "<NAME_1>"
    ],
    [
     ". Паспорт ",
     null
    ],
    [
     "E12345678",
     "<PASSPORT_1>"
    ],
    [
     ", телефон ",
     null
    ],
    [
     "+44 7700 900123",
     "<PHONE_1>"
    ],
    [
     ". Я у ",
     null
    ],
    [
     "входа 3 отеля «Лотос»",
     "<LOCATION_1>"
    ],
    [
     ".",
     null
    ]
   ],
   "privLede": "Имена, номера паспортов, телефоны, почта и точные адреса заменяются метками до передачи модели.",
   "priv1": "Сотрудники видят обезличенное обращение со случайным номером, а не ваш аккаунт.",
   "priv2": "Данные раскрываются лишь по необходимости, на ограниченное время и с записью доступа.",
   "priv3": "Вы можете просматривать, исправлять и удалять сохранённые сведения.",
   "you": "Вы",
   "modelSees": "Что видит модель",
   "footTag": "Ваш личный помощник в Китае.",
   "companyName": "Guangzhou Chuangjing Technology Co., Ltd",
   "companyAddress": "Room 410, Tower A, R&F Yingtai Plaza, No. 100 Huangpu Avenue, Tianhe District, Guangzhou, China"
  },
  "es": {
   "nav": {
    "how": "Cómo funciona",
    "places": "Destinos",
    "privacy": "Privacidad"
   },
   "heroTitle": "Tu asistente para cada día en China.",
   "heroLede": "Pregunta a CJ Agent cómo moverte, pagar, comer y reservar. Si un problema requiere una llamada o una comprobación en el lugar, JT Agent recurre a una persona real.",
   "heroNote": "Primero en iPhone. Estamos invitando a viajeros en pequeños grupos.",
   "howTitle": "Cómo trabajan juntos CJ Agent y JT Agent",
   "howLede": "CJ Agent es con quien hablas. JT Agent trabaja en segundo plano: sigue tu viaje, abre un caso cuando algo falla y pasa a una persona del equipo lo que la IA no puede resolver.",
   "cjRole": "En tu chat",
   "jtRole": "En segundo plano",
   "cjList": [
    "Responde sobre pagos, transporte, comida y entradas, con fuentes que puedes comprobar.",
    "Planifica tus días según lo que recuerda de ti y respeta lo que ya confirmaste.",
    "Prepara reservas y cambios, y espera tu sí antes de pagar o mover nada.",
    "Te muestra frases y datos de la reserva en chino cuando tienes que enseñárselos a alguien.",
    "Habla en inglés y en chino dentro de la misma conversación."
   ],
   "jtList": [
    "Sigue tus reservas, trenes, vuelos y llegadas al hotel.",
    "Detecta cuando algo sale mal o una pregunta da vueltas sin resolverse.",
    "Abre un caso solo con los datos que necesita el siguiente paso.",
    "Pasa las llamadas y comprobaciones locales a una persona del equipo y las sigue hasta el final.",
    "Te devuelve el resultado a través de CJ Agent, todo en el mismo chat."
   ],
   "scTitle": "Así se ve durante el viaje",
   "tabs": [
    "El hotel no encuentra tu reserva",
    "Han cancelado tu tren",
    "Necesitas ayuda urgente"
   ],
   "laneChat": "En tu chat",
   "laneBack": "En segundo plano",
   "who": {
    "you": "Tú",
    "cj": "CJ Agent",
    "jt": "JT Agent",
    "mate": "Equipo"
   },
   "scenes": {
    "hotel": {
     "steps": [
      "En recepción dicen que no encuentran mi reserva.",
      "Enséñales esta tarjeta. También he pedido a una persona del equipo que llame al hotel.",
      "Reserva no encontrada al llegar. Se trata como una incidencia del viaje.",
      "Caso abierto con el nombre del hotel, el número de reserva y las fechas. El pasaporte y los datos de la cuenta quedan fuera.",
      "Llamada a recepción en chino. La reserva estaba a nombre de CLARKE EMMA.",
      "Resuelto: la reserva estaba como «CLARKE EMMA». Tu habitación está lista. Una persona del equipo llamó al hotel para confirmarlo."
     ],
     "note": "Si no hubiera habitación, CJ Agent te mostraría opciones cercanas con precios y solo reservaría cuando eligieras."
    },
    "train": {
     "steps": [
      "Comprobación de estado: el tren de las 14:05 a Xi’an está cancelado.",
      "Revisa lo que depende de él: la llegada al hotel esta noche y las entradas de mañana a las 9:00.",
      "Han cancelado tu tren de las 14:05 a Xi’an. El de las 15:20 llega a las 19:58 y mantiene el hotel de esta noche y las entradas de mañana. ¿Lo reservo?",
      "Sí, reserva el de las 15:20.",
      "Billete cambiado y aviso al hotel de que llegarás sobre las 20:30.",
      "Listo. Tu nuevo billete y el plan actualizado ya están en tu viaje."
     ],
     "note": "No se pagó ni cambió nada hasta que dijiste que sí."
    },
    "sos": {
     "steps": [
      "Me he caído en las escaleras y no puedo apoyar el tobillo.",
      "Si es grave, llama ya al 120 para pedir una ambulancia. Enseña esto al conductor o a quien tengas cerca:",
      "Señal de seguridad. Los pasos de emergencia se enviaron al momento, sin esperar a abrir un caso.",
      "Aviso a la persona de guardia para ayudar por mensaje.",
      "Una persona del equipo seguirá ayudándote aquí. El hospital más cercano con personal que habla inglés está a 2 km."
     ],
     "note": "La ayuda de emergencia está abierta a todos los usuarios: orientación y apoyo por mensaje. Ante un peligro, llama siempre al 110 (policía), 120 (ambulancia) o 119 (bomberos)."
    }
   },
   "watchTitle": "Qué vigila JT Agent",
   "cols": [
    "Situación",
    "Por ejemplo",
    "Qué pasa"
   ],
   "watch": [
    [
     "Tu seguridad",
     "Una lesión, una enfermedad repentina, perderte.",
     "Números de emergencia y frases en chino al momento; después, una persona del equipo te ayuda por mensaje."
    ],
    [
     "Documentos y dinero",
     "Un pasaporte perdido, una tarjeta bloqueada, un pago que no pasa.",
     "Primero, los pasos para denunciar y reponer; después, el equipo comprueba los detalles."
    ],
    [
     "Imprevistos",
     "Un vuelo cambiado, un hotel que no encuentra tu reserva, una atracción cerrada.",
     "Averigua qué más se ve afectado y propone una solución."
    ],
    [
     "Cambios que pides",
     "Cambiar de hotel, mover un día, añadir una ciudad.",
     "CJ Agent prepara opciones. Nada cambia hasta que lo confirmas."
    ],
    [
     "Cuando la IA se atasca",
     "Una pregunta que sigue sin respuesta, una herramienta que falla una y otra vez.",
     "Una persona del equipo lo resuelve en segundo plano y CJ Agent te cuenta el resultado."
    ]
   ],
   "rules": [
    [
     "Tú decides",
     "Nada que cueste dinero o cambie tu viaje ocurre sin tu sí."
    ],
    [
     "Lo sabrás",
     "Si te ha ayudado una persona, CJ Agent te dice qué hizo."
    ],
    [
     "Solo lo necesario",
     "El equipo ve un número de caso y los pocos datos que requiere la tarea, nunca tu cuenta."
    ]
   ],
   "placesTitle": "¿Adónde vas?",
   "placesLede": "De Pekín a Kashgar, del dim sum al hot pot. Pregunta por cualquiera en inglés o en chino.",
   "privTitle": "Tus datos siguen siendo tuyos.",
   "eaTitle": "Solicita acceso anticipado",
   "eaLede": "Invitamos a viajeros en pequeños grupos, empezando por iPhone. Cuéntanos un poco sobre tu viaje y te escribiremos cuando haya una plaza para ti.",
   "f": {
    "name": "Nombre",
    "email": "Correo electrónico",
    "source": "¿Cómo conociste G2C?",
    "sourcePh": "Elige una opción",
    "country": "País o región",
    "optional": "opcional",
    "when": "¿Cuándo visitarás China?",
    "dest": "¿Adónde te gustaría ir?",
    "other": "Otro lugar",
    "otherPh": "Ciudad o región",
    "needs": "¿Qué te ayudaría más?",
    "note": "¿Algo más?"
   },
   "sending": "Enviando…",
   "ok": "¡Gracias! Ya estás en la lista. Te escribiremos cuando tu invitación esté lista.",
   "bad": "Indica tu nombre, un correo válido y cómo conociste G2C.",
   "fail": "No hemos podido enviar tu solicitud. Inténtalo de nuevo en un minuto o escribe a hello@go2china.space.",
   "failAlt": "También puedes usar el formulario alternativo.",
   "opt": {
    "source": [
     "Amigos o familia",
     "Buscador",
     "Instagram",
     "TikTok",
     "YouTube",
     "Xiaohongshu (RED)",
     "Reddit",
     "Evento",
     "Otro"
    ],
    "when": [
     "En los próximos 3 meses",
     "En 3–6 meses",
     "En 6–12 meses",
     "Aún no lo sé",
     "Ya estoy en China"
    ],
    "dest": [
     "Pekín",
     "Shanghái",
     "Xi’an",
     "Chengdu",
     "Cantón y Shenzhen",
     "Aún no lo sé"
    ],
    "needs": [
     "Pagos",
     "Transporte",
     "Planificar el viaje",
     "Reservas",
     "Comida",
     "Idioma",
     "Visado y entrada"
    ]
   },
   "credits": "Créditos de las fotos",
   "online": "Tu asistente personal",
   "inputHint": "Pregunta sobre tu viaje…",
   "suggest": [
    "Pagar en China",
    "3 días en Pekín",
    "Reservar una clase"
   ],
   "chat": [
    {
     "t": "hello",
     "text": "¡Hola! Soy CJ, tu asistente personal para China. ¿En qué te ayudo?"
    },
    {
     "t": "user",
     "q": 0,
     "draft": "¿Necesito efectivo",
     "text": "¿Cómo puedo pagar sin efectivo?"
    },
    {
     "t": "bot",
     "text": "Lo habitual es usar Alipay o WeChat Pay. Ambos permiten vincular Visa y Mastercard extranjeras. Conviene configurarlos antes de volar; te guío paso a paso.",
     "src": "Fuente: guías oficiales de Alipay y WeChat Pay"
    },
    {
     "t": "user",
     "q": 1,
     "draft": "Organiza tres días",
     "text": "Llego a Pekín el viernes para 3 días. Me encanta comer y evito las multitudes."
    },
    {
     "t": "bot",
     "text": "Lo recordaré para este viaje y los siguientes."
    },
    {
     "t": "mem",
     "text": "Guardado · le gusta comer · evita multitudes"
    },
    {
     "t": "plan",
     "title": "3 días en Pekín",
     "tag": "BORRADOR",
     "rows": [
      [
       "Vie",
       "Desayuno por los hutong antes de los grupos"
      ],
      [
       "Sáb",
       "Gran Muralla en Mutianyu, por el tramo tranquilo"
      ],
      [
       "Dom",
       "Templo del Cielo al abrir y clase de jiaozi"
      ]
     ],
     "foot": "Fuentes: horarios oficiales · tiempos de traslado"
    },
    {
     "t": "user",
     "q": 2,
     "text": "Reserva la clase para dos. Pasaporte ",
     "secret": "E12345678",
     "ph": "<PASSPORT_1>"
    },
    {
     "t": "shield",
     "text": "Datos ocultos antes de llegar al modelo"
    },
    {
     "t": "ask",
     "text": "Domingo a las 10:00, unos ¥300 para dos. ¿Sigo?",
     "yes": "Confirmar",
     "no": "Ahora no"
    },
    {
     "t": "sys",
     "text": "<b>JT Agent</b> · el equipo confirma con el local",
     "done": "<b>Confirmado</b> · domingo a las 10:00 añadido al viaje"
    }
   ],
   "redact": [
    [
     "Hola, soy ",
     null
    ],
    [
     "Ana García",
     "<NAME_1>"
    ],
    [
     ". Pasaporte ",
     null
    ],
    [
     "E12345678",
     "<PASSPORT_1>"
    ],
    [
     ", teléfono ",
     null
    ],
    [
     "+44 7700 900123",
     "<PHONE_1>"
    ],
    [
     ". Estoy en ",
     null
    ],
    [
     "la puerta 3 del Hotel Lotus",
     "<LOCATION_1>"
    ],
    [
     ".",
     null
    ]
   ],
   "privLede": "Nombres, pasaportes, teléfonos, correos y ubicaciones precisas se sustituyen por etiquetas antes de que el modelo los lea.",
   "priv1": "El equipo ve casos anonimizados con un número aleatorio, no tu cuenta.",
   "priv2": "Los datos solo se revelan cuando son necesarios, por tiempo limitado y con registro de acceso.",
   "priv3": "Puedes consultar, corregir o borrar lo que se recuerda de ti.",
   "you": "Tú",
   "modelSees": "Lo que ve el modelo",
   "footTag": "Tu asistente personal para China.",
   "companyName": "Guangzhou Chuangjing Technology Co., Ltd",
   "companyAddress": "Room 410, Tower A, R&F Yingtai Plaza, No. 100 Huangpu Avenue, Tianhe District, Guangzhou, China"
  },
  "fr": {
   "nav": {
    "how": "Fonctionnement",
    "places": "Destinations",
    "privacy": "Confidentialité"
   },
   "heroTitle": "Votre assistant pour chaque jour en Chine.",
   "heroLede": "Demandez à CJ Agent comment vous déplacer, payer, manger et réserver. Quand un problème demande un appel ou une vérification sur place, JT Agent fait intervenir une vraie personne.",
   "heroNote": "D’abord sur iPhone. Nous invitons les voyageurs par petits groupes.",
   "howTitle": "Comment CJ Agent et JT Agent travaillent ensemble",
   "howLede": "CJ Agent est celui à qui vous parlez. JT Agent travaille en coulisses : il suit votre voyage, ouvre un dossier quand quelque chose se passe mal et confie à un membre de l’équipe ce que l’IA ne peut pas terminer.",
   "cjRole": "Dans votre conversation",
   "jtRole": "En coulisses",
   "cjList": [
    "Répond sur les paiements, les transports, la cuisine et les billets, avec des sources vérifiables.",
    "Organise vos journées selon ce qu’il sait de vous et garde intact ce qui est confirmé.",
    "Prépare réservations et modifications, et attend votre accord avant de payer ou de déplacer quoi que ce soit.",
    "Affiche des phrases et les détails de réservation en chinois quand vous devez les montrer.",
    "Parle anglais et chinois dans la même conversation."
   ],
   "jtList": [
    "Suit vos réservations, trains, vols et arrivées à l’hôtel.",
    "Remarque quand quelque chose tourne mal ou qu’une question tourne en rond.",
    "Ouvre un dossier avec les seules informations utiles à l’étape suivante.",
    "Confie appels et vérifications sur place à un membre de l’équipe et suit l’affaire jusqu’au bout.",
    "Vous transmet le résultat via CJ Agent, dans la même conversation."
   ],
   "scTitle": "En voyage, concrètement",
   "tabs": [
    "L’hôtel ne trouve pas votre réservation",
    "Votre train est annulé",
    "Vous avez besoin d’aide, vite"
   ],
   "laneChat": "Dans votre conversation",
   "laneBack": "En coulisses",
   "who": {
    "you": "Vous",
    "cj": "CJ Agent",
    "jt": "JT Agent",
    "mate": "Équipe"
   },
   "scenes": {
    "hotel": {
     "steps": [
      "La réception dit qu’elle ne trouve pas ma réservation.",
      "Montrez-leur cette carte. J’ai aussi demandé à un membre de l’équipe d’appeler l’hôtel.",
      "Réservation introuvable à l’arrivée. Traitée comme une perturbation du voyage.",
      "Dossier ouvert avec le nom de l’hôtel, le numéro de réservation et les dates. Passeport et compte restent hors du dossier.",
      "Appel à la réception en chinois. La réservation était au nom de CLARKE EMMA.",
      "C’est réglé : la réservation était au nom de « CLARKE EMMA ». Votre chambre est prête. Un membre de l’équipe a appelé l’hôtel pour confirmer."
     ],
     "note": "S’il n’y avait plus de chambre, CJ Agent vous montrerait des options à proximité avec leurs prix et ne réserverait qu’après votre choix."
    },
    "train": {
     "steps": [
      "Vérification : le train de 14 h 05 pour Xi’an est annulé.",
      "Regarde ce qui en dépend : l’arrivée à l’hôtel ce soir et les billets de demain à 9 h.",
      "Votre train de 14 h 05 pour Xi’an est annulé. Celui de 15 h 20 arrive à 19 h 58 et conserve l’hôtel de ce soir et les billets de demain. Je le réserve ?",
      "Oui, réserve celui de 15 h 20.",
      "Billet échangé et hôtel prévenu de votre arrivée vers 20 h 30.",
      "C’est fait. Votre nouveau billet et le programme mis à jour sont dans votre voyage."
     ],
     "note": "Rien n’a été payé ni modifié avant votre accord."
    },
    "sos": {
     "steps": [
      "Je suis tombé dans l’escalier et je ne peux plus poser le pied.",
      "Si c’est grave, appelez tout de suite le 120 pour une ambulance. Montrez ceci au chauffeur ou aux personnes autour de vous :",
      "Signal de sécurité. Les consignes d’urgence sont parties aussitôt, sans attendre l’ouverture d’un dossier.",
      "Membre de l’équipe de garde prévenu pour aider par message.",
      "Un membre de l’équipe continue de vous aider ici. L’hôpital le plus proche avec du personnel anglophone est à 2 km."
     ],
     "note": "L’aide d’urgence est ouverte à tous les utilisateurs : conseils et soutien par message. En cas de danger, appelez toujours le 110 (police), le 120 (ambulance) ou le 119 (pompiers)."
    }
   },
   "watchTitle": "Ce que surveille JT Agent",
   "cols": [
    "Situation",
    "Par exemple",
    "Ce qui se passe"
   ],
   "watch": [
    [
     "Votre sécurité",
     "Une blessure, un malaise soudain, vous êtes perdu.",
     "Numéros d’urgence et phrases en chinois tout de suite, puis un membre de l’équipe aide par message."
    ],
    [
     "Papiers et argent",
     "Un passeport perdu, une carte bloquée, un paiement refusé.",
     "D’abord les démarches de déclaration et de remplacement, puis l’équipe vérifie les détails."
    ],
    [
     "Imprévus",
     "Un vol modifié, un hôtel qui ne trouve pas votre réservation, un site fermé.",
     "Identifie ce qui est touché par ricochet, puis propose une solution."
    ],
    [
     "Changements demandés",
     "Changer d’hôtel, déplacer une journée, ajouter une ville.",
     "CJ Agent prépare des options. Rien ne change sans votre confirmation."
    ],
    [
     "Quand l’IA bloque",
     "Une question qui reste sans réponse, un outil qui échoue encore et encore.",
     "Un membre de l’équipe règle le problème en coulisses et CJ Agent vous donne le résultat."
    ]
   ],
   "rules": [
    [
     "Vous décidez",
     "Rien qui coûte de l’argent ou modifie votre voyage ne se fait sans votre accord."
    ],
    [
     "Vous êtes informé",
     "Quand une personne a aidé, CJ Agent vous dit ce qu’elle a fait."
    ],
    [
     "Le strict nécessaire",
     "L’équipe voit un numéro de dossier et les quelques informations utiles, jamais votre compte."
    ]
   ],
   "placesTitle": "Où allez-vous ?",
   "placesLede": "De Pékin à Kachgar, des dim sum à la fondue chinoise. Posez vos questions en anglais ou en chinois.",
   "privTitle": "Vos données restent les vôtres.",
   "eaTitle": "Demander un accès anticipé",
   "eaLede": "Nous invitons les voyageurs par petits groupes, d’abord sur iPhone. Parlez-nous un peu de votre voyage : nous vous écrirons quand une place sera disponible.",
   "f": {
    "name": "Nom",
    "email": "E-mail",
    "source": "Comment avez-vous connu G2C ?",
    "sourcePh": "Choisissez",
    "country": "Pays ou région",
    "optional": "facultatif",
    "when": "Quand venez-vous en Chine ?",
    "dest": "Où aimeriez-vous aller ?",
    "other": "Ailleurs",
    "otherPh": "Ville ou région",
    "needs": "Qu’est-ce qui vous aiderait le plus ?",
    "note": "Autre chose ?"
   },
   "sending": "Envoi…",
   "ok": "Merci, vous êtes sur la liste. Nous vous écrirons quand votre invitation sera prête.",
   "bad": "Indiquez votre nom, un e-mail valide et comment vous avez connu G2C.",
   "fail": "Votre demande n’a pas pu être envoyée. Réessayez dans une minute ou écrivez à hello@go2china.space.",
   "failAlt": "Vous pouvez aussi utiliser le formulaire de secours.",
   "opt": {
    "source": [
     "Amis ou famille",
     "Moteur de recherche",
     "Instagram",
     "TikTok",
     "YouTube",
     "Xiaohongshu (RED)",
     "Reddit",
     "Événement",
     "Autre"
    ],
    "when": [
     "D’ici 3 mois",
     "Dans 3 à 6 mois",
     "Dans 6 à 12 mois",
     "Je ne sais pas encore",
     "Déjà en Chine"
    ],
    "dest": [
     "Pékin",
     "Shanghai",
     "Xi’an",
     "Chengdu",
     "Canton et Shenzhen",
     "Je ne sais pas encore"
    ],
    "needs": [
     "Paiements",
     "Transports",
     "Organisation du voyage",
     "Réservations",
     "Cuisine",
     "Langue",
     "Visa et entrée"
    ]
   },
   "credits": "Crédits photo",
   "online": "Votre assistant personnel",
   "inputHint": "Posez une question sur votre voyage…",
   "suggest": [
    "Payer en Chine",
    "3 jours à Pékin",
    "Réserver un cours"
   ],
   "chat": [
    {
     "t": "hello",
     "text": "Bonjour ! Je suis CJ, votre assistant pour la Chine. Posez-moi vos questions."
    },
    {
     "t": "user",
     "q": 0,
     "draft": "Faut-il du liquide",
     "text": "Comment payer sans espèces ?"
    },
    {
     "t": "bot",
     "text": "Alipay et WeChat Pay sont très utilisés et acceptent les cartes Visa et Mastercard étrangères. Configurez-les avant le départ : je vous guide.",
     "src": "Source : guides officiels Alipay et WeChat Pay"
    },
    {
     "t": "user",
     "q": 1,
     "draft": "Prépare trois jours",
     "text": "J’arrive à Pékin vendredi pour 3 jours. J’aime bien manger, mais pas les foules."
    },
    {
     "t": "bot",
     "text": "Je le retiens pour ce voyage et les prochains."
    },
    {
     "t": "mem",
     "text": "Mémorisé · aime la cuisine · évite les foules"
    },
    {
     "t": "plan",
     "title": "3 jours à Pékin",
     "tag": "BROUILLON",
     "rows": [
      [
       "Ven",
       "Petit-déjeuner dans les hutong avant les groupes"
      ],
      [
       "Sam",
       "Grande Muraille à Mutianyu, côté tranquille"
      ],
      [
       "Dim",
       "Temple du Ciel à l’ouverture, puis cours de raviolis"
      ]
     ],
     "foot": "Sources : horaires officiels · temps de trajet"
    },
    {
     "t": "user",
     "q": 2,
     "text": "Réserve le cours pour deux. Passeport ",
     "secret": "E12345678",
     "ph": "<PASSPORT_1>"
    },
    {
     "t": "shield",
     "text": "Données masquées avant l’envoi au modèle"
    },
    {
     "t": "ask",
     "text": "Dimanche à 10 h, environ ¥300 pour deux. Je continue ?",
     "yes": "Confirmer",
     "no": "Pas maintenant"
    },
    {
     "t": "sys",
     "text": "<b>JT Agent</b> · l’équipe vérifie auprès du lieu",
     "done": "<b>Confirmé</b> · dimanche à 10 h ajouté au voyage"
    }
   ],
   "redact": [
    [
     "Bonjour, je suis ",
     null
    ],
    [
     "Emma Martin",
     "<NAME_1>"
    ],
    [
     ". Passeport ",
     null
    ],
    [
     "E12345678",
     "<PASSPORT_1>"
    ],
    [
     ", téléphone ",
     null
    ],
    [
     "+44 7700 900123",
     "<PHONE_1>"
    ],
    [
     ". Je suis à ",
     null
    ],
    [
     "l’entrée 3 de l’hôtel Lotus",
     "<LOCATION_1>"
    ],
    [
     ".",
     null
    ]
   ],
   "privLede": "Noms, passeports, téléphones, e-mails et positions précises sont remplacés par des balises avant que le modèle ne les lise.",
   "priv1": "L’équipe voit un dossier anonymisé avec un numéro aléatoire, jamais votre compte.",
   "priv2": "Un accès aux données n’est accordé que si nécessaire, pour une durée limitée et avec traçabilité.",
   "priv3": "Consultez, corrigez ou supprimez les informations mémorisées à tout moment.",
   "you": "Vous",
   "modelSees": "Ce que voit le modèle",
   "footTag": "Votre assistant personnel pour la Chine.",
   "companyName": "Guangzhou Chuangjing Technology Co., Ltd",
   "companyAddress": "Room 410, Tower A, R&F Yingtai Plaza, No. 100 Huangpu Avenue, Tianhe District, Guangzhou, China"
  },
  "ar": {
   "nav": {
    "how": "كيف يعمل",
    "places": "الوجهات",
    "privacy": "الخصوصية"
   },
   "heroTitle": "مساعدك الشخصي في كل يوم في الصين.",
   "heroLede": "اسأل CJ Agent عن التنقل والدفع والطعام والحجز. وعندما تحتاج مشكلة إلى مكالمة هاتفية أو تحقق محلي، يستعين JT Agent بشخص حقيقي.",
   "heroNote": "يصل أولًا إلى iPhone. ندعو المسافرين على دفعات صغيرة.",
   "howTitle": "كيف يعمل CJ Agent وJT Agent معًا",
   "howLede": "CJ Agent هو من تتحدث معه. أما JT Agent فيعمل في الخلفية: يتابع رحلتك، ويفتح طلب متابعة عندما يحدث خلل، ويسلّم إلى أحد أفراد الفريق ما لا يستطيع الذكاء الاصطناعي إنجازه.",
   "cjRole": "في محادثتك",
   "jtRole": "في الخلفية",
   "cjList": [
    "يجيب عن الدفع والمواصلات والطعام والتذاكر، مع مصادر يمكنك التحقق منها.",
    "ينظم أيامك وفق ما يتذكره عنك، ويحافظ على الخطط التي أكّدتها.",
    "يجهّز الحجوزات والتعديلات، ولا يدفع أو يغيّر شيئًا قبل موافقتك.",
    "يعرض عبارات وتفاصيل الحجز بالصينية عندما تحتاج إلى إظهارها لأحد.",
    "يتحدث الإنجليزية والصينية في المحادثة نفسها."
   ],
   "jtList": [
    "يتابع حجوزاتك وقطاراتك ورحلاتك الجوية وتسجيل الوصول.",
    "يلاحظ عندما يحدث خلل أو يبقى سؤال دون حل.",
    "يفتح طلب متابعة بالمعلومات اللازمة للخطوة التالية فقط.",
    "يسلّم المكالمات والتحقق المحلي إلى أحد أفراد الفريق ويتابعها حتى النهاية.",
    "يعيد إليك النتيجة عبر CJ Agent، في المحادثة نفسها."
   ],
   "scTitle": "كيف يبدو ذلك أثناء الرحلة",
   "tabs": [
    "الفندق لا يجد حجزك",
    "أُلغي قطارك",
    "تحتاج إلى مساعدة عاجلة"
   ],
   "laneChat": "في محادثتك",
   "laneBack": "في الخلفية",
   "who": {
    "you": "أنت",
    "cj": "CJ Agent",
    "jt": "JT Agent",
    "mate": "الفريق"
   },
   "scenes": {
    "hotel": {
     "steps": [
      "يقول موظف الاستقبال إنه لا يجد حجزي.",
      "أرِهم هذه البطاقة. وطلبتُ أيضًا من أحد أفراد الفريق الاتصال بالفندق.",
      "لم يُعثر على الحجز عند الوصول. يُعامَل كتعطّل في الرحلة.",
      "فُتح طلب متابعة يتضمن اسم الفندق ورقم الحجز والتواريخ، دون جواز السفر أو بيانات الحساب.",
      "اتصال بالاستقبال بالصينية. الحجز مسجّل باسم CLARKE EMMA.",
      "تم الحل: الحجز مسجّل باسم «CLARKE EMMA». غرفتك جاهزة. اتصل أحد أفراد الفريق بالفندق للتأكيد."
     ],
     "note": "لو لم تكن هناك غرفة، لعرض عليك CJ Agent خيارات قريبة بأسعارها، ولن يحجز إلا بعد أن تختار."
    },
    "train": {
     "steps": [
      "فحص الحالة: أُلغي قطار الساعة 14:05 إلى شيآن.",
      "يتحقق مما يعتمد عليه: تسجيل الوصول إلى الفندق الليلة وتذاكر الغد الساعة 9:00.",
      "أُلغي قطارك إلى شيآن الساعة 14:05. قطار الساعة 15:20 يصل الساعة 19:58 ويحافظ على فندق الليلة وتذاكر الغد. هل أحجزه؟",
      "نعم، احجز قطار 15:20.",
      "تم تغيير التذكرة وإبلاغ الفندق بأنك ستصل نحو الساعة 20:30.",
      "تم. تذكرتك الجديدة وخطتك المحدثة موجودتان في رحلتك."
     ],
     "note": "لم يُدفع شيء ولم يتغير شيء قبل موافقتك."
    },
    "sos": {
     "steps": [
      "سقطت على الدرج ولا أستطيع الوقوف على كاحلي.",
      "إذا كانت الحالة خطيرة، اتصل فورًا بالرقم 120 لطلب سيارة إسعاف. أرِ هذا للسائق أو لمن حولك:",
      "إشارة سلامة. أُرسلت خطوات الطوارئ فورًا دون انتظار فتح طلب متابعة.",
      "تم تنبيه أحد أفراد الفريق المناوب للمساعدة عبر الرسائل.",
      "سيتابع معك أحد أفراد الفريق هنا. أقرب مستشفى فيه موظفون يتحدثون الإنجليزية على بعد 2 كم."
     ],
     "note": "المساعدة الطارئة متاحة لجميع المستخدمين: إرشاد ودعم عبر الرسائل. عند الخطر، اتصل دائمًا بالرقم 110 (الشرطة) أو 120 (الإسعاف) أو 119 (الإطفاء)."
    }
   },
   "watchTitle": "ما الذي يراقبه JT Agent",
   "cols": [
    "الحالة",
    "أمثلة",
    "ما الذي يحدث"
   ],
   "watch": [
    [
     "سلامتك",
     "إصابة، مرض مفاجئ، الضياع.",
     "أرقام الطوارئ وعبارات بالصينية فورًا، ثم يساعدك أحد أفراد الفريق عبر الرسائل."
    ],
    [
     "الوثائق والمال",
     "جواز سفر مفقود، بطاقة محظورة، دفعة لا تمر.",
     "خطوات الإبلاغ والاستبدال أولًا، ثم يتحقق الفريق من التفاصيل."
    ],
    [
     "تعطّل الرحلة",
     "رحلة جوية تغيّرت، فندق لا يجد حجزك، معلم سياحي مغلق.",
     "يحدد ما الذي يتأثر أيضًا، ثم يقترح حلًا."
    ],
    [
     "تغييرات تطلبها",
     "تغيير الفندق، نقل يوم، إضافة مدينة.",
     "يجهّز CJ Agent الخيارات. لا يتغير شيء قبل تأكيدك."
    ],
    [
     "عندما يتعثر الذكاء الاصطناعي",
     "سؤال يبقى بلا جواب، أداة تتعطل مرارًا.",
     "يحل أحد أفراد الفريق المشكلة في الخلفية، ويخبرك CJ Agent بالنتيجة."
    ]
   ],
   "rules": [
    [
     "القرار لك",
     "لا شيء يكلّف مالًا أو يغيّر رحلتك يحدث دون موافقتك."
    ],
    [
     "ستعرف",
     "عندما يساعدك شخص، يخبرك CJ Agent بما فعله."
    ],
    [
     "القدر اللازم فقط",
     "يرى الفريق رقم الطلب والقليل من التفاصيل اللازمة للمهمة، ولا يرى حسابك أبدًا."
    ]
   ],
   "placesTitle": "إلى أين تتجه؟",
   "placesLede": "من بكين إلى كاشغر، ومن الديم سام إلى الهوت بوت. اسأل عن أي منها بالإنجليزية أو بالصينية.",
   "privTitle": "بياناتك تبقى ملكك.",
   "eaTitle": "اطلب الوصول المبكر",
   "eaLede": "ندعو المسافرين على دفعات صغيرة، بدءًا من iPhone. أخبرنا قليلًا عن رحلتك وسنراسلك عندما يتوفر لك مكان.",
   "f": {
    "name": "الاسم",
    "email": "البريد الإلكتروني",
    "source": "كيف عرفت G2C؟",
    "sourcePh": "اختر",
    "country": "البلد أو المنطقة",
    "optional": "اختياري",
    "when": "متى ستزور الصين؟",
    "dest": "إلى أين تود الذهاب؟",
    "other": "مكان آخر",
    "otherPh": "المدينة أو المنطقة",
    "needs": "ما الذي يساعدك أكثر؟",
    "note": "هل من شيء آخر؟"
   },
   "sending": "جارٍ الإرسال…",
   "ok": "شكرًا! أنت على القائمة. سنراسلك عندما تكون دعوتك جاهزة.",
   "bad": "أدخل اسمك وبريدًا إلكترونيًا صحيحًا وكيف عرفت G2C.",
   "fail": "تعذّر إرسال طلبك الآن. حاول مرة أخرى بعد دقيقة أو راسلنا على hello@go2china.space.",
   "failAlt": "يمكنك أيضًا استخدام النموذج البديل.",
   "opt": {
    "source": [
     "الأصدقاء أو العائلة",
     "محرك البحث",
     "Instagram",
     "TikTok",
     "YouTube",
     "Xiaohongshu (RED)",
     "Reddit",
     "فعالية",
     "غير ذلك"
    ],
    "when": [
     "خلال 3 أشهر",
     "بعد 3–6 أشهر",
     "بعد 6–12 شهرًا",
     "لست متأكدًا بعد",
     "أنا في الصين الآن"
    ],
    "dest": [
     "بكين",
     "شنغهاي",
     "شيآن",
     "تشنغدو",
     "قوانغتشو وشنتشن",
     "لست متأكدًا بعد"
    ],
    "needs": [
     "الدفع",
     "المواصلات",
     "تخطيط الرحلة",
     "الحجز",
     "الطعام",
     "اللغة",
     "التأشيرة والدخول"
    ]
   },
   "credits": "مصادر الصور",
   "online": "مساعدك الشخصي",
   "inputHint": "اسأل عن رحلتك…",
   "suggest": [
    "الدفع في الصين",
    "3 أيام في بكين",
    "حجز درس"
   ],
   "chat": [
    {
     "t": "hello",
     "text": "مرحبًا! أنا CJ، مساعدك الشخصي في الصين. كيف أساعدك؟"
    },
    {
     "t": "user",
     "q": 0,
     "draft": "هل أحتاج إلى النقد",
     "text": "كيف أدفع دون نقود؟"
    },
    {
     "t": "bot",
     "text": "يشيع استخدام Alipay وWeChat Pay، وكلاهما يدعم بطاقات Visa وMastercard الأجنبية. من الأفضل إعدادهما قبل السفر، وسأرشدك خطوة بخطوة.",
     "src": "المصدر: أدلة Alipay وWeChat Pay الرسمية"
    },
    {
     "t": "user",
     "q": 1,
     "draft": "خطط لثلاثة أيام",
     "text": "أصل إلى بكين الجمعة لثلاثة أيام. أحب الطعام وأتجنب الزحام."
    },
    {
     "t": "bot",
     "text": "سأتذكر ذلك لهذه الرحلة والرحلات القادمة."
    },
    {
     "t": "mem",
     "text": "تم الحفظ · يحب الطعام · يتجنب الزحام"
    },
    {
     "t": "plan",
     "title": "3 أيام في بكين",
     "tag": "مسودة",
     "rows": [
      [
       "الجمعة",
       "إفطار في أزقة الهوتونغ قبل وصول المجموعات"
      ],
      [
       "السبت",
       "سور الصين في موتيانيو، في الجزء الأهدأ"
      ],
      [
       "الأحد",
       "معبد السماء عند الافتتاح، ثم درس لتحضير الزلابية"
      ]
     ],
     "foot": "المصادر: أوقات العمل الرسمية · أوقات التنقل"
    },
    {
     "t": "user",
     "q": 2,
     "text": "احجز الدرس لشخصين. جواز السفر ",
     "secret": "E12345678",
     "ph": "<PASSPORT_1>"
    },
    {
     "t": "shield",
     "text": "تُحجب البيانات قبل إرسالها إلى النموذج"
    },
    {
     "t": "ask",
     "text": "الأحد الساعة 10:00، نحو ¥300 لشخصين. هل أتابع؟",
     "yes": "تأكيد",
     "no": "ليس الآن"
    },
    {
     "t": "sys",
     "text": "<b>JT Agent</b> · يتواصل الفريق مع المكان للتأكيد",
     "done": "<b>تم التأكيد</b> · أضيف الأحد الساعة 10:00 إلى رحلتك"
    }
   ],
   "redact": [
    [
     "مرحبًا، أنا ",
     null
    ],
    [
     "سارة أحمد",
     "<NAME_1>"
    ],
    [
     ". جواز سفري ",
     null
    ],
    [
     "E12345678",
     "<PASSPORT_1>"
    ],
    [
     "، وهاتفي ",
     null
    ],
    [
     "+44 7700 900123",
     "<PHONE_1>"
    ],
    [
     ". أنا عند ",
     null
    ],
    [
     "البوابة 3 في فندق لوتس",
     "<LOCATION_1>"
    ],
    [
     ".",
     null
    ]
   ],
   "privLede": "تُستبدل الأسماء وأرقام الجوازات والهواتف والبريد والمواقع الدقيقة برموز قبل أن يقرأها النموذج.",
   "priv1": "يرى الفريق طلبًا محجوب البيانات برقم عشوائي، ولا يرى حسابك.",
   "priv2": "لا تُكشف البيانات إلا عند الحاجة ولمدة محدودة، مع تسجيل الوصول إليها.",
   "priv3": "يمكنك عرض المعلومات المحفوظة وتصحيحها أو حذفها متى شئت.",
   "you": "أنت",
   "modelSees": "ما يراه النموذج",
   "footTag": "مساعدك الشخصي في الصين.",
   "companyName": "Guangzhou Chuangjing Technology Co., Ltd",
   "companyAddress": "Room 410, Tower A, R&F Yingtai Plaza, No. 100 Huangpu Avenue, Tianhe District, Guangzhou, China"
  }
 },
 "SCENES": {
  "hotel": [
   {
    "lane": "chat",
    "who": "you"
   },
   {
    "lane": "chat",
    "who": "cj",
    "card": "您好，我在贵酒店有预订。\n预订号：HB-48213\n入住：11月14日，共2晚"
   },
   {
    "lane": "back",
    "who": "jt"
   },
   {
    "lane": "back",
    "who": "jt"
   },
   {
    "lane": "back",
    "who": "mate"
   },
   {
    "lane": "chat",
    "who": "cj"
   }
  ],
  "train": [
   {
    "lane": "back",
    "who": "jt"
   },
   {
    "lane": "back",
    "who": "jt"
   },
   {
    "lane": "chat",
    "who": "cj"
   },
   {
    "lane": "chat",
    "who": "you"
   },
   {
    "lane": "back",
    "who": "mate"
   },
   {
    "lane": "chat",
    "who": "cj"
   }
  ],
  "sos": [
   {
    "lane": "chat",
    "who": "you"
   },
   {
    "lane": "chat",
    "who": "cj",
    "card": "我脚踝受伤了，请帮我叫救护车。"
   },
   {
    "lane": "back",
    "who": "jt"
   },
   {
    "lane": "back",
    "who": "jt"
   },
   {
    "lane": "chat",
    "who": "cj"
   }
  ]
 },
 "PLACES": [
  {
   "id": "forbidden",
   "zh": [
    "故宫",
    "北京"
   ],
   "en": [
    "Forbidden City",
    "Beijing"
   ],
   "ru": [
    "Запретный город",
    "Пекин"
   ],
   "es": [
    "Ciudad Prohibida",
    "Pekín"
   ],
   "fr": [
    "Cité interdite",
    "Pékin"
   ],
   "ar": [
    "المدينة المحرمة",
    "بكين"
   ]
  },
  {
   "id": "liriver",
   "zh": [
    "漓江",
    "桂林"
   ],
   "en": [
    "Li River",
    "Guilin"
   ],
   "ru": [
    "Река Лицзян",
    "Гуйлинь"
   ],
   "es": [
    "Río Li",
    "Guilin"
   ],
   "fr": [
    "Rivière Li",
    "Guilin"
   ],
   "ar": [
    "نهر لي",
    "قويلين"
   ]
  },
  {
   "id": "shanghai",
   "zh": [
    "外滩",
    "上海"
   ],
   "en": [
    "The Bund",
    "Shanghai"
   ],
   "ru": [
    "Набережная Бунд",
    "Шанхай"
   ],
   "es": [
    "El Bund",
    "Shanghái"
   ],
   "fr": [
    "Le Bund",
    "Shanghai"
   ],
   "ar": [
    "البوند",
    "شنغهاي"
   ]
  },
  {
   "id": "terracotta",
   "zh": [
    "兵马俑",
    "西安"
   ],
   "en": [
    "Terracotta Army",
    "Xi’an"
   ],
   "ru": [
    "Терракотовая армия",
    "Сиань"
   ],
   "es": [
    "Guerreros de terracota",
    "Xi’an"
   ],
   "fr": [
    "Armée de terre cuite",
    "Xi’an"
   ],
   "ar": [
    "جيش التيراكوتا",
    "شيآن"
   ]
  },
  {
   "id": "zhangjiajie",
   "zh": [
    "张家界",
    "湖南"
   ],
   "en": [
    "Zhangjiajie",
    "Hunan"
   ],
   "ru": [
    "Чжанцзяцзе",
    "Хунань"
   ],
   "es": [
    "Zhangjiajie",
    "Hunan"
   ],
   "fr": [
    "Zhangjiajie",
    "Hunan"
   ],
   "ar": [
    "تشانغجياجيه",
    "هونان"
   ]
  },
  {
   "id": "westlake",
   "zh": [
    "西湖",
    "杭州"
   ],
   "en": [
    "West Lake",
    "Hangzhou"
   ],
   "ru": [
    "Озеро Сиху",
    "Ханчжоу"
   ],
   "es": [
    "Lago del Oeste",
    "Hangzhou"
   ],
   "fr": [
    "Lac de l’Ouest",
    "Hangzhou"
   ],
   "ar": [
    "البحيرة الغربية",
    "هانغتشو"
   ]
  },
  {
   "id": "panda",
   "zh": [
    "大熊猫",
    "成都"
   ],
   "en": [
    "Giant pandas",
    "Chengdu"
   ],
   "ru": [
    "Большие панды",
    "Чэнду"
   ],
   "es": [
    "Pandas gigantes",
    "Chengdu"
   ],
   "fr": [
    "Pandas géants",
    "Chengdu"
   ],
   "ar": [
    "الباندا العملاقة",
    "تشنغدو"
   ]
  },
  {
   "id": "hongkong",
   "zh": [
    "维多利亚港",
    "香港"
   ],
   "en": [
    "Victoria Harbour",
    "Hong Kong"
   ],
   "ru": [
    "Гавань Виктория",
    "Гонконг"
   ],
   "es": [
    "Puerto de Victoria",
    "Hong Kong"
   ],
   "fr": [
    "Port Victoria",
    "Hong Kong"
   ],
   "ar": [
    "ميناء فيكتوريا",
    "هونغ كونغ"
   ]
  },
  {
   "id": "heaven",
   "zh": [
    "天坛",
    "北京"
   ],
   "en": [
    "Temple of Heaven",
    "Beijing"
   ],
   "ru": [
    "Храм Неба",
    "Пекин"
   ],
   "es": [
    "Templo del Cielo",
    "Pekín"
   ],
   "fr": [
    "Temple du Ciel",
    "Pékin"
   ],
   "ar": [
    "معبد السماء",
    "بكين"
   ]
  },
  {
   "id": "jiuzhaigou",
   "zh": [
    "九寨沟",
    "四川"
   ],
   "en": [
    "Jiuzhaigou",
    "Sichuan"
   ],
   "ru": [
    "Цзючжайгоу",
    "Сычуань"
   ],
   "es": [
    "Jiuzhaigou",
    "Sichuan"
   ],
   "fr": [
    "Jiuzhaigou",
    "Sichuan"
   ],
   "ar": [
    "جيوتشايقو",
    "سيتشوان"
   ]
  },
  {
   "id": "dimsum",
   "zh": [
    "早茶点心",
    "广州"
   ],
   "en": [
    "Dim sum",
    "Guangzhou"
   ],
   "ru": [
    "Димсамы",
    "Гуанчжоу"
   ],
   "es": [
    "Dim sum",
    "Cantón"
   ],
   "fr": [
    "Dim sum",
    "Canton"
   ],
   "ar": [
    "الديم سام",
    "قوانغتشو"
   ]
  },
  {
   "id": "potala",
   "zh": [
    "布达拉宫",
    "拉萨"
   ],
   "en": [
    "Potala Palace",
    "Lhasa"
   ],
   "ru": [
    "Дворец Потала",
    "Лхаса"
   ],
   "es": [
    "Palacio de Potala",
    "Lhasa"
   ],
   "fr": [
    "Palais du Potala",
    "Lhassa"
   ],
   "ar": [
    "قصر بوتالا",
    "لاسا"
   ]
  },
  {
   "id": "suzhou",
   "zh": [
    "苏州园林",
    "苏州"
   ],
   "en": [
    "Classical gardens",
    "Suzhou"
   ],
   "ru": [
    "Классические сады",
    "Сучжоу"
   ],
   "es": [
    "Jardines clásicos",
    "Suzhou"
   ],
   "fr": [
    "Jardins classiques",
    "Suzhou"
   ],
   "ar": [
    "الحدائق الكلاسيكية",
    "سوتشو"
   ]
  },
  {
   "id": "chongqing",
   "zh": [
    "重庆夜景",
    "重庆"
   ],
   "en": [
    "Chongqing at night",
    "Chongqing"
   ],
   "ru": [
    "Ночной Чунцин",
    "Чунцин"
   ],
   "es": [
    "Chongqing de noche",
    "Chongqing"
   ],
   "fr": [
    "Chongqing la nuit",
    "Chongqing"
   ],
   "ar": [
    "تشونغتشينغ ليلًا",
    "تشونغتشينغ"
   ]
  },
  {
   "id": "longji",
   "zh": [
    "龙脊梯田",
    "广西"
   ],
   "en": [
    "Longji rice terraces",
    "Guangxi"
   ],
   "ru": [
    "Рисовые террасы Лунцзи",
    "Гуанси"
   ],
   "es": [
    "Terrazas de arroz de Longji",
    "Guangxi"
   ],
   "fr": [
    "Rizières de Longji",
    "Guangxi"
   ],
   "ar": [
    "مدرجات الأرز في لونغجي",
    "قوانغشي"
   ]
  },
  {
   "id": "xianwall",
   "zh": [
    "西安城墙",
    "西安"
   ],
   "en": [
    "City Wall",
    "Xi’an"
   ],
   "ru": [
    "Городская стена",
    "Сиань"
   ],
   "es": [
    "Muralla de la ciudad",
    "Xi’an"
   ],
   "fr": [
    "Remparts",
    "Xi’an"
   ],
   "ar": [
    "سور المدينة",
    "شيآن"
   ]
  },
  {
   "id": "harbin",
   "zh": [
    "冰雪大世界",
    "哈尔滨"
   ],
   "en": [
    "Ice and Snow World",
    "Harbin"
   ],
   "ru": [
    "Мир льда и снега",
    "Харбин"
   ],
   "es": [
    "Mundo de Hielo y Nieve",
    "Harbin"
   ],
   "fr": [
    "Monde de glace et de neige",
    "Harbin"
   ],
   "ar": [
    "عالم الجليد والثلج",
    "هاربين"
   ]
  },
  {
   "id": "summerpalace",
   "zh": [
    "颐和园",
    "北京"
   ],
   "en": [
    "Summer Palace",
    "Beijing"
   ],
   "ru": [
    "Летний дворец",
    "Пекин"
   ],
   "es": [
    "Palacio de Verano",
    "Pekín"
   ],
   "fr": [
    "Palais d’Été",
    "Pékin"
   ],
   "ar": [
    "القصر الصيفي",
    "بكين"
   ]
  },
  {
   "id": "hotpot",
   "zh": [
    "火锅",
    "四川"
   ],
   "en": [
    "Hotpot",
    "Sichuan"
   ],
   "ru": [
    "Хого",
    "Сычуань"
   ],
   "es": [
    "Hot pot",
    "Sichuan"
   ],
   "fr": [
    "Fondue chinoise",
    "Sichuan"
   ],
   "ar": [
    "الهوت بوت",
    "سيتشوان"
   ]
  },
  {
   "id": "leshan",
   "zh": [
    "乐山大佛",
    "四川"
   ],
   "en": [
    "Leshan Giant Buddha",
    "Sichuan"
   ],
   "ru": [
    "Большой Будда в Лэшане",
    "Сычуань"
   ],
   "es": [
    "Gran Buda de Leshan",
    "Sichuan"
   ],
   "fr": [
    "Grand Bouddha de Leshan",
    "Sichuan"
   ],
   "ar": [
    "بوذا ليشان العملاق",
    "سيتشوان"
   ]
  },
  {
   "id": "pingyao",
   "zh": [
    "平遥古城",
    "山西"
   ],
   "en": [
    "Pingyao Ancient City",
    "Shanxi"
   ],
   "ru": [
    "Древний город Пинъяо",
    "Шаньси"
   ],
   "es": [
    "Ciudad antigua de Pingyao",
    "Shanxi"
   ],
   "fr": [
    "Cité antique de Pingyao",
    "Shanxi"
   ],
   "ar": [
    "مدينة بينغياو القديمة",
    "شانشي"
   ]
  },
  {
   "id": "yangshuo",
   "zh": [
    "阳朔",
    "广西"
   ],
   "en": [
    "Yangshuo",
    "Guangxi"
   ],
   "ru": [
    "Яншо",
    "Гуанси"
   ],
   "es": [
    "Yangshuo",
    "Guangxi"
   ],
   "fr": [
    "Yangshuo",
    "Guangxi"
   ],
   "ar": [
    "يانغشو",
    "قوانغشي"
   ]
  },
  {
   "id": "cantontower",
   "zh": [
    "广州塔",
    "广州"
   ],
   "en": [
    "Canton Tower",
    "Guangzhou"
   ],
   "ru": [
    "Телебашня Кантон",
    "Гуанчжоу"
   ],
   "es": [
    "Torre de Cantón",
    "Cantón"
   ],
   "fr": [
    "Tour de Canton",
    "Canton"
   ],
   "ar": [
    "برج كانتون",
    "قوانغتشو"
   ]
  },
  {
   "id": "huangshan",
   "zh": [
    "黄山",
    "安徽"
   ],
   "en": [
    "Huangshan",
    "Anhui"
   ],
   "ru": [
    "Хуаншань",
    "Аньхой"
   ],
   "es": [
    "Huangshan",
    "Anhui"
   ],
   "fr": [
    "Huangshan",
    "Anhui"
   ],
   "ar": [
    "جبل هوانغشان",
    "آنهوي"
   ]
  },
  {
   "id": "yugarden",
   "zh": [
    "豫园",
    "上海"
   ],
   "en": [
    "Yu Garden",
    "Shanghai"
   ],
   "ru": [
    "Сад Юйюань",
    "Шанхай"
   ],
   "es": [
    "Jardín Yu",
    "Shanghái"
   ],
   "fr": [
    "Jardin Yu",
    "Shanghai"
   ],
   "ar": [
    "حديقة يو",
    "شنغهاي"
   ]
  },
  {
   "id": "danxia",
   "zh": [
    "张掖丹霞",
    "甘肃"
   ],
   "en": [
    "Zhangye Danxia",
    "Gansu"
   ],
   "ru": [
    "Данься в Чжанъе",
    "Ганьсу"
   ],
   "es": [
    "Danxia de Zhangye",
    "Gansu"
   ],
   "fr": [
    "Danxia de Zhangye",
    "Gansu"
   ],
   "ar": [
    "دانشيا تشانغيه",
    "قانسو"
   ]
  },
  {
   "id": "lijiang",
   "zh": [
    "丽江",
    "云南"
   ],
   "en": [
    "Lijiang",
    "Yunnan"
   ],
   "ru": [
    "Лицзян",
    "Юньнань"
   ],
   "es": [
    "Lijiang",
    "Yunnan"
   ],
   "fr": [
    "Lijiang",
    "Yunnan"
   ],
   "ar": [
    "ليجيانغ",
    "يونان"
   ]
  },
  {
   "id": "train",
   "zh": [
    "高铁",
    "全国"
   ],
   "en": [
    "High-speed rail",
    "Across China"
   ],
   "ru": [
    "Скоростные поезда",
    "По всей стране"
   ],
   "es": [
    "Tren de alta velocidad",
    "Por todo el país"
   ],
   "fr": [
    "Train à grande vitesse",
    "Partout en Chine"
   ],
   "ar": [
    "القطار فائق السرعة",
    "في أنحاء الصين"
   ]
  },
  {
   "id": "fenghuang",
   "zh": [
    "凤凰古城",
    "湖南"
   ],
   "en": [
    "Fenghuang Old Town",
    "Hunan"
   ],
   "ru": [
    "Старый город Фэнхуан",
    "Хунань"
   ],
   "es": [
    "Ciudad antigua de Fenghuang",
    "Hunan"
   ],
   "fr": [
    "Vieille ville de Fenghuang",
    "Hunan"
   ],
   "ar": [
    "بلدة فنغهوانغ القديمة",
    "هونان"
   ]
  },
  {
   "id": "longjing",
   "zh": [
    "龙井茶园",
    "杭州"
   ],
   "en": [
    "Longjing tea fields",
    "Hangzhou"
   ],
   "ru": [
    "Чайные плантации Лунцзин",
    "Ханчжоу"
   ],
   "es": [
    "Campos de té Longjing",
    "Hangzhou"
   ],
   "fr": [
    "Champs de thé Longjing",
    "Hangzhou"
   ],
   "ar": [
    "حقول شاي لونغجينغ",
    "هانغتشو"
   ]
  },
  {
   "id": "macau",
   "zh": [
    "议事亭前地",
    "澳门"
   ],
   "en": [
    "Senado Square",
    "Macao"
   ],
   "ru": [
    "Площадь Сенадо",
    "Макао"
   ],
   "es": [
    "Largo del Senado",
    "Macao"
   ],
   "fr": [
    "Place du Sénat",
    "Macao"
   ],
   "ar": [
    "ساحة سينادو",
    "ماكاو"
   ]
  },
  {
   "id": "tigerleaping",
   "zh": [
    "虎跳峡",
    "云南"
   ],
   "en": [
    "Tiger Leaping Gorge",
    "Yunnan"
   ],
   "ru": [
    "Ущелье Прыгающего тигра",
    "Юньнань"
   ],
   "es": [
    "Garganta del Salto del Tigre",
    "Yunnan"
   ],
   "fr": [
    "Gorges du Saut du Tigre",
    "Yunnan"
   ],
   "ar": [
    "مضيق قفزة النمر",
    "يونان"
   ]
  },
  {
   "id": "kashgar",
   "zh": [
    "喀什古城",
    "新疆"
   ],
   "en": [
    "Kashgar Old City",
    "Xinjiang"
   ],
   "ru": [
    "Старый город Кашгара",
    "Синьцзян"
   ],
   "es": [
    "Ciudad vieja de Kashgar",
    "Xinjiang"
   ],
   "fr": [
    "Vieille ville de Kachgar",
    "Xinjiang"
   ],
   "ar": [
    "مدينة كاشغر القديمة",
    "شينجيانغ"
   ]
  },
  {
   "id": "hutong",
   "zh": [
    "胡同",
    "北京"
   ],
   "en": [
    "Hutongs",
    "Beijing"
   ],
   "ru": [
    "Хутуны",
    "Пекин"
   ],
   "es": [
    "Hutongs",
    "Pekín"
   ],
   "fr": [
    "Hutongs",
    "Pékin"
   ],
   "ar": [
    "الهوتونغ",
    "بكين"
   ]
  },
  {
   "id": "lanterns",
   "zh": [
    "红灯笼",
    "春节"
   ],
   "en": [
    "Red lanterns",
    "Lunar New Year"
   ],
   "ru": [
    "Красные фонари",
    "Китайский Новый год"
   ],
   "es": [
    "Farolillos rojos",
    "Año Nuevo chino"
   ],
   "fr": [
    "Lanternes rouges",
    "Nouvel An chinois"
   ],
   "ar": [
    "الفوانيس الحمراء",
    "رأس السنة الصينية"
   ]
  }
 ]
};
