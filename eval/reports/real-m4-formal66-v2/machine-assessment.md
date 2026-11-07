# G2C M4 evaluation

Dataset: 2:2a5df582ee63f461afebe7a280cc5587e6281190f6aab05b458fa89f029d2e56
Product scenarios: 33; fixed holdout: 11
Evaluation quality decision: FAIL
Other release prerequisites: UNKNOWN
Network policy: JT-2026-11-06-M4-NETWORK (#32 JT 2026-11-06; PR568); mainland development Mac + VPN; client submitted-task clocks required.
Read-only snapshot diagnostics and server location do not certify submitted-task timing.

JT 2026-11-04: each language completion >=90%, serious errors0, first-body p95<=5s, full-answer p95<=90s.

| Candidate | Language | Network | Completion | Serious errors | First-body p95 | Full-answer p95 | Real quality decision |
|---|---|---|---|---|---|---|---|
| 9215f745b54872f1f2b5673074056068b18d1403 | zh | hk-private-real-exits | FAIL 0/33 | UNKNOWN n=0 | FAIL 17.4694269040192s | PASS 17.4694269040192s | FAIL |
| 9215f745b54872f1f2b5673074056068b18d1403 | en | hk-private-real-exits | FAIL 0/33 | UNKNOWN n=0 | FAIL 18.497360007022507s | UNKNOWN 18.497360007022507s | FAIL |

| Language | Network | Actual billed currency subtotals | Estimated / reserved | Fee completeness | Model / tool / memory calls (known; unknown attempts) |
|---|---|---|---|---|---|
| zh | hk-private-real-exits | UNKNOWN | UNKNOWN / {'CNY': '61'} | UNKNOWN, 33 unknown/missing attempts | 53; 0 UNKNOWN / 8; 0 UNKNOWN / 0; 0 UNKNOWN |
| en | hk-private-real-exits | UNKNOWN | UNKNOWN / {'CNY': '74'} | UNKNOWN, 33 unknown/missing attempts | 56; 0 UNKNOWN / 18; 0 UNKNOWN / 0; 0 UNKNOWN |

Fake/local/synthetic rows validate formatting only; their real quality decision is UNRUN.

| Language | Network | Split | Task | N | PASS | FAIL | UNKNOWN | UNRUN | PASS / started | API p50 / p95 (s) | Model calls known / unknown attempts |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|
| zh | hk-private-real-exits | tuning | answer | 7 | 0 | 0 | 7 | 0 | 0 / 7 | None / None | 7 / 0 |
| zh | hk-private-real-exits | tuning | memory | 8 | 0 | 0 | 8 | 0 | 0 / 8 | None / None | 16 / 0 |
| zh | hk-private-real-exits | tuning | planning | 7 | 0 | 0 | 7 | 0 | 0 / 7 | None / None | 16 / 0 |
| zh | hk-private-real-exits | holdout | answer | 9 | 0 | 0 | 9 | 0 | 0 / 9 | None / None | 10 / 0 |
| zh | hk-private-real-exits | holdout | memory | 1 | 0 | 0 | 1 | 0 | 0 / 1 | None / None | 2 / 0 |
| zh | hk-private-real-exits | holdout | planning | 1 | 0 | 0 | 1 | 0 | 0 / 1 | None / None | 2 / 0 |
| en | hk-private-real-exits | tuning | answer | 7 | 0 | 0 | 7 | 0 | 0 / 7 | None / None | 8 / 0 |
| en | hk-private-real-exits | tuning | memory | 8 | 0 | 1 | 7 | 0 | 0 / 8 | None / None | 16 / 0 |
| en | hk-private-real-exits | tuning | planning | 7 | 0 | 1 | 6 | 0 | 0 / 7 | None / None | 15 / 0 |
| en | hk-private-real-exits | holdout | answer | 9 | 0 | 0 | 9 | 0 | 0 / 9 | None / None | 11 / 0 |
| en | hk-private-real-exits | holdout | memory | 1 | 0 | 0 | 1 | 0 | 0 / 1 | None / None | 4 / 0 |
| en | hk-private-real-exits | holdout | planning | 1 | 0 | 0 | 1 | 0 | 0 / 1 | None / None | 2 / 0 |

API latency includes the scenario's signed operations, original worker and final authoritative read; it is not UI first-body latency.
Unavailable first-body/draft visibility and missing networks stay UNKNOWN/UNRUN. Repeated attempts are separate rows in report.json.
Cost details retain known currency subtotals and incomplete-attempt counts in report.json; absent monetary receipts are UNKNOWN.

Serious errors: 0. An unresolved serious error cannot be cancelled by a mean or another language.
