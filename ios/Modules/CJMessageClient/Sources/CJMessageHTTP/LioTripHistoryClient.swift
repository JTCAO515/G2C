import CJMessageClient
import Foundation

/// Read the signed trip and journal the exact undo before any network write.
@MainActor
public final class LioTripHistoryClient {
    public enum UndoState: Sendable, Equatable {
        case committed, pending, changed
    }

    enum SubmissionResult {
        case committed(Data)
        case conflict(Data)
    }

    private let recovery: MessageRecovery
    private let scope: StorageScope
    private let lease: Lease
    private let conversationID: String?
    private let readHistory: @MainActor (String?) async throws -> LioTripHistoryWire.Page
    private let submit: @MainActor (LioTripHistoryWire.Undo) async throws -> SubmissionResult
    private let readReceipt: @MainActor (LioTripHistoryWire.Undo) async throws -> Data?
    private var working = false

    public convenience init(timeline: LioTimelineHTTP, recovery: MessageRecovery, scope: StorageScope, lease: Lease,
                            conversationID: String? = nil) {
        self.init(recovery: recovery, scope: scope, lease: lease, conversationID: conversationID,
                  readHistory: { try await timeline.tripHistory(before: $0, conversationID: conversationID) },
                  submit: { try await timeline.submitUndo($0) },
                  readReceipt: { try await timeline.readUndo($0) })
    }

    init(recovery: MessageRecovery, scope: StorageScope, lease: Lease,
         conversationID: String? = nil,
         readHistory: @escaping @MainActor (String?) async throws -> LioTripHistoryWire.Page,
         submit: @escaping @MainActor (LioTripHistoryWire.Undo) async throws -> SubmissionResult,
         readReceipt: @escaping @MainActor (LioTripHistoryWire.Undo) async throws -> Data?) {
        self.recovery = recovery
        self.scope = scope
        self.lease = lease
        self.conversationID = conversationID
        self.readHistory = readHistory
        self.submit = submit
        self.readReceipt = readReceipt
    }

    public func history(before: String? = nil) async throws -> LioTripHistoryWire.Page {
        try await readHistory(before)
    }

    public func hasPendingUndo() throws -> Bool {
        guard let undo = try pending() else { return false }
        return undo.conversationID == conversationID
    }

    public func undo(_ target: LioTripHistoryWire.Target) async throws -> UndoState {
        guard target.conversationID == conversationID else { throw MessageHTTPFailure.invalidConfiguration }
        guard !working, try pending() == nil else { return .pending }
        working = true
        defer { working = false }
        let undo = try LioTripHistoryWire.Undo(target: target)
        try recovery.stage(messageID: undo.actionID, originalUTF8: undo.originalUTF8, lease: lease)
        let submission = try recovery.beginSubmission(messageID: undo.actionID, lease: lease)
        let result: SubmissionResult
        do {
            result = try await submit(undo)
        } catch is CancellationError {
            // The journal already requires a read. Cancellation does not authorize another write.
            throw CancellationError()
        } catch {
            try recovery.observeUnknown(submission.operation)
            return .pending
        }
        switch result {
        case .committed(let receipt):
            try saveCommit(undo, operation: submission.operation, receipt: receipt)
            return .committed
        case .conflict(let proof):
            try recovery.observeSubmissionRejection(submission.operation, httpStatus: 409, responseUTF8: proof)
            return .changed
        }
    }

    public func reconcileUndo() async throws -> UndoState? {
        guard !working else { return .pending }
        guard let undo = try pending(), undo.conversationID == conversationID else { return nil }
        working = true
        defer { working = false }
        let operation = try recovery.beginQuery(messageID: undo.actionID, lease: lease)
        let receipt: Data?
        do {
            receipt = try await readReceipt(undo)
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            try recovery.observeUnknown(operation)
            return .pending
        }
        guard let receipt else {
            try recovery.observeNotObserved(operation)
            return .pending
        }
        try saveCommit(undo, operation: operation, receipt: receipt)
        return .committed
    }

    private func pending() throws -> LioTripHistoryWire.Undo? {
        let projection = try recovery.localProjection(scope: scope, lease: lease)
        let actions = projection.actions.filter { row in
            row.messageID.hasPrefix(LioTripHistoryWire.Undo.idPrefix)
                && (row.phase == .staged || row.phase == .queryRequired || row.phase == .notObserved)
        }
        guard actions.count <= 1 else { throw RecoveryError.invalidSnapshot }
        guard let action = actions.first else { return nil }
        guard let record = try recovery.action(messageID: action.messageID, lease: lease) else {
            throw RecoveryError.invalidSnapshot
        }
        return try LioTripHistoryWire.Undo(originalUTF8: record.originalUTF8, expectedActionID: record.messageID)
    }

    private func saveCommit(_ undo: LioTripHistoryWire.Undo, operation: CJMessageClient.Operation, receipt: Data) throws {
        guard try undo.committed(receipt),
              let record = try recovery.action(messageID: undo.actionID, lease: lease) else {
            throw RecoveryError.receiptMismatch
        }
        try recovery.observeReceipt(operation, messageID: undo.actionID, inputSHA256: record.inputSHA256, receipt: receipt)
    }
}
