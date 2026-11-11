import CJMessageClient
import Foundation

/// The exact reviewed choice is sealed in the account's existing encrypted journal.
@MainActor
public final class LioMemoryActionsClient {
    public enum State: Equatable, Sendable { case remembered, dismissed, pending, changed }

    enum SubmissionResult {
        case receipt(Data)
        case conflict(Data)
    }

    private let recovery: MessageRecovery
    private let scope: StorageScope
    private let lease: Lease
    private let submit: @MainActor (LioMemoryWire.Action) async throws -> SubmissionResult
    private let readReceipt: @MainActor (LioMemoryWire.Action) async throws -> Data
    private var working = false
    private var erasedItems = Set<Data>()

    public convenience init(timeline: LioTimelineHTTP, recovery: MessageRecovery, scope: StorageScope, lease: Lease) {
        self.init(recovery: recovery, scope: scope, lease: lease,
                  submit: { try await timeline.submitMemoryChoice($0) },
                  readReceipt: { try await timeline.readMemoryChoice($0) })
    }

    init(recovery: MessageRecovery, scope: StorageScope, lease: Lease,
         submit: @escaping @MainActor (LioMemoryWire.Action) async throws -> SubmissionResult,
         readReceipt: @escaping @MainActor (LioMemoryWire.Action) async throws -> Data) {
        self.recovery = recovery
        self.scope = scope
        self.lease = lease
        self.submit = submit
        self.readReceipt = readReceipt
    }

    public func hasPendingChoice() throws -> Bool {
        try pending() != nil
    }

    public func choose(_ choice: LioMemoryWire.Choice, tag: LioMemoryWire.Tag) async throws -> State {
        if erasedItems.contains(Data(tag.id.utf8)) { return .changed }
        guard !working, try pending() == nil else { return .pending }
        if let prior = try observedChoice(for: tag) { return prior }
        working = true
        defer { working = false }
        let action = try LioMemoryWire.Action(choice: choice, tag: tag)
        try recovery.stage(messageID: action.actionID, originalUTF8: action.originalUTF8, lease: lease)
        let submission = try recovery.beginSubmission(messageID: action.actionID, lease: lease)
        let result: SubmissionResult
        do {
            result = try await submit(action)
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            try recovery.observeUnknown(submission.operation)
            return .pending
        }
        switch result {
        case .receipt(let bytes):
            return try observe(action, operation: submission.operation, bytes: bytes)
        case .conflict(let proof):
            try recovery.observeSubmissionRejection(submission.operation, httpStatus: 409, responseUTF8: proof)
            return .changed
        }
    }

    public func clearErasedItem(_ itemID: String, environment: UUID, account: UUID) throws {
        guard scope.environment.utf8.elementsEqual(environment.uuidString.utf8),
              scope.account.utf8.elementsEqual(account.uuidString.utf8) else { throw RecoveryError.inactive }
        let rows = try actions()
        erasedItems.insert(Data(itemID.utf8))
        guard !working else { throw RecoveryError.queryOnly }
        working = true
        defer { working = false }
        let matching = try rows.compactMap { row -> String? in
            let original = try record(row)
            let action = try LioMemoryWire.Action(originalUTF8: original.originalUTF8, expectedActionID: row.messageID)
            return try action.erasureItemID().utf8.elementsEqual(itemID.utf8) ? row.messageID : nil
        }
        try recovery.eraseActionOriginals(messageIDs: matching, lease: lease)
    }

    public func reconcileChoice() async throws -> State? {
        guard !working else { return .pending }
        guard let record = try pending() else { return nil }
        working = true
        defer { working = false }
        let action = try LioMemoryWire.Action(originalUTF8: record.originalUTF8, expectedActionID: record.messageID)
        let operation = try recovery.beginQuery(messageID: action.actionID, lease: lease)
        let bytes: Data
        do {
            bytes = try await readReceipt(action)
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            try recovery.observeUnknown(operation)
            return .pending
        }
        return try observe(action, operation: operation, bytes: bytes)
    }

    private func actions() throws -> [LocalActionReference] {
        try recovery.localProjection(scope: scope, lease: lease).actions.filter {
            $0.messageID.hasPrefix(LioMemoryWire.Action.idPrefix)
        }
    }

    private func pending() throws -> ActionRecord? {
        let rows = try actions().filter { $0.phase == .staged || $0.phase == .queryRequired || $0.phase == .notObserved }
        guard rows.count <= 1 else { throw RecoveryError.invalidSnapshot }
        guard let row = rows.first else { return nil }
        return try record(row)
    }

    private func observedChoice(for tag: LioMemoryWire.Tag) throws -> State? {
        for row in try actions() where row.phase == .accepted || row.phase == .notAccepted {
            let original = try record(row)
            let action = try LioMemoryWire.Action(originalUTF8: original.originalUTF8, expectedActionID: row.messageID)
            guard action.matches(tag) else { continue }
            if row.phase == .notAccepted { return .changed }
            guard let receipt = original.receipt else { throw RecoveryError.invalidSnapshot }
            return try action.outcome(receipt)
        }
        return nil
    }

    private func record(_ row: LocalActionReference) throws -> ActionRecord {
        guard let value = try recovery.action(messageID: row.messageID, lease: lease) else {
            throw RecoveryError.invalidSnapshot
        }
        return value
    }

    private func observe(_ action: LioMemoryWire.Action, operation: CJMessageClient.Operation, bytes: Data) throws -> State {
        let state = try action.outcome(bytes)
        if state == .pending {
            try recovery.observeUnknown(operation)
        } else {
            guard let record = try recovery.action(messageID: action.actionID, lease: lease) else {
                throw RecoveryError.receiptMismatch
            }
            try recovery.observeReceipt(operation, messageID: action.actionID, inputSHA256: record.inputSHA256, receipt: bytes)
        }
        return state
    }
}
