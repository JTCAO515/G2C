# CJ006 local render continuation — partial, interaction blocked

Date: 2026-10-23, Asia/Shanghai. Original branch cj/006-session-bridge-host, base 2c3980b7d9930459d5cfc3ea5428164da256c13a. Before changes, full CJShell tree a44a4ed77d2d1c3707df10f524ab33c279606bb5 matched published main b33184fdc14c55098f2f21cd7e33d05b8a5d01f0 byte-for-byte. Worktree was clean. No whole-main merge or producer source change.

## Actual first write and build

Existing standalone Demo and build-demo.sh were reused. First package build passed, but hand-linked Demo failed: sandbox-exec sandbox_apply Operation not permitted; SwiftUIMacros.StateMacro produced malformed response. Preserved build-first.txt.xz is the original failure, not a product render result.

Only script change: standalone swiftc now uses -disable-sandbox, matching the existing SwiftPM local macro subprocess mode; dependency preparation uses --disable-automatic-resolution so it requires prepared inputs. This does not change app entitlements, signing/root configuration or production runtime. Build-second.txt records successful actual Demo build/link and local simulator signature. bash -n and git diff --check passed. No new model tests or domain suite reruns.

## Actual local launch/render

Used existing dedicated CJ006-Shell-20261021, UDID 824A7623-8882-45C9-94A7-7BD2F758B685, installed iOS 26.5. No runtime download, new device or CJ007 probe. XcodeBuildMCP installed /tmp/cj006-render-20261023/CJShellDemo.app and launched local.cj006.shell.demo, PID 92918. It is the normal disconnected shell, with no synthetic message/session flags or production resources. Default account host creates no session store. Existing demo language preference was Chinese; no old business account or Keychain was read.

normal-disconnected.jpg and snapshots.json show the actual Assistant render, four Tab labels, disabled sending, no original-run resources and no message recovery. This is render evidence only. The screenshot was captured through XcodeBuildMCP; a shell simctl screenshot attempt failed to connect to CoreSimulatorService in the restricted shell and was not counted as success.

## Input failure and unknown approval state

XcodeBuildMCP tap e25 (original usage, x58 y273) and e60 (Memory tab, x328 y803) returned simulated success, but repeated runtime snapshots and screenshot retained Assistant, selected tab unchanged and screenHash 1517ei4. These attempts are NOT interaction PASS and do not prove a product navigation defect. A label-only call was rejected by tool validation; this installed tool requires elementRef. Initial boot/launch extra-argument attempts required session defaults; after setting defaults the intended dedicated device launch succeeded.

CUA getApp Simulator did not resolve because Xcode's current frontend is Device Hub. Inventory identified com.apple.dt.Devices; getApp returned after about 524 seconds and exposed its selected physical JTs17 window plus the dedicated CJ006 simulator row. No physical device action was performed. Selecting only the observed CJ006 row via sim.click(6) timed out after about 12 seconds with kernel reset. No success/denial/approval decision was returned for that click; actual input/approval state is UNKNOWN. Main reported an earlier waitingOnApproval state; that report is not dismissed or bypassed. No CUA retry, alternate HID path, privilege escalation or simulator reset followed. Read-only runtime snapshot still showed the same Assistant state.

## Remaining gates

Issue7 is NOT complete. Four Tab transitions, Memory account/language/help/privacy navigation, language/draft retention, actual Usage sheet dismissal and two-step interaction, keyboard/long-text/large-type safety and VoiceOver spoken/focus behavior remain UNRUN or UNVERIFIED in this continuation. Prior source/unit tests do not close them. No product UI change was invented to compensate for tooling uncertainty. Default missing-source/unavailable semantics remain unchanged. Issue4 renderer/component acceptance is separate, as are real business source/dispatch/I and physical device acceptance.

Next exact action after Main confirms native input/approval availability: select the CJ006 simulator in Device Hub, verify a Memory Tab click changes the real view, then resume the specified navigation/keyboard/accessibility loop. No password, account, provider, Keychain or network operation is needed. The only fixed deliverable here is the independently useful local Demo build-script repair plus honest render/input evidence; it does not close either issue.
