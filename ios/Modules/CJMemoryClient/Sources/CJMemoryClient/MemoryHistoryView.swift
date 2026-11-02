import SwiftUI

/// Consent is conversation-specific. Settings are current; receipts remain historical.
public struct MemoryHistoryView: View {
    public let model: MemoryHistoryPresentation
    public let language: MemoryLanguage
    public init(model: MemoryHistoryPresentation, language: MemoryLanguage) { self.model = model; self.language = language }
    public var body: some View {
        Form {
            Section {
                MemoryRowText(text: language.text("History organization is off by default for each conversation. Saving one memory does not authorize organization of all history.", "每段会话的历史整理默认关闭。保存单条记忆，不等于授权整理全部历史。"), style: .body)
                    .accessibilityIdentifier("historyConsent.scope")
                if let conversation = model.conversationID {
                    MemoryRowText(text: language.text("Selected conversation: ", "已选择会话：") + conversation, style: .body)
                        .accessibilityIdentifier("historyConsent.conversation")
                }
                MemoryLifecycleButton(title: language.text("Read current settings", "读取当前设置"), identifier: "historyConsent.read", enabled: model.canRead) {
                    if let work = model.prepareRead() { Task { await model.perform(work) } }
                }
                if let settings = model.settings {
                    Toggle(isOn: Binding(get: { settings.enabled }, set: { enabled in
                        if let work = model.prepareChange(enabled ? .enable : .disable) { Task { await model.perform(work) } }
                    })) {
                        MemoryRowText(text: language.text("Allow organization of this conversation", "允许整理本会话历史"), style: .body)
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    }.disabled(!model.canChange).accessibilityIdentifier("historyConsent.toggle")
                    MemoryRowText(text: settings.enabled ? language.text("Current settings allow this conversation only.", "当前设置只允许这段会话。") : language.text("Current settings do not allow this conversation.", "当前设置未允许这段会话。"), style: .body)
                        .accessibilityIdentifier("historyConsent.current")
                    MemoryRowText(text: language.text("Source version: ", "来源版本：") + String(settings.sourceVersion), style: .caption)
                        .accessibilityIdentifier("historyConsent.version")
                }
                if model.state.isBusy { ProgressView().accessibilityLabel(language.text("Checking conversation history settings", "正在核验会话历史设置")) }
                MemoryRowText(text: status, style: .body).accessibilityIdentifier("historyConsent.status")
            }
            Section {
                MemoryRowText(text: language.text("Stopping prevents new organization tasks for this source. Previously confirmed memories remain until you manage or delete them separately.", "停用后不再为这个来源派发新的整理任务。此前已确认的记忆仍保留，需要单独管理或删除。"), style: .body)
                    .accessibilityIdentifier("historyConsent.stopExplanation")
                MemoryRowText(text: language.text("Allowing organization does not mean the history was processed or remembered. Inferred candidates still need your confirmation before they become active memories.", "允许整理不代表历史已处理或已记住。推断候选还需你单独确认，才会成为有效记忆。"), style: .body)
                    .accessibilityIdentifier("historyConsent.confirmationExplanation")
            } header: { MemoryRowText(text: language.text("Scope and stopping", "范围与停用说明"), style: .caption).accessibilityAddTraits(.isHeader) }
            Section {
                MemoryLifecycleButton(title: language.text("Load original changes", "读取原变更记录"), identifier: "historyConsent.loadPending", enabled: model.canRead) {
                    if let work = model.prepareReload() { Task { await model.perform(work) } }
                }
                ForEach(model.pendingActions, id: \.actionID) { original in
                    MemoryLifecycleButton(title: changeTitle(original.change) + " · " + original.actionID,
                        identifier: "historyConsent.pending." + original.actionID, enabled: !model.state.isBusy) {
                        model.selectPending(actionID: original.actionID)
                    }
                }
                if let original = model.original {
                    MemoryRowText(text: language.text("Original change: ", "原变更：") + changeTitle(original.change), style: .body)
                        .accessibilityIdentifier("historyConsent.originalChange")
                    MemoryRowText(text: original.actionID, style: .caption).accessibilityIdentifier("historyConsent.originalID")
                    MemoryLifecycleButton(title: language.text("Check original change", "查询原变更"), identifier: "historyConsent.query", enabled: model.canRead) {
                        if let work = model.prepareQuery() { Task { await model.perform(work) } }
                    }
                }
            } header: { MemoryRowText(text: language.text("Original action recovery", "原操作恢复"), style: .caption).accessibilityAddTraits(.isHeader) }
            if let receipt = model.receipt {
                Section {
                    MemoryRowText(text: language.text("The original change was recorded. This historical receipt does not describe the current setting; use the settings read above.", "原变更已记录。这是历史回执，不代表当前设置，请以上方设置读取结果为准。"), style: .body)
                        .accessibilityIdentifier("historyConsent.historicalNotice")
                    MemoryRowText(text: receipt.actionID, style: .caption).accessibilityIdentifier("historyConsent.receiptID")
                    MemoryRowText(text: language.text("Historical result: ", "历史结果：") + (receipt.historical.enabled ? language.text("allowed", "已允许") : language.text("stopped", "已停用")), style: .body)
                        .accessibilityIdentifier("historyConsent.receiptResult")
                } header: { MemoryRowText(text: language.text("Historical receipt", "历史回执"), style: .caption).accessibilityAddTraits(.isHeader) }
            }
        }.navigationTitle(language.text("Conversation history", "会话历史整理"))
    }
    private func changeTitle(_ change: MemoryHistoryChange) -> String {
        change == .enable ? language.text("Allow this source", "允许此来源") : language.text("Stop this source", "停用此来源")
    }
    private var status: String {
        switch model.state {
        case .unconfigured: language.text("History settings are not connected for this account. No change was sent.", "当前账号的历史设置尚未接入，未发送变更。")
        case .unselected: language.text("Choose one conversation in Assistant server history first.", "请先在助手的服务器历史中选择一段会话。")
        case .unread: language.text("Read current settings before making a change.", "请先读取当前设置，再明确变更。")
        case .loading: language.text("Reading current settings and original changes…", "正在读取当前设置与原变更…")
        case .ready: model.hasUnresolved ? language.text("Current settings were read. Check the unresolved original change before another change.", "当前设置已读取。请先核对尚未确认的原变更，再发起新变更。") : language.text("Current settings were read. Changes apply only to this conversation.", "当前设置已读取。变更只适用于这段会话。")
        case .changing: language.text("Submitting this conversation's change…", "正在提交本会话的变更…")
        case .reconciling: language.text("Checking the original change…", "正在查询原变更…")
        case .unknown: language.text("The change is not confirmed. Keep the original and query it; do not resend.", "变更结果尚未确认。请保留原记录并查询，不要重新发送。")
        case .conflict: language.text("The source changed. Read and review current settings before a new explicit change; the original is retained.", "来源版本已变化。请重新读取并核对当前设置，再明确发起新变更；原操作已保留。")
        case .unavailable: model.receipt != nil ? language.text("The original change was recorded, but current settings could not be verified.", "原变更已记录，但当前设置尚未核实。") : language.text("Current settings could not be verified. This does not mean organization is off or on.", "暂时无法核验当前设置，不能据此认为已关闭或已启用。")
        case .recoveryUnavailable: language.text("The original change could not be verified. Keep it; this is not proof it was not submitted.", "暂时无法核验原变更。请保留记录，这不代表未提交。")
        }
    }
}
