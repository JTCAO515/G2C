import Foundation
import Observation
import CJMessageClient
import CJAPI

/// Trusted composition input, never constructed from view text or a session token.
/// queryOriginal must use the same recovery/scope/lease and a verified query adapter.
@MainActor public struct AssistantMessageBinding {
    let recovery: MessageRecovery
    let scope: StorageScope
    let lease: Lease
    let generation: ShellGeneration
    let conversationID: String?
    let messageID: String?
    let synthetic: Bool
    let isCurrent: @MainActor () -> Bool
    let invalidateResources: @MainActor () -> Void
    let queryOriginal: (@MainActor (String, Lease) async throws -> Void)?

    public init(recovery: MessageRecovery, scope: StorageScope, lease: Lease,
                generation: ShellGeneration, conversationID: String? = nil, messageID: String? = nil,
                synthetic: Bool, isCurrent: @escaping @MainActor () -> Bool,
                invalidateResources: @escaping @MainActor () -> Void,
                queryOriginal: (@MainActor (String, Lease) async throws -> Void)? = nil) {
        self.recovery = recovery; self.scope = scope; self.lease = lease
        self.generation = generation; self.conversationID = conversationID; self.messageID = messageID
        self.synthetic = synthetic; self.isCurrent = isCurrent; self.queryOriginal = queryOriginal
        self.invalidateResources = invalidateResources
    }
}

/// Captured only from the current transport-accepted canonical MESSAGE record.
/// No public initializer, credentials, or UI-derived message/run identifiers.
@MainActor public final class AcceptedMessageRunReceipt: CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    let receipt: Components.Schemas.MessageReceipt
    let isCurrent: @MainActor () -> Bool
    let isStillOwned: @MainActor () -> Bool
    fileprivate init(receipt: Components.Schemas.MessageReceipt, isCurrent: @escaping @MainActor () -> Bool,
                     isStillOwned: @escaping @MainActor () -> Bool) {
        self.receipt = receipt; self.isCurrent = isCurrent; self.isStillOwned = isStillOwned
    }
    public nonisolated var description: String { "<redacted accepted message receipt>" }
    public nonisolated var debugDescription: String { description }
    public nonisolated var customMirror: Mirror { Mirror(self, children: [:]) }
}

/// Current canonical recovery input only. The USAGE client, not the UI, must decode
/// and capture its own closed AcceptedUsageMessage. No public constructor or actor IDs.
@MainActor public final class AcceptedMessageUsageInput: CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    let recovery: MessageRecovery
    let scope: StorageScope
    let lease: Lease
    let record: ActionRecord
    let isCurrent: @MainActor () -> Bool
    let isStillOwned: @MainActor () -> Bool
    fileprivate init(binding: AssistantMessageBinding, record: ActionRecord,
                     isCurrent: @escaping @MainActor () -> Bool, isStillOwned: @escaping @MainActor () -> Bool) {
        recovery = binding.recovery; scope = binding.scope; lease = binding.lease; self.record = record
        self.isCurrent = isCurrent; self.isStillOwned = isStillOwned
    }
    public nonisolated var description: String { "<redacted accepted message usage input>" }
    public nonisolated var debugDescription: String { description }
    public nonisolated var customMirror: Mirror { Mirror(self, children: [:]) }
}

/// Activity only; canonical action phase/bytes/receipt stay in CJMessageClient.ActionRecord.
public enum MessageHostActivity: Equatable {
    case unavailable, ready, querying, unknown, storageBlocked, invalidated
}

@MainActor @Observable public final class AssistantMessageHost {
    public private(set) var activity: MessageHostActivity = .unavailable
    private var storedDraftBytes: Data?
    public var draftStored: Bool { bindingIsCurrent && storedDraftBytes == Data(shell.draft.utf8) }
    @ObservationIgnored private let shell: ShellState
    @ObservationIgnored private var binding: AssistantMessageBinding?
    @ObservationIgnored private var usedGeneration: ShellGeneration?
    @ObservationIgnored private var task: Task<Void, Never>?
    private var record: ActionRecord?
    private var projection: LocalRecoveryProjection?
    private var selectedConversationID: String?
    private var selectedMessageID: String?
    private var runSelectionRevision = UUID()
    private var runSelectionAllowed = false
    public var visibleProjection: LocalRecoveryProjection? {
        guard bindingIsCurrent, let binding, let projection,
              (try? binding.recovery.validateProjection(projection, scope: binding.scope, lease: binding.lease)) != nil else { return nil }
        return projection
    }
    public var canSelectLocalItem: Bool { bindingIsCurrent && activity != .querying }

    public var visibleRecord: ActionRecord? { bindingIsCurrent ? record : nil }
    public var isSynthetic: Bool { bindingIsCurrent && binding?.synthetic == true }
    public var isConfigured: Bool { bindingIsCurrent }
    public var canSaveDraft: Bool { bindingIsCurrent && selectedConversationID != nil && activity != .querying && activity != .storageBlocked }
    public var canQuery: Bool {
        guard bindingIsCurrent, binding?.queryOriginal != nil, activity != .querying,
              let record else { return false }
        return record.phase == .queryRequired || record.phase == .notObserved
    }
    public var canSend: Bool { false }

    public init(shell: ShellState) {
        self.shell = shell
        shell.messageHost?.invalidate()
        shell.messageHost = self
    }
    func belongs(to shell: ShellState) -> Bool { self.shell === shell }

    /// Once per UI generation. Rebinding cannot erase ambiguity within an identity lifetime.
    @discardableResult public func bind(_ value: AssistantMessageBinding) -> Bool {
        guard !shell.messageBindingBlocked, value.generation == shell.generation, usedGeneration != value.generation,
              value.isCurrent(), value.conversationID?.isEmpty != true else { return false }
        // isCurrent is injected and may synchronously reenter with a newer account.
        guard !shell.messageBindingBlocked, value.generation == shell.generation,
              usedGeneration != value.generation else { return false }
        usedGeneration = value.generation
        do {
            try value.recovery.validateScope(value.scope, lease: value.lease)
            let draft = try value.conversationID.flatMap { try value.recovery.draft(conversationID: $0, lease: value.lease) }
            let restored = try value.messageID.flatMap { try value.recovery.action(messageID: $0, lease: value.lease) }
            retireRunSelection()
            binding = value
            projection = try value.recovery.localProjection(scope: value.scope, lease: value.lease)
            selectedConversationID = value.conversationID
            selectedMessageID = value.messageID
            runSelectionAllowed = value.messageID != nil
            if let draft {
                guard let text = String(data: draft, encoding: .utf8) else { throw RecoveryError.invalidInput }
                shell.draft = text
            }
            record = restored
            activity = .ready
            return true
        } catch {
            guard value.generation == shell.generation, usedGeneration == value.generation,
                  binding == nil || isSameBinding(value) else { return false }
            // A rejected/unacquired lease cannot authorize invalidating that resource.
            binding = nil; record = nil; projection = nil; activity = .storageBlocked
            return false
        }
    }

    @discardableResult public func selectAction(_ reference: LocalActionReference, from captured: LocalRecoveryProjection) -> Bool {
        guard canSelectLocalItem, let binding else { return false }
        do {
            try binding.recovery.validateProjection(captured, scope: binding.scope, lease: binding.lease)
            guard captured.actions.contains(where: { Data($0.messageID.utf8) == Data(reference.messageID.utf8) }),
                  let action = try binding.recovery.action(messageID: reference.messageID, lease: binding.lease) else { return false }
            retireRunSelection()
            selectedMessageID = reference.messageID
            runSelectionAllowed = true
            record = action
            projection = try binding.recovery.localProjection(scope: binding.scope, lease: binding.lease)
            activity = .ready
            return true
        } catch { return false } // stale selection is rejected without invalidating a newer binding
    }

    /// Explicit replacement confirmed by the view; no preview/body appears in the list.
    @discardableResult public func selectDraft(_ reference: LocalDraftReference, from captured: LocalRecoveryProjection) -> Bool {
        guard canSelectLocalItem, let binding else { return false }
        do {
            try binding.recovery.validateProjection(captured, scope: binding.scope, lease: binding.lease)
            guard captured.drafts.contains(where: { Data($0.conversationID.utf8) == Data(reference.conversationID.utf8) }),
                  let bytes = try binding.recovery.draft(conversationID: reference.conversationID, lease: binding.lease),
                  let text = String(data: bytes, encoding: .utf8) else { return false }
            retireRunSelection()
            selectedConversationID = reference.conversationID
            shell.draft = text
            storedDraftBytes = bytes
            return true
        } catch { return false }
    }

    private func retireRunSelection() {
        runSelectionRevision = UUID(); runSelectionAllowed = false
        shell.runContainerHost?.retireSelection()
        shell.originalUsageContainerHost?.retireSelection()
    }
    public func captureAcceptedUsageInput() -> AcceptedMessageUsageInput? {
        let revision = runSelectionRevision
        guard let originalBinding = binding, runSelectionAllowed, let id = selectedMessageID,
              bindingIsCurrent, isSameBinding(originalBinding), revision == runSelectionRevision,
              let record = try? originalBinding.recovery.action(messageID: id, lease: originalBinding.lease),
              record.phase == .accepted, record.receipt != nil,
              ownsRunReceipt(record, binding: originalBinding, revision: revision) else { return nil }
        return AcceptedMessageUsageInput(binding: originalBinding, record: record, isCurrent: { [weak self] in
            self?.ownsRunReceipt(record, binding: originalBinding, revision: revision) == true
        }, isStillOwned: { [weak self] in
            self?.ownsRunReceiptWithoutCallbacks(record, binding: originalBinding, revision: revision) == true
        })
    }
    /// Decode the exact typed payload encoded by MessageHTTPClient only after its
    /// accepted recovery state, original bytes/hash, lease and current selection agree.
    public func captureAcceptedRunReceipt() -> AcceptedMessageRunReceipt? {
        let revision = runSelectionRevision
        guard let originalBinding = binding, runSelectionAllowed, let id = selectedMessageID,
              bindingIsCurrent, isSameBinding(originalBinding), revision == runSelectionRevision,
              let record = try? originalBinding.recovery.action(messageID: id, lease: originalBinding.lease),
              record.phase == .accepted, let bytes = record.receipt,
              let receipt = try? JSONDecoder().decode(Components.Schemas.MessageReceipt.self, from: bytes),
              Data(receipt.message_id.utf8) == Data(record.messageID.utf8), receipt.input_sha256 == record.inputSHA256,
              ownsRunReceipt(record, binding: originalBinding, revision: revision) else { return nil }
        return AcceptedMessageRunReceipt(receipt: receipt, isCurrent: { [weak self] in
            self?.ownsRunReceipt(record, binding: originalBinding, revision: revision) == true
        }, isStillOwned: { [weak self] in
            self?.ownsRunReceiptWithoutCallbacks(record, binding: originalBinding, revision: revision) == true
        })
    }
    private func ownsRunReceipt(_ original: ActionRecord, binding: AssistantMessageBinding, revision: UUID) -> Bool {
        guard ownsRunReceiptWithoutCallbacks(original, binding: binding, revision: revision),
              bindingIsCurrent else { return false }
        return ownsRunReceiptWithoutCallbacks(original, binding: binding, revision: revision)
    }
    /// Canonical in-memory lease/record reads only: safe after the last trusted callback.
    /// This establishes original ownership, not admission or server authorization.
    private func ownsRunReceiptWithoutCallbacks(_ original: ActionRecord, binding: AssistantMessageBinding, revision: UUID) -> Bool {
        guard !shell.messageBindingBlocked, isSameBinding(binding), revision == runSelectionRevision, runSelectionAllowed,
              selectedMessageID.map({ Data($0.utf8) == Data(original.messageID.utf8) }) == true,
              (try? binding.recovery.validateScope(binding.scope, lease: binding.lease)) != nil,
              let current = try? binding.recovery.action(messageID: original.messageID, lease: binding.lease) else { return false }
        return current == original && current.phase == .accepted
    }

    private func isSameBinding(_ original: AssistantMessageBinding) -> Bool {
        guard let current = binding else { return false }
        return current.recovery === original.recovery && current.lease == original.lease
            && current.generation == original.generation && shell.generation == original.generation
    }

    private var bindingIsCurrent: Bool {
        guard !shell.messageBindingBlocked, let binding, binding.generation == shell.generation, binding.isCurrent() else { return false }
        return (try? binding.recovery.validateScope(binding.scope, lease: binding.lease)) != nil
            && isSameBinding(binding) && !shell.messageBindingBlocked
    }

    public func saveDraft() {
        guard canSaveDraft, let binding, let selectedConversationID else { return }
        let originalBytes = Data(shell.draft.utf8)
        do {
            try binding.recovery.saveDraft(originalBytes, conversationID: selectedConversationID, lease: binding.lease)
            guard isSameBinding(binding) else { return }
            guard bindingIsCurrent else { blockStorage(for: binding); return }
            guard isSameBinding(binding) else { return }
            storedDraftBytes = originalBytes
            projection = try binding.recovery.localProjection(scope: binding.scope, lease: binding.lease)
        } catch { blockStorage(for: binding) }
    }

    public func queryOriginal() {
        guard canQuery, let binding, let messageID = selectedMessageID, let query = binding.queryOriginal else { return }
        retireRunSelection()
        activity = .querying
        task = Task { [weak self] in
            do {
                try await query(messageID, binding.lease)
                guard let self, self.isSameBinding(binding) else { return }
                guard self.bindingIsCurrent else { self.blockStorage(for: binding); return }
                guard self.isSameBinding(binding) else { return }
                self.record = try binding.recovery.action(messageID: messageID, lease: binding.lease)
                self.runSelectionAllowed = true
                self.projection = try binding.recovery.localProjection(scope: binding.scope, lease: binding.lease)
                self.activity = .ready
                self.task = nil
            } catch {
                guard let self, self.isSameBinding(binding) else { return }
                let current = self.bindingIsCurrent
                guard self.isSameBinding(binding) else { return }
                if current { self.activity = .unknown; self.task = nil }
                else { self.blockStorage(for: binding) }
            }
        }
    }

    /// Called synchronously by ShellState BEFORE its identity generation/clear changes.
    public func invalidate() { retire(as: .invalidated) }

    private func retire(as nextActivity: MessageHostActivity) {
        let previous = binding
        binding = nil; record = nil; projection = nil; storedDraftBytes = nil
        selectedConversationID = nil; selectedMessageID = nil
        retireRunSelection()
        task?.cancel(); task = nil
        activity = nextActivity
        // Detach before invoking an external callback; never mutate a replacement afterward.
        previous?.recovery.invalidate()
        previous?.invalidateResources()
    }
    private func blockStorage(for original: AssistantMessageBinding) {
        guard isSameBinding(original) else { return }
        retire(as: .storageBlocked)
    }
}
