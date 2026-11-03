#if os(iOS)
import SwiftUI
import CJAPI
import CJRunClient
import CJMessageHTTP

struct ServerHistoryView: View {
    let host: ServerHistoryHost
    let language: ShellLanguage
    var body: some View {
        let readContext = host.captureReadContext()
        let writeContext = host.captureDraftWriteContext()
        let queryContext = host.captureDraftQueryContext()
        let cancelContext = host.captureDraftCancelContext()
        ScrollView {
          VStack(alignment: .leading, spacing: 16) {
            RunReadableText(text: language.text("Server records. Local recovery is a separate source. Reads never replace your editor.", "服务器记录，与本地恢复不同。读取不会替换编辑中的草稿。"))
            if host.isSynthetic { RunReadableText(text: language.text("Synthetic intercepted responses", "合成拦截响应")) }
            Section {
                status(host.conversationsStatus)
                Button { Task { await host.loadConversations(context:readContext) } } label: {
                    RunReadableText(text:language.text("Load from first page", "从第一页读取"))
                        .frame(maxWidth:.infinity,minHeight:44,alignment:.leading).contentShape(Rectangle())
                }.buttonStyle(.plain)
                    .accessibilityIdentifier("history.loadConversations")
                    .disabled(!host.isConfigured || host.conversationsStatus == .loading || host.draftWriteStatus == .saving || host.draftQueryStatus == .loading)
                let selectionToken = host.conversationSelectionToken
                ForEach(host.conversations, id: \.conversationBytes) { row in
                    historyButton(row.conversation_id) { _ = host.selectConversation(row, token: selectionToken) }
                        .accessibilityIdentifier("history.conversation." + row.conversation_id)
                        .disabled(host.draftWriteStatus == .saving || host.draftQueryStatus == .loading)
                }
                if host.hasMoreConversations {
                    historyButton(language.text("Next conversations page", "下一页会话")) { Task { await host.loadConversations(context: readContext, more: true) } }
                        .accessibilityIdentifier("history.nextConversations")
                        .disabled(host.draftWriteStatus == .saving || host.draftQueryStatus == .loading)
                }
            } header: {
                RunReadableText(text:language.text("Conversations", "会话"),style:.headline)
                    .accessibilityAddTraits(.isHeader)
            }
            if let selected = host.selectedConversation {
                Section {
                    status(host.historyStatus).accessibilityIdentifier("history.messages.status")
                    historyButton(language.text("Load messages from first page", "从第一页读取消息")) { Task { await host.loadHistory(context: readContext) } }
                        .accessibilityIdentifier("history.loadMessages")
                        .disabled(host.historyStatus == .loading)
                    ForEach(host.humanMessages, id: \.id) { row in
                        humanMessage(row)
                    }
                    ForEach(host.messages, id: \.messageBytes) { row in
                        RunReadableText(text: row.text).textSelection(.enabled).accessibilityIdentifier("history.message." + row.receipt.message_id)
                    }
                    if host.hasMoreMessages {
                        historyButton(language.text("Next messages page", "下一页消息")) { Task { await host.loadHistory(context: readContext, more: true) } }
                            .accessibilityIdentifier("history.nextMessages")
                    }
                } header: { historyHeading(language.text("Stored messages", "已存消息") + " · " + selected.conversation_id) }
                Section {
                    status(host.draftStatus)
                    historyButton(language.text("Read server draft", "读取服务器草稿")) { Task { await host.loadServerDraft(context: readContext) } }
                        .disabled(host.draftStatus == .loading)
                    if let draft = host.serverDraft {
                        RunReadableText(text: language.text("Saved revision", "保存版本") + " \(draft.revision)")
                        if let bytes = Data(base64Encoded: draft.original_utf8_base64), let text = String(data: bytes, encoding: .utf8) {
                            RunReadableText(text: text.isEmpty ? language.text("Saved empty draft", "已保存的空草稿") : text).textSelection(.enabled)
                        }
                    }
                } header: { historyHeading(language.text("Server draft — read only", "服务器草稿——只读")) }
                Section {
                    RunReadableText(text: writeStatus)
                    RunReadableText(text: language.text("Draft saving is unavailable in this session. Reading history does not grant permission to save.", "此会话暂不能保存草稿。读取历史不会授予保存权限。"), style: .caption)
                    historyButton(language.text("Save current editor draft", "保存当前编辑草稿")) {
                        host.saveServerDraft(context: writeContext)
                    }.disabled(writeContext == nil)
                    if host.draftWriteStatus == .saving {
                        historyButton(language.text("Cancel local waiting", "取消本地等待")) { host.cancelServerDraftSave(context: cancelContext) }
                            .disabled(cancelContext == nil)
                    }
                    historyButton(language.text("Query original draft operation", "查询原草稿操作")) {
                        Task { await host.queryOriginalDraft(context: queryContext) }
                    }.disabled(queryContext == nil)
                    RunReadableText(text: queryStatus, style: .caption)
                } header: { historyHeading(language.text("Server draft save", "服务器草稿保存")) }
            }
          }.frame(maxWidth: .infinity, alignment: .leading).padding()
        }.navigationTitle(language.text("Server history", "服务器历史"))
    }
    private func historyHeading(_ text: String) -> some View {
        RunReadableText(text: text, style: .headline).accessibilityAddTraits(.isHeader).textCase(nil)
    }
    private func historyButton(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title).fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle())
        }.buttonStyle(ShellReadableButtonStyle())
    }
    @ViewBuilder private func humanMessage(_ row: MessageHumanHistoryItem) -> some View {
        let run = host.humanRun(row)
        let source = run?.sourceState ?? row.sourceState
        let context = host.captureHumanRun(row)
        RunReadableText(text: row.text).textSelection(.enabled)
            .accessibilityIdentifier("history.message." + row.receipt.message_id)
        if source == .erased {
            RunReadableText(text: language.text(
                "The original model source was cleared. This history is available for viewing only.",
                "原模型来源已清理，这段历史仅供查看。"))
                .accessibilityIdentifier("history.source.erased." + row.receipt.message_id)
        }
        Button { Task { await host.loadHumanRun(context: context) } } label: {
            RunReadableText(text: language.text("Read original answer", "读取原回答")).frame(minHeight: 44)
        }.disabled(context == nil)
            .accessibilityIdentifier("history.answer.read." + row.receipt.message_id)
        status(host.humanRunStatus(row))
            .accessibilityIdentifier("history.answer.status." + row.receipt.message_id)
        if let run {
            RunReadableText(text: run.snapshot.text).textSelection(.enabled)
                .accessibilityIdentifier("history.answer.text." + row.receipt.message_id)
            RunReadableText(text: language.text(
                "Reading this answer does not resend the message or restart its task.",
                "读取原回答不会重发消息或重新执行任务。"))
                .accessibilityIdentifier("history.answer.readonly." + row.receipt.message_id)
        }
    }
    private var writeStatus: String {
        switch host.draftWriteStatus {
        case .unavailable: language.text("Save unavailable: no separate write capability.", "保存不可用：没有独立写能力。")
        case .ready: language.text("Save requires an explicit current version and editor snapshot.", "保存需要明确的当前版本和编辑快照。")
        case .saving: language.text("Saving the original editor snapshot…", "正在保存原编辑快照…")
        case .savedCurrentEdit: language.text("This exact editor revision was confirmed saved.", "此编辑版本已获原响应确认保存。")
        case .savedEarlierEdit: language.text("An earlier editor snapshot was saved. Current edits are not marked saved.", "较早的编辑快照已保存，当前编辑未标为已保存。")
        case .queryOnly: language.text("Original operation retained. Query only; do not retry save.", "原操作已保留，仅可查询，请勿重试保存。")
        case .unknown: language.text("Save result unknown. Original CAS retained; query only.", "保存结果未知，原 CAS 已保留，仅可查询。")
        case .conflict: language.text("Save conflicted. Original CAS retained; no automatic replacement.", "保存冲突，原 CAS 已保留，不自动替换。")
        case .blocked: language.text("Draft save is blocked. No new write or saved-state claim is permitted.", "草稿保存已阻断，不能新增写入或宣称保存成功。")
        }
    }
    private var queryStatus: String {
        switch host.draftQueryStatus {
        case .idle: language.text("A GET observation cannot resolve an unknown write or grant save permission.", "GET 观察不能确认未知写入，也不能授予保存许可。")
        case .loading: language.text("Querying only the original CAS target…", "仅查询原 CAS 目标中…")
        case .observed: language.text("Server draft observed. Original write remains unresolved, even if content matches.", "已观察到服务器草稿；即使内容一致，原写入仍未解决。")
        case .missing: language.text("No draft observed. Null does not authorize another save.", "未观察到草稿。null 不允许再次保存。")
        case .failed: language.text("Query failed. Original write remains unresolved.", "查询失败，原写入仍未解决。")
        }
    }
    private func status(_ value: ServerReadStatus) -> some View {
        Group {
            switch value {
            case .unconfigured: RunReadableText(text: language.text("Unavailable: no trusted server binding.", "不可用：尚无可信服务器绑定。"))
            case .idle: RunReadableText(text: language.text("Not loaded. Choose an explicit read.", "尚未加载，请明确选择读取。"))
            case .loading: ProgressView(language.text("Loading…", "正在读取…"))
            case .empty: RunReadableText(text: language.text("The read returned no records.", "本次读取未返回记录。"))
            case .ready: EmptyView()
            case .failed: RunReadableText(text: language.text("Read failed. No empty or successful result is inferred. Restart explicitly.", "读取失败，不能推定为空或成功。请明确重新读取。"))
            case .resync: RunReadableText(text: language.text("Resynchronization required. The old page chain was discarded; restart from the first page.", "需要重新同步。旧分页链已丢弃，请从第一页重新读取。"))
            }
        }
    }
}
private extension Components.Schemas.ConversationSummary { var conversationBytes: Data { Data(conversation_id.utf8) } }
private extension Components.Schemas.MessageHistoryItem { var messageBytes: Data { Data(receipt.message_id.utf8) } }
#endif
