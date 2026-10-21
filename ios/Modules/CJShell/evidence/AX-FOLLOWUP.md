# CJ006 bounded AX follow-up / manual VoiceOver gap

2026-10-21 Asia/Shanghai. Source fixed at 0c2462f6633d1ff4fcfe58021b2400ede8a4aab7; this delta adds evidence only. Main reports this candidate has passed independent review/testing and entered local Publish integration. That coordination report does not supply VoiceOver evidence. The candidate remains intact; no shared integration tree touched.

## Executed

Reused installed CJShellDemo and own CJ006-Shell-20261021 / iPhone 17 Pro / iOS 26.5 / 824A7623-8882-45C9-94A7-7BD2F758B685. Session defaults verified before launch. No rebuild or repeat suite. Runtime semantic snapshots saved in ax-followup/snapshots.json.

- PASS, bounded AX observation: Assistant exposed 消息草稿 / 开始聊天, 聊天历史 and four tabs 助手/行程/插件/记忆 in declared order. This array order is not VoiceOver focus order.
- PASS, bounded AX actions: opened Memory and observed 事实/经历/偏好, 账号/语言, 帮助/隐私/支持. Opened Help → back → Privacy → back → Support, verified each destination's actual explanatory text and labelled 记忆 back action. Four tab targets remained present on each destination. No broken setting route, missing label or false support-send action observed in this scope.
- Reused, not rerun: prior actual four-tab round-trip/account/language observations in RUNTIME-DELTA.md, source-matched snapshots, and e85fc06 large-keyboard-compact screenshot plus compact-keyboard-snapshots.json. Those establish input value Large draft, visible Done, dismissal retaining draft at accessibility3 on this device; not spoken accessibility acceptance or every font/device combination.
- App stopped and this device read back Shutdown. No other device operated. No product source modified.

## Explicit limitations

Available XcodeBuildMCP tools expose semantic snapshot, targeted taps/text input, ordinary gestures and keyboard keys. No dedicated VoiceOver toggle, next/previous accessibility-focus command, spoken output capture or playback observation was exposed. The snapshot `focused` predicate would concern UI focus; it does not establish spoken VoiceOver focus. This run did not enable VoiceOver or infer its behavior from AX taps. Generic gestures were not represented as validated VoiceOver gestures.

Therefore complete VoiceOver focus order, focus restoration after navigation/language changes, double-tap activation, disabled announcements, rotor behavior and actual bilingual speech remain **UNRUN**. No new UI defect was established by this bounded check; no speculative accessibility fix added. True-device and full font/device matrix acceptance remain UNRUN. This is a tool-evidence limit, not a new product authorization request.

## Minimal operator steps (not executed)

Use an allocated test iPhone with this fixed candidate installed, or a simulator setup with independently verified VoiceOver support and audible output. Do not use another owner's device without allocation.

1. Open system Settings → Accessibility → VoiceOver and enable it. Confirm audible speech and visible focus. Open CJShellDemo normally, not the gallery. Record device/OS, candidate and language.
2. Use one-finger right/left swipes to traverse, and double-tap to activate. Verify four tabs are announced in the specified order, selected state is clear, and no hidden content from a different tab is read. Record actual sequence rather than expecting AX snapshot order.
3. In Memory traverse the three groups, Account, Language, Help, Privacy, Support. Activate each, read its text and back button, then return. Check focus returns to the originating row, no trap, no missing or duplicated meaningful label. Account must not imply sign-in; support must not imply a sent request.
4. In Assistant verify history, neutral assistant, gift/media unavailable announcements and draft. Enter a harmless draft, use Done, change language inside Memory and return. Confirm draft survives and labels/speech follow the selected language without losing the settings route. Do not attempt permissions or real service operations.
5. With larger accessibility text, repeat draft → keyboard → Done and settings navigation. Check all controls remain reachable by focus/activation and text can be read/scrolls; record any clipping, focus loss or unreachable button. Gallery synthetic long text may supplement this step but its Close control is not product UI.
6. Record PASS/FAIL per step and actual spoken sequence/observations. Leave unsupported VoiceOver behavior UNRUN. Restore VoiceOver to its prior state on the allocated test device and report results to Main for the existing acceptance lane.

No remote changes, real account, paid service or new product features. Existing CJ004/CJ005 integration gates and whole-ticket closure remain unchanged.
