# China-mainland Mac + VPN: corrected protected-read baseline

Fixed original B06 only; no C sample or new message. All6 GETs passed the existing v1 generated contract, X-Request-ID/no-store, original message/RUN/generation and completed-text checks. All returned462UTF8 bytes with the same original text SHA2d6a7433...4a5aa9e.

| Attempt | Protected-read seconds | Outcome |
|---|---:|---|
| 1 | 20.360924 | PASS |
| 2 | 20.457692 | PASS |
| 3 | 20.674094 | PASS |
| 4 | 20.392199 | PASS |
| 5 | 20.429929 | PASS |
| 6 | 20.868486 | PASS |

Known n=6/planned6, p50=20.429929s, p95/max=20.868486s (nearest rank). This includes TLS/network/server processing; it is not pure network RTT or original-user-submit answer latency. Both user-first-body and full-answer quality remain UNRUN. No model completion, semantic review, C smoke/full cell or product quality PASS is inferred.

Actual user condition: China-mainland Mac with VPN on; both default and target routes utun6, HTTP/HTTPS proxy flags enabled. Settings unchanged, actual egress location UNKNOWN. No overseas client is claimed or required by JT11-06.

Source code d766d558 reuses the frozen generated v1 contract. The initial6680 collector incorrectly applied v6 to v1: its one HTTP200/21.293291s validation FAIL and5UNRUN remain in read-001. The correction was tested using the actual producer codec, and only the affected readonly probe was rerun. Stages are not averaged or selected as one successful run.

Current c4/a856 API/worker and original346-row ADOPTED ef9624...d84d8b match before/after. C sent0POST,0model/tool requests and wrote0financial or canonical phase records; only a short beta-a credential was used and its exact file was deleted. Credential values/headers and raw process/HTTP files stay outside Git. B's separate Feedback business write is not mislabeled as global zero writes. Actual total paid cost, including infrastructure, UNKNOWN.

Transport observation complete; M4 quality still unproven. The six-model-smoke prerequisite, formal66, grounded independent review and original JT90%/0/5s/90s remain unchanged and incomplete.
