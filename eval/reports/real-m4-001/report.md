# Real batch evidence and limits

Conclusion: **FAIL — do not release this evaluated candidate.** Only synthetic data; original33 paired scenarios and11 fixed holdout, no prompt/judge/holdout tuning.

The quality numerator is independently certified PASS, not model self-scoring. RUN completion was zh2/33 and en4/33; 60 ended UNKNOWN. Completed answers have no full independent semantic/factual review and remain quality UNKNOWN. Even treating every completed answer as PASS could not reach90% in this batch.

The frozen program retains one serious hard-state FAIL per language in accept-once: formal_write_count was0, expected1. The RUN had ended UNKNOWN before a proposal/confirmation was available; no accept action occurred. This is a failed required save, not evidence of an unauthorized write. No model or reviewer overrode that original classification.

60 original terminal clocks were mislabeled as full answers in the initial collector output. Read-only reconciliation retains them as time_to_terminal_seconds and sets unavailable full_answer_seconds to null; original files/hashes, failures, judgments, fees and attempts are unchanged. No paid scenario was rerun for this correction.

Displayed p95 values with UNKNOWN are known-subset diagnostics, never full-population PASS. First/full clocks are actual TCP v2 protected-snapshot observations at200ms polling, including submission and waiting. Source-only links are excluded. The necessary candidate is included when delivered. The gate can prove full-population FAIL when enough known slow samples exceed the allowed tail; otherwise incomplete populations remain UNKNOWN.

Real outbound evidence:137 model intents (93 complete receipts;44 UNKNOWN),8 place receipts,46 weather receipts,8 fact intents (0 complete); route0. Complete model receipts expose107183 input/11537 output tokens. Counts do not assert that every uncertain intent reached a vendor. Actual invoiced fees are UNKNOWN; C conservative holds are model¥137/tools¥54. Shared after-snapshot including M1 is model¥167/tools¥64; no budget reset.

Development-Mac network only. The loopback API is real and external model/place/weather exits are real; geographic overseas/China target attribution is UNKNOWN. api-beta target testing is UNRUN pending B #30 readiness; fact access and route availability are not certified. Project-wide release prerequisites remain UNKNOWN.

Raw HTTP/process logs and credentials are not committed. report.json is the durable per-attempt evaluation/audit report, including original-evidence hashes and timing corrections. Original receipt/run evidence is linked in the PR description; raw files remain in the batch output. B #523 owns the real UNKNOWN/no-body and external adapter defects; C does not modify B files.

Historical preparation failures retained: missing CJ_ENV import guard; the first pre-RUN snapshot read; wrong confirmation Content-Type. The corrected offline fixture passed10 signed/PG/worker recipes. Delay0.6s and2.5s fixture controls passed; they did not establish the cause of the real UNKNOWN runs.

---
# G2C M4 evaluation

Dataset: 2:2a5df582ee63f461afebe7a280cc5587e6281190f6aab05b458fa89f029d2e56
Product scenarios: 33; fixed holdout: 11
Evaluation quality decision: FAIL
Other release prerequisites: UNKNOWN
JT 2026-11-04: each language completion >=90%, serious errors0, first-body p95<=5s, full-answer p95<=90s.

| Candidate | Language | Network | Completion | Serious errors | First-body p95 | Full-answer p95 | Real quality decision |
|---|---|---|---|---|---|---|---|
| 9ba2d4df8a220f238ddf438e210cb055167c1cc0 | zh | development-mac-real-exits | FAIL 0/33 | FAIL n=1 | UNKNOWN 4.9365433329949155s | UNKNOWN 4.9365433329949155s | FAIL |
| 9ba2d4df8a220f238ddf438e210cb055167c1cc0 | en | development-mac-real-exits | FAIL 0/33 | FAIL n=1 | FAIL 12.23389970898279s | UNKNOWN 12.23389970898279s | FAIL |

| Language | Network | Actual billed currency subtotals | Estimated / reserved | Fee completeness | Model / tool / memory calls (known; unknown attempts) |
|---|---|---|---|---|---|
| zh | development-mac-real-exits | UNKNOWN | UNKNOWN / {'CNY': '111'} | UNKNOWN, 33 unknown/missing attempts | 76; 0 UNKNOWN / 38; 0 UNKNOWN / 0; 0 UNKNOWN |
| en | development-mac-real-exits | UNKNOWN | UNKNOWN / {'CNY': '80'} | UNKNOWN, 33 unknown/missing attempts | 61; 0 UNKNOWN / 24; 0 UNKNOWN / 0; 0 UNKNOWN |

Fake/local/synthetic rows validate formatting only; their real quality decision is UNRUN.

| Language | Network | Split | Task | N | PASS | FAIL | UNKNOWN | UNRUN | PASS / started | API p50 / p95 (s) | Model calls known / unknown attempts |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|
| zh | development-mac-real-exits | tuning | answer | 7 | 0 | 7 | 0 | 0 | 0 / 7 | None / None | 9 / 0 |
| zh | development-mac-real-exits | tuning | memory | 8 | 0 | 8 | 0 | 0 | 0 / 8 | None / None | 30 / 0 |
| zh | development-mac-real-exits | tuning | planning | 7 | 0 | 7 | 0 | 0 | 0 / 7 | None / None | 13 / 0 |
| zh | development-mac-real-exits | holdout | answer | 9 | 0 | 7 | 2 | 0 | 0 / 9 | None / None | 19 / 0 |
| zh | development-mac-real-exits | holdout | memory | 1 | 0 | 1 | 0 | 0 | 0 / 1 | None / None | 2 / 0 |
| zh | development-mac-real-exits | holdout | planning | 1 | 0 | 1 | 0 | 0 | 0 / 1 | None / None | 3 / 0 |
| en | development-mac-real-exits | tuning | answer | 7 | 0 | 6 | 1 | 0 | 0 / 7 | None / None | 8 / 0 |
| en | development-mac-real-exits | tuning | memory | 8 | 0 | 8 | 0 | 0 | 0 / 8 | None / None | 20 / 0 |
| en | development-mac-real-exits | tuning | planning | 7 | 0 | 7 | 0 | 0 | 0 / 7 | None / None | 17 / 0 |
| en | development-mac-real-exits | holdout | answer | 9 | 0 | 7 | 2 | 0 | 0 / 9 | None / None | 11 / 0 |
| en | development-mac-real-exits | holdout | memory | 1 | 0 | 0 | 1 | 0 | 0 / 1 | None / None | 4 / 0 |
| en | development-mac-real-exits | holdout | planning | 1 | 0 | 1 | 0 | 0 | 0 / 1 | None / None | 1 / 0 |

API latency includes the scenario's signed operations, original worker and final authoritative read; it is not UI first-body latency.
Unavailable first-body/draft visibility and missing networks stay UNKNOWN/UNRUN. Repeated attempts are separate rows in report.json.
Cost details retain known currency subtotals and incomplete-attempt counts in report.json; absent monetary receipts are UNKNOWN.

Serious errors: 2. An unresolved serious error cannot be cancelled by a mean or another language.

- ['9ba2d4df8a220f238ddf438e210cb055167c1cc0', 'accept-once', 'zh', 'development-mac-real-exits', 1]: formal_write_count violated an independent state/constraint assertion (resolved=False)
- ['9ba2d4df8a220f238ddf438e210cb055167c1cc0', 'accept-once', 'en', 'development-mac-real-exits', 1]: formal_write_count violated an independent state/constraint assertion (resolved=False)
