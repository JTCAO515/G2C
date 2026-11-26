// POST /api/service-request
// Request form for an English–Chinese business companion in Guangzhou (#1777). A person on our team reads
// each request and replies by email. Visitors only ever talk to go2china.space.
//
// SERVICE_REQUEST_ENABLED is the switch, and it must stay false until all of these are true:
//   1. The privacy policy (docs/privacy/privacy-policy.md) is public at /privacy; its first publication
//      needs JT's own sign-off. The form links to /privacy.
//   2. DEFAULT_DESTINATION in api/_service-request-destination.js is the service lane's request backend
//      (W9, contract #1768), not the log-only stand-in.
//   3. The coordinator has named who receives the requests, and one test request has reached them (#32).
// While it is false this endpoint answers 404 to every request and reads nothing.
// The page has its own copy of the switch in service-request.js; scripts/test_web_service_request.cjs
// checks that the two agree. Turning it on means changing both constants (and the destination).
"use strict";

const { DEFAULT_DESTINATION } = require("./_service-request-destination");

const SERVICE_REQUEST_ENABLED = false;

const MAX_BODY_BYTES = 16 * 1024;
// The only service and city the form offers. The server sets the city itself; the browser cannot change it.
const SERVICE = "English–Chinese business companion";
const CITY = "Guangzhou";
const LANGUAGES = ["en", "zh", "ru", "es", "fr", "ar"];
const LIMITS = { name: 100, email: 254, note: 1000 };
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const MIN_FILL_MS = 2500;
const DAY_MS = 24 * 60 * 60 * 1000;
const BEIJING_OFFSET_MS = 8 * 60 * 60 * 1000;
const MAX_DAYS_AHEAD = 365;

const text = (v, max) => (typeof v === "string" ? v.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "").trim().slice(0, max) : "");
const beijingDate = (ms) => new Date(ms + BEIJING_OFFSET_MS).toISOString().slice(0, 10);

// A real calendar date (YYYY-MM-DD) from today in Beijing up to MAX_DAYS_AHEAD days ahead.
function checkDate(value, nowMs) {
  if (typeof value !== "string" || !DATE.test(value)) return "";
  const ms = Date.parse(`${value}T00:00:00Z`);
  if (Number.isNaN(ms) || new Date(ms).toISOString().slice(0, 10) !== value) return "";
  if (value < beijingDate(nowMs) || value > beijingDate(nowMs + MAX_DAYS_AHEAD * DAY_MS)) return "";
  return value;
}

// Validates the browser payload once, here at the trust boundary. Returns { ok, data } or { ok: false, field }.
function validate(body, nowMs = Date.now()) {
  if (!body || typeof body !== "object" || Array.isArray(body)) return { ok: false, field: "body" };
  const data = {
    service: SERVICE,
    city: CITY,
    name: text(body.name, LIMITS.name),
    email: text(body.email, LIMITS.email),
    date: checkDate(body.date, nowMs),
    note: text(body.note, LIMITS.note),
    lang: LANGUAGES.includes(body.lang) ? body.lang : "en"
  };
  if (body.service !== SERVICE) return { ok: false, field: "service" };
  if (!data.name) return { ok: false, field: "name" };
  if (!EMAIL.test(data.email)) return { ok: false, field: "email" };
  if (!data.date) return { ok: false, field: "date" };
  if (body.consent !== true) return { ok: false, field: "consent" };
  return { ok: true, data };
}

function looksLikeBot(body) {
  if (typeof body.website === "string" && body.website.trim() !== "") return true;
  return typeof body.elapsedMs === "number" && body.elapsedMs < MIN_FILL_MS;
}

function send(res, status, payload) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.end(JSON.stringify(payload));
}

class BodyTooLarge extends Error {}

function checkBodySize(bytes) {
  if (bytes > MAX_BODY_BYTES) throw new BodyTooLarge();
}

async function readJson(req) {
  checkBodySize(Number(req.headers["content-length"]));
  const body = req.body;
  if (Buffer.isBuffer(body)) {
    checkBodySize(body.length);
    return JSON.parse(body.toString("utf8"));
  }
  if (typeof body === "string") {
    checkBodySize(Buffer.byteLength(body));
    return JSON.parse(body);
  }
  if (body !== undefined) {
    // Vercel can provide parsed JSON before the handler receives the request.
    checkBodySize(Buffer.byteLength(JSON.stringify(body)));
    return body;
  }
  const chunks = [];
  let size = 0;
  // An early exit must leave the request open long enough to send the 413.
  for await (const chunk of req.iterator({ destroyOnReturn: false })) {
    const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += bytes.length;
    checkBodySize(size);
    chunks.push(bytes);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
}

function createHandler({ enabled, destination, now = Date.now }) {
  return async function handler(req, res) {
    // Switched off: behave as if the endpoint did not exist. Nothing is read, logged or forwarded.
    if (!enabled) return send(res, 404, { ok: false, error: "not_found" });

    if (req.method !== "POST") {
      res.setHeader("Allow", "POST");
      return send(res, 405, { ok: false, error: "method_not_allowed" });
    }
    const mediaType = String(req.headers["content-type"] || "").split(";", 1)[0].trim().toLowerCase();
    if (mediaType !== "application/json") {
      return send(res, 415, { ok: false, error: "json_required" });
    }
    let body;
    try { body = await readJson(req); } catch (error) {
      if (error instanceof BodyTooLarge) return send(res, 413, { ok: false, error: "body_too_large" });
      return send(res, 400, { ok: false, error: "bad_json" });
    }

    // Spam traps: answer as if accepted so bots learn nothing, but forward nothing.
    if (body && typeof body === "object" && looksLikeBot(body)) return send(res, 200, { ok: true });

    const checked = validate(body, now());
    if (!checked.ok) return send(res, 422, { ok: false, error: "invalid", field: checked.field });

    try {
      await destination.deliver({ ...checked.data, receivedAt: new Date(now()).toISOString() });
      return send(res, 200, { ok: true });
    } catch (_) {
      // The error may quote the request; log only that delivery failed.
      console.error("service-request: delivery failed");
      return send(res, 502, { ok: false, error: "upstream" });
    }
  };
}

module.exports = createHandler({ enabled: SERVICE_REQUEST_ENABLED, destination: DEFAULT_DESTINATION });
module.exports.SERVICE_REQUEST_ENABLED = SERVICE_REQUEST_ENABLED;
module.exports.SERVICE = SERVICE;
module.exports.createHandler = createHandler;
module.exports.validate = validate;
