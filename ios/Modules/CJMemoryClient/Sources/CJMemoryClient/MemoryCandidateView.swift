import Foundation
import SwiftUI
import CJAPI

/// Both languages render the same current projection and captured editor entry.
/// A historical receipt never supplies the current candidate rows.
public struct MemoryCandidateView: View {
    public let model: MemoryCandidatePresentation
    public let language: MemoryLanguage
    @State private var editor: MemoryCandidateEditorEntry?
    public init(model: MemoryCandidatePresentation, language: MemoryLanguage) {
        self.model = model; self.language = language
    }
    public var body: some View {
        Form {
            Section {
                MemoryRowText(text: language.text("These suggestions are not active memories. Review each one; only your explicit confirmation can activate it. Leaving a suggestion alone does not confirm it.", "这些建议尚未成为有效记忆。请逐条核对，只有你明确确认后才会生效；不处理不等于确认。"), style: .body)
                    .accessibilityIdentifier("memoryCandidate.scope")
                if let conversation = model.conversationID {
                    MemoryRowText(text: language.text("Selected conversation: ", "已选择会话：") + conversation, style: .body)
                        .accessibilityIdentifier("memoryCandidate.conversation")
                }
                MemoryLifecycleButton(title: language.text("Read conversation suggestions", "读取本会话建议"), identifier: "memoryCandidate.discover", enabled: model.canRead) {
                    perform(model.prepareDiscovery())
                }
                if !model.usesCurrentProjection && model.state == .ready && model.jobs.isEmpty && model.producer == nil {
                    MemoryRowText(text: language.text("This conversation currently has no suggestions awaiting confirmation.", "这段会话当前没有待确认建议。"), style: .body)
                        .accessibilityIdentifier("memoryCandidate.emptyDiscovery")
                }
                if model.state.isBusy { ProgressView().accessibilityLabel(language.text("Checking memory suggestions", "正在核验记忆建议")) }
                MemoryRowText(text: status, style: .body).accessibilityIdentifier("memoryCandidate.status")
            }
            if !model.jobs.isEmpty {
                Section {
                    ForEach(Array(model.jobs.enumerated()), id: \.element) { index, producer in
                        MemoryLifecycleButton(title: language.text("Read suggestion group ", "读取建议组 ") + String(index + 1),
                            identifier: "memoryCandidate.producer." + String(index), enabled: model.canRead) {
                            perform(model.prepareCandidates(producer: producer))
                        }
                    }
                    if model.hasMore {
                        MemoryLifecycleButton(title: language.text("More suggestion groups", "更多建议组"), identifier: "memoryCandidate.more", enabled: model.canRead) {
                            perform(model.prepareDiscovery(more: true))
                        }
                    }
                } header: { heading(language.text("Conversation suggestions", "会话建议")) }
            }
            if model.producer != nil || model.usesCurrentProjection {
                Section {
                    if model.candidates.isEmpty && model.state == .ready {
                        MemoryRowText(text: model.usesCurrentProjection ? language.text("This conversation currently has no suggestions awaiting confirmation.", "这段会话当前没有待确认建议。") : language.text("This group currently has no suggestions.", "这个建议组当前没有内容。"), style: .body)
                            .accessibilityIdentifier("memoryCandidate.empty")
                    }
                    ForEach(model.candidates, id: \.utf8Identity) { candidate in
                        VStack(alignment: .leading, spacing: 12) {
                            MemoryRowText(text: candidate.text, style: .body)
                            MemoryRowText(text: language.text("About: ", "关于：") + candidate.subject + " · " + candidate.slot, style: .caption)
                            MemoryRowText(text: language.text("Time: ", "时间：") + candidate.occurredAt, style: .body)
                            MemoryRowText(text: candidate.extent == .long_term ? language.text("Scope: long-term memory", "范围：长期记忆") : language.text("Scope: this trip", "范围：本次行程"), style: .body)
                            MemoryRowText(text: stateTitle(candidate), style: .body)
                            if !candidate.actionV1IdentifierIsSupported {
                                MemoryRowText(text: language.text("This suggestion can be viewed, but cannot be reviewed with the current service. No action was submitted.", "这条建议可查看，但当前服务暂不支持核对它，未提交操作。"), style: .body)
                                    .accessibilityIdentifier("memoryCandidate.reviewUnavailable")
                            }
                            MemoryLifecycleButton(title: language.text("Review this suggestion", "核对这条建议"), identifier: "memoryCandidate.review." + candidate.utf8Identity.base64EncodedString(), enabled: model.canReview(candidateID: candidate.id)) {
                                editor = model.captureReview(candidateID: candidate.id)
                            }
                        }
                        .padding(12)
                        .background(.quaternary, in: RoundedRectangle(cornerRadius: 16))
                    }
                } header: { heading(language.text("Current suggestion status", "建议当前状态")) }
            }
            if model.usesCurrentProjection && model.hasMore {
                MemoryLifecycleButton(title: language.text("More suggestions", "更多建议"), identifier: "memoryCandidate.more", enabled: model.canRead) {
                    perform(model.prepareDiscovery(more: true))
                }
            }
            Section {
                MemoryRowText(text: language.text("If a submission is uncertain, keep its original record and check it. Reopening never sends it again.", "提交结果不明确时，请保留并查询原记录；重新打开不会再次发送。"), style: .body)
                MemoryLifecycleButton(title: language.text("Load original reviews", "读取原核对记录"), identifier: "memoryCandidate.loadOriginals", enabled: !model.state.isBusy) {
                    perform(model.prepareOriginals())
                }
                ForEach(model.pendingActions, id: \.utf8Identity) { original in
                    MemoryLifecycleButton(title: language.text("Original review: ", "原核对：") + original.actionID,
                        identifier: "memoryCandidate.original." + original.actionID, enabled: !model.state.isBusy) {
                        model.selectOriginal(actionID: original.actionID)
                    }
                }
                if let original = model.original {
                    MemoryRowText(text: original.actionID, style: .caption).accessibilityIdentifier("memoryCandidate.originalID")
                    MemoryLifecycleButton(title: language.text("Check original review", "查询原核对"), identifier: "memoryCandidate.query", enabled: !model.state.isBusy) {
                        perform(model.prepareQuery())
                    }
                }
            } header: { heading(language.text("Original review recovery", "原核对恢复")) }
            if let receipt = model.historicalReceipt {
                Section {
                    MemoryRowText(text: language.text("This is the recorded result of the original review. It does not prove the memory is still active; read its current status separately.", "这是原核对操作的历史结果，不代表记忆现在仍有效；请另行读取当前状态。"), style: .body)
                        .accessibilityIdentifier("memoryCandidate.historicalNotice")
                    MemoryRowText(text: receipt.active ? language.text("Original result: confirmed", "原结果：已确认") : language.text("Original result: rejected", "原结果：已拒绝"), style: .body)
                        .accessibilityIdentifier("memoryCandidate.receiptResult")
                } header: { heading(language.text("Historical receipt", "历史回执")) }
            }
        }
        .navigationTitle(language.text("Memory suggestions", "记忆建议"))
        .sheet(item: $editor) { entry in
            MemoryCandidateEditor(model: model, entry: entry, language: language)
        }
    }
    private func perform(_ work: MemoryCandidatePresentationWork?) {
        guard let work else { return }; Task { await model.perform(work) }
    }
    private func heading(_ text: String) -> some View {
        MemoryRowText(text: text, style: .caption).accessibilityAddTraits(.isHeader)
    }
    private func stateTitle(_ candidate: MemoryCandidate) -> String {
        switch candidate.status {
        case .candidate: language.text("Awaiting your confirmation", "待你确认")
        case .active: language.text("Currently active", "当前有效")
        case .disabled: language.text("Currently disabled", "当前已停用")
        case .withdrawn: language.text("Currently withdrawn", "当前已撤回")
        }
    }
    private var status: String {
        switch model.state {
        case .unconfigured: language.text("Suggestions are not connected for this account. Nothing was submitted.", "当前账号的建议尚未接入，未提交任何操作。")
        case .unselected: language.text("Choose a conversation in Assistant server history first.", "请先在助手的服务器历史中选择一段会话。")
        case .unread: language.text("Read this conversation's suggestions to review them.", "请读取本会话的建议，再逐条核对。")
        case .loading: language.text("Reading suggestions…", "正在读取建议…")
        case .ready: language.text("Current suggestions were read. Each confirmation applies to one suggestion only.", "已读取当前建议，每次确认只适用于一条建议。")
        case .invalidReview: language.text("Choose a memory type and provide nonempty text and time. Nothing new was submitted.", "请选择记忆类型，并填写内容和时间；未提交新操作。")
        case .changing: language.text("Submitting your review…", "正在提交你的核对结果…")
        case .reconciling: language.text("Checking the original review…", "正在查询原核对…")
        case .unknown: language.text("The original result is uncertain. Query it without resending.", "原结果尚不明确，请查询原操作，不要重新发送。")
        case .conflict: language.text("The suggestion or its source changed. Read it again before a new explicit review. The original record is retained.", "建议或来源已变化，请重新读取后再明确核对；原记录已保留。")
        case .unavailable: model.historicalReceipt != nil ? language.text("The original review was recorded, but current status could not be verified.", "原核对已记录，但当前状态尚未核实。") : language.text("Current suggestions could not be verified. This does not mean there are none.", "暂时无法核验当前建议，不能据此认为没有建议。")
        case .recoveryUnavailable: language.text("The original record could not be verified. Keep it; this does not prove it was never submitted.", "暂时无法核验原记录。请保留它，这不代表从未提交。")
        }
    }
}

private struct MemoryCandidateEditor: View {
    let model: MemoryCandidatePresentation
    let entry: MemoryCandidateEditorEntry
    let language: MemoryLanguage
    @Environment(\.dismiss) private var dismiss
    @State private var kind: String
    @State private var text: String
    @State private var occurredAt: String
    @State private var refused = false
    init(model: MemoryCandidatePresentation, entry: MemoryCandidateEditorEntry, language: MemoryLanguage) {
        self.model = model; self.entry = entry; self.language = language
        _kind = State(initialValue: entry.candidate.kind == .inference ? "" : entry.candidate.kind.rawValue)
        _text = State(initialValue: entry.candidate.text); _occurredAt = State(initialValue: entry.candidate.occurredAt)
    }
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    MemoryRowText(text: language.text("Review this one suggestion. Confirming does not authorize organization of other history or change this suggestion's trip scope.", "请核对这一条建议。确认不等于授权整理其他历史，也不会改变这条建议的行程范围。"), style: .body)
                        .accessibilityIdentifier("memoryCandidate.editor.scope")
                    Picker(selection: $kind) {
                        Text(language.text("Choose a type", "请选择类型")).tag("")
                        Text(language.text("Fact", "事实")).tag("fact")
                        Text(language.text("Experience", "经历")).tag("experience")
                        Text(language.text("Preference", "偏好")).tag("preference")
                    } label: { MemoryRowText(text: language.text("Memory type", "记忆类型"), style: .body) }
                    .accessibilityIdentifier("memoryCandidate.editor.kind")
                    TextField(language.text("Memory text", "记忆内容"), text: $text, axis: .vertical)
                        .accessibilityIdentifier("memoryCandidate.editor.text")
                    TextField(language.text("Time or original uncertainty", "时间或原有不确定说明"), text: $occurredAt, axis: .vertical)
                        .accessibilityIdentifier("memoryCandidate.editor.time")
                    MemoryRowText(text: entry.candidate.extent == .long_term ? language.text("Scope: long-term memory", "范围：长期记忆") : language.text("Scope: this trip", "范围：本次行程"), style: .body)
                    MemoryLifecycleButton(title: language.text("Confirm this memory", "确认这条记忆"), identifier: "memoryCandidate.editor.confirm", enabled: canSubmit && !kind.isEmpty) {
                        guard let selected = Components.Schemas.MemoryManualSaveCommand.kindPayload(rawValue: kind) else { return }
                        submit(.confirm(kind: selected, text: text, occurredAt: occurredAt, travel: entry.candidate.travel))
                    }
                    MemoryLifecycleButton(title: language.text("Reject this suggestion", "拒绝这条建议"), identifier: "memoryCandidate.editor.reject", enabled: canSubmit) { submit(.reject) }
                    if refused || !canSubmit {
                        MemoryRowText(text: language.text("This review could not be prepared. Check the text and time, or close and read the current suggestion again. No replacement was sent.", "暂时无法准备此操作。请核对内容与时间，或关闭后重新读取当前建议；未发送替代操作。"), style: .body)
                            .accessibilityIdentifier("memoryCandidate.editor.refused")
                    }
                }
            }
            .navigationTitle(language.text("Review suggestion", "核对建议"))
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button(language.text("Close", "关闭")) { dismiss() }.accessibilityIdentifier("memoryCandidate.editor.close") } }
        }
    }
    private var canSubmit: Bool { model.canReview(entry: entry) }
    private func submit(_ review: MemoryCandidateReview) {
        guard let work = model.prepareReview(entry: entry, review: review) else { refused = true; return }
        Task { await model.perform(work) }; dismiss()
    }
}
private extension MemoryCandidate { var utf8Identity: Data { Data(id.utf8) } }
private extension MemoryCandidateOriginal { var utf8Identity: Data { Data(actionID.utf8) } }
