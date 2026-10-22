import Foundation
import Observation
import CJMessageClient
import CJMessageHTTP
import CJAPI

public enum ServerReadStatus: Equatable { case unconfigured, idle, loading, ready, empty, failed, resync }

/// Explicit trusted composition only. No endpoint/credentials/client is constructed by the UI.
@MainActor public struct ServerHistoryBinding {
    fileprivate let id = UUID()
    let client: MessageHTTPClient
    let recovery: MessageRecovery
    let scope: StorageScope
    let lease: Lease
    let generation: ShellGeneration
    let limit: Int
    let limits: MessageReadLimits
    let synthetic: Bool
    let isCurrent: @MainActor () -> Bool
    public init(client: MessageHTTPClient, recovery: MessageRecovery, scope: StorageScope, lease: Lease,
                generation: ShellGeneration, limit: Int, limits: MessageReadLimits, synthetic: Bool,
                isCurrent: @escaping @MainActor () -> Bool) {
        self.client = client; self.recovery = recovery; self.scope = scope; self.lease = lease
        self.generation = generation; self.limit = limit; self.limits = limits
        self.synthetic = synthetic; self.isCurrent = isCurrent
    }
}

/// Local action origin captured before Task creation. Not a wire cursor or authority.
@MainActor public struct ServerReadContext {
    fileprivate let binding: ServerHistoryBinding
    fileprivate let selectionEpoch: UUID
    fileprivate let listRequest: UUID
    fileprivate let historyRequest: UUID
    fileprivate let draftRequest: UUID
    fileprivate let selected: Components.Schemas.ConversationSummary?
    fileprivate let listCursor: MessageReadCursor?
    fileprivate let historyCursor: MessageReadCursor?
}

@MainActor @Observable public final class ServerHistoryHost {
    private let shell: ShellState
    private var binding: ServerHistoryBinding?
    private var listState: ServerReadStatus = .unconfigured
    private var messagesState: ServerReadStatus = .unconfigured
    private var serverDraftState: ServerReadStatus = .unconfigured
    private var listPages: [MessageReadResult<[Components.Schemas.ConversationSummary]>] = []
    private var messagePages: [MessageReadResult<[Components.Schemas.MessageHistoryItem]>] = []
    private var draftResult: MessageReadResult<Components.Schemas.MessageDraftSnapshot?>?
    private var selection: Components.Schemas.ConversationSummary?
    private var selectionEpoch = UUID()
    private var listRequest = UUID()
    private var historyRequest = UUID()
    private var draftRequest = UUID()
    public var isConfigured: Bool { current }
    public var isSynthetic: Bool { current && binding?.synthetic == true }
    public var conversationsStatus: ServerReadStatus { current ? listState : .unconfigured }
    public var historyStatus: ServerReadStatus { current ? messagesState : .unconfigured }
    public var draftStatus: ServerReadStatus { current ? serverDraftState : .unconfigured }
    public var conversationSelectionToken: UUID { listRequest }
    public var selectedConversation: Components.Schemas.ConversationSummary? { current ? selection : nil }
    public var conversations: [Components.Schemas.ConversationSummary] {
        guard current, let binding, listPages.allSatisfy({ (try? binding.client.validateRead($0, lease: binding.lease)) != nil }) else { return [] }
        return listPages.flatMap(\.value)
    }
    public var messages: [Components.Schemas.MessageHistoryItem] {
        guard current, let binding, messagePages.allSatisfy({ (try? binding.client.validateRead($0, lease: binding.lease)) != nil }) else { return [] }
        return messagePages.flatMap(\.value)
    }
    public var serverDraft: Components.Schemas.MessageDraftSnapshot? {
        guard current, let binding, let draftResult,
              (try? binding.client.validateRead(draftResult, lease: binding.lease)) != nil else { return nil }
        return draftResult.value
    }
    public var hasMoreConversations: Bool { current && listState == .ready && listPages.last?.next != nil }
    public var hasMoreMessages: Bool { current && messagesState == .ready && messagePages.last?.next != nil }
    public init(shell: ShellState) {
        self.shell = shell
        shell.serverHistoryHost?.invalidate()
        shell.serverHistoryHost = self
    }
    func belongs(to shell: ShellState) -> Bool { self.shell === shell }
    @discardableResult public func bind(_ candidate: ServerHistoryBinding) -> Bool {
        guard binding == nil, !shell.messageBindingBlocked, candidate.generation == shell.generation,
              candidate.isCurrent(), candidate.generation == shell.generation,
              (1...candidate.limits.maximumPageItems).contains(candidate.limit),
              (try? candidate.recovery.validateScope(candidate.scope, lease: candidate.lease)) != nil else { return false }
        guard binding == nil, !shell.messageBindingBlocked, candidate.generation == shell.generation else { return false }
        binding = candidate; listState = .idle; messagesState = .idle; serverDraftState = .idle
        return true
    }
    private var current: Bool {
        guard let binding, !shell.messageBindingBlocked, binding.generation == shell.generation,
              binding.isCurrent() else { return false }
        return self.binding?.id == binding.id && shell.generation == binding.generation
            && (try? binding.recovery.validateScope(binding.scope, lease: binding.lease)) != nil
    }
    private func current(_ original: ServerHistoryBinding) -> Bool { current && binding?.id == original.id }
    public func invalidate() {
        selectionEpoch = UUID()
        binding = nil; listRequest = UUID(); historyRequest = UUID(); draftRequest = UUID()
        listPages = []; messagePages = []; draftResult = nil; selection = nil
        listState = .unconfigured; messagesState = .unconfigured; serverDraftState = .unconfigured
        // Root owns shared recovery/credential resources. This host only retires read projections.
    }
    public func captureReadContext() -> ServerReadContext? {
        guard current, let binding else { return nil }
        return ServerReadContext(binding: binding, selectionEpoch: selectionEpoch,
            listRequest: listRequest, historyRequest: historyRequest, draftRequest: draftRequest,
            selected: selection, listCursor: listPages.last?.next, historyCursor: messagePages.last?.next)
    }
    private func accepts(_ context: ServerReadContext) -> Bool {
        current(context.binding) && selectionEpoch == context.selectionEpoch
    }

    public func loadConversations(context: ServerReadContext?, more: Bool = false) async {
        guard let context, accepts(context), listRequest == context.listRequest,
              listState != .loading, !more || hasMoreConversations else { return }
        let original = context.binding
        let cursor = more ? context.listCursor : nil
        if !more {
            selectionEpoch = UUID()
            listPages = []; selection = nil; messagePages = []; draftResult = nil
            historyRequest = UUID(); draftRequest = UUID(); messagesState = .idle; serverDraftState = .idle
        }
        let resultSelectionEpoch = selectionEpoch
        let request = UUID(); listRequest = request; listState = .loading
        do {
            let result = try await original.client.conversations(limit: original.limit, after: cursor, limits: original.limits, lease: original.lease)
            try original.client.validateRead(result, lease: original.lease)
            guard current(original), listRequest == request, selectionEpoch == resultSelectionEpoch else { return }
            listPages.append(result)
            listState = listPages.flatMap(\.value).isEmpty ? .empty : .ready
        } catch {
            guard current(original), listRequest == request, selectionEpoch == resultSelectionEpoch else { return }
            selectionEpoch = UUID()
            listPages = []; selection = nil; messagePages = []; draftResult = nil
            historyRequest = UUID(); draftRequest = UUID(); messagesState = .idle; serverDraftState = .idle
            listState = status(for: error)
        }
    }
    @discardableResult public func selectConversation(_ row: Components.Schemas.ConversationSummary, token: UUID) -> Bool {
        guard token == listRequest, current, conversations.contains(where: { Data($0.conversation_id.utf8) == Data(row.conversation_id.utf8) && Data($0.generation.utf8) == Data(row.generation.utf8) && $0.epoch == row.epoch }) else { return false }
        selectionEpoch = UUID()
        listRequest = UUID() // retire a list read issued under the previous selected context
        if listState == .loading { listState = listPages.isEmpty ? .idle : .ready }
        selection = row; messagePages = []; draftResult = nil
        historyRequest = UUID(); draftRequest = UUID(); messagesState = .idle; serverDraftState = .idle
        return true
    }
    public func loadHistory(context: ServerReadContext?, more: Bool = false) async {
        guard let context, accepts(context), historyRequest == context.historyRequest,
              let selected = context.selected, messagesState != .loading,
              !more || hasMoreMessages else { return }
        let original = context.binding
        let cursor = more ? context.historyCursor : nil
        if !more { messagePages = [] }
        let request = UUID(); historyRequest = request; messagesState = .loading
        do {
            let result = try await original.client.history(conversationID: selected.conversation_id, limit: original.limit,
                after: cursor, limits: original.limits, lease: original.lease)
            try original.client.validateRead(result, lease: original.lease)
            guard current(original), selectionEpoch == context.selectionEpoch, historyRequest == request else { return }
            guard result.value.allSatisfy({ Data($0.receipt.generation.utf8) == Data(selected.generation.utf8) }) else {
                throw MessageReadFailure.resyncRequired
            }
            messagePages.append(result); messagesState = messagePages.flatMap(\.value).isEmpty ? .empty : .ready
        } catch {
            guard current(original), selectionEpoch == context.selectionEpoch, historyRequest == request else { return }
            messagePages = []; messagesState = status(for: error)
        }
    }
    public func loadServerDraft(context: ServerReadContext?) async {
        guard let context, accepts(context), draftRequest == context.draftRequest,
              let selected = context.selected, serverDraftState != .loading else { return }
        let original = context.binding
        let request = UUID(); draftRequest = request; draftResult = nil; serverDraftState = .loading
        do {
            let result = try await original.client.draft(conversationID: selected.conversation_id, generation: selected.generation,
                limits: original.limits, lease: original.lease)
            try original.client.validateRead(result, lease: original.lease)
            guard current(original), selectionEpoch == context.selectionEpoch, draftRequest == request else { return }
            draftResult = result; serverDraftState = result.value == nil ? .empty : .ready
            // Deliberately never assign shell.draft: server reads cannot overwrite local editing.
        } catch {
            guard current(original), selectionEpoch == context.selectionEpoch, draftRequest == request else { return }
            draftResult = nil; serverDraftState = status(for: error)
        }
    }
    private func status(for error: Error) -> ServerReadStatus {
        if case MessageReadFailure.resyncRequired = error { return .resync }
        return .failed // no raw request/error/credential details cross the UI boundary
    }
}
