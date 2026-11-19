"use strict";

const assert = require("node:assert/strict");
const { Readable } = require("node:stream");
const { test } = require("node:test");
const handler = require("../web/api/early-access");

const application = { name: "Test Guest", email: "guest@example.com", source: "Search" };

async function submit({ body, chunks = [], headers = {} }) {
  const request = Object.assign(Readable.from(chunks), {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body
  });
  const responseHeaders = {};
  let result;
  const response = {
    setHeader(name, value) { responseHeaders[name] = value; },
    end(text) { result = JSON.parse(text); }
  };
  await handler(request, response);
  assert.equal(responseHeaders["Cache-Control"], "no-store");
  if (chunks.length && response.statusCode === 413) {
    assert.equal(request.destroyed, false, "keep the request socket open to send 413");
  }
  return { status: response.statusCode, result };
}

function configure(t, base) {
  for (const [name, value] of Object.entries({
    JOTFORM_API_KEY: "local-test-key",
    JOTFORM_FORM_ID: "local-test-form",
    JOTFORM_API_BASE: base
  })) {
    const previous = process.env[name];
    t.after(() => {
      if (previous === undefined) delete process.env[name];
      else process.env[name] = previous;
    });
    if (value === undefined) delete process.env[name];
    else process.env[name] = value;
  }
}

test("accepts JSON with charset and forwards the validated form once", async (t) => {
  configure(t, "https://eu-api.jotform.com/");
  const outbound = t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "https://eu-api.jotform.com/form/local-test-form/submissions");
    assert.equal(options.method, "POST");
    assert.equal(options.redirect, "error");
    assert.equal(options.body.get("submission[3]"), application.email);
    return Response.json({ responseCode: 200 });
  });
  const body = Buffer.from(JSON.stringify(application));
  assert.deepEqual(await submit({ body, headers: { "content-type": "application/json; charset=utf-8" } }),
    { status: 200, result: { ok: true } });
  assert.equal(outbound.mock.callCount(), 1);
});

test("enforces the same byte limit for parsed, buffered, string and streamed JSON", async (t) => {
  configure(t);
  const outbound = t.mock.method(globalThis, "fetch", async () => Response.json({ responseCode: 200 }));
  const large = { ...application, note: "旅".repeat(6000) };
  const raw = JSON.stringify(large);
  const bytes = Buffer.from(raw);
  for (const input of [
    { body: large }, { body: bytes }, { body: raw }, { chunks: [bytes.subarray(0, 12000), bytes.subarray(12000)] },
    { body: application, headers: { "content-length": "16385" } }
  ]) {
    assert.deepEqual(await submit(input), { status: 413, result: { ok: false, error: "body_too_large" } });
  }
  assert.equal(outbound.mock.callCount(), 0);
});

test("rejects a different JSON subtype and preserves invalid JSON handling", async (t) => {
  configure(t);
  const outbound = t.mock.method(globalThis, "fetch", async () => Response.json({ responseCode: 200 }));
  assert.equal((await submit({ body: application, headers: { "content-type": "application/json-seq" } })).status, 415);
  assert.equal((await submit({ chunks: [Buffer.from("{")] })).status, 400);
  assert.equal(outbound.mock.callCount(), 0);
});

test("rejects a non-Jotform upstream configuration before forwarding", async (t) => {
  configure(t, "https://example.com");
  const outbound = t.mock.method(globalThis, "fetch", async () => Response.json({ responseCode: 200 }));
  t.mock.method(console, "error", () => {});
  assert.deepEqual(await submit({ body: application }), { status: 503, result: { ok: false, error: "not_configured" } });
  assert.equal(outbound.mock.callCount(), 0);
});

test("upstream errors keep application content out of logs", async (t) => {
  configure(t);
  const log = t.mock.method(console, "error", () => {});
  t.mock.method(globalThis, "fetch", async () => Response.json(
    { responseCode: 400, message: "invalid email: guest@example.com" }, { status: 400 }
  ));
  assert.deepEqual(await submit({ body: application }), { status: 502, result: { ok: false, error: "upstream" } });
  assert.equal(log.mock.callCount(), 1);
  assert.doesNotMatch(JSON.stringify(log.mock.calls[0].arguments), /guest@example\.com/);
});
