import Foundation
import Observation
import CJMessageClient
import CJMessageHTTP
import CJAPI

public enum ServerDraftWriteCapability { case interceptedTestOnly }
public enum ServerDraftWriteStatus: Equatable { case unavailable, ready, saving, savedCurrentEdit, savedEarlierEdit, queryOnly, unknown, conflict, blocked }
public enum ServerDraftQueryStatus: Equatable { case idle, loading, observed, missing, failed }

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
    let draftWriteCapability: ServerDraftWriteCapability?
    let isCurrent: @MainActor () -> Bool
    let selectForSending: (@MainActor (String) -> Bool)?
    public init(client: MessageHTTPClient, recovery: MessageRecovery, scope: StorageScope, lease: Lease,
                generation: ShellGeneration, limit: Int, limits: MessageReadLimits, synthetic: Bool,
                draftWriteCapability: ServerDraftWriteCapability? = nil, isCurrent: @escaping @MainActor () -> Bool,
                selectForSending: (@MainActor (String) -> Bool)? = nil) {
        self.client = client; self.recovery = recovery; self.scope = scope; self.lease = lease
        self.generation = generation; self.limit = limit; self.limits = limits
        self.synthetic = synthetic; self.isCurrent = isCurrent
        self.draftWriteCapability = draftWriteCapability
        self.selectForSending = selectForSending
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

@MainActor public struct ServerDraftWriteContext {
    fileprivate let read: ServerReadContext
    fileprivate let bytes: Data
    fileprivate let editorRevision: UUID
    fileprivate let expectedRevision: Int64
    fileprivate let writeEpoch: UUID
}
/// Captured while the original cancel control is displayed; never resolves a later task.
@MainActor public struct ServerDraftCancelContext {
    fileprivate let bindingID: UUID
    fileprivate let generation: ShellGeneration
    fileprivate let selectionEpoch: UUID
    fileprivate let writeEpoch: UUID
    fileprivate let task: Task<Void, Never>
}
@MainActor public struct ServerDraftQueryContext {
    fileprivate let read: ServerReadContext
    fileprivate let original: DraftSaveRecord
    fileprivate let writeEpoch: UUID
    fileprivate let queryRequest: UUID
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
    private var writeEpoch = UUID()
    private var writeTask: Task<Void, Never>?
    private var writeState: ServerDraftWriteStatus = .ready
    private var writeCancelled = false
    private var confirmation: DraftSaveConfirmation?
    private var confirmedEdit: UUID?
    private var queryState: ServerDraftQueryStatus = .idle
    private var draftQueryRequest = UUID()
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
        let pendingWrite = writeTask
        writeTask = nil; writeEpoch = UUID(); confirmation = nil; confirmedEdit = nil
        writeState = .ready; writeCancelled = false; queryState = .idle
        selectionEpoch = UUID()
        binding = nil; listRequest = UUID(); historyRequest = UUID(); draftRequest = UUID()
        listPages = []; messagePages = []; draftResult = nil; selection = nil
        listState = .unconfigured; messagesState = .unconfigured; serverDraftState = .unconfigured
        // Retire all state before cancellation can invoke external completion handlers.
        pendingWrite?.cancel()
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
              listState != .loading, writeState != .saving, queryState != .loading,
              !more || hasMoreConversations else { return }
        let original = context.binding
        let cursor = more ? context.listCursor : nil
        if !more {
            guard writeState != .saving && queryState != .loading else { return }
            resetWriteSelection()
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
        guard writeState != .saving && queryState != .loading else { return false }
        guard let original = binding else { return false }
        if let select = original.selectForSending {
            guard select(row.conversation_id), current(original), token == listRequest else { return false }
        }
        resetWriteSelection()
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
    private func resetWriteSelection() {
        writeEpoch = UUID(); confirmation = nil; confirmedEdit = nil
        if writeState != .blocked { writeState = .ready }
        queryState = .idle
        // Selection or GET refresh is not authority to remove a local cancellation barrier.
    }
    private var pendingDraft: DraftSaveRecord? {
        guard current, let binding, let selection else { return nil }
        return try? binding.recovery.draftSave(conversationID: selection.conversation_id, lease: binding.lease)
    }
    public var draftWriteStatus: ServerDraftWriteStatus {
        guard current, let binding, let selected = selection else { return .unavailable }
        if writeState == .saving { return .saving }
        if let record = pendingDraft {
            guard Data(record.generation.utf8) == Data(selected.generation.utf8) else { return .blocked }
            if record.confirmedRevision == nil || writeCancelled {
                return writeState == .conflict ? .conflict : (writeState == .unknown ? .unknown : .queryOnly)
            }
            if let confirmation, confirmedEdit == shell.draftRevision,
               Data(base64Encoded: confirmation.snapshot.original_utf8_base64) == Data(shell.draft.utf8),
               (try? binding.client.validateDraftConfirmation(confirmation, lease: binding.lease)) == true {
                return .savedCurrentEdit
            }
            return .savedEarlierEdit
        }
        if writeState == .blocked || writeCancelled { return .blocked }
        guard binding.synthetic, binding.draftWriteCapability == .interceptedTestOnly else { return .unavailable }
        return .ready
    }
    public var draftQueryStatus: ServerDraftQueryStatus { current ? queryState : .idle }
    public func captureDraftWriteContext() -> ServerDraftWriteContext? {
        guard let read = captureReadContext(), let selected = read.selected,
              read.binding.synthetic, read.binding.draftWriteCapability == .interceptedTestOnly,
              listState != .loading, writeState != .saving, writeState != .blocked, !writeCancelled, queryState != .loading else { return nil }
        let revision: Int64
        if let prior = try? read.binding.recovery.draftSave(conversationID: selected.conversation_id, lease: read.binding.lease) {
            guard let confirmed = prior.confirmedRevision, Data(prior.generation.utf8) == Data(selected.generation.utf8) else { return nil }
            revision = confirmed
        } else {
            guard let draftResult, serverDraftState == .ready || serverDraftState == .empty,
                  (try? read.binding.client.validateRead(draftResult, lease: read.binding.lease)) != nil else { return nil }
            revision = draftResult.value?.revision ?? 0
        }
        guard accepts(read), revision < Int64.max else { return nil }
        return ServerDraftWriteContext(read: read, bytes: Data(shell.draft.utf8), editorRevision: shell.draftRevision,
                                       expectedRevision: revision, writeEpoch: writeEpoch)
    }
    private func ownsWrite(_ context: ServerReadContext, epoch: UUID) -> Bool {
        binding?.id == context.binding.id && shell.generation == context.binding.generation
            && selectionEpoch == context.selectionEpoch && writeEpoch == epoch
    }
    @discardableResult public func saveServerDraft(context: ServerDraftWriteContext?) -> Task<Void, Never>? {
        guard let context, accepts(context.read), ownsWrite(context.read, epoch: context.writeEpoch),
              draftRequest == context.read.draftRequest, let selected = context.read.selected,
              shell.draftRevision == context.editorRevision, Data(shell.draft.utf8) == context.bytes,
              captureDraftWriteContext() != nil else { return nil }
        guard ownsWrite(context.read, epoch: context.writeEpoch), shell.draftRevision == context.editorRevision else { return nil }
        let original = context.read.binding
        let epoch = UUID(); writeEpoch = epoch; writeState = .saving; confirmation = nil; confirmedEdit = nil
        do {
            try original.recovery.saveDraft(context.bytes, conversationID: selected.conversation_id, lease: original.lease)
        } catch {
            if ownsWrite(context.read, epoch: epoch) { writeState = .blocked }
            return nil
        }
        guard ownsWrite(context.read, epoch: epoch), current(original) else { return nil }
        let task = Task { [weak self] in
            guard self?.current(original) == true, self?.ownsWrite(context.read, epoch: epoch) == true, !Task.isCancelled else {
                if self?.ownsWrite(context.read, epoch: epoch) == true { self?.writeState = .blocked; self?.writeTask = nil }
                return
            }
            do {
                let result = try await original.client.saveDraft(conversationID: selected.conversation_id, generation: selected.generation,
                    expectedRevision: context.expectedRevision, originalUTF8: context.bytes, limits: original.limits, lease: original.lease)
                let matches = try original.client.validateDraftConfirmation(result, lease: original.lease)
                guard let self, self.ownsWrite(context.read, epoch: epoch), self.current(original) else { return }
                self.writeTask = nil
                if self.writeCancelled || Task.isCancelled { self.writeState = .queryOnly; return }
                self.confirmation = result; self.confirmedEdit = context.editorRevision
                self.writeState = matches && self.shell.draftRevision == context.editorRevision ? .savedCurrentEdit : .savedEarlierEdit
                self.draftResult = nil; self.serverDraftState = .idle; self.draftRequest = UUID()
            } catch {
                guard let self, self.ownsWrite(context.read, epoch: epoch) else { return }
                self.writeTask = nil
                if !self.current(original) { self.writeState = .blocked; return }
                if case MessageReadFailure.rejected(let status, _) = error, status == 409 { self.writeState = .conflict }
                else { self.writeState = self.pendingDraft == nil ? .blocked : .unknown }
            }
        }
        writeTask = task
        return task
    }
    public func captureDraftCancelContext() -> ServerDraftCancelContext? {
        guard let binding, binding.generation == shell.generation,
              writeState == .saving, let task = writeTask else { return nil }
        return ServerDraftCancelContext(bindingID: binding.id, generation: binding.generation,
            selectionEpoch: selectionEpoch, writeEpoch: writeEpoch, task: task)
    }
    public func cancelServerDraftSave(context: ServerDraftCancelContext?) {
        guard let context, binding?.id == context.bindingID, shell.generation == context.generation,
              selectionEpoch == context.selectionEpoch, writeEpoch == context.writeEpoch,
              writeState == .saving, writeTask != nil else { return }
        writeTask = nil
        writeCancelled = true; writeState = .queryOnly
        context.task.cancel() // only original task; no mutation after external cancellation handlers
    }
    public func captureDraftQueryContext() -> ServerDraftQueryContext? {
        guard let read = captureReadContext(), let selected = read.selected, let original = pendingDraft,
              Data(original.generation.utf8) == Data(selected.generation.utf8),
              original.confirmedRevision == nil || writeCancelled,
              listState != .loading, writeState != .saving, queryState != .loading else { return nil }
        return ServerDraftQueryContext(read: read, original: original, writeEpoch: writeEpoch, queryRequest: draftQueryRequest)
    }
    public func queryOriginalDraft(context: ServerDraftQueryContext?) async {
        guard let context, accepts(context.read), ownsWrite(context.read, epoch: context.writeEpoch),
              pendingDraft == context.original, listState != .loading, queryState != .loading, draftQueryRequest == context.queryRequest else { return }
        let queryRequest = UUID(); draftQueryRequest = queryRequest
        queryState = .loading
        let original = context.read.binding
        do {
            let result = try await original.client.reconcileDraft(conversationID: context.original.conversationID, limits: original.limits, lease: original.lease)
            try original.client.validateRead(result, lease: original.lease)
            guard draftQueryRequest == queryRequest, ownsWrite(context.read, epoch: context.writeEpoch), current(original), pendingDraft == context.original else { return }
            queryState = result.value == nil ? .missing : .observed
            // Observation only: no confirmation, revision substitution or permission restoration.
        } catch {
            guard draftQueryRequest == queryRequest, ownsWrite(context.read, epoch: context.writeEpoch), current(original) else { return }
            queryState = .failed
        }
    }

    private func status(for error: Error) -> ServerReadStatus {
        if case MessageReadFailure.resyncRequired = error { return .resync }
        return .failed // no raw request/error/credential details cross the UI boundary
    }
}
