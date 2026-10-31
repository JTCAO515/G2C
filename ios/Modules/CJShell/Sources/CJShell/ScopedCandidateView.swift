#if os(iOS)
import SwiftUI
import CJManualPreviewClient
import CJTripClient
import CJRunClient

struct ScopedCandidateView: View {
    let host: ScopedCandidateHost
    let messages: AssistantMessageHost
    let language: ShellLanguage
    private var acceptedMessageID: String? { messages.visibleRecord?.phase == .accepted ? messages.visibleRecord?.messageID : nil }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            RunReadableText(text: language.text("Scoped candidate", "局部候选"), style: .headline)
            command("scoped.discover", language.text("Read candidate for the original message", "读取原消息的候选"), disabled: host.busy || acceptedMessageID == nil) {
                if let work = host.prepareDiscovery() { Task { await work() } }
            }
            if let read = host.read {
                RunReadableText(text: stateText(read.value.state)).accessibilityIdentifier("scoped.discovery.state")
                if let candidate = read.value.candidate {
                    candidateDetail(candidate)
                    let canChoose = candidate.status == "pending" && candidate.expiresAt > Int64(Date().timeIntervalSince1970) && !host.busy && host.actionID == nil
                    command("scoped.accept", language.text("Accept these exact changes", "接受这份确切改动"), disabled: !canChoose) {
                        if let work = host.prepareDecision(.accept, read: read) { Task { await work() } }
                    }
                    command("scoped.reject", language.text("Reject this candidate", "拒绝这份候选"), disabled: !canChoose) {
                        if let work = host.prepareDecision(.reject, read: read) { Task { await work() } }
                    }
                }
            }
            RunReadableText(text: activityText).accessibilityIdentifier("scoped.activity")
            if let id = host.actionID {
                RunSelectableText(text: id).accessibilityIdentifier("scoped.action.id")
            }
            if let receipt = host.receipt {
                RunReadableText(text: receipt.kind == .accept ? language.text("The original acceptance is confirmed.", "原接受动作已确认。") : language.text("The original rejection is confirmed. The Trip was not changed by this action.", "原拒绝动作已确认，本动作未改变正式行程。"))
                    .accessibilityIdentifier("scoped.receipt")
                if let version = receipt.committedVersion {
                    RunReadableText(text: language.text("Committed version ", "已提交版本 ") + String(version)).accessibilityIdentifier("scoped.receipt.version")
                }
            }
            if let formal = host.formal {
                RunReadableText(text: language.text("Formal Trip read back: ", "正式行程读回：") + formal.tripID + " · " + String(formal.version)).accessibilityIdentifier("scoped.formal.version")
                ForEach(formal.document.items) { item in
                    RunReadableText(text: item.text).accessibilityIdentifier("scoped.formal.item." + item.id)
                }
            }
            if host.formalUnavailable { RunReadableText(text: language.text("Acceptance confirmed; current formal Trip could not be read. Keep the original receipt and read again.", "接受已确认，当前正式行程暂不可读取。请保留原回执并重新读取。")) }
            command("scoped.originals", language.text("Read earlier scoped actions", "读取此前局部动作"), disabled: host.busy) { host.loadOriginals() }
            ForEach(host.actions) { original in
                command("scoped.query." + original.actionID, language.text("Check original ", "核对原动作 ") + original.actionID, disabled: host.busy) {
                    if let work = host.prepareQuery(original.actionID) { Task { await work() } }
                }
            }
            RunReadableText(text: language.text("Reading never generates another candidate. Unknown outcomes keep the original action and allow only reconciliation.", "读取不会再次生成候选。结果未知时保留原动作，只允许核对。"), style: .caption)
        }
        .accessibilityElement(children: .contain).accessibilityIdentifier("scoped.candidate")
        .onChange(of: acceptedMessageID) { _, _ in host.clearSelection() }
    }
    private func candidateDetail(_ candidate: ScopedCandidate) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            RunReadableText(text: candidate.before.title, style: .headline)
            RunReadableText(text: language.text("Original version ", "原版本 ") + String(candidate.expectedVersion) + " · " + candidate.status).accessibilityIdentifier("scoped.candidate.version")
            RunReadableText(text: language.text("Feasibility: ", "可行性：") + candidate.feasibilityStatus).accessibilityIdentifier("scoped.feasibility")
            ForEach(Array(candidate.checks.enumerated()), id: \.offset) { _, check in
                RunReadableText(text: check.status + " · " + (language == .english ? check.english : check.chinese))
                if !check.missing.isEmpty {
                    RunReadableText(text: language.text("Missing evidence: ", "缺少依据：") + check.missing.joined(separator: ", "), style: .caption)
                }
            }
            RunReadableText(text: language == .english ? candidate.outputEnglish : candidate.outputChinese)
            ForEach(Array(candidate.before.items.enumerated()), id: \.element.id) { index, before in
                let after = candidate.after.items[index]
                VStack(alignment: .leading, spacing: 6) {
                    RunReadableText(text: before.id, style: .caption)
                    RunReadableText(text: language.text("Before: ", "修改前：") + before.text).accessibilityIdentifier("scoped.before." + before.id)
                    RunReadableText(text: schedule(before))
                    RunReadableText(text: language.text("After: ", "修改后：") + after.text).accessibilityIdentifier("scoped.after." + after.id)
                    RunReadableText(text: schedule(after))
                    RunReadableText(text: language.text("Fixed: ", "固定状态：") + observation(after.fixed) { $0 ? language.text("yes", "是") : language.text("no", "否") })
                    RunReadableText(text: language.text("Evidence: ", "依据：") + (after.evidence.isEmpty ? language.text("UNKNOWN — no evidence", "UNKNOWN — 尚无依据") : after.evidence.joined(separator: ", ")))
                }.padding(.vertical, 4)
            }
            RunReadableText(text: language.text("Only the shown candidate is confirmed. UNKNOWN evidence remains unknown; accepting does not verify it.", "本次只确认展示的候选。UNKNOWN 依据仍未知，接受不代表已核实。"), style: .caption)
        }
    }
    private func observation<T>(_ value: TripObservation<T>, known: (T) -> String) -> String {
        switch value {
        case .known(let value): known(value)
        case .missing: language.text("missing", "缺失")
        case .unknown: "UNKNOWN"
        case .uncertain(let note): language.text("uncertain: ", "不确定：") + note
        }
    }
    private func schedule(_ item: StructuredTripItem) -> String {
        func edge(_ event: StructuredTripEvent) -> String {
            [observation(event.date) { $0 }, observation(event.time) { $0 }, observation(event.timezone) { $0 }, observation(event.utcOffset) { $0 }].joined(separator: " · ")
        }
        return edge(item.start) + " → " + edge(item.end)
    }
    private func stateText(_ state: ScopedDiscoveryState) -> String {
        switch state {
        case .published: language.text("Original candidate returned for review.", "已返回原候选，等待审阅。")
        case .pending: language.text("Original run is pending. Read it again later.", "原运行尚未完成，请稍后读取。")
        case .notRequested: language.text("This original message was discussion only.", "原消息仅用于讨论。")
        case .noCandidate: language.text("The original run produced no acceptable candidate. No Trip was changed.", "原运行没有产生可接受候选，正式行程未改变。")
        case .unknown: language.text("Original outcome UNKNOWN. Do not send another request as a retry.", "原结果 UNKNOWN，请勿另发请求冒充重试。")
        case .unavailable: language.text("The original run is unavailable for a candidate.", "原运行当前没有可用候选。")
        }
    }
    private var activityText: String {
        switch host.activity {
        case .idle: language.text("Choose an accepted original message to read its candidate.", "请选中已接受的原消息，读取其候选。")
        case .reading: language.text("Reading the protected original…", "正在读取受保护的原记录…")
        case .deciding: language.text("Checking the original decision…", "正在核对原决定…")
        case .ready: language.text("Original read completed.", "原记录读取完成。")
        case .unknown: language.text("Original result UNKNOWN. Reconcile the original action; no resend is available.", "原动作结果 UNKNOWN。请核对原动作，不能重发。")
        case .conflict: language.text("The original candidate conflicts with the current version. Keep the original input and read the current Trip.", "原候选与当前版本冲突。请保留原输入，读取当前行程。")
        case .unavailable: language.text("Protected candidate unavailable. Read the original again; this does not generate a candidate or create an action.", "受保护候选暂不可读取。可再次读取原记录，不会生成候选或创建动作。")
        }
    }
    private func command(_ id: String, _ label: String, disabled: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) { RunReadableText(text: label).frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle()) }
            .buttonStyle(ShellReadableButtonStyle()).disabled(disabled).accessibilityIdentifier(id)
    }
}
#endif
