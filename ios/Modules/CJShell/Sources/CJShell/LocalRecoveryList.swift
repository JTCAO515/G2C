#if os(iOS)
import SwiftUI
import CJMessageClient
import CJRunClient

private extension LocalActionReference { var byteIdentity: Data { Data(messageID.utf8) } }
private extension LocalDraftReference { var byteIdentity: Data { Data(conversationID.utf8) } }

struct LocalRecoveryList: View {
    let host: AssistantMessageHost
    let language: ShellLanguage
    @State private var pendingDraft: (LocalDraftReference, LocalRecoveryProjection)?
    @State private var selectionFailed = false
    var body: some View {
        List {
            Text(language.text("Unordered local references — not server history. No message or draft text is shown here.", "无序本地引用，并非服务端历史。这里不展示消息或草稿原文。"))
            if host.isSynthetic { Text(language.text("Synthetic local fixture", "合成本地样例")) }
            if selectionFailed { Text(language.text("Selection is no longer available. No content was loaded.", "该选择已不可用，未加载内容。")) }
            if let projection = host.visibleProjection {
                if projection.actions.isEmpty && projection.drafts.isEmpty {
                    Text(language.text("No local references in this snapshot. This does not establish empty server history.", "本地快照暂无引用，不能据此认定服务端历史为空。"))
                }
                Section(language.text("Local drafts", "本地草稿")) {
                    ForEach(projection.drafts, id: \.byteIdentity) { reference in
                        Button { pendingDraft = (reference, projection) } label: {
                            Label(reference.conversationID, systemImage: "doc.text")
                        }.disabled(!host.canSelectLocalItem)
                    }
                }
                Section(language.text("Local actions", "本地操作")) {
                    ForEach(projection.actions, id: \.byteIdentity) { reference in
                        Button {
                            selectionFailed = !host.selectAction(reference, from: projection)
                        } label: {
                            VStack(alignment: .leading) {
                                Text(reference.messageID)
                                Text(phase(reference.phase)).font(.caption)
                            }
                        }.disabled(!host.canSelectLocalItem)
                            .accessibilityIdentifier("recovery.action." + reference.messageID)
                    }
                }
                if host.supportsTripDiscussions {
                    Section(language.text("Original new-chat requests","原新聊天请求")) {
                        ForEach(host.conversationOpenings.sorted { Data($0.conversationID.utf8).lexicographicallyPrecedes(Data($1.conversationID.utf8)) },id:\.conversationID) { record in
                            let query=host.captureConversationQuery(id:record.conversationID)
                            let selection=host.captureConversationSelection(id:record.conversationID)
                            VStack(alignment:.leading,spacing:8) {
                                RunSelectableText(text:record.conversationID)
                                RunReadableText(text:openingPhase(record.phase),style:.caption)
                                Button(language.text("Check original chat","核对原聊天")) { if let query { host.performConversationIntent(query) } }
                                    .disabled(query==nil).accessibilityIdentifier("conversation.query."+record.conversationID)
                                Button(language.text("Select this chat","选择此聊天")) { if let selection { host.performConversationIntent(selection) } }
                                    .disabled(selection==nil).accessibilityIdentifier("conversation.select."+record.conversationID)
                            }
                        }
                    }
                }
            } else {
                Text(language.text("Local recovery is unavailable or not configured.", "本地恢复不可用或尚未配置。"))
            }
        }
        .confirmationDialog(language.text("Replace the editor with this local draft?", "用此本地草稿替换当前编辑内容？"),
            isPresented: Binding(get: { pendingDraft != nil }, set: { if !$0 { pendingDraft = nil } }), titleVisibility: .visible) {
            Button(language.text("Load selected draft", "加载所选草稿")) {
                if let (reference, projection) = pendingDraft {
                    selectionFailed = !host.selectDraft(reference, from: projection)
                }
                pendingDraft = nil
            }
            Button(language.text("Cancel", "取消"), role: .cancel) { pendingDraft = nil }
        }
        .onChange(of: host.isConfigured) { _, configured in if !configured { pendingDraft = nil } }
    }
    private func phase(_ value: ActionPhase) -> String {
        switch value {
        case .staged: language.text("Staged locally — send unavailable", "本地暂存，发送不可用")
        case .queryRequired: language.text("Query only", "仅可查询")
        case .notObserved: language.text("Receipt not observed — do not resend", "未观察到回执，请勿重发")
        case .accepted: language.text("Original-action receipt available", "原操作已有回执")
        case .notAccepted: language.text("Original request will no longer be accepted", "原请求不会再被接受")
        case .integrityError: language.text("Integrity mismatch — sending stopped", "完整性不一致，已停止发送")
        case .resyncRequired: language.text("Resynchronization required — sending stopped", "需要重新同步，已停止发送")
        }
    }
    private func openingPhase(_ value:ConversationOpeningPhase) -> String {
        switch value {
        case .queryRequired:language.text("Original result unknown — query only","原结果未知——仅可查询")
        case .available:language.text("Historical chat availability recorded; sending still needs a fresh read","已记录历史可读结果；发送仍需新读取")
        case .failed:language.text("Original request failed; retained for reconciliation","原请求失败，保留以供核对")
        }
    }
}
#endif
