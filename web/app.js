(() => {
  "use strict";

  // Waitlist sign-ups go to FormSubmit (https://formsubmit.co), which emails each entry to CONTACT
  // as a table. The very first submission triggers a one-time activation email to CONTACT; entries
  // arrive after that link is clicked. To use another form service, point WAITLIST_ENDPOINT at any
  // HTTPS endpoint that accepts a JSON POST and answers 2xx.
  const CONTACT = "hello@go2china.space";
  const WAITLIST_ENDPOINT = "https://formsubmit.co/ajax/" + CONTACT;

  // Form options: [value sent to the sheet (English), English label, 中文 label]
  const OPTS = {
    source: [["Friend or family", "Friend or family", "亲友推荐"], ["Instagram", "Instagram", "Instagram"], ["TikTok", "TikTok", "TikTok"],
      ["YouTube", "YouTube", "YouTube"], ["Xiaohongshu (RED)", "Xiaohongshu (RED)", "小红书"], ["Reddit", "Reddit", "Reddit"],
      ["Search engine", "Google or other search", "搜索引擎"], ["News or blog", "News or blog", "新闻或博客"], ["Event", "Event or meetup", "活动或聚会"], ["Other", "Other", "其他"]],
    optWhen: [["Within 3 months", "Within 3 months", "3 个月内"], ["3-6 months", "3–6 months", "3–6 个月"], ["6-12 months", "6–12 months", "6–12 个月"], ["Not sure yet", "Not sure yet", "还没定"], ["Already in China", "I'm in China now", "我已在中国"]],
    optWho: [["Solo", "Solo", "独自"], ["Partner", "With a partner", "伴侣"], ["Family with kids", "Family with kids", "带孩子的家庭"], ["Friends", "Friends", "朋友"], ["Business", "Business", "商务"]],
    optCities: [["Beijing", "Beijing", "北京"], ["Shanghai", "Shanghai", "上海"], ["Xi'an", "Xi'an", "西安"], ["Chengdu", "Chengdu", "成都"], ["Guilin", "Guilin", "桂林"],
      ["Hangzhou", "Hangzhou", "杭州"], ["Guangzhou & Shenzhen", "Guangzhou & Shenzhen", "广州与深圳"], ["Yunnan", "Yunnan", "云南"], ["Tibet", "Tibet", "西藏"], ["Not sure yet", "Not sure yet", "还没想好"]],
    optHelp: [["Payments", "Paying with apps", "移动支付"], ["Getting around", "Getting around", "交通出行"], ["Itinerary", "Planning the itinerary", "规划行程"],
      ["Booking", "Booking tickets & tables", "预订门票与餐厅"], ["Food", "Finding great food", "找美食"], ["Language", "Language help", "语言沟通"], ["Visa & entry", "Visa & entry", "签证与入境"], ["Emergencies", "Help in an emergency", "紧急求助"]]
  };

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
      cta: "Join Waitlist",
      heroTitle: "A personal agent for <i>every day</i> in China.",
      heroLede: "CJ Agent answers, plans and gets things done. JT Agent quietly brings in a real person when it matters. And your personal details are redacted before any model sees them.",
      soon: "Coming soon on iPhone · English & 中文",
      online: "Your personal agent",
      inputHint: "Ask anything about your trip…",
      agentsTitle: "Two agents, <i>one trip</i> that just works.",
      cjTag: "Talks with you. Thinks ahead. Takes action.",
      cjA: "Answers", cjAText: "Payments, transit, tickets, food — clear answers in plain English, with sources you can check.",
      cjP: "Plans", cjPText: "Day-by-day itineraries shaped by what it remembers about you, and kept safe once you confirm them.",
      cjE: "Acts", cjEText: "Turns the plan into done — and anything that spends money or changes your trip waits for your OK.",
      jtTag: "Watches your back, and brings in a real person when AI isn't enough.",
      jt1: "Spots what needs attention — a changed flight, a hotel that can't find you, a question going in circles.",
      jt2: "Opens a private case with only the details that step needs.",
      jt3: "A teammate verifies, calls, confirms — no queue, no “please hold”.",
      jt4: "You simply get the result, back in your chat.",
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
      sightsTitle: "From the Great Wall to the Bund, <i>it knows the way.</i>",
      wlTitle: "Join the waitlist", wlLede: "A few quick questions so we can shape G2C around your trip.",
      fName: "Name", fNamePh: "Your name", fEmail: "Email", fCountry: "Where are you from?", fCountryPh: "Country or region",
      fSource: "How did you hear about us?", fSourcePh: "Choose one", fWhen: "When are you planning to visit China?",
      fWho: "Who are you traveling with?", fCities: "Where would you like to go?", fHelp: "What would help you most?",
      fNote: "Anything else we should know? (optional)",
      bad: "Please add your name, a valid email and how you heard about us.",
      sending: "Sending…",
      ok: "You're on the list! We'll email you when your spot opens.",
      fail: "Something went wrong. Please try again, or email " + CONTACT + ".",
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
      cta: "加入候补名单",
      heroTitle: "在中国的<i>每一天</i>，都有你的私人助理。",
      heroLede: "CJ Agent 为你解答、规划、办成事；JT Agent 在关键时刻悄悄请真人接手。你的个人信息在任何模型看到之前就已脱敏。",
      soon: "即将登陆 iPhone · 中文 & English",
      online: "你的私人助理",
      inputHint: "问问关于行程的任何事…",
      agentsTitle: "两个 Agent，<i>一趟</i>省心的旅程。",
      cjTag: "陪你聊，替你想，帮你办。",
      cjA: "解答", cjAText: "支付、交通、门票、美食——清楚直接的回答，附上可以核对的来源。",
      cjP: "规划", cjPText: "根据它记住的你来安排每日行程；一经确认，就被妥善保护。",
      cjE: "执行", cjEText: "把计划变成现实——凡是花钱或改变行程的事，都先等你点头。",
      jtTag: "在背后守护你，AI 搞不定时请真人接手。",
      jt1: "识别需要处理的情况——航班变动、酒店查不到订单、问题反复没解决。",
      jt2: "建立独立工单，只带这一步需要的信息。",
      jt3: "团队成员核实、致电、确认——不排队，不用“请稍候”。",
      jt4: "你只需在对话里收到结果。",
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
      sightsTitle: "从长城到外滩，<i>它都熟门熟路。</i>",
      wlTitle: "加入候补名单", wlLede: "回答几个小问题，帮我们把 G2C 做得更贴合你的旅程。",
      fName: "称呼", fNamePh: "你的名字", fEmail: "邮箱", fCountry: "你来自哪里？", fCountryPh: "国家或地区",
      fSource: "你从哪里了解到我们？", fSourcePh: "请选择", fWhen: "计划什么时候来中国？",
      fWho: "和谁一起出行？", fCities: "想去哪些地方？", fHelp: "最需要哪方面的帮助？",
      fNote: "还有什么想告诉我们的？（选填）",
      bad: "请填写称呼、有效邮箱，并选择了解渠道。",
      sending: "提交中…",
      ok: "已加入候补名单！名额开放时我们会发邮件通知你。",
      fail: "提交失败，请重试，或发邮件至 " + CONTACT + "。",
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

  let lang = "en";
  try {
    const saved = localStorage.getItem("g2c-lang");
    if (saved === "en" || saved === "zh") lang = saved;
    else if ((navigator.language || "").toLowerCase().startsWith("zh")) lang = "zh";
  } catch (_) { /* storage unavailable */ }

  const $ = (s, r = document) => r.querySelector(s);
  const el = (tag, cls, html) => { const n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; return n; };
  const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function applyLang() {
    const d = T[lang];
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
    document.querySelectorAll("[data-i18n]").forEach((n) => { n.textContent = d[n.dataset.i18n]; });
    document.querySelectorAll("[data-i18n-html]").forEach((n) => { n.innerHTML = d[n.dataset.i18nHtml]; });
    document.querySelectorAll("[data-i18n-ph]").forEach((n) => { n.placeholder = d[n.dataset.i18nPh]; });
    $("#lang-toggle").textContent = lang === "zh" ? "EN" : "中文";
    $("#form-note").textContent = "";
    startChat();
    startRedact();
    renderSights();
    renderOptions();
  }

  $("#lang-toggle").addEventListener("click", () => {
    lang = lang === "zh" ? "en" : "zh";
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
    const card = ([id, en, enSub, zh, zhSub]) =>
      `<figure class="sight"><img src="assets/sights/${id}.webp" alt="${esc(lang === "zh" ? zh : en)}" loading="lazy" width="1024" height="683">` +
      `<figcaption><strong>${esc(lang === "zh" ? zh : en)}</strong><span>${esc(lang === "zh" ? zhSub : enSub)}</span></figcaption></figure>`;
    const a = SIGHTS.slice(0, 5), b = SIGHTS.slice(5);
    const row = (items, cls) => `<div class="track${cls}">${items.map(card).join("")}${items.map(card).join("").replace(/<img /g, '<img aria-hidden="true" ')}</div>`;
    $("#marquee").innerHTML = row(a, "") + row(b, " rev");
  }

  /* ---------- Waitlist ---------- */
  const modal = $("#waitlist-modal"), form = $("#waitlist-form"), note = $("#form-note"), submitBtn = $("#wl-submit");
  const label = (o) => (lang === "zh" ? o[2] : o[1]);

  function renderOptions() {
    const sel = $("#f-source"), cur = sel.value;
    sel.innerHTML = `<option value="" disabled ${cur ? "" : "selected"}>${esc(T[lang].fSourcePh)}</option>` +
      OPTS.source.map((o) => `<option value="${esc(o[0])}" ${o[0] === cur ? "selected" : ""}>${esc(label(o))}</option>`).join("");
    form.querySelectorAll(".opts").forEach((box) => {
      const picked = new Set([...box.querySelectorAll("input:checked")].map((i) => i.value));
      box.innerHTML = OPTS[box.dataset.key].map((o) =>
        `<label><input type="${box.dataset.type}" name="${box.dataset.name}" value="${esc(o[0])}" ${picked.has(o[0]) ? "checked" : ""}><span>${esc(label(o))}</span></label>`).join("");
    });
  }

  function openModal(e) {
    if (e) e.preventDefault();
    if (typeof modal.showModal === "function") modal.showModal(); else modal.setAttribute("open", "");
    const first = form.querySelector('input[name="name"]'); if (first && !form.classList.contains("sent")) first.focus();
  }
  const closeModal = () => { if (modal.close) modal.close(); else modal.removeAttribute("open"); };
  document.querySelectorAll("[data-open-waitlist]").forEach((a) => a.addEventListener("click", openModal));
  $("#wl-close").addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });
  if (location.hash === "#waitlist") setTimeout(openModal, 300);

  form.addEventListener("input", (e) => { const f = e.target.closest(".f"); if (f) f.classList.remove("bad"); });
  const params = new URLSearchParams(location.search);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const d = T[lang];
    const fd = new FormData(form);
    if (fd.get("_honey")) return;
    const name = String(fd.get("name") || "").trim();
    const email = String(fd.get("email") || "").trim();
    const source = String(fd.get("source") || "");
    form.querySelectorAll(".f").forEach((f) => f.classList.remove("bad"));
    const bad = [];
    if (!name) bad.push('input[name="name"]');
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) bad.push('input[name="email"]');
    if (!source) bad.push('select[name="source"]');
    note.classList.remove("err");
    if (bad.length) {
      bad.forEach((q) => form.querySelector(q).closest(".f").classList.add("bad"));
      note.textContent = d.bad; note.classList.add("err"); form.querySelector(bad[0]).focus(); return;
    }
    const all = (k) => fd.getAll(k).join(", ");
    const payload = {
      name, email, source,
      country: String(fd.get("country") || "").trim(),
      travel_time: all("travel_time"), travel_party: all("travel_party"),
      destinations: all("destinations"), needs: all("needs"),
      note: String(fd.get("note") || "").trim(),
      language: lang,
      utm_source: params.get("utm_source") || "", utm_medium: params.get("utm_medium") || "", utm_campaign: params.get("utm_campaign") || "",
      referrer: document.referrer || "",
      _subject: "G2C waitlist: " + name, _template: "table", _captcha: "false"
    };
    submitBtn.disabled = true; note.textContent = d.sending;
    try {
      const r = await fetch(WAITLIST_ENDPOINT, { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(payload) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || String(j.success) === "false") throw new Error(String(r.status));
      form.classList.add("sent"); note.textContent = d.ok; form.reset();
    } catch (_) {
      note.textContent = d.fail; note.classList.add("err");
    } finally { submitBtn.disabled = false; }
  });

  $("#year").textContent = String(new Date().getFullYear());
  applyLang();
})();
