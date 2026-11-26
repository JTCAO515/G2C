// Privacy policy page (/privacy). privacy.html is generated from docs/privacy/privacy-policy.md by
// scripts/build_privacy_page.cjs and holds the policy in Chinese and in English, the only two languages
// it is published in. Chinese is shown to visitors who chose Chinese; everyone else gets English, and
// visitors who chose another site language are told why.
(() => {
  "use strict";

  const { T } = window.G2C;
  const LANGUAGES = ["en", "zh", "ru", "es", "ar", "fr"];
  const $ = (s) => document.querySelector(s);
  const pick = (d, path) => path.split(".").reduce((o, k) => (o == null ? o : o[k]), d);

  // The same choice as app.js: the language saved on the home page, else the browser's, else English.
  const browserLanguage = (navigator.language || "en").toLowerCase().split("-")[0];
  let lang = LANGUAGES.includes(browserLanguage) ? browserLanguage : "en";
  try {
    const saved = localStorage.getItem("g2c-lang");
    if (LANGUAGES.includes(saved)) lang = saved;
  } catch (_) { /* storage unavailable */ }

  const articles = { en: $("#policy-en"), zh: $("#policy-zh") };
  const note = $("#policy-note");

  // Only the article on screen carries the anchor ids, so links such as /privacy#cross-border work in
  // either language and the page never has two elements with the same id.
  function showPolicy(view) {
    for (const [key, article] of Object.entries(articles)) {
      const shown = key === view;
      article.hidden = !shown;
      article.querySelectorAll(shown ? "[data-anchor]" : "[id]").forEach((n) => {
        if (shown) { n.id = n.dataset.anchor; n.removeAttribute("data-anchor"); }
        else { n.dataset.anchor = n.id; n.removeAttribute("id"); }
      });
    }
  }

  function apply() {
    const d = T[lang];
    const view = lang === "zh" ? "zh" : "en";
    document.documentElement.lang = lang === "zh" ? "zh-CN" : lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    document.title = `${d.privacyPage.title} — go2china.space`;
    document.querySelectorAll("[data-i18n]").forEach((n) => { const v = pick(d, n.dataset.i18n); if (v != null) n.textContent = v; });
    $("#lang-select").value = lang;
    note.textContent = view === "en" && lang !== "en" ? d.privacyPage.fallback : "";
    note.hidden = !note.textContent;
    showPolicy(view);
  }

  $("#lang-select").addEventListener("change", (event) => {
    lang = event.target.value;
    try { localStorage.setItem("g2c-lang", lang); } catch (_) { /* ignore */ }
    apply();
  });

  apply();
  // The ids may have moved to the Chinese article after the browser looked for the anchor, and the
  // browser's own load-time scrolling can undo an early jump, so jump again (without animation) once
  // the page has loaded.
  function jump() {
    if (location.hash.length < 2) return;
    let id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch (_) { return; } // malformed: stay at the top
    const target = document.getElementById(id);
    if (target) target.scrollIntoView({ behavior: "instant", block: "start" });
  }
  jump();
  if (document.readyState !== "complete") window.addEventListener("load", jump, { once: true });
})();
