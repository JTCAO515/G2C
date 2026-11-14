(() => {
  "use strict";

  const { T, SCENES, PLACES } = window.G2C;
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
    renderWatch();
    renderRules();
    renderTabs();
    renderScene();
    renderFormOptions();
    renderWallCaptions();
    startChat();
    startRedact();
  }

  $("#lang-select").addEventListener("change", (event) => {
    lang = event.target.value;
    try { localStorage.setItem("g2c-lang", lang); } catch (_) { /* ignore */ }
    applyLang();
  });

  /* ---------- How it works: table and rules ---------- */
  function renderWatch() {
    const d = T[lang];
    $("#watch-head").innerHTML = d.cols.map((c) => `<th scope="col">${esc(c)}</th>`).join("");
    $("#watch-body").innerHTML = d.watch.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("");
  }
  function renderRules() {
    $("#rules").innerHTML = T[lang].rules.map(([h, p]) => `<div><h4>${esc(h)}</h4><p>${esc(p)}</p></div>`).join("");
  }

  /* ---------- Scenario tabs (move only when the visitor picks a tab) ---------- */
  const SCENE_KEYS = ["hotel", "train", "sos"];
  let scene = "hotel";
  function renderTabs() {
    const tabs = $("#scene-tabs");
    tabs.innerHTML = T[lang].tabs.map((label, i) => {
      const on = SCENE_KEYS[i] === scene;
      return `<button type="button" role="tab" id="tab-${SCENE_KEYS[i]}" aria-controls="scene" aria-selected="${on}" tabindex="${on ? 0 : -1}" data-scene="${SCENE_KEYS[i]}">${esc(label)}</button>`;
    }).join("");
  }
  function renderScene() {
    const d = T[lang];
    const texts = d.scenes[scene].steps;
    $("#scene").setAttribute("aria-labelledby", "tab-" + scene);
    $("#scene-steps").innerHTML = SCENES[scene].map((s, i) => {
      const lane = s.lane === "back" ? "back" : "chat";
      const card = s.card ? `<div class="zh-card" lang="zh-CN">${esc(s.card)}</div>` : "";
      return `<li class="step ${lane} ${s.who}" style="grid-row:${i + 1};animation-delay:${reduced ? 0 : i * 90}ms">` +
        `<div class="actor ${s.who}">${esc(d.who[s.who])}</div><div class="bubble">${esc(texts[i])}</div>${card}</li>`;
    }).join("");
    $("#scene-note").textContent = d.scenes[scene].note;
  }
  $("#scene-tabs").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-scene]");
    if (!b || b.dataset.scene === scene) return;
    scene = b.dataset.scene;
    renderTabs(); renderScene();
    $(`#tab-${scene}`).focus();
  });
  $("#scene-tabs").addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    let i = SCENE_KEYS.indexOf(scene);
    const step = (document.documentElement.dir === "rtl" ? -1 : 1) * (e.key === "ArrowRight" ? 1 : -1);
    if (e.key === "Home") i = 0; else if (e.key === "End") i = SCENE_KEYS.length - 1; else i = (i + step + SCENE_KEYS.length) % SCENE_KEYS.length;
    scene = SCENE_KEYS[i];
    renderTabs(); renderScene();
    $(`#tab-${scene}`).focus();
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

  // instant: final state now (reduced motion), not a timer that clear() would cancel.
  function render(step, instant = false) {
    const at = instant ? (fn) => fn() : later;
    let n;
    switch (step.t) {
      case "user":
        n = el("div", "msg user", esc(step.text));
        if (step.secret) {
          const m = el("span", "mask", esc(step.secret));
          n.appendChild(m);
          at(() => { m.textContent = step.ph; m.classList.add("on"); }, 900);
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
        at(() => { const y = n.querySelector(".yes"); if (y) y.classList.add("pressed"); }, 1300);
        break;
      case "sys":
        n = el("div", "sys", `<span class="spin"></span><span class="txt">${step.text}</span>`);
        at(() => { n.classList.add("done"); n.querySelector(".txt").innerHTML = step.done; }, 2400);
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
    const full = step.text + (step.secret || "");
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
      return k <= stage ? `<span class="tok ph" dir="ltr">${esc(ph)}</span>` : `<span class="tok">${esc(s)}</span>`;
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
      website: String(fd.get("website") || ""),
      elapsedMs: Date.now() - startedAt,
      lang
    };
    form.querySelectorAll(".field-l").forEach((f) => f.classList.remove("bad"));
    const bad = [];
    if (!data.name) bad.push("name");
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(data.email)) bad.push("email");
    if (!data.source) bad.push("source");
    msg.classList.remove("err");
    if (bad.length) {
      bad.forEach((n) => form.elements[n].closest(".field-l").classList.add("bad"));
      msg.classList.add("err"); msg.textContent = d.bad; form.elements[bad[0]].focus();
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
