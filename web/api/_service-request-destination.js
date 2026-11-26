// Where a validated service request goes (#1777). The underscore keeps Vercel from turning this file into
// a function of its own; api/service-request.js is the only caller.
//
// A destination is { kind, deliver(request) }: deliver resolves once the request is safely with the people
// who answer it, and throws otherwise (the visitor then sees the failure message and the email fallback).
//
// Today the only destination is LOG_ONLY, a stand-in for offline tests. It never writes the visitor's
// words, name, email or date to the log, nor anything derived from them (no hashes): only field
// lengths and whether the date is present.
// Before SERVICE_REQUEST_ENABLED is set to true, replace DEFAULT_DESTINATION with the service request
// backend from the service lane (W9, contract #1768). scripts/test_web_service_request.cjs fails if the
// switch is on while the default destination is still LOG_ONLY. Jotform is not used for this form.
"use strict";

const LOG_ONLY = {
  kind: "log-only",
  async deliver(request) {
    console.info("service-request: received (log-only destination)", JSON.stringify({
      service: request.service,
      city: request.city,
      lang: request.lang,
      nameLength: request.name.length,
      emailLength: request.email.length,
      noteLength: request.note.length,
      hasDate: Boolean(request.date)
    }));
  }
};

const DEFAULT_DESTINATION = LOG_ONLY;

module.exports = { LOG_ONLY, DEFAULT_DESTINATION };
