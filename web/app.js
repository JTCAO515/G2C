(() => {
  "use strict";

  const SIGHTS = [
    ["greatwall", "The Great Wall", "Beijing", "长城", "北京"],
    ["forbidden", "The Forbidden City", "Beijing", "故宫", "北京"],
    ["shanghai", "The Bund at night", "Shanghai", "外滩夜景", "上海"],
    ["terracotta", "Terracotta Army", "Xi'an", "兵马俑", "西安"],
    ["huangshan", "Huangshan", "Anhui", "黄山", "安徽"],
    ["heaven", "Temple of Heaven", "Beijing", "天坛", "北京"],
    ["panda", "Giant pandas", "Chengdu", "大熊猫", "成都"],
    ["potala", "Potala Palace", "Lhasa", "布达拉宫", "拉萨"],
    ["lanterns", "Red lanterns", "Lunar New Year", "红灯笼", "春节"]
  ];

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const T = {
    en: {
      cta: "Apply Early Access",
      heroTitle: "A personal agent for <i>every day</i> in China.",
      heroLede: "CJ Agent helps with travel questions, daily plans and bookings. JT Agent brings in a person for problems that need a call or a local check. Your personal details are redacted before any model sees them.",
      soon: "Coming soon on iPhone · English & 中文",
      online: "Your personal agent",
      inputHint: "Ask anything about your trip…",
      agentsTitle: "Two agents, <i>one trip</i> that just works.",
      cjTag: "Answers questions. Plans your days. Helps you act.",
      cjA: "Answers", cjAText: "How to pay, catch a train or book a ticket — practical answers with sources you can check.",
      cjP: "Plans", cjPText: "Build a daily plan around your interests, budget and pace. Keep confirmed arrangements safe as the trip changes.",
      cjE: "Acts", cjEText: "Help with bookings and follow-up. Anything that spends money or changes your itinerary waits for your OK.",
      jtTag: "A person steps in when the trip needs more than an answer.",
      jt1: "Flags a changed flight, a missing hotel booking or an unresolved question.",
      jt2: "Creates a private case with only the information needed to resolve it.",
      jt3: "A teammate checks the details and contacts the hotel, venue or other provider.",
      jt4: "The outcome and next step come back to your chat.",
      privTitle: "Your details <i>stay yours.</i>",
      privLede: "Names, passport numbers, phone numbers, emails and exact locations are swapped for placeholders on our side before any model reads them.",
      priv1: "Teammates see masked cases under a random case ID, never your account.",
      priv2: "Revealing a field is limited to what the task needs, time-boxed and logged.",
      priv3: "Your memory is yours: see it, correct it, delete it whenever you like.",
      you: "You", modelSees: "What the model sees",
      s1: "Remembers you", s1t: "Preferences carry over across chats and trips.",
      s2: "Shows its sources", s2t: "Advice you can verify, not guesswork.",
      s3: "Protects your plans", s3t: "Confirmed days don't shift without you.",
      s4: "English & 中文", s4t: "Switch any time, in the same conversation.",
      appTitle: "G2C for iPhone, <i>landing soon.</i>",
      appLede: "We're opening the first spots to invited travelers. Leave your email and we'll let you know when it's your turn.",
      emailLabel: "Email address", emailPh: "you@example.com",
      footTag: "Your personal agent for China.",
      companyName: "Guangzhou Chuangjing Technology Co., Ltd",
      companyAddress: "Room 410, Tower A, R&F Yingtai Plaza, No. 100 Huangpu Avenue, Tianhe District, Guangzhou, China",
      sightsTitle: "From the Great Wall to the Bund, <i>it knows the way.</i>",
      redact: [
        ["Hi, I'm ", null], ["Emma Clarke", "<NAME_1>"], [". Passport ", null], ["E12345678", "<PASSPORT_1>"],
        [", call me on ", null], ["+44 7700 900123", "<PHONE_1>"], [" — I'm at ", null], ["Gate 3, Hotel Lotus", "<LOCATION_1>"], [".", null]
      ],
      suggest: ["Paying in China", "3 days in Beijing", "Book a class"],
      chat: [
        { t: "hello", text: "Hi! I'm CJ, your personal agent for China. Ask me anything." },
        { t: "user", q: 0, draft: "Do I need cash in Chi", text: "How do I pay for things without cash?" },
        { t: "bot", text: "Most places use Alipay or WeChat Pay, and both accept foreign Visa and Mastercard. Set one up before you fly — I'll walk you through it.", src: "Source: official Alipay & WeChat Pay guides" },
        { t: "user", q: 1, draft: "Plan 3 days in Shang", text: "Landing in Beijing on Friday — 3 days. Love food, hate crowds." },
        { t: "bot", text: "Lovely. I'll remember that for this trip and the next." },
        { t: "mem", text: "Remembered · loves food · avoids crowds" },
        { t: "plan", title: "3 days in Beijing", tag: "DRAFT",
          rows: [["Fri", "Hutong breakfast walk, out before the tour buses"], ["Sat", "Great Wall at Mutianyu — the quieter stretch"], ["Sun", "Temple of Heaven at opening, then a dumpling class"]],
          foot: "Sources: official opening hours · transit times" },
        { t: "user", q: 2, text: "Book the dumpling class for two. Passport ", secret: "E12345678", ph: "<PASSPORT_1>" },
        { t: "shield", text: "Redacted before any model sees it" },
        { t: "ask", text: "Sunday 10:00, about ¥300 for two. Shall I go ahead?", yes: "Confirm", no: "Not now" },
        { t: "sys", text: "<b>JT Agent</b> · a teammate is confirming with the venue", done: "<b>Confirmed</b> · Sun 10:00 is on your trip" }
      ]
    },
    zh: {
      cta: "Apply Early Access",
      heroTitle: "在中国的<i>每一天</i>，都有你的私人助理。",
      heroLede: "CJ Agent 解答旅行问题、安排每日行程、协助预订；遇到需要打电话或当地核实的问题，JT Agent 请真人接手。个人信息在模型读取前已脱敏。",
      soon: "即将登陆 iPhone · 中文 & English",
      online: "你的私人助理",
      inputHint: "问问关于行程的任何事…",
      agentsTitle: "两个 Agent，<i>一趟</i>省心的旅程。",
      cjTag: "解答问题，安排每天，协助办事。",
      cjA: "解答", cjAText: "怎么付款、坐高铁、订门票——给出实用步骤，并附上可核对的来源。",
      cjP: "规划", cjPText: "结合兴趣、预算和节奏安排每日行程；后续调整时，保护你已确认的安排。",
      cjE: "执行", cjEText: "协助预订和后续跟进；凡是花钱或改变行程的事，都先等你点头。",
      jtTag: "需要进一步核实或沟通时，让真人接手。",
      jt1: "识别航班变动、酒店查不到订单，或反复未解决的问题。",
      jt2: "建立独立工单，只带解决这件事所需的信息。",
      jt3: "团队成员核实情况，联系酒店、场馆或其他服务方。",
      jt4: "处理结果和下一步，回到同一段对话。",
      privTitle: "你的信息，<i>只属于你。</i>",
      privLede: "姓名、护照号、电话、邮箱和精确位置，在任何模型读取之前就已在我们这边替换为占位符。",
      priv1: "团队成员只看到打码的工单和随机工单号，看不到你的账号。",
      priv2: "揭示字段仅限任务所需，有时限，并全程留痕。",
      priv3: "记忆归你所有：随时查看、更正或删除。",
      you: "你", modelSees: "模型看到的",
      s1: "记得你", s1t: "偏好跨对话、跨旅程延续。",
      s2: "有据可查", s2t: "建议附来源，不靠猜。",
      s3: "保护行程", s3t: "已确认的安排，不会背着你变动。",
      s4: "中文 & English", s4t: "同一段对话里随时切换。",
      appTitle: "G2C iPhone 版，<i>即将上线。</i>",
      appLede: "首批名额将开放给受邀旅行者。留下邮箱，轮到你时我们会第一时间通知。",
      emailLabel: "邮箱地址", emailPh: "you@example.com",
      footTag: "你在中国的私人助理。",
      companyName: "广州创竞科技有限公司",
      companyAddress: "广州市天河区黄埔大道100号富力盈泰广场A座410室",
      sightsTitle: "从长城到外滩，<i>它都熟门熟路。</i>",
      redact: [
        ["你好，我是", null], ["王小明", "<NAME_1>"], ["，护照号 ", null], ["E12345678", "<PASSPORT_1>"],
        ["，电话 ", null], ["138 0013 8000", "<PHONE_1>"], ["，我在", null], ["莲花酒店 3 号门", "<LOCATION_1>"], ["。", null]
      ],
      suggest: ["不带现金怎么付款", "北京 3 日游", "帮我预订"],
      chat: [
        { t: "hello", text: "你好！我是 CJ，你在中国的私人助理，想问什么都可以。" },
        { t: "user", q: 0, draft: "在中国需要带现", text: "没有现金，在中国怎么付款？" },
        { t: "bot", text: "大多数地方用支付宝或微信支付，两者都支持绑定境外 Visa / Mastercard。建议出发前开通，我一步步带你设置。", src: "来源：支付宝与微信支付官方指引" },
        { t: "user", q: 1, draft: "帮我规划上海", text: "周五落地北京，玩 3 天。爱吃，怕人多。" },
        { t: "bot", text: "好的，这次和以后的旅程我都会记住。" },
        { t: "mem", text: "已记住 · 爱美食 · 避开人流" },
        { t: "plan", title: "北京 3 日", tag: "草稿",
          rows: [["周五", "胡同早餐漫步，赶在旅行团之前"], ["周六", "慕田峪长城，走人少的那一段"], ["周日", "天坛开门即入，再去上饺子课"]],
          foot: "来源：官方开放时间 · 交通时长" },
        { t: "user", q: 2, text: "帮我订两人的饺子课。护照 ", secret: "E12345678", ph: "<PASSPORT_1>" },
        { t: "shield", text: "已脱敏，模型看不到原文" },
        { t: "ask", text: "周日 10:00，两人约 ¥300。要我继续吗？", yes: "确认", no: "暂不" },
        { t: "sys", text: "<b>JT Agent</b> · 团队成员正在与商家确认", done: "<b>已确认</b> · 周日 10:00 已加入行程" }
      ]
    }
  };

  T.ru = {
    ...T.en,
    heroTitle: "Личный помощник на <i>каждый день</i> в Китае.",
    heroLede: "CJ Agent отвечает на вопросы, планирует дни и помогает с бронированием. JT Agent подключает человека, когда нужен звонок или проверка на месте. Личные данные скрываются до передачи модели.",
    soon: "Скоро на iPhone · английский и китайский", online: "Ваш личный помощник", inputHint: "Спросите о поездке…",
    agentsTitle: "Два помощника. <i>Одна спокойная поездка.</i>", cjTag: "Ответы, планы и помощь в делах.",
    cjA: "Ответы", cjAText: "Как платить, ездить на поезде и покупать билеты — понятные шаги с проверяемыми источниками.",
    cjP: "Планы", cjPText: "План на каждый день с учётом интересов, бюджета и темпа. Подтверждённые договорённости сохраняются при изменениях.",
    cjE: "Действия", cjEText: "Помощь с бронированием и дальнейшими шагами. Расходы и изменения маршрута — только с вашего согласия.",
    jtTag: "Человек подключается, когда одного ответа мало.",
    jt1: "Замечает изменение рейса, пропавшую бронь или нерешённый вопрос.", jt2: "Создаёт отдельное обращение только с нужными для решения данными.",
    jt3: "Сотрудник проверяет детали и связывается с отелем, площадкой или другим поставщиком услуг.", jt4: "Результат и следующий шаг приходят в тот же чат.",
    privTitle: "Ваши данные <i>остаются вашими.</i>", privLede: "Имена, номера паспортов, телефоны, почта и точные адреса заменяются метками до передачи модели.",
    priv1: "Сотрудники видят обезличенное обращение со случайным номером, а не ваш аккаунт.", priv2: "Данные раскрываются лишь по необходимости, на ограниченное время и с записью доступа.", priv3: "Вы можете просматривать, исправлять и удалять сохранённые сведения.",
    you: "Вы", modelSees: "Что видит модель", s1: "Помнит вас", s1t: "Предпочтения сохраняются между беседами и поездками.", s2: "Указывает источники", s2t: "Проверяемые советы вместо догадок.", s3: "Берегёт планы", s3t: "Подтверждённое не меняется без вашего согласия.", s4: "Английский и 中文", s4t: "Переключайтесь в одной беседе.",
    appTitle: "G2C для iPhone — <i>скоро.</i>", appLede: "Первые места — для приглашённых путешественников. Оставьте почту, и мы сообщим, когда появится место.", footTag: "Ваш личный помощник в Китае.", sightsTitle: "От Великой стены до Бунда — <i>он знает путь.</i>",
    redact: [["Здравствуйте, я ",null],["Анна Иванова","<NAME_1>"],[". Паспорт ",null],["E12345678","<PASSPORT_1>"],[", телефон ",null],["+44 7700 900123","<PHONE_1>"],[". Я у ",null],["входа 3 отеля «Лотос»","<LOCATION_1>"],[".",null]],
    suggest: ["Оплата в Китае", "3 дня в Пекине", "Забронировать занятие"],
    chat: [
      {t:"hello",text:"Привет! Я CJ, ваш личный помощник в Китае. Спрашивайте!"},
      {t:"user",q:0,draft:"Нужны ли наличные",text:"Как платить без наличных?"},
      {t:"bot",text:"Чаще всего используют Alipay и WeChat Pay. Можно привязать иностранную Visa или Mastercard. Лучше настроить всё до вылета — помогу по шагам.",src:"Источник: официальные инструкции Alipay и WeChat Pay"},
      {t:"user",q:1,draft:"План на три дня",text:"Прилетаю в Пекин в пятницу на 3 дня. Люблю вкусно поесть, не люблю толпы."},
      {t:"bot",text:"Запомню это для этой и следующих поездок."}, {t:"mem",text:"Сохранено · любит еду · избегает толп"},
      {t:"plan",title:"3 дня в Пекине",tag:"ЧЕРНОВИК",rows:[["Пт","Завтрак в хутунах до приезда групп"],["Сб","Великая стена в Мутяньюй — тихий участок"],["Вс","Храм Неба к открытию, затем урок пельменей"]],foot:"Источники: часы работы · время в пути"},
      {t:"user",q:2,text:"Забронируй урок на двоих. Паспорт ",secret:"E12345678",ph:"<PASSPORT_1>"},
      {t:"shield",text:"Личные данные скрыты до передачи модели"},
      {t:"ask",text:"Воскресенье, 10:00, около ¥300 за двоих. Продолжить?",yes:"Подтвердить",no:"Не сейчас"},
      {t:"sys",text:"<b>JT Agent</b> · сотрудник уточняет бронь",done:"<b>Подтверждено</b> · воскресенье, 10:00 добавлено в план"}
    ],
    sights: [["Великая стена","Пекин"],["Запретный город","Пекин"],["Ночной Бунд","Шанхай"],["Терракотовая армия","Сиань"],["Хуаншань","Аньхой"],["Храм Неба","Пекин"],["Большие панды","Чэнду"],["Дворец Потала","Лхаса"],["Красные фонари","Новый год по лунному календарю"]]
  };
  T.es = {
    ...T.en,
    heroTitle: "Tu asistente para <i>cada día</i> en China.",
    heroLede: "CJ Agent resuelve dudas, organiza tus días y ayuda con las reservas. JT Agent recurre a una persona si hace falta llamar o comprobar algo allí. Tus datos personales se ocultan antes de enviarlos al modelo.",
    soon: "Próximamente en iPhone · inglés y chino", online: "Tu asistente personal", inputHint: "Pregunta sobre tu viaje…",
    agentsTitle: "Dos agentes, <i>un viaje sin complicaciones.</i>", cjTag: "Resuelve dudas. Organiza tus días. Te ayuda a actuar.",
    cjA: "Respuestas", cjAText: "Cómo pagar, tomar un tren o comprar entradas: pasos prácticos con fuentes que puedes consultar.",
    cjP: "Planes", cjPText: "Un plan diario según tus intereses, presupuesto y ritmo. Lo que ya confirmaste se respeta al hacer cambios.",
    cjE: "Acciones", cjEText: "Ayuda con reservas y gestiones. Cualquier gasto o cambio de itinerario requiere tu aprobación.",
    jtTag: "Una persona interviene cuando una respuesta no basta.", jt1: "Detecta cambios de vuelo, reservas que no aparecen o dudas sin resolver.", jt2: "Abre un caso privado con solo los datos necesarios.", jt3: "Un miembro del equipo comprueba los detalles y contacta con el hotel, recinto o proveedor.", jt4: "El resultado y el siguiente paso vuelven al mismo chat.",
    privTitle: "Tus datos <i>siguen siendo tuyos.</i>", privLede: "Nombres, pasaportes, teléfonos, correos y ubicaciones precisas se sustituyen por etiquetas antes de que el modelo los lea.", priv1: "El equipo ve casos anonimizados con un número aleatorio, no tu cuenta.", priv2: "Los datos solo se revelan cuando son necesarios, por tiempo limitado y con registro de acceso.", priv3: "Puedes consultar, corregir o borrar lo que se recuerda de ti.",
    you: "Tú", modelSees: "Lo que ve el modelo", s1: "Te recuerda", s1t: "Tus preferencias continúan entre chats y viajes.", s2: "Cita sus fuentes", s2t: "Consejos verificables, sin conjeturas.", s3: "Protege tus planes", s3t: "Lo confirmado no cambia sin tu permiso.", s4: "Inglés y 中文", s4t: "Cambia de idioma en la misma conversación.",
    appTitle: "G2C para iPhone, <i>muy pronto.</i>", appLede: "Las primeras plazas serán por invitación. Deja tu correo y te avisaremos cuando haya una para ti.", footTag: "Tu asistente personal para China.", sightsTitle: "De la Gran Muralla al Bund, <i>conoce el camino.</i>",
    redact: [["Hola, soy ",null],["Ana García","<NAME_1>"],[". Pasaporte ",null],["E12345678","<PASSPORT_1>"],[", teléfono ",null],["+44 7700 900123","<PHONE_1>"],[". Estoy en ",null],["la puerta 3 del Hotel Lotus","<LOCATION_1>"],[".",null]],
    suggest: ["Pagar en China", "3 días en Pekín", "Reservar una clase"],
    chat: [
      {t:"hello",text:"¡Hola! Soy CJ, tu asistente personal para China. ¿En qué te ayudo?"},
      {t:"user",q:0,draft:"¿Necesito efectivo",text:"¿Cómo puedo pagar sin efectivo?"},
      {t:"bot",text:"Lo habitual es usar Alipay o WeChat Pay. Ambos permiten vincular Visa y Mastercard extranjeras. Conviene configurarlos antes de volar; te guío paso a paso.",src:"Fuente: guías oficiales de Alipay y WeChat Pay"},
      {t:"user",q:1,draft:"Organiza tres días",text:"Llego a Pekín el viernes para 3 días. Me encanta comer y evito las multitudes."},
      {t:"bot",text:"Lo recordaré para este viaje y los siguientes."},{t:"mem",text:"Guardado · le gusta comer · evita multitudes"},
      {t:"plan",title:"3 días en Pekín",tag:"BORRADOR",rows:[["Vie","Desayuno por los hutong antes de los grupos"],["Sáb","Gran Muralla en Mutianyu, por el tramo tranquilo"],["Dom","Templo del Cielo al abrir y clase de jiaozi"]],foot:"Fuentes: horarios oficiales · tiempos de traslado"},
      {t:"user",q:2,text:"Reserva la clase para dos. Pasaporte ",secret:"E12345678",ph:"<PASSPORT_1>"},{t:"shield",text:"Datos ocultos antes de llegar al modelo"},
      {t:"ask",text:"Domingo a las 10:00, unos ¥300 para dos. ¿Sigo?",yes:"Confirmar",no:"Ahora no"},
      {t:"sys",text:"<b>JT Agent</b> · el equipo confirma con el local",done:"<b>Confirmado</b> · domingo a las 10:00 añadido al viaje"}
    ],
    sights: [["Gran Muralla","Pekín"],["Ciudad Prohibida","Pekín"],["El Bund de noche","Shanghái"],["Ejército de terracota","Xi'an"],["Huangshan","Anhui"],["Templo del Cielo","Pekín"],["Pandas gigantes","Chengdu"],["Palacio de Potala","Lhasa"],["Farolillos rojos","Año Nuevo lunar"]]
  };
  T.fr = {
    ...T.en,
    heroTitle: "Votre assistant pour <i>chaque jour</i> en Chine.",
    heroLede: "CJ Agent répond à vos questions, organise vos journées et aide aux réservations. JT Agent fait intervenir une personne lorsqu’un appel ou une vérification sur place est nécessaire. Vos données personnelles sont masquées avant tout envoi au modèle.",
    soon: "Bientôt sur iPhone · anglais et chinois", online: "Votre assistant personnel", inputHint: "Posez une question sur votre voyage…",
    agentsTitle: "Deux agents, <i>un voyage serein.</i>", cjTag: "Des réponses, des itinéraires et une aide concrète.",
    cjA: "Réponses", cjAText: "Payer, prendre le train ou acheter un billet : des étapes pratiques avec des sources vérifiables.", cjP: "Itinéraires", cjPText: "Un programme quotidien adapté à vos envies, votre budget et votre rythme. Les dispositions confirmées sont préservées lors des changements.", cjE: "Actions", cjEText: "Une aide pour les réservations et leur suivi. Toute dépense ou modification du voyage attend votre accord.",
    jtTag: "Une personne prend le relais quand une réponse ne suffit pas.", jt1: "Repère un vol modifié, une réservation introuvable ou une question non résolue.", jt2: "Ouvre un dossier privé avec les seules informations nécessaires.", jt3: "Un membre de l’équipe vérifie les détails et contacte l’hôtel, le lieu ou le prestataire.", jt4: "Le résultat et la prochaine étape reviennent dans la même conversation.",
    privTitle: "Vos données <i>restent les vôtres.</i>", privLede: "Noms, passeports, téléphones, e-mails et positions précises sont remplacés par des balises avant que le modèle ne les lise.", priv1: "L’équipe voit un dossier anonymisé avec un numéro aléatoire, jamais votre compte.", priv2: "Un accès aux données n’est accordé que si nécessaire, pour une durée limitée et avec traçabilité.", priv3: "Consultez, corrigez ou supprimez les informations mémorisées à tout moment.",
    you: "Vous", modelSees: "Ce que voit le modèle", s1: "Se souvient de vous", s1t: "Vos préférences suivent vos conversations et voyages.", s2: "Cite ses sources", s2t: "Des conseils vérifiables, sans devinettes.", s3: "Protège vos projets", s3t: "Rien de confirmé ne change sans votre accord.", s4: "Anglais et 中文", s4t: "Changez de langue dans la même conversation.",
    appTitle: "G2C sur iPhone, <i>bientôt disponible.</i>", appLede: "Les premières places seront sur invitation. Laissez votre e-mail : nous vous préviendrons lorsqu’une place se libère.", footTag: "Votre assistant personnel pour la Chine.", sightsTitle: "De la Grande Muraille au Bund, <i>il connaît le chemin.</i>",
    redact: [["Bonjour, je suis ",null],["Emma Martin","<NAME_1>"],[". Passeport ",null],["E12345678","<PASSPORT_1>"],[", téléphone ",null],["+44 7700 900123","<PHONE_1>"],[". Je suis à ",null],["l’entrée 3 de l’hôtel Lotus","<LOCATION_1>"],[".",null]],
    suggest: ["Payer en Chine", "3 jours à Pékin", "Réserver un cours"],
    chat: [
      {t:"hello",text:"Bonjour ! Je suis CJ, votre assistant pour la Chine. Posez-moi vos questions."},
      {t:"user",q:0,draft:"Faut-il du liquide",text:"Comment payer sans espèces ?"},
      {t:"bot",text:"Alipay et WeChat Pay sont très utilisés et acceptent les cartes Visa et Mastercard étrangères. Configurez-les avant le départ : je vous guide.",src:"Source : guides officiels Alipay et WeChat Pay"},
      {t:"user",q:1,draft:"Prépare trois jours",text:"J’arrive à Pékin vendredi pour 3 jours. J’aime bien manger, mais pas les foules."},
      {t:"bot",text:"Je le retiens pour ce voyage et les prochains."},{t:"mem",text:"Mémorisé · aime la cuisine · évite les foules"},
      {t:"plan",title:"3 jours à Pékin",tag:"BROUILLON",rows:[["Ven","Petit-déjeuner dans les hutong avant les groupes"],["Sam","Grande Muraille à Mutianyu, côté tranquille"],["Dim","Temple du Ciel à l’ouverture, puis cours de raviolis"]],foot:"Sources : horaires officiels · temps de trajet"},
      {t:"user",q:2,text:"Réserve le cours pour deux. Passeport ",secret:"E12345678",ph:"<PASSPORT_1>"},{t:"shield",text:"Données masquées avant l’envoi au modèle"},
      {t:"ask",text:"Dimanche à 10 h, environ ¥300 pour deux. Je continue ?",yes:"Confirmer",no:"Pas maintenant"},
      {t:"sys",text:"<b>JT Agent</b> · l’équipe vérifie auprès du lieu",done:"<b>Confirmé</b> · dimanche à 10 h ajouté au voyage"}
    ],
    sights: [["Grande Muraille","Pékin"],["Cité interdite","Pékin"],["Le Bund de nuit","Shanghai"],["Armée de terre cuite","Xi'an"],["Huangshan","Anhui"],["Temple du Ciel","Pékin"],["Pandas géants","Chengdu"],["Palais du Potala","Lhassa"],["Lanternes rouges","Nouvel An lunaire"]]
  };
  T.ar = {
    ...T.en,
    heroTitle: "مساعدك الشخصي في <i>كل يوم</i> في الصين.",
    heroLede: "يجيب CJ Agent عن أسئلتك وينظم أيام رحلتك ويساعدك في الحجوزات. ويستعين JT Agent بشخص عند الحاجة إلى مكالمة أو تحقق محلي. تُحجب بياناتك الشخصية قبل إرسالها إلى النموذج.",
    soon: "قريبًا على iPhone · الإنجليزية والصينية", online: "مساعدك الشخصي", inputHint: "اسأل عن رحلتك…",
    agentsTitle: "مساعدان، <i>ورحلة مريحة.</i>", cjTag: "يجيب عن أسئلتك وينظم أيامك ويساعدك على إنجاز خططك.",
    cjA: "إجابات", cjAText: "كيف تدفع أو تستقل القطار أو تحجز تذكرة؟ خطوات عملية مع مصادر يمكنك مراجعتها.", cjP: "خطط", cjPText: "برنامج يومي يناسب اهتماماتك وميزانيتك ووتيرتك، مع الحفاظ على الترتيبات التي أكّدتها عند إجراء تغييرات.", cjE: "مساعدة عملية", cjEText: "مساعدة في الحجز والمتابعة. أي إنفاق أو تغيير في برنامج الرحلة ينتظر موافقتك.",
    jtTag: "يتدخل شخص عندما تحتاج الرحلة إلى أكثر من إجابة.", jt1: "يرصد تغيير الرحلة الجوية أو الحجز المفقود أو السؤال الذي لم يُحل.", jt2: "ينشئ طلب متابعة خاصًا بالمعلومات اللازمة فقط.", jt3: "يتحقق أحد أفراد الفريق من التفاصيل ويتواصل مع الفندق أو المكان أو مقدم الخدمة.", jt4: "تصلك النتيجة والخطوة التالية في المحادثة نفسها.",
    privTitle: "بياناتك <i>تبقى ملكك.</i>", privLede: "تُستبدل الأسماء وأرقام الجوازات والهواتف والبريد والمواقع الدقيقة برموز قبل أن يقرأها النموذج.", priv1: "يرى الفريق طلبًا محجوب البيانات برقم عشوائي، ولا يرى حسابك.", priv2: "لا تُكشف البيانات إلا عند الحاجة ولمدة محدودة، مع تسجيل الوصول إليها.", priv3: "يمكنك عرض المعلومات المحفوظة وتصحيحها أو حذفها متى شئت.",
    you: "أنت", modelSees: "ما يراه النموذج", s1: "يتذكرك", s1t: "تستمر تفضيلاتك بين المحادثات والرحلات.", s2: "يذكر مصادره", s2t: "نصائح يمكنك التحقق منها، لا تخمينات.", s3: "يحمي خططك", s3t: "لا تتغير ترتيباتك المؤكدة دون موافقتك.", s4: "الإنجليزية و中文", s4t: "بدّل اللغة ضمن المحادثة نفسها.",
    appTitle: "G2C على iPhone، <i>قريبًا.</i>", appLede: "ستتاح المقاعد الأولى بدعوات للمسافرين. اترك بريدك لنخبرك عندما يتاح لك مكان.", footTag: "مساعدك الشخصي في الصين.", sightsTitle: "من سور الصين إلى البوند، <i>يعرف الطريق.</i>",
    redact: [["مرحبًا، أنا ",null],["سارة أحمد","<NAME_1>"],[". جواز سفري ",null],["E12345678","<PASSPORT_1>"],["، وهاتفي ",null],["+44 7700 900123","<PHONE_1>"],[". أنا عند ",null],["البوابة 3 في فندق لوتس","<LOCATION_1>"],[".",null]],
    suggest: ["الدفع في الصين", "3 أيام في بكين", "حجز درس"],
    chat: [
      {t:"hello",text:"مرحبًا! أنا CJ، مساعدك الشخصي في الصين. كيف أساعدك؟"},
      {t:"user",q:0,draft:"هل أحتاج إلى النقد",text:"كيف أدفع دون نقود؟"},
      {t:"bot",text:"يشيع استخدام Alipay وWeChat Pay، وكلاهما يدعم بطاقات Visa وMastercard الأجنبية. من الأفضل إعدادهما قبل السفر، وسأرشدك خطوة بخطوة.",src:"المصدر: أدلة Alipay وWeChat Pay الرسمية"},
      {t:"user",q:1,draft:"خطط لثلاثة أيام",text:"أصل إلى بكين الجمعة لثلاثة أيام. أحب الطعام وأتجنب الزحام."},
      {t:"bot",text:"سأتذكر ذلك لهذه الرحلة والرحلات القادمة."},{t:"mem",text:"تم الحفظ · يحب الطعام · يتجنب الزحام"},
      {t:"plan",title:"3 أيام في بكين",tag:"مسودة",rows:[["الجمعة","إفطار في أزقة الهوتونغ قبل وصول المجموعات"],["السبت","سور الصين في موتيانيو، في الجزء الأهدأ"],["الأحد","معبد السماء عند الافتتاح، ثم درس لتحضير الزلابية"]],foot:"المصادر: أوقات العمل الرسمية · أوقات التنقل"},
      {t:"user",q:2,text:"احجز الدرس لشخصين. جواز السفر ",secret:"E12345678",ph:"<PASSPORT_1>"},{t:"shield",text:"تُحجب البيانات قبل إرسالها إلى النموذج"},
      {t:"ask",text:"الأحد الساعة 10:00، نحو ¥300 لشخصين. هل أتابع؟",yes:"تأكيد",no:"ليس الآن"},
      {t:"sys",text:"<b>JT Agent</b> · يتواصل الفريق مع المكان للتأكيد",done:"<b>تم التأكيد</b> · أضيف الأحد الساعة 10:00 إلى رحلتك"}
    ],
    sights: [["سور الصين العظيم","بكين"],["المدينة المحرمة","بكين"],["البوند ليلًا","شنغهاي"],["جيش التيراكوتا","شيآن"],["هوانغشان","آنهوي"],["معبد السماء","بكين"],["الباندا العملاقة","تشنغدو"],["قصر بوتالا","لاسا"],["الفوانيس الحمراء","رأس السنة القمرية"]]
  };

  const LANGUAGES = ["en", "zh", "ru", "es", "ar", "fr"];
  const browserLanguage = (navigator.language || "en").toLowerCase().split("-")[0];
  let lang = LANGUAGES.includes(browserLanguage) ? browserLanguage : "en";
  try {
    const saved = localStorage.getItem("g2c-lang");
    if (LANGUAGES.includes(saved)) lang = saved;
  } catch (_) { /* storage unavailable */ }

  const $ = (s, r = document) => r.querySelector(s);
  const el = (tag, cls, html) => { const n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; return n; };
  const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function applyLang() {
    const d = T[lang];
    document.documentElement.lang = lang === "zh" ? "zh-CN" : lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    document.title = "go2china.space — " + d.footTag;
    document.querySelectorAll("[data-i18n]").forEach((n) => { n.textContent = d[n.dataset.i18n]; });
    document.querySelectorAll("[data-i18n-html]").forEach((n) => { n.innerHTML = d[n.dataset.i18nHtml]; });
    $("#lang-select").value = lang;
    const formLanguage = lang === "zh" ? "zh-CN" : lang;
    document.querySelectorAll("a.btn").forEach((a) => {
      a.href = "https://form.jotform.com/263094082842055?language=" + formLanguage;
    });
    startChat();
    startRedact();
    renderSights();
  }

  $("#lang-select").addEventListener("change", (event) => {
    lang = event.target.value;
    try { localStorage.setItem("g2c-lang", lang); } catch (_) { /* ignore */ }
    applyLang();
  });

  /* ---------- Chat demo (scripted animation, no real conversation) ---------- */
  const chat = $("#chat");
  let timers = [];
  let run = 0;
  const later = (fn, ms) => { timers.push(setTimeout(fn, ms)); };
  const clear = () => { timers.forEach(clearTimeout); timers = []; };

  const ICON_MEM = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M8 2l1.8 3.7 4 .6-2.9 2.8.7 4L8 11.2 4.4 13l.7-4L2.2 6.3l4-.6z"/></svg>';
  const ICON_SHIELD = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M8 1.8l5 2v4c0 3-2.2 5.4-5 6.4-2.8-1-5-3.4-5-6.4v-4z"/><path d="M5.8 8.2l1.6 1.6 3-3.2"/></svg>';

  function scrollChat() {
    // Keep the latest message in view by trimming from the top.
    while (chat.scrollHeight > chat.clientHeight + 2 && chat.children.length > 1) chat.removeChild(chat.firstChild);
  }

  function typing(cb, ms = 900) {
    const t = el("div", "msg bot typing", "<i></i><i></i><i></i>");
    chat.appendChild(t); scrollChat();
    later(() => { t.remove(); cb(); }, ms);
  }

  function render(step) {
    let n;
    switch (step.t) {
      case "user":
        n = el("div", "msg user", esc(step.text));
        if (step.secret) {
          const m = el("span", "mask", esc(step.secret));
          n.appendChild(m);
          later(() => { m.textContent = step.ph; m.classList.add("on"); }, 900);
        }
        break;
      case "hello":
      case "bot": n = el("div", "msg bot", esc(step.text) + (step.src ? `<span class="src">${esc(step.src)}</span>` : "")); break;
      case "mem": n = el("div", "chip mem", ICON_MEM + esc(step.text)); break;
      case "shield": n = el("div", "chip shield", ICON_SHIELD + esc(step.text)); break;
      case "plan":
        n = el("div", "plan",
          `<header>${esc(step.title)}<small>${esc(step.tag)}</small></header><ul>` +
          step.rows.map(([d, x]) => `<li><b>${esc(d)}</b><span>${esc(x)}</span></li>`).join("") +
          `</ul><footer>${esc(step.foot)}</footer>`);
        break;
      case "ask":
        n = el("div", "msg bot", `${esc(step.text)}<div class="actions"><span class="yes">${esc(step.yes)}</span><span>${esc(step.no)}</span></div>`);
        later(() => { const y = n.querySelector(".yes"); if (y) y.classList.add("pressed"); }, 1300);
        break;
      case "sys":
        n = el("div", "sys", `<span class="spin"></span><span class="txt">${step.text}</span>`);
        later(() => { n.classList.add("done"); n.querySelector(".txt").innerHTML = step.done; }, 2400);
        break;
    }
    chat.appendChild(n);
    scrollChat();
    // content inside may grow (plan rows); trim again after it settles
    later(scrollChat, 700);
  }

  const inputBox = document.querySelector(".chat-input");
  const typedEl = $("#typed"), sendEl = $("#send"), suggestEl = $("#suggest");

  function renderSuggest() {
    suggestEl.innerHTML = T[lang].suggest.map((x) => `<span>${esc(x)}</span>`).join("");
  }
  function pick(q) {
    suggestEl.querySelectorAll("span").forEach((n, k) => n.classList.toggle("on", k === q));
  }
  function typeText(text, cb, speed = 48) {
    let k = typedEl.textContent.length;
    const tick = () => {
      if (k >= text.length) { cb(); return; }
      typedEl.textContent = text.slice(0, ++k);
      later(tick, speed + Math.random() * 40);
    };
    tick();
  }
  function deleteText(cb, speed = 26) {
    const tick = () => {
      const v = typedEl.textContent;
      if (!v.length) { cb(); return; }
      typedEl.textContent = v.slice(0, -1);
      later(tick, speed);
    };
    later(tick, 450);
  }
  function composeAndSend(step, done) {
    const full = step.text + (step.secret || "");
    pick(step.q);
    inputBox.classList.add("busy");
    typedEl.textContent = "";
    const finish = () => later(() => {
      sendEl.classList.add("tap");
      later(() => {
        sendEl.classList.remove("tap");
        typedEl.textContent = "";
        inputBox.classList.remove("busy");
        pick(-1);
        done();
      }, 180);
    }, 450);
    later(() => {
      if (step.draft) typeText(step.draft, () => deleteText(() => typeText(full, finish)));
      else typeText(full, finish);
    }, 500);
  }

  const GAP = { hello: 900, user: 1500, bot: 1300, mem: 1100, plan: 2600, shield: 1300, ask: 1900, sys: 4200 };

  function startChat() {
    clear();
    run++;
    const my = run;
    chat.classList.remove("fade");
    chat.innerHTML = "";
    typedEl.textContent = "";
    inputBox.classList.remove("busy");
    renderSuggest();
    const steps = T[lang].chat;

    if (reduced) { steps.slice(-6).forEach((s) => render(s)); clear(); return; }

    let i = 0;
    const next = () => {
      if (my !== run) return;
      if (i >= steps.length) {
        later(() => { chat.classList.add("fade"); later(startChat, 600); }, 2600);
        return;
      }
      const s = steps[i++];
      const go = () => { render(s); later(next, GAP[s.t] || 1300); };
      if (s.t === "bot" || s.t === "plan" || s.t === "ask") typing(go, s.t === "plan" ? 1200 : 850);
      else if (s.t === "user") composeAndSend(s, () => { render(s); later(next, 700); });
      else go();
    };
    later(next, 500);
  }

  /* ---------- Redaction demo ---------- */
  let redactTimers = [];
  function startRedact() {
    redactTimers.forEach(clearTimeout); redactTimers = [];
    const parts = T[lang].redact;
    const inEl = $("#redact-text"), outEl = $("#redact-out");
    inEl.innerHTML = parts.map(([s, ph]) => ph ? `<span class="tok">${esc(s)}</span>` : esc(s)).join("");
    const build = (stage) => parts.map(([s, ph], idx) => {
      if (!ph) return esc(s);
      const k = parts.slice(0, idx + 1).filter((p) => p[1]).length;
      return k <= stage ? `<span class="tok ph">${esc(ph)}</span>` : `<span class="tok">${esc(s)}</span>`;
    }).join("");
    const total = parts.filter((p) => p[1]).length;
    outEl.innerHTML = build(reduced ? total : 0);
    if (reduced) return;
    const toks = () => inEl.querySelectorAll(".tok");
    const cycle = () => {
      outEl.innerHTML = build(0);
      toks().forEach((t) => t.classList.remove("hot"));
      for (let k = 1; k <= total; k++) {
        redactTimers.push(setTimeout(() => {
          toks().forEach((t, j) => t.classList.toggle("hot", j === k - 1));
          outEl.innerHTML = build(k);
        }, 900 * k));
      }
      redactTimers.push(setTimeout(() => toks().forEach((t) => t.classList.remove("hot")), 900 * total + 700));
      redactTimers.push(setTimeout(cycle, 900 * total + 3400));
    };
    cycle();
  }

  /* ---------- Reveal + JT flow ---------- */
  const revealTargets = document.querySelectorAll(".section-title, .agent, .privacy, .strip > div, .app-visual, .app-copy");
  if ("IntersectionObserver" in window && !reduced) {
    revealTargets.forEach((n) => n.classList.add("reveal"));
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (!e.isIntersecting) return;
        e.target.classList.add("in");
        if (e.target.classList.contains("agent-jt")) {
          e.target.querySelectorAll(".flow li").forEach((li, k) => setTimeout(() => li.classList.add("lit"), 400 + k * 450));
        }
        io.unobserve(e.target);
      });
    }, { threshold: 0.18 });
    revealTargets.forEach((n) => io.observe(n));
  } else {
    document.querySelectorAll(".flow li").forEach((li) => li.classList.add("lit"));
  }

  /* ---------- Sights ---------- */
  function renderSights() {
    const card = (item) => {
      const [id, en, enSub, zh, zhSub] = item;
      const [name, region] = T[lang].sights ? T[lang].sights[SIGHTS.indexOf(item)] : (lang === "zh" ? [zh, zhSub] : [en, enSub]);
      return `<figure class="sight"><img src="assets/sights/${id}.webp" alt="${esc(name)}" loading="lazy" width="1024" height="683">` +
        `<figcaption><strong>${esc(name)}</strong><span>${esc(region)}</span></figcaption></figure>`;
    };
    const a = SIGHTS.slice(0, 5), b = SIGHTS.slice(5);
    const row = (items, cls) => `<div class="track${cls}">${items.map(card).join("")}${items.map(card).join("").replace(/<img /g, '<img aria-hidden="true" ')}</div>`;
    $("#marquee").innerHTML = row(a, "") + row(b, " rev");
  }

  $("#year").textContent = String(new Date().getFullYear());
  applyLang();
})();
