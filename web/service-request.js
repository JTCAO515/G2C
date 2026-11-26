// Request form for an English–Chinese business companion in Guangzhou (#1777).
// While SERVICE_REQUEST_ENABLED is false this script stops at the first line: the page has no form,
// no entry link (header or hero), and sends nothing. api/service-request.js has the same switch (and answers 404
// while it is off); scripts/test_web_service_request.cjs checks that the two agree.
//
// Keep it false until all of these are true:
//   1. The privacy policy (docs/privacy/privacy-policy.md) is public at PRIVACY_URL; its first
//      publication needs JT's own sign-off.
//   2. The function delivers to the service lane's request backend (W9, contract #1768), not the
//      log-only stand-in in api/_service-request-destination.js.
//   3. The coordinator has named who receives the requests, and one test request has reached them (#32).
(() => {
  "use strict";

  const SERVICE_REQUEST_ENABLED = false;
  if (!SERVICE_REQUEST_ENABLED) return;

  // Where the website will publish the privacy policy. Not live yet; see the list above.
  const PRIVACY_URL = "/privacy";
  // Must match SERVICE in api/service-request.js, which rejects any other value.
  const SERVICE = "English–Chinese business companion";
  const MAX_LEN = { name: 100, email: 254, note: 1000 };
  const DAY_MS = 24 * 60 * 60 * 1000;
  const beijingDate = (ms) => new Date(ms + 8 * 60 * 60 * 1000).toISOString().slice(0, 10);

  const { T } = window.G2C;
  const $ = (s, r = document) => r.querySelector(s);
  const startedAt = Date.now();

  // Two ways in: the header navigation (hidden on narrow screens) and a link under the hero text,
  // which shows on every screen size.
  const nav = document.createElement("a");
  nav.href = "#service-request";
  $(".links").appendChild(nav);

  const entry = document.createElement("a");
  entry.className = "svc-entry";
  entry.href = "#service-request";
  $(".hero-text").appendChild(entry);

  const section = document.createElement("section");
  section.className = "svc";
  section.id = "service-request";
  section.innerHTML = `
    <div class="svc-in">
      <h2 data-sr="title"></h2>
      <p class="lede" data-sr="lede"></p>
      <dl class="svc-facts"></dl>
      <form id="sr-form" novalidate>
        <div class="row2">
          <label class="field-l"><span data-sr="f.name"></span>
            <input name="name" type="text" autocomplete="nickname" required maxlength="${MAX_LEN.name}"></label>
          <label class="field-l"><span data-sr="f.email"></span>
            <input name="email" type="email" autocomplete="email" required maxlength="${MAX_LEN.email}" dir="ltr"></label>
        </div>
        <label class="field-l svc-date"><span data-sr="f.date"></span>
          <input name="date" type="date" required dir="ltr"></label>
        <label class="field-l"><span><span data-sr="f.note"></span> <em data-sr="f.optional"></em></span>
          <textarea name="note" rows="4" maxlength="${MAX_LEN.note}" aria-describedby="sr-note-hint"></textarea>
          <small class="svc-hint" id="sr-note-hint" data-sr="f.noteHint"></small></label>
        <label class="field-l svc-consent"><span><input name="consent" type="checkbox" required>
          <span><span data-sr="f.consentBefore"></span><a href="${PRIVACY_URL}" data-sr="f.consentLink"></a><span data-sr="f.consentAfter"></span></span></span></label>
        <div class="hp" aria-hidden="true"><label>Website <input name="website" type="text" tabindex="-1" autocomplete="off"></label></div>
        <div class="submit-row">
          <button class="btn btn-ink" type="submit" id="sr-submit"></button>
          <p class="form-msg" id="sr-msg" role="status" aria-live="polite"></p>
        </div>
      </form>
    </div>`;
  $("main").appendChild(section);

  const form = $("#sr-form"), msg = $("#sr-msg"), submit = $("#sr-submit");
  const pick = (d, path) => path.split(".").reduce((o, k) => (o == null ? o : o[k]), d);
  // app.js owns the language picker and applies the language first (its listener was added first);
  // this script follows the picker's value and leaves app.js as it is.
  const langSelect = $("#lang-select");
  const currentLang = () => (T[langSelect.value] ? langSelect.value : "en");
  const copy = () => T[currentLang()].sr;

  function render() {
    const d = copy();
    nav.textContent = d.nav;
    entry.textContent = d.entry;
    section.querySelectorAll("[data-sr]").forEach((n) => { n.textContent = pick(d, n.dataset.sr) || ""; });
    const facts = $(".svc-facts", section);
    facts.replaceChildren(...d.rows.flatMap(([term, value]) => {
      const dt = document.createElement("dt"), dd = document.createElement("dd");
      dt.textContent = term; dd.textContent = value;
      return [dt, dd];
    }));
    submit.textContent = d.submit;
    if (form.classList.contains("sent")) msg.textContent = d.ok;
    else { msg.textContent = ""; msg.classList.remove("err"); }
  }

  const dateInput = form.elements.date;
  dateInput.min = beijingDate(Date.now());
  dateInput.max = beijingDate(Date.now() + 365 * DAY_MS);

  form.addEventListener("input", (e) => {
    const f = e.target.closest(".field-l"); if (f) f.classList.remove("bad");
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const d = copy();
    const data = {
      service: SERVICE,
      name: form.elements.name.value.trim(),
      email: form.elements.email.value.trim(),
      date: dateInput.value,
      note: form.elements.note.value.trim(),
      consent: form.elements.consent.checked,
      website: form.elements.website.value,
      elapsedMs: Date.now() - startedAt,
      lang: currentLang()
    };
    form.querySelectorAll(".field-l").forEach((f) => f.classList.remove("bad"));
    const bad = [];
    if (!data.name) bad.push("name");
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(data.email)) bad.push("email");
    if (!data.date || data.date < dateInput.min || data.date > dateInput.max) bad.push("date");
    if (!data.consent) bad.push("consent");
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
      const r = await fetch("/api/service-request", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data), signal: ctrl.signal
      });
      clearTimeout(timer);
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.ok) throw new Error(String(r.status));
      form.classList.add("sent"); msg.textContent = d.ok;
    } catch (_) {
      msg.classList.add("err"); msg.textContent = d.fail;
    } finally {
      submit.disabled = false;
    }
  });

  langSelect.addEventListener("change", render);
  render();
  // The section is added after load, so the browser could not follow a link to it yet.
  if (location.hash === "#service-request") section.scrollIntoView();
})();
