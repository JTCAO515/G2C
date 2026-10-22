#if os(iOS)
import SwiftUI
import CJAPI

struct ServerHistoryView: View {
    let host: ServerHistoryHost
    let language: ShellLanguage
    var body: some View {
        let readContext = host.captureReadContext()
        List {
            Text(language.text("Server read-only records. Local recovery is a separate source. Your editor will not be changed.", "服务器只读记录，与本地恢复不同。不会修改编辑中的草稿。"))
            if host.isSynthetic { Text(language.text("Synthetic intercepted responses", "合成拦截响应")) }
            Section(language.text("Conversations", "会话")) {
                status(host.conversationsStatus)
                Button(language.text("Load from first page", "从第一页读取")) { Task { await host.loadConversations(context: readContext) } }
                    .disabled(!host.isConfigured || host.conversationsStatus == .loading)
                let selectionToken = host.conversationSelectionToken
                ForEach(host.conversations, id: \.conversationBytes) { row in
                    Button(row.conversation_id) { _ = host.selectConversation(row, token: selectionToken) }
                }
                if host.hasMoreConversations {
                    Button(language.text("Next conversations page", "下一页会话")) { Task { await host.loadConversations(context: readContext, more: true) } }
                }
            }
            if let selected = host.selectedConversation {
                Section(language.text("Stored messages", "已存消息") + " · " + selected.conversation_id) {
                    status(host.historyStatus)
                    Button(language.text("Load messages from first page", "从第一页读取消息")) { Task { await host.loadHistory(context: readContext) } }
                        .disabled(host.historyStatus == .loading)
                    ForEach(host.messages, id: \.messageBytes) { row in
                        Text(row.text).textSelection(.enabled)
                    }
                    if host.hasMoreMessages {
                        Button(language.text("Next messages page", "下一页消息")) { Task { await host.loadHistory(context: readContext, more: true) } }
                    }
                }
                Section(language.text("Server draft — read only", "服务器草稿——只读")) {
                    status(host.draftStatus)
                    Button(language.text("Read server draft", "读取服务器草稿")) { Task { await host.loadServerDraft(context: readContext) } }
                        .disabled(host.draftStatus == .loading)
                    if let draft = host.serverDraft {
                        Text(language.text("Saved revision", "保存版本") + " \(draft.revision)")
                        if let bytes = Data(base64Encoded: draft.original_utf8_base64), let text = String(data: bytes, encoding: .utf8) {
                            Text(text.isEmpty ? language.text("Saved empty draft", "已保存的空草稿") : text).textSelection(.enabled)
                        }
                    }
                }
            }
        }.navigationTitle(language.text("Server history", "服务器历史"))
    }
    private func status(_ value: ServerReadStatus) -> some View {
        Group {
            switch value {
            case .unconfigured: Text(language.text("Unavailable: no trusted server binding.", "不可用：尚无可信服务器绑定。"))
            case .idle: Text(language.text("Not loaded. Choose an explicit read.", "尚未加载，请明确选择读取。"))
            case .loading: ProgressView(language.text("Loading…", "正在读取…"))
            case .empty: Text(language.text("The read returned no records.", "本次读取未返回记录。"))
            case .ready: EmptyView()
            case .failed: Text(language.text("Read failed. No empty or successful result is inferred. Restart explicitly.", "读取失败，不能推定为空或成功。请明确重新读取。"))
            case .resync: Text(language.text("Resynchronization required. The old page chain was discarded; restart from the first page.", "需要重新同步。旧分页链已丢弃，请从第一页重新读取。"))
            }
        }
    }
}
private extension Components.Schemas.ConversationSummary { var conversationBytes: Data { Data(conversation_id.utf8) } }
private extension Components.Schemas.MessageHistoryItem { var messageBytes: Data { Data(receipt.message_id.utf8) } }
#endif
