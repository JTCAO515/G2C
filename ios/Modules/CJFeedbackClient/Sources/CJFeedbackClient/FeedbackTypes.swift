import Foundation
import CJAPI

public enum FeedbackFailure: Error, Equatable, Sendable {
    case unconfigured, staleBinding, invalidInput, invalidResponse, liveWriteUnavailable
    case pendingRequiresQuery, exchangeUnknown, storageUnavailable, keyUnavailable
    case rejected(Int)
}

/// Supplied by the trusted host; never serialized as server ownership or authority.
public struct FeedbackBinding: Hashable, Sendable {
    public let environment: UUID
    public let account: UUID
    public let generation: UUID
    public let selection: UUID
    public init(environment: UUID, account: UUID, generation: UUID, selection: UUID) {
        self.environment = environment; self.account = account
        self.generation = generation; self.selection = selection
    }
}

/// Only a trusted host may supply the current message association. Server verifies ownership.
/// There is no run-only, memory, proposal, Trip, owner, or diagnostic input surface.
public struct FeedbackContext: Sendable {
    public let messageID: String
    public let runID: String?
    public init(messageID: String, runID: String? = nil) throws {
        guard referenceID(messageID), runID.map(referenceID) ?? true else { throw FeedbackFailure.invalidInput }
        self.messageID = messageID; self.runID = runID
    }
    var references: [Components.Schemas.FeedbackReference] {
        [.init(kind: .message, id: messageID)] + (runID.map { [.init(kind: .run, id: $0)] } ?? [])
    }
}

func same(_ lhs: String, _ rhs: String) -> Bool { Data(lhs.utf8) == Data(rhs.utf8) }
func feedbackID(_ text: String) -> Bool {
    (1...128).contains(text.utf8.count) && text.utf8.allSatisfy {
        (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0) || $0 == 95 || $0 == 45
    }
}
func referenceID(_ text: String) -> Bool {
    (1...1024).contains(text.utf8.count) && !text.contains("\0") && !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
}
func validHash(_ text: String) -> Bool {
    text.utf8.count == 64 && text.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
}

/// Immutable original bytes. No public constructor permits caller-chosen wire or action IDs.
public struct FeedbackPending: Codable, Sendable, CustomStringConvertible, CustomDebugStringConvertible {
    public let actionID: String
    public let originalUTF8: Data
    public let inputSHA256: String
    public var description: String { "<private feedback pending>" }
    public var debugDescription: String { description }
    init(problem: String, expectation: String, context: FeedbackContext?, actionID: String = UUID().uuidString) throws {
        self.actionID = actionID
        let action = Components.Schemas.FeedbackAction(action_id: actionID, problem: problem, expectation: expectation,
                                                      references: context?.references ?? [])
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        originalUTF8 = try encoder.encode(action)
        inputSHA256 = digest(originalUTF8)
        try validate()
    }
    public func action() throws -> Components.Schemas.FeedbackAction {
        try JSONDecoder().decode(Components.Schemas.FeedbackAction.self, from: originalUTF8)
    }
    func validate() throws {
        guard originalUTF8.count <= 16384, feedbackID(actionID), same(inputSHA256, digest(originalUTF8)) else { throw FeedbackFailure.invalidInput }
        var strict = StrictFeedbackJSON(bytes: Array(originalUTF8)); try strict.check()
        let action = try action()
        guard same(action.action_id, actionID), !action.problem.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              action.problem.utf8.count <= 6000, action.expectation.utf8.count <= 6000,
              !action.problem.contains("\0"), !action.expectation.contains("\0"), action.references.count <= 2,
              action.references.allSatisfy({ referenceID($0.id) }),
              Set(action.references.map(\.kind)).count == action.references.count,
              action.references.isEmpty || action.references.contains(where: { $0.kind == .message }) else { throw FeedbackFailure.invalidInput }
    }
}

public enum FeedbackResult: Sendable {
    case submitted(Components.Schemas.FeedbackReceipt)
    case notObserved // Still unknown; never noncommit proof or replacement-ID authority.
}

func validateReceipt(_ receipt: Components.Schemas.FeedbackReceipt, original: FeedbackPending) throws {
    try original.validate()
    guard same(receipt.action_id, original.actionID), same(receipt.input_sha256, original.inputSHA256),
          receipt.submitted_at.timeIntervalSince1970.isFinite else { throw FeedbackFailure.invalidResponse }
    let references = try original.action().references
    switch receipt.source {
    case .case2(let value):
        guard value.value == nil, references.isEmpty else { throw FeedbackFailure.invalidResponse }
    case .FeedbackSourceObservation(let source):
        guard let message = references.first(where: { $0.kind == .message }), same(source.message_id, message.id),
              references.first(where: { $0.kind == .run }).map({ same(source.run_id, $0.id) }) ?? true,
              referenceID(source.message_id), referenceID(source.run_id),
              !source.conversation_id.isEmpty, !source.generation.isEmpty,
              source.message_sequence > 0, source.event_highwater_at_read >= 0,
              validHash(source.message_input_sha256) else { throw FeedbackFailure.invalidResponse }
    }
}
