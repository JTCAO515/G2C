(() => {
  "use strict";

  // Set to an HTTPS endpoint that accepts POST {email, lang} to collect sign-ups.
  // Left empty, the form opens a pre-filled email to the team instead.
  const WAITLIST_ENDPOINT = "";
  const CONTACT = "hello@go2china.space";

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
      bad: "Please enter a valid email address.",
      ok: "You're on the list. We'll be in touch soon.",
      okMail: "Your email app should open — just hit send and you're on the list.",
      fail: "Something went wrong. Please email " + CONTACT + ".",
      mailSubject: "Join the G2C waitlist",
      mailBody: "Please add me to the G2C waitlist: ",
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
      bad: "请输入有效的邮箱地址。",
      ok: "已加入候补名单，我们会尽快联系你。",
      okMail: "邮件应用即将打开——点击发送即可加入候补名单。",
      fail: "提交失败，请发邮件至 " + CONTACT + "。",
      mailSubject: "加入 G2C 候补名单",
      mailBody: "请将我加入 G2C 候补名单：",
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

  /* ---------- Waitlist ---------- */
  const form = $("#waitlist-form"), note = $("#form-note"), input = $("#email");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const d = T[lang];
    const email = input.value.trim();
    note.classList.remove("err");
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) { note.textContent = d.bad; note.classList.add("err"); input.focus(); return; }
    if (WAITLIST_ENDPOINT) {
      try {
        const r = await fetch(WAITLIST_ENDPOINT, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, lang }) });
        if (!r.ok) throw new Error(String(r.status));
        note.textContent = d.ok; form.reset();
      } catch (_) { note.textContent = d.fail; note.classList.add("err"); }
      return;
    }
    window.location.href = `mailto:${CONTACT}?subject=${encodeURIComponent(d.mailSubject)}&body=${encodeURIComponent(d.mailBody + email)}`;
    note.textContent = d.okMail;
  });

  $("#year").textContent = String(new Date().getFullYear());
  applyLang();
})();
