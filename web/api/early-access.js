// POST /api/early-access
// Receives the early access application from go2china.space and forwards it to the existing Jotform form
// through the official Jotform API. Visitors only ever talk to go2china.space, so the form works from
// mainland China, where Jotform's own pages are often unreachable.
//
// Environment (set in the Vercel project, never in the repo):
//   JOTFORM_API_KEY   required; a Jotform API key with write access to the form
//   JOTFORM_FORM_ID   optional; defaults to the current early access form
//   JOTFORM_API_BASE  optional; https://api.jotform.com (default), https://eu-api.jotform.com or https://hipaa-api.jotform.com
"use strict";

const DEFAULT_FORM_ID = "263094082842055";

// Jotform question ids (qid) of the early access form, and the option values the form accepts.
const QID = { name: 11, email: 3, source: 4, country: 5, when: 6, dest: 7, needs: 8, note: 9 };
const VALUES = {
  source: ["Friend or family", "Search", "Instagram", "TikTok", "YouTube", "Xiaohongshu (RED)", "Reddit", "Event", "Other"],
  when: ["Within 3 months", "3–6 months", "6–12 months", "Not sure", "Already in China"],
  dest: ["Beijing", "Shanghai", "Xi’an", "Chengdu", "Guangzhou & Shenzhen", "Not sure"],
  needs: ["Payments", "Transport", "Trip planning", "Booking", "Food", "Language", "Visa & entry"]
};
const LIMITS = { name: 100, email: 254, country: 80, destOther: 80, note: 1000 };
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const MIN_FILL_MS = 2500;

const text = (v, max) => (typeof v === "string" ? v.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "").trim().slice(0, max) : "");
const list = (v, allowed) => (Array.isArray(v) ? [...new Set(v.filter((x) => allowed.includes(x)))] : []);

// Validates the browser payload once, here at the trust boundary. Returns { ok, data } or { ok: false, field }.
function validate(body) {
  if (!body || typeof body !== "object" || Array.isArray(body)) return { ok: false, field: "body" };
  const data = {
    name: text(body.name, LIMITS.name),
    email: text(body.email, LIMITS.email),
    source: VALUES.source.includes(body.source) ? body.source : "",
    country: text(body.country, LIMITS.country),
    when: VALUES.when.includes(body.when) ? body.when : "",
    dest: list(body.dest, VALUES.dest),
    destOther: text(body.destOther, LIMITS.destOther),
    needs: list(body.needs, VALUES.needs),
    note: text(body.note, LIMITS.note)
  };
  if (!data.name) return { ok: false, field: "name" };
  if (!EMAIL.test(data.email)) return { ok: false, field: "email" };
  if (!data.source) return { ok: false, field: "source" };
  return { ok: true, data };
}

// Jotform API form fields, keyed by question id.
function buildSubmission(data) {
  const p = new URLSearchParams();
  p.append(`submission[${QID.name}]`, data.name);
  p.append(`submission[${QID.email}]`, data.email);
  p.append(`submission[${QID.source}]`, data.source);
  if (data.country) p.append(`submission[${QID.country}]`, data.country);
  if (data.when) p.append(`submission[${QID.when}]`, data.when);
  data.dest.forEach((d) => p.append(`submission[${QID.dest}][]`, d));
  if (data.destOther) p.append(`submission[${QID.dest}][other]`, data.destOther);
  data.needs.forEach((n) => p.append(`submission[${QID.needs}][]`, n));
  if (data.note) p.append(`submission[${QID.note}]`, data.note);
  return p;
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

async function readJson(req) {
  if (req.body && typeof req.body === "object") return req.body;
  if (typeof req.body === "string") return JSON.parse(req.body);
  const chunks = [];
  let size = 0;
  for await (const c of req) {
    size += c.length;
    if (size > 16 * 1024) throw new Error("too large");
    chunks.push(c);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
}

async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return send(res, 405, { ok: false, error: "method_not_allowed" });
  }
  if (!String(req.headers["content-type"] || "").toLowerCase().startsWith("application/json")) {
    return send(res, 415, { ok: false, error: "json_required" });
  }
  let body;
  try { body = await readJson(req); } catch (_) { return send(res, 400, { ok: false, error: "bad_json" }); }

  // Spam traps: answer as if accepted so bots learn nothing, but forward nothing.
  if (body && typeof body === "object" && looksLikeBot(body)) return send(res, 200, { ok: true });

  const checked = validate(body);
  if (!checked.ok) return send(res, 422, { ok: false, error: "invalid", field: checked.field });

  const key = process.env.JOTFORM_API_KEY;
  if (!key) {
    console.error("early-access: JOTFORM_API_KEY is not set");
    return send(res, 503, { ok: false, error: "not_configured" });
  }
  const base = (process.env.JOTFORM_API_BASE || "https://api.jotform.com").replace(/\/+$/, "");
  const formId = process.env.JOTFORM_FORM_ID || DEFAULT_FORM_ID;

  try {
    const r = await fetch(`${base}/form/${encodeURIComponent(formId)}/submissions`, {
      method: "POST",
      headers: { APIKEY: key, "Content-Type": "application/x-www-form-urlencoded" },
      body: buildSubmission(checked.data),
      signal: AbortSignal.timeout(10000)
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || Number(j.responseCode) !== 200) {
      console.error("early-access: Jotform rejected the submission", r.status, j.responseCode, j.message);
      return send(res, 502, { ok: false, error: "upstream" });
    }
    return send(res, 200, { ok: true });
  } catch (e) {
    console.error("early-access: Jotform request failed", e && e.name);
    return send(res, 502, { ok: false, error: "upstream" });
  }
}

module.exports = handler;
module.exports.validate = validate;
module.exports.buildSubmission = buildSubmission;
