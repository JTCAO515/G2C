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
    /// Superseded by `prepare` + `confirm`: a decision always needs a server-prepared original action.
    public func choose(_ kind: TripActionKind, proposal: Components.Schemas.SourceTripProposalSnapshot, binding: TripBinding) async throws -> TripActionResult {
        _ = try capture(binding)
        throw TripFailure.liveWriteUnavailable
    }
    /// Asks the server to prepare one signed original action for the reviewed proposal. Read-only on
    /// the server. The response must repeat the exact reviewed proposal; any change needs a new review.
    public func prepare(_ kind: TripActionKind, proposal reviewed: Components.Schemas.SourceTripProposalSnapshot,
                        binding: TripBinding) async throws -> TripPreparedAction {
        let token = try capture(binding)
        guard writesEnabled else { throw TripFailure.liveWriteUnavailable }
        guard let store else { throw TripFailure.unconfigured }
        try store.validate(binding)
        try validateProposal(reviewed)
        guard reviewed.status == .pending else { throw TripFailure.invalidInput }
        try requireNoUnsettled(store, binding, token, proposalID: reviewed.proposal_id)
        guard let requestKind = Components.Schemas.TripConfirmationRequest.kindPayload(rawValue: kind.rawValue) else { throw TripFailure.invalidInput }
        let actionID = "a-" + UUID().uuidString.lowercased()
        let client = try await api(binding, token)
        let output = try await exchange(binding, token) {
            try await client.prepareTripConfirmation(headers: .init(X_hyphen_CJ_hyphen_Trip_hyphen_Content: .provenance_period_1), body: .json(.init(action_id: actionID, kind: requestKind,
                proposal_id: reviewed.proposal_id, candidate_hash: reviewed.candidate_hash)))
        }
        switch output {
        case .ok(let value):
            let body = try value.body.json.sourcePreparation
            guard let bytes = Data(base64Encoded: body.action_utf8_base64), bytes.count <= endpoint.maximumRequestBytes else { throw TripFailure.invalidResponse }
            try validateProposal(body.proposal)
            let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
            // The server must sign exactly what the user reviewed; a changed candidate is never silently adopted.
            guard try encoder.encode(body.proposal) == encoder.encode(reviewed) else { throw TripFailure.invalidResponse }
            let pending = try TripPending(serverBytes: bytes, proposal: body.proposal)
            guard same(pending.actionID, actionID), pending.kind == kind, let expiry = pending.confirmationExpiry,
                  expiry == body.expires_at, expiry <= reviewed.expires_at else { throw TripFailure.invalidResponse }
            try check(binding, token)
            return TripPreparedAction(pending: pending, expiresAt: expiry, owner: owner, generation: token, binding: binding)
        case .default(let status, let value): throw TripFailure.rejected(status, try value.body.json.error.code)
        }
    }
    /// Submits the prepared original action after the user's explicit confirmation. The exact bytes
    /// are written to the encrypted pending store before they leave the device; any later outcome is
    /// reconciled with `query(actionID:)` for this same action, never by preparing a replacement.
    public func confirm(_ prepared: TripPreparedAction, binding: TripBinding, now: Int) async throws -> TripActionResult {
        guard writesEnabled else { throw TripFailure.liveWriteUnavailable }
        guard prepared.owner == owner, prepared.generation == generation, prepared.binding == binding else {
            throw TripFailure.staleBinding
        }
        guard prepared.expiresAt - confirmationClockMargin > now else { throw TripFailure.invalidInput }
        return try await submit(prepared.pending, binding: binding, now: now)
    }
    /// Test-only fixture path. Caller owns the exact server-held proof; no proof is fabricated here.
    func submitFixture(_ original: TripPending, binding: TripBinding, now: Int) async throws -> TripActionResult {
        guard testWrites else { throw TripFailure.liveWriteUnavailable }
        return try await submit(original, binding: binding, now: now)
    }
    private func requireNoUnsettled(_ store: TripPendingStore, _ binding: TripBinding, _ token: UUID, proposalID: String) throws {
        let existing = try store.pending(); try check(binding, token)
        // Every frozen action gets one dispatch attempt; earlier ones must be reconciled first.
        guard !existing.contains(where: { same($0.proposal.proposal_id, proposalID) }),
              existing.allSatisfy({ confirmed.contains(Data($0.actionID.utf8)) }) else { throw TripFailure.pendingRequiresQuery }
    }
    private func submit(_ original: TripPending, binding: TripBinding, now: Int) async throws -> TripActionResult {
        let token = try capture(binding)
        guard let store else { throw TripFailure.unconfigured }
        try store.validate(binding)
        try original.validate()
        guard original.proposal.status == .pending, original.proposal.expires_at > now,
              original.originalUTF8.count <= endpoint.maximumRequestBytes else { throw TripFailure.invalidInput }
        let existing = try store.pending(); try check(binding, token)
        guard !existing.contains(where: { same($0.actionID, original.actionID) }) else { throw TripFailure.pendingRequiresQuery }
        try requireNoUnsettled(store, binding, token, proposalID: original.proposal.proposal_id)
        try store.append(original) { try self.check(binding, token) }
        try check(binding, token)
        let client = try await api(binding, token, original: original)
        let output = try await exchange(binding, token) { try await client.actOnTripProposal(body: .binary(HTTPBody(original.originalUTF8))) }
        switch output {
        case .ok(let value): return try settle(value.body.json.receipt, original, binding, token)
        case .default(let status, let value): throw TripFailure.rejected(status, try value.body.json.error.code)
        }
    }
    public func query(actionID: String, binding: TripBinding,
                      now: Int = Int(Date().timeIntervalSince1970)) async throws -> TripActionResult {
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
            case .case2(let null):
                guard null.value == nil else { throw TripFailure.invalidResponse }
                // Signed confirmations cannot commit after expiry, so a missing receipt is then final.
                if let expiry = original.confirmationExpiry, now > expiry + confirmationClockMargin {
                    try check(binding, token)
                    confirmed.insert(Data(original.actionID.utf8))
                    return .expiredUncommitted
                }
                return .notObserved
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
