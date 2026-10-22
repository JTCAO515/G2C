import Foundation
import CJAPI

public typealias TripActionKind = Components.Schemas.TripActionReceipt.kindPayload
public enum TripActionResult: Sendable {
    case confirmed(Components.Schemas.TripActionReceipt)
    case notObserved // Still unknown; never permission to resend.
}

/// Frozen original action. No public initializer or confirmation-reference input exists.
public struct TripPending: Codable, Sendable {
    public let actionID: String
    public let kind: TripActionKind
    public let proposal: Components.Schemas.TripProposalSnapshot
    public let originalUTF8: Data

    // Internal construction is restricted to test-held confirmation fixtures until an issuer is accepted.
    init(actionID: String, kind: TripActionKind, proposal: Components.Schemas.TripProposalSnapshot, confirmationReference: String) throws {
        try validateProposal(proposal)
        guard tripID(actionID), tripID(confirmationReference) else { throw TripFailure.invalidInput }
        self.actionID = actionID; self.kind = kind; self.proposal = proposal
        let encoder = JSONEncoder(); encoder.outputFormatting = [.withoutEscapingSlashes]
        originalUTF8 = try encoder.encode([actionID, kind.rawValue, proposal.proposal_id, proposal.candidate_hash, confirmationReference])
    }
    func validate() throws {
        try validateProposal(proposal)
        let fields = try JSONDecoder().decode([String].self, from: originalUTF8)
        guard fields.count == 5, tripID(actionID), same(fields[0], actionID), same(fields[1], kind.rawValue),
              same(fields[2], proposal.proposal_id), same(fields[3], proposal.candidate_hash), tripID(fields[4]) else { throw TripFailure.invalidInput }
        let encoder = JSONEncoder(); encoder.outputFormatting = [.withoutEscapingSlashes]
        guard try encoder.encode(fields) == originalUTF8 else { throw TripFailure.invalidInput }
    }
}

func validateReceipt(_ receipt: Components.Schemas.TripActionReceipt, original: TripPending) throws {
    guard same(receipt.action_id, original.actionID), receipt.kind == original.kind,
          same(receipt.proposal_id, original.proposal.proposal_id), same(receipt.candidate_hash, original.proposal.candidate_hash),
          same(receipt.trip_id, original.proposal.trip_id) else { throw TripFailure.invalidResponse }
    switch receipt.committed_version {
    case .case1(let version):
        guard receipt.kind == .accept, original.proposal.expected_version < Int.max,
              version == original.proposal.expected_version + 1 else { throw TripFailure.invalidResponse }
    case .case2(let null):
        guard receipt.kind == .reject, null.value == nil else { throw TripFailure.invalidResponse }
    }
}
