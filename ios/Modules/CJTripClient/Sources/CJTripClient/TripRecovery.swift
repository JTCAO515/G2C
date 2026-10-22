import Foundation
import CJAPI
import OpenAPIRuntime

extension TripClient {
    public func pending(binding: TripBinding) throws -> [TripPending] {
        let token = try capture(binding)
        guard let store else { throw TripFailure.unconfigured }
        try store.validate(binding)
        let records = try store.pending(); try check(binding, token)
        return records
    }
    /// Public user action remains unavailable until a real confirmation issuer is integrated.
    public func choose(_ kind: TripActionKind, proposal: Components.Schemas.TripProposalSnapshot, binding: TripBinding) async throws -> TripActionResult {
        _ = try capture(binding)
        throw TripFailure.liveWriteUnavailable
    }
    /// Test-only fixture path. Caller owns the exact server-held proof; no proof is fabricated here.
    func submitFixture(_ original: TripPending, binding: TripBinding, now: Int) async throws -> TripActionResult {
        let token = try capture(binding)
        guard testWrites else { throw TripFailure.liveWriteUnavailable }
        guard let store else { throw TripFailure.unconfigured }
        try store.validate(binding)
        try original.validate()
        guard original.proposal.status == .pending, original.proposal.expires_at > now,
              original.originalUTF8.count <= endpoint.maximumRequestBytes else { throw TripFailure.invalidInput }
        let existing = try store.pending(); try check(binding, token)
        // Every frozen action gets one dispatch attempt, including an apparently failed attempt.
        guard !existing.contains(where: { same($0.actionID, original.actionID) || same($0.proposal.proposal_id, original.proposal.proposal_id) }),
              existing.allSatisfy({ confirmed.contains(Data($0.actionID.utf8)) }) else { throw TripFailure.pendingRequiresQuery }
        try store.append(original) { try self.check(binding, token) }
        try check(binding, token)
        let client = try await api(binding, token, original: original)
        let output = try await exchange(binding, token) { try await client.actOnTripProposal(body: .binary(HTTPBody(original.originalUTF8))) }
        switch output {
        case .ok(let value): return try settle(value.body.json.receipt, original, binding, token)
        case .default(let status, let value): throw TripFailure.rejected(status, try value.body.json.error.code)
        }
    }
    public func query(actionID: String, binding: TripBinding) async throws -> TripActionResult {
        let token = try capture(binding)
        guard let store else { throw TripFailure.unconfigured }
        try store.validate(binding)
        guard let original = try store.pending().first(where: { same($0.actionID, actionID) }) else { throw TripFailure.invalidInput }
        try check(binding, token)
        let client = try await api(binding, token, original: original)
        let output = try await exchange(binding, token) { try await client.queryTripAction(query: .init(action_id: original.actionID)) }
        switch output {
        case .ok(let value):
            switch try value.body.json.receipt {
            case .TripActionReceipt(let receipt): return try settle(receipt, original, binding, token)
            case .case2(let null): guard null.value == nil else { throw TripFailure.invalidResponse }; return .notObserved
            }
        case .default(let status, let value): throw TripFailure.rejected(status, try value.body.json.error.code)
        }
    }
    private func settle(_ receipt: Components.Schemas.TripActionReceipt, _ original: TripPending,
                        _ binding: TripBinding, _ token: UUID) throws -> TripActionResult {
        try check(binding, token)
        try validateReceipt(receipt, original: original)
        guard let store else { throw TripFailure.unconfigured }
        let proof = try store.requireOriginal(original); try check(binding, token)
        try store.validateDurability(proof)
        confirmed.insert(Data(original.actionID.utf8))
        return .confirmed(receipt)
    }
}
