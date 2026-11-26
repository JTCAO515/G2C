"use strict";
// Offline checks for the Guangzhou business companion request form (#1777).
// Usage (repository root): node --test scripts/test_web_service_request.cjs

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { Readable } = require("node:stream");
const { test } = require("node:test");

const WEB = path.join(__dirname, "..", "web");
const handler = require("../web/api/service-request");
const { createHandler, SERVICE, CONSENTS, validate } = handler;
const earlyAccess = require("../web/api/early-access");
const { DEFAULT_DESTINATION, LOG_ONLY } = require("../web/api/_service-request-destination");

const pageScript = fs.readFileSync(path.join(WEB, "service-request.js"), "utf8");
const indexHtml = fs.readFileSync(path.join(WEB, "index.html"), "utf8");

// 2026-11-27 04:00 in Beijing.
const NOW = Date.parse("2026-11-26T20:00:00Z");
const request = {
  service: SERVICE, name: "Sam", email: "guest@example.com", date: "2026-12-03",
  note: "Factory visit in Panyu, two meetings", lang: "zh",
  readPolicy: true, consentTravel: true, consentCompanion: true, consentCrossBorder: true
};

async function submit(fn, { body, chunks = [], headers = {}, method = "POST" }) {
  const req = Object.assign(Readable.from(chunks), {
    method, headers: { "content-type": "application/json", ...headers }, body
  });
  const responseHeaders = {};
  let result;
  const res = {
    setHeader(name, value) { responseHeaders[name] = value; },
    end(text) { result = JSON.parse(text); }
  };
  await fn(req, res);
  assert.equal(responseHeaders["Cache-Control"], "no-store");
  if (chunks.length && res.statusCode === 413) {
    assert.equal(req.destroyed, false, "keep the request socket open to send 413");
  }
  return { status: res.statusCode, result, req };
}

function recorder() {
  const delivered = [];
  return { delivered, destination: { kind: "test", async deliver(r) { delivered.push(r); } } };
}

function silenceLogs(t) {
  return {
    info: t.mock.method(console, "info", () => {}),
    error: t.mock.method(console, "error", () => {}),
    log: t.mock.method(console, "log", () => {})
  };
}

function pageSwitch() {
  const found = [...pageScript.matchAll(/^\s*const SERVICE_REQUEST_ENABLED = (true|false);$/gm)];
  assert.equal(found.length, 1, "service-request.js declares the switch exactly once");
  return found[0][1] === "true";
}

test("the page and the function use the same switch", () => {
  assert.equal(typeof handler.SERVICE_REQUEST_ENABLED, "boolean");
  assert.equal(pageSwitch(), handler.SERVICE_REQUEST_ENABLED);
});

test("the switch cannot be on while requests would only be logged", () => {
  if (handler.SERVICE_REQUEST_ENABLED) assert.notEqual(DEFAULT_DESTINATION.kind, "log-only");
  assert.ok(typeof DEFAULT_DESTINATION.deliver === "function");
});

test("the page and the function agree on the one service offered", () => {
  const match = pageScript.match(/const SERVICE = "([^"]+)";/);
  assert.ok(match, "service-request.js declares SERVICE");
  assert.equal(match[1], SERVICE);
  assert.equal(SERVICE, "English–Chinese business companion");
});

async function expectSwitchedOff(t, fn, destination) {
  const logs = silenceLogs(t);
  const deliver = t.mock.method(destination, "deliver", async () => {});
  for (const input of [
    { body: request }, { method: "GET" }, { chunks: [Buffer.from(JSON.stringify(request))] },
    { body: "x".repeat(20000) }, { body: request, headers: { "content-type": "text/plain" } }
  ]) {
    const { status, result, req } = await submit(fn, input);
    assert.deepEqual({ status, result }, { status: 404, result: { ok: false, error: "not_found" } });
    assert.equal(req.readableEnded, false, "the request body is not read");
  }
  assert.equal(deliver.mock.callCount(), 0);
  for (const log of Object.values(logs)) assert.equal(log.mock.callCount(), 0);
}

test("switched off, the endpoint answers 404 to everything and reads nothing", async (t) => {
  const destination = { kind: "test", async deliver() {} };
  await expectSwitchedOff(t, createHandler({ enabled: false, destination }), destination);
  // The deployed handler, as long as the repository switch is off.
  if (!handler.SERVICE_REQUEST_ENABLED) await expectSwitchedOff(t, handler, DEFAULT_DESTINATION);
});

const withSwitch = (on) =>
  pageScript.replace(/const SERVICE_REQUEST_ENABLED = (true|false);/, `const SERVICE_REQUEST_ENABLED = ${on};`);

function loadCopy() {
  const w = {};
  new Function("window", fs.readFileSync(path.join(WEB, "i18n.js"), "utf8"))(w);
  return w.G2C;
}

// Just enough of a page to run service-request.js: every element records what is set on it, where it
// is appended and which listeners it gets; anything else it is asked for is another such element.
function fakePage(lang) {
  const created = [];
  const known = {};
  const make = (label) => {
    const state = { label, listeners: {} };
    const methods = {
      appendChild(child) { child.parentLabel = label; return child; },
      addEventListener(type, fn) { (state.listeners[type] ||= []).push(fn); },
      querySelector(selector) { return find(`${label} ${selector}`); },
      querySelectorAll() { return []; }
    };
    return new Proxy(() => {}, {
      get(_, key) {
        if (key in methods) return methods[key];
        if (key in state) return state[key];
        if (typeof key === "symbol") return undefined;
        return (state[key] = make(`${label}.${key}`));
      },
      set(_, key, value) { state[key] = value; return true; },
      apply() { return make(`${label}()`); }
    });
  };
  const find = (selector) => (known[selector] ||= make(selector));
  find("#lang-select").value = lang;
  const document = {
    createElement(tag) { const node = make(tag); created.push(node); return node; },
    querySelector: find
  };
  return { created, document, find };
}

function runPage(on, lang = "en") {
  const G2C = loadCopy();
  const page = fakePage(lang);
  const requests = [];
  const fetch = async (url, options) => { requests.push({ url, body: JSON.parse(options.body) }); return Response.json({ ok: true }); };
  new Function("window", "document", "location", "fetch", withSwitch(on))({ G2C }, page.document, { hash: "" }, fetch);
  return { ...page, requests, T: G2C.T };
}

// Fills the form on the fake page with valid answers, ticks only the given boxes and submits it.
async function submitPage(ticked) {
  const page = runPage(true);
  const form = page.find("#sr-form");
  Object.assign(form.elements.name, { value: "Sam" });
  Object.assign(form.elements.email, { value: "guest@example.com" });
  Object.assign(form.elements.note, { value: "" });
  Object.assign(form.elements.website, { value: "" });
  form.elements.date.value = form.elements.date.min;
  for (const name of CONSENTS) form.elements[name].checked = ticked.includes(name);
  for (const fn of form.listeners.submit) await fn({ preventDefault() {} });
  return { ...page, message: page.find("#sr-msg").textContent };
}

test("switched off, the page script stops before touching the page", () => {
  const untouchable = new Proxy({}, { get() { throw new Error("the page was touched"); } });
  new Function("window", "document", "fetch", withSwitch(false))(untouchable, untouchable, untouchable);
  assert.equal(runPage(false).created.length, 0, "no form, no entry links");
});

test("switched on, the header and the hero both link to the form", () => {
  const { created, find, T } = runPage(true);
  const links = created.filter((n) => n.href === "#service-request");
  assert.deepEqual(links.map((n) => n.parentLabel).sort(), [".hero-text", ".links"]);
  const entry = links.find((n) => n.parentLabel === ".hero-text");
  assert.equal(entry.className, "svc-entry");
  assert.equal(entry.textContent, T.en.sr.entry);
  const section = created.find((n) => n.label === "section");
  assert.equal(section.id, "service-request");
  assert.equal(section.parentLabel, "main");
  assert.match(section.innerHTML, /<form id="sr-form"/);
  // Follows the language picker that app.js owns.
  find("#lang-select").value = "ar";
  find("#lang-select").listeners.change.forEach((fn) => fn());
  assert.equal(entry.textContent, T.ar.sr.entry);
});

test("switched off, the page HTML has no form and no entry link", () => {
  assert.doesNotMatch(indexHtml, /sr-form|svc-entry|service-request"|#service-request|\/api\/service-request/);
  assert.equal(indexHtml.match(/<script src="service-request\.js" defer><\/script>/g).length, 1);
});

test("app.js knows nothing about the service request", () => {
  assert.doesNotMatch(fs.readFileSync(path.join(WEB, "app.js"), "utf8"), /service|g2c:lang|G2C\.lang/i);
});

test("styles for the service request stay inside its own form and section", () => {
  const css = fs.readFileSync(path.join(WEB, "styles.css"), "utf8");
  const start = css.indexOf("/* Service request");
  const block = css.slice(start, css.indexOf("/* Footer */", start));
  for (const rule of block.split("\n").filter((line) => line.includes("{"))) {
    assert.match(rule.trim(), /^(\.svc|#sr-form|#sr-|:dir\(rtl\) \.svc)/, rule);
  }
});

test("the form asks for all four boxes, each linking to its part of the privacy policy", () => {
  assert.deepEqual(CONSENTS, ["readPolicy", "consentTravel", "consentCompanion", "consentCrossBorder"]);
  const { created } = runPage(true);
  const html = created.find((n) => n.label === "section").innerHTML;
  for (const name of CONSENTS) assert.match(html, new RegExp(`<input name="${name}" type="checkbox" required>`));
  for (const anchor of ["website-requests", "in-person-services", "cross-border"]) {
    assert.match(html, new RegExp(`<a href="/privacy#${anchor}"`));
  }
  assert.match(html, /<a href="\/privacy" data-sr="f.consentLink">/);
});

test("the page stops a request with any box unticked, and sends one with all four", async () => {
  for (const missing of CONSENTS) {
    const { requests, message, T } = await submitPage(CONSENTS.filter((name) => name !== missing));
    assert.equal(requests.length, 0, missing);
    assert.equal(message, T.en.sr.bad, missing);
  }
  const { requests, message, T } = await submitPage(CONSENTS);
  assert.equal(message, T.en.sr.ok);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "/api/service-request");
  for (const name of CONSENTS) assert.equal(requests[0].body[name], true, name);
  // What the page sends is what the server accepts.
  assert.equal(validate(requests[0].body).ok, true);
});

test("the server answers 400 and delivers nothing unless all four boxes are true", async () => {
  const { delivered, destination } = recorder();
  const fn = createHandler({ enabled: true, destination, now: () => NOW });
  for (const name of CONSENTS) {
    for (const value of [undefined, false, "true", 1]) {
      const { status, result } = await submit(fn, { body: { ...request, [name]: value } });
      assert.deepEqual({ status, result }, { status: 400, result: { ok: false, error: "consent_required", field: name } },
        `${name}=${value}`);
    }
  }
  assert.equal(delivered.length, 0);
  assert.equal((await submit(fn, { body: request })).status, 200);
  assert.deepEqual(delivered[0].consents, CONSENTS);
});

test("a valid request is delivered once, with the city and service set by the server", async (t) => {
  const { delivered, destination } = recorder();
  const fn = createHandler({ enabled: true, destination, now: () => NOW });
  const body = { ...request, city: "Beijing", passport: "E12345678", website: "", elapsedMs: 30000 };
  assert.deepEqual((await submit(fn, { body, headers: { "content-type": "application/json; charset=utf-8" } })).result,
    { ok: true });
  assert.deepEqual(delivered, [{
    service: SERVICE, city: "Guangzhou", name: "Sam", email: "guest@example.com", date: "2026-12-03",
    note: "Factory visit in Panyu, two meetings", lang: "zh",
    consents: ["readPolicy", "consentTravel", "consentCompanion", "consentCrossBorder"],
    receivedAt: "2026-11-26T20:00:00.000Z"
  }]);
});

test("rejects missing or invalid fields without delivering", async (t) => {
  const { delivered, destination } = recorder();
  const fn = createHandler({ enabled: true, destination, now: () => NOW });
  const cases = [
    [{ name: " " }, "name"], [{ email: "guest@example" }, "email"],
    [{ date: "2026-11-26" }, "date"], [{ date: "2026-02-30" }, "date"], [{ date: "2027-11-28" }, "date"],
    [{ date: "3 December" }, "date"],
    [{ service: "Airport pickup" }, "service"]
  ];
  for (const [change, field] of cases) {
    assert.deepEqual(await submit(fn, { body: { ...request, ...change } }).then(({ status, result }) => ({ status, result })),
      { status: 422, result: { ok: false, error: "invalid", field } }, JSON.stringify(change));
  }
  assert.equal((await submit(fn, { body: [request] })).status, 422);
  // Today in Beijing and 365 days ahead are both accepted.
  assert.equal((await submit(fn, { body: { ...request, date: "2026-11-27" } })).status, 200);
  assert.equal((await submit(fn, { body: { ...request, date: "2027-11-27" } })).status, 200);
  assert.equal(delivered.length, 2);
});

test("trims, strips control characters and cuts long text to the limit, like the early access endpoint", async () => {
  const { delivered, destination } = recorder();
  const fn = createHandler({ enabled: true, destination, now: () => NOW });
  const body = { ...request, name: "  Sam\u0007 ", note: "n".repeat(1500), lang: "de" };
  assert.equal((await submit(fn, { body })).status, 200);
  assert.equal(delivered[0].name, "Sam");
  assert.equal(delivered[0].note.length, 1000);
  assert.equal(delivered[0].lang, "en");
  // early-access.js cuts over-long text to its limit instead of rejecting it; this endpoint does the same.
  const early = earlyAccess.validate({ name: "x".repeat(150), email: "guest@example.com", source: "Search", note: "n".repeat(1500) });
  assert.equal(early.ok, true);
  assert.equal(early.data.name.length, 100);
  assert.equal(early.data.note.length, 1000);
  const ours = validate({ ...request, name: "x".repeat(150), note: "n".repeat(1500) }, NOW);
  assert.equal(ours.ok, true);
  assert.equal(ours.data.name.length, 100);
  assert.equal(ours.data.note.length, 1000);
});

test("spam traps answer ok and deliver nothing", async () => {
  const { delivered, destination } = recorder();
  const fn = createHandler({ enabled: true, destination, now: () => NOW });
  assert.deepEqual((await submit(fn, { body: { ...request, website: "http://spam.example" } })).result, { ok: true });
  assert.deepEqual((await submit(fn, { body: { ...request, elapsedMs: 800 } })).result, { ok: true });
  assert.equal(delivered.length, 0);
});

test("method, media type, JSON and byte limits match the early access endpoint", async () => {
  const { delivered, destination } = recorder();
  const fn = createHandler({ enabled: true, destination, now: () => NOW });
  assert.equal((await submit(fn, { method: "GET" })).status, 405);
  assert.equal((await submit(fn, { body: request, headers: { "content-type": "application/json-seq" } })).status, 415);
  assert.equal((await submit(fn, { chunks: [Buffer.from("{")] })).status, 400);
  const large = { ...request, note: "旅".repeat(6000) };
  const raw = JSON.stringify(large);
  const bytes = Buffer.from(raw);
  for (const input of [
    { body: large }, { body: bytes }, { body: raw }, { chunks: [bytes.subarray(0, 12000), bytes.subarray(12000)] },
    { body: request, headers: { "content-length": "16385" } }
  ]) {
    assert.deepEqual((await submit(fn, input)).result, { ok: false, error: "body_too_large" });
  }
  assert.equal(delivered.length, 0);
});

test("a failed delivery answers 502 and keeps the request out of the logs", async (t) => {
  const logs = silenceLogs(t);
  const fn = createHandler({
    enabled: true, now: () => NOW,
    destination: { kind: "test", async deliver() { throw new Error("rejected guest@example.com Sam"); } }
  });
  assert.deepEqual((await submit(fn, { body: request })).result, { ok: false, error: "upstream" });
  assert.equal(logs.error.mock.callCount(), 1);
  assert.doesNotMatch(JSON.stringify(logs.error.mock.calls[0].arguments), /guest@example\.com|Sam/);
});

test("the log-only stand-in logs field lengths only, nothing that could identify the visitor", async (t) => {
  const logs = silenceLogs(t);
  const fn = createHandler({ enabled: true, destination: LOG_ONLY, now: () => NOW });
  assert.equal((await submit(fn, { body: request })).status, 200);
  assert.equal(logs.info.mock.callCount(), 1);
  const [label, detail] = logs.info.mock.calls[0].arguments;
  assert.equal(label, "service-request: received (log-only destination)");
  assert.deepEqual(JSON.parse(detail), {
    service: SERVICE, city: "Guangzhou", lang: "zh",
    nameLength: 3, emailLength: 17, noteLength: request.note.length, hasDate: true
  });
});

test("every language has the full form copy and says only what the form does", () => {
  const w = {};
  new Function("window", fs.readFileSync(path.join(WEB, "i18n.js"), "utf8"))(w);
  const languages = Object.keys(w.G2C.T);
  assert.deepEqual(languages.sort(), ["ar", "en", "es", "fr", "ru", "zh"]);
  const shape = (o) => (Array.isArray(o) ? o.map(shape) : typeof o === "object" ? Object.fromEntries(Object.entries(o).map(([k, v]) => [k, shape(v)])) : typeof o);
  const strings = (o) => (typeof o === "string" ? [o] : Object.values(o).flatMap(strings));
  const en = w.G2C.T.en.sr;
  for (const lang of languages) {
    const sr = w.G2C.T[lang].sr;
    assert.deepEqual(shape(sr), shape(en), lang);
    for (const s of strings(sr)) assert.ok(s.trim(), lang);
    assert.equal(sr.rows.length, 3, lang);
    // One business day, Beijing time, by email: the only reply promise, before and after sending.
    assert.match(sr.rows[2][1], /1 |واحد/, `${lang}: reply time`);
    assert.match(sr.ok, /1 |واحد/, `${lang}: reply time after sending`);
  }
  assert.match(w.G2C.T.zh.sr.rows[2][1], /1 个工作日内（北京时间）通过邮件回复/);
  assert.match(w.G2C.T.zh.sr.f.noteHint, /不要填写证件号、健康信息/);
  assert.equal(w.G2C.T.zh.sr.f.noteHint, "简单说说你需要什么帮助，我们会通过邮件和你确认时间和地点。请不要填写证件号、健康信息。");
  assert.equal(en.f.noteHint, "Briefly tell us what you need. We’ll confirm the time and place with you by email. Please don’t include ID numbers or health details.");
  for (const lang of languages) {
    const f = w.G2C.T[lang].sr.f;
    // The note hint no longer asks for places or meeting topics.
    assert.doesNotMatch(f.noteHint, /meetings are about|For example|会谈内容/);
    assert.equal(f.consents.length, 3, lang);
  }
  assert.equal(w.G2C.T.zh.sr.f.consentBefore + w.G2C.T.zh.sr.f.consentLink, "我已阅读隐私政策");
  assert.match(pageScript, /const PRIVACY_URL = "\/privacy";/);
});
