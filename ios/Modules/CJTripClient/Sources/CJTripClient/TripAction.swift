import Foundation
import CJAPI

public typealias TripActionKind = Components.Schemas.TripActionReceipt.kindPayload
public enum TripActionResult: Sendable {
    case confirmed(Components.Schemas.TripActionReceipt)
    case notObserved // Still unknown; never permission to resend.
    /// No server receipt and the server-signed confirmation is past its expiry plus clock
    /// margin, so this original action can never commit. Still not permission to resend it.
    case expiredUncommitted
}

/// Host-granted capability for live Trip writes. Grant it only when the API host enforces
/// server-signed confirmations (`POST /v1/trip-confirmations`); it carries no credential.
public struct TripLiveWrites: Sendable {
    public init() {}
}

/// Server-prepared original action awaiting the user's explicit confirmation.
/// Preparing never writes a Trip; only `TripClient.confirm` submits these exact bytes.
public struct TripPreparedAction: Sendable {
    public let pending: TripPending
    public let expiresAt: Int
    let owner: UUID
    let generation: UUID
    let binding: TripBinding
    public var proposal: Components.Schemas.SourceTripProposalSnapshot { pending.proposal }
    public var kind: TripActionKind { pending.kind }
}

/// Seconds of client/server clock difference tolerated before treating an expired
/// confirmation as unable to commit, and kept free before expiry when confirming.
let confirmationClockMargin = 60

/// Frozen original action. No public initializer or confirmation-reference input exists.
public struct TripPending: Codable, Sendable {
    public let actionID: String
    public let kind: TripActionKind
    public let proposal: Components.Schemas.SourceTripProposalSnapshot
    public let originalUTF8: Data

    // Internal construction is restricted to test-held confirmation fixtures until an issuer is accepted.
    init(actionID: String, kind: TripActionKind, proposal: Components.Schemas.SourceTripProposalSnapshot, confirmationReference: String) throws {
        try validateProposal(proposal)
        guard tripID(actionID), tripID(confirmationReference) else { throw TripFailure.invalidInput }
        self.actionID = actionID; self.kind = kind; self.proposal = proposal
        let encoder = JSONEncoder(); encoder.outputFormatting = [.withoutEscapingSlashes]
        originalUTF8 = try encoder.encode([actionID, kind.rawValue, proposal.proposal_id, proposal.candidate_hash, confirmationReference])
    }
    /// Exact server-prepared bytes (`[action_id, kind, proposal_id, candidate_hash, confirmation_ref]`).
    init(serverBytes: Data, proposal: Components.Schemas.SourceTripProposalSnapshot) throws {
        let fields = try JSONDecoder().decode([String].self, from: serverBytes)
        guard fields.count == 5, let kind = TripActionKind(rawValue: fields[1]) else { throw TripFailure.invalidResponse }
        actionID = fields[0]; self.kind = kind; self.proposal = proposal; originalUTF8 = serverBytes
        do { try validate() } catch { throw TripFailure.invalidResponse }
    }
    /// Expiry signed into a `tc1.<expires_at>.<mac>` confirmation reference, if any.
    var confirmationExpiry: Int? {
        guard let fields = try? JSONDecoder().decode([String].self, from: originalUTF8), fields.count == 5 else { return nil }
        let parts = fields[4].split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 3, parts[0] == "tc1", (1...12).contains(parts[1].count),
              let first = parts[1].utf8.first, (49...57).contains(first),
              parts[1].utf8.allSatisfy({ (48...57).contains($0) }), parts[2].count == 64,
              parts[2].utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }),
              let value = Int(parts[1]), value > 0 else { return nil }
        return value
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
