(() => {
  "use strict";

  const { T, PLACES } = window.G2C;
  const LANGUAGES = ["en", "zh", "ru", "es", "ar", "fr"];
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Values exactly as the Jotform early access form stores them (the server checks the same lists).
  const VALUES = {
    source: ["Friend or family", "Search", "Instagram", "TikTok", "YouTube", "Xiaohongshu (RED)", "Reddit", "Event", "Other"],
    when: ["Within 3 months", "3–6 months", "6–12 months", "Not sure", "Already in China"],
    dest: ["Beijing", "Shanghai", "Xi’an", "Chengdu", "Guangzhou & Shenzhen", "Not sure"],
    needs: ["Payments", "Transport", "Trip planning", "Booking", "Food", "Language", "Visa & entry"]
  };
  // Backup: the hosted Jotform form. It can be unreachable from mainland China, so it is only offered after a failed send.
  const BACKUP_FORM = "https://form.jotform.com/263094082842055";
  const HERO_PLACE = {
    en: "Jinshanling Great Wall, Hebei", zh: "河北", ru: "Великая стена, Цзиньшаньлин, Хэбэй",
    es: "Gran Muralla en Jinshanling, Hebei", fr: "Grande Muraille à Jinshanling, Hebei", ar: "سور الصين العظيم في جينشانلينغ، خبي"
  };

  const browserLanguage = (navigator.language || "en").toLowerCase().split("-")[0];
  let lang = LANGUAGES.includes(browserLanguage) ? browserLanguage : "en";
  try {
    const saved = localStorage.getItem("g2c-lang");
    if (LANGUAGES.includes(saved)) lang = saved;
  } catch (_) { /* storage unavailable */ }

  const $ = (s, r = document) => r.querySelector(s);
  const el = (tag, cls, html) => { const n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; return n; };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pick = (d, path) => path.split(".").reduce((o, k) => (o == null ? o : o[k]), d);

  function applyLang() {
    const d = T[lang];
    document.documentElement.lang = lang === "zh" ? "zh-CN" : lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    document.title = "go2china.space — " + d.footTag;
    document.querySelectorAll("[data-i18n]").forEach((n) => { const v = pick(d, n.dataset.i18n); if (v != null) n.textContent = v; });
    document.querySelectorAll("[data-i18n-ph]").forEach((n) => { n.placeholder = pick(d, n.dataset.i18nPh) || ""; });
    document.querySelectorAll("[data-list]").forEach((n) => { n.innerHTML = d[n.dataset.list].map((x) => `<li>${esc(x)}</li>`).join(""); });
    $("[data-place='jinshanling']").textContent = HERO_PLACE[lang];
    $("#lang-select").value = lang;
    renderRules();
    renderFormOptions();
    renderWallCaptions();
    startChat();
  }

  $("#lang-select").addEventListener("change", (event) => {
    lang = event.target.value;
    try { localStorage.setItem("g2c-lang", lang); } catch (_) { /* ignore */ }
    applyLang();
  });

  /* ---------- How it works: rules ---------- */
  function renderRules() {
    $("#rules").innerHTML = T[lang].rules.map(([h, p]) => `<div><h4>${esc(h)}</h4><p>${esc(p)}</p></div>`).join("");
  }

  /* ---------- Chat demo (scripted animation, no real conversation) ---------- */
  const chat = $("#chat");
  let timers = [];
  let run = 0;
  const later = (fn, ms) => { timers.push(setTimeout(fn, ms)); };
  const clear = () => { timers.forEach(clearTimeout); timers = []; };

  const ICON_MEM = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M8 2l1.8 3.7 4 .6-2.9 2.8.7 4L8 11.2 4.4 13l.7-4L2.2 6.3l4-.6z"/></svg>';

  function scrollChat() {
    // Keep the latest message in view by trimming from the top.
    while (chat.scrollHeight > chat.clientHeight + 2 && chat.children.length > 1) chat.removeChild(chat.firstChild);
  }

  function typing(cb, ms = 900) {
    const t = el("div", "msg bot typing", "<i></i><i></i><i></i>");
    chat.appendChild(t); scrollChat();
    later(() => { t.remove(); cb(); }, ms);
  }

  // instant: final state now (reduced motion), not a timer that clear() would cancel.
  function render(step, instant = false) {
    const at = instant ? (fn) => fn() : later;
    let n;
    switch (step.t) {
      case "user":
        n = el("div", "msg user", esc(step.text));
        break;
      case "hello":
      case "bot": n = el("div", "msg bot", esc(step.text) + (step.src ? `<span class="src">${esc(step.src)}</span>` : "")); break;
      case "mem": n = el("div", "chip mem", ICON_MEM + esc(step.text)); break;
      case "plan":
        n = el("div", "plan",
          `<header>${esc(step.title)}<small>${esc(step.tag)}</small></header><ul>` +
          step.rows.map(([d, x]) => `<li><b>${esc(d)}</b><span>${esc(x)}</span></li>`).join("") +
          `</ul><footer>${esc(step.foot)}</footer>`);
        break;
    }
    chat.appendChild(n);
    scrollChat();
    // content inside may grow (plan rows); trim again after it settles
    at(scrollChat, 700);
  }

  const inputBox = $(".chat-input");
  const typedEl = $("#typed"), sendEl = $("#send"), suggestEl = $("#suggest");

  function renderSuggest() {
    suggestEl.innerHTML = T[lang].suggest.map((x) => `<span>${esc(x)}</span>`).join("");
  }
  function pickSuggest(q) {
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
    const full = step.text;
    pickSuggest(step.q);
    inputBox.classList.add("busy");
    typedEl.textContent = "";
    const finish = () => later(() => {
      sendEl.classList.add("tap");
      later(() => {
        sendEl.classList.remove("tap");
        typedEl.textContent = "";
        inputBox.classList.remove("busy");
        pickSuggest(-1);
        done();
      }, 180);
    }, 450);
    later(() => {
      if (step.draft) typeText(step.draft, () => deleteText(() => typeText(full, finish)));
      else typeText(full, finish);
    }, 500);
  }

  const GAP = { hello: 900, user: 1500, bot: 1300, mem: 1100, plan: 2600 };

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

    if (reduced) { steps.slice(-6).forEach((s) => render(s, true)); return; }

    let i = 0;
    const next = () => {
      if (my !== run) return;
      if (i >= steps.length) {
        later(() => { chat.classList.add("fade"); later(startChat, 600); }, 2600);
        return;
      }
      const s = steps[i++];
      const go = () => { render(s); later(next, GAP[s.t] || 1300); };
      if (s.t === "bot" || s.t === "plan") typing(go, s.t === "plan" ? 1200 : 850);
      else if (s.t === "user") composeAndSend(s, () => { render(s); later(next, 700); });
      else go();
    };
    later(next, 500);
  }

  /* ---------- Photo wall: one tile at a time swaps to a place not on screen ---------- */
  const wall = $("#wall");
  const TILES = 7;
  const order = PLACES.map((p) => p.id);
  const byId = Object.fromEntries(PLACES.map((p) => [p.id, p]));
  const shown = order.slice(0, TILES);
  let queue = order.slice(TILES);
  const tileEls = [];

  function caption(id) {
    const p = byId[id];
    const [name, region] = p[lang];
    const han = lang === "zh" ? "" : `<span class="han" lang="zh-CN">${esc(p.zh[0])}</span>`;
    return `<b>${esc(name)}</b>${han}<br><span>${esc(region)}</span>`;
  }
  function altText(id) { const [name, region] = byId[id][lang]; return `${name}, ${region}`; }

  shown.forEach((id, i) => {
    const fig = el("figure", "tile");
    const img = el("img");
    img.src = `assets/sights/${id}.webp`; img.alt = altText(id); img.loading = i < 3 ? "eager" : "lazy"; img.decoding = "async";
    const cap = el("figcaption", null, caption(id));
    fig.append(img, cap);
    wall.appendChild(fig);
    tileEls.push({ fig, img, cap, id });
  });

  function renderWallCaptions() {
    tileEls.forEach((t) => { t.cap.innerHTML = caption(t.id); t.img.alt = altText(t.id); });
  }

  let wallVisible = false, swapTimer = null, lastTile = -1;
  function swapOne() {
    const visibleTiles = tileEls.filter((t) => t.fig.offsetParent !== null);
    if (!visibleTiles.length) return;
    let t;
    do { t = visibleTiles[Math.floor(Math.random() * visibleTiles.length)]; } while (visibleTiles.length > 1 && tileEls.indexOf(t) === lastTile);
    lastTile = tileEls.indexOf(t);
    const nextId = queue.shift();
    queue.push(t.id);
    const incoming = el("img");
    incoming.alt = altText(nextId); incoming.decoding = "async"; incoming.className = "out";
    incoming.src = `assets/sights/${nextId}.webp`;
    const show = () => {
      t.fig.insertBefore(incoming, t.cap);
      t.cap.style.opacity = "0";
      requestAnimationFrame(() => requestAnimationFrame(() => incoming.classList.remove("out")));
      setTimeout(() => { t.img.remove(); t.img = incoming; t.id = nextId; t.cap.innerHTML = caption(nextId); t.cap.style.opacity = "1"; }, 1000);
    };
    (incoming.decode ? incoming.decode() : Promise.resolve()).then(show, show);
  }
  function syncWallTimer() {
    const run = wallVisible && !document.hidden && !reduced;
    if (run && !swapTimer) swapTimer = setInterval(swapOne, 2600);
    if (!run && swapTimer) { clearInterval(swapTimer); swapTimer = null; }
  }
  if ("IntersectionObserver" in window) {
    new IntersectionObserver((entries) => { wallVisible = entries[0].isIntersecting; syncWallTimer(); }, { threshold: 0.2 }).observe(wall);
  }
  document.addEventListener("visibilitychange", syncWallTimer);

  /* ---------- Early access form: posts to our own domain, which forwards to Jotform ---------- */
  const form = $("#ea-form"), msg = $("#form-msg"), submit = $("#ea-submit");
  const startedAt = Date.now();

  function renderFormOptions() {
    const d = T[lang];
    const sel = $("#f-source"), cur = sel.value;
    sel.innerHTML = `<option value="" ${cur ? "" : "selected"} disabled>${esc(d.f.sourcePh)}</option>` +
      VALUES.source.map((v, i) => `<option value="${esc(v)}" ${v === cur ? "selected" : ""}>${esc(d.opt.source[i])}</option>`).join("");
    form.querySelectorAll(".chips").forEach((box) => {
      const group = box.dataset.group;
      const picked = new Set([...box.querySelectorAll("input:checked")].map((i) => i.value));
      box.innerHTML = VALUES[group].map((v, i) =>
        `<label><input type="${box.dataset.type}" name="${group}" value="${esc(v)}" ${picked.has(v) ? "checked" : ""}><span>${esc(d.opt[group][i])}</span></label>`).join("") +
        (group === "dest" ? `<label><input type="checkbox" name="destOtherOn" value="1" ${form.elements.destOtherOn && form.elements.destOtherOn.checked ? "checked" : ""}><span>${esc(d.f.other)}</span></label>` : "");
    });
    syncOther();
    msg.textContent = ""; msg.classList.remove("err");
  }
  function syncOther() {
    const on = form.elements.destOtherOn && form.elements.destOtherOn.checked;
    form.elements.destOther.hidden = !on;
  }
  form.addEventListener("change", (e) => { if (e.target.name === "destOtherOn") { syncOther(); if (e.target.checked) form.elements.destOther.focus(); } });
  form.addEventListener("input", (e) => {
    const f = e.target.closest(".field-l"); if (f) f.classList.remove("bad");
    if (msg.classList.contains("err") && !form.querySelector(".field-l.bad")) { msg.textContent = ""; msg.classList.remove("err"); }
  });

  function showError(text) {
    msg.classList.add("err");
    msg.innerHTML = `${esc(text)} <a href="${BACKUP_FORM}?language=${lang === "zh" ? "zh-CN" : lang}" rel="noopener">${esc(T[lang].failAlt)}</a>`;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const d = T[lang];
    const fd = new FormData(form);
    const data = {
      name: String(fd.get("name") || "").trim(),
      email: String(fd.get("email") || "").trim(),
      source: String(fd.get("source") || ""),
      country: String(fd.get("country") || "").trim(),
      when: String(fd.get("when") || ""),
      dest: fd.getAll("dest").map(String),
      destOther: fd.get("destOtherOn") ? String(fd.get("destOther") || "").trim() : "",
      needs: fd.getAll("needs").map(String),
      note: String(fd.get("note") || "").trim(),
      // Required: the application goes to Jotform in the United States. Checked again by the server, not forwarded.
      consentAbroad: form.elements.consentAbroad.checked,
      website: String(fd.get("website") || ""),
      elapsedMs: Date.now() - startedAt,
      lang
    };
    form.querySelectorAll(".field-l").forEach((f) => f.classList.remove("bad"));
    const bad = [];
    if (!data.name) bad.push("name");
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(data.email)) bad.push("email");
    if (!data.source) bad.push("source");
    if (!data.consentAbroad) bad.push("consentAbroad");
    msg.classList.remove("err");
    if (bad.length) {
      bad.forEach((n) => form.elements[n].closest(".field-l").classList.add("bad"));
      const text = [bad.some((n) => n !== "consentAbroad") ? d.bad : "", data.consentAbroad ? "" : d.eaAbroadBad];
      msg.classList.add("err"); msg.textContent = text.filter(Boolean).join(lang === "zh" ? "" : " "); form.elements[bad[0]].focus();
      return;
    }
    submit.disabled = true; msg.textContent = d.sending;
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 15000);
      const r = await fetch("/api/early-access", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data), signal: ctrl.signal
      });
      clearTimeout(timer);
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.ok) throw new Error(String(r.status));
      form.classList.add("sent"); msg.classList.remove("err"); msg.textContent = d.ok;
    } catch (_) {
      showError(d.fail);
    } finally {
      submit.disabled = false;
    }
  });

  $("#year").textContent = String(new Date().getFullYear());
  applyLang();
})();
