import Testing
import Foundation
import CJAPI
@testable import CJTripClient

/// Server-prepared confirmation (P2c, CJ-015): prepare is read-only, confirm submits the exact
/// prepared bytes after persisting them, and unknown outcomes reconcile only the original action.
@MainActor struct ConfirmationFlowTests {
    nonisolated static let mac = String(repeating: "ab", count: 32)

    /// Mirrors the server: canonical five-string action with a `tc1.<expires>.<mac>` reference.
    nonisolated static func preparedBody(_ request: Data, expires: Int, proposal: Components.Schemas.TripProposalSnapshot,
                             actionID: String? = nil, kind: String? = nil, hash: String? = nil,
                             reference: String? = nil, bodyExpires: Int? = nil) throws -> String {
        let input = try JSONDecoder().decode([String: String].self, from: request)
        let fields = [actionID ?? input["action_id"]!, kind ?? input["kind"]!, input["proposal_id"]!,
                      hash ?? input["candidate_hash"]!, reference ?? "tc1.\(expires).\(mac)"]
        let encoder = JSONEncoder(); encoder.outputFormatting = [.withoutEscapingSlashes]
        let action = try encoder.encode(fields).base64EncodedString()
        return "{\"request_id\":\"\(trace)\",\"action_utf8_base64\":\"\(action)\",\"expires_at\":\(bodyExpires ?? expires),\"proposal\":\(try json(proposal))}"
    }

    @Test func prepareThenConfirmSubmitsExactServerBytesAfterPersisting() async throws {
        let h = try Harness(); defer { h.clean() }
        let proposal = try fixture().proposal
        let expires = 1_900_000_000
        let store = try h.store()
        let interceptor = Interceptor { request, bytes, operation in
            switch operation {
            case "prepareTripConfirmation":
                return try Self.preparedBody(bytes, expires: expires, proposal: proposal)
            case "actOnTripProposal":
                let original = try await MainActor.run { try #require(try store.pending().first) }
                #expect(original.originalUTF8 == bytes) // durable before it left the device
                return try response("receipt", actionReceipt(original))
            default: Issue.record("unexpected \(operation)"); return ""
            }
        }
        let client = try h.client(interceptor, store: store)
        let prepared = try await client.prepare(.accept, proposal: proposal, binding: h.binding)
        #expect(prepared.expiresAt == expires && prepared.kind == .accept)
        #expect(try store.pending().isEmpty) // preparing writes nothing locally either
        guard case .confirmed(let receipt) = try await client.confirm(prepared, binding: h.binding, now: expires - 120) else {
            Issue.record("expected receipt"); return
        }
        #expect(receipt.action_id == prepared.pending.actionID && receipt.committed_version == .case1(1))
        let calls = await interceptor.calls
        #expect(calls.map(\.operation) == ["prepareTripConfirmation", "actOnTripProposal"])
        #expect(calls[1].bytes == prepared.pending.originalUTF8)
    }

    @Test(arguments: ["actionID", "kind", "hash", "reference", "bodyExpires", "beyondProposal", "proposal"])
    func tamperedPreparationIsRejectedAndNothingPersists(_ damage: String) async throws {
        let h = try Harness(); defer { h.clean() }
        let proposal = try fixture().proposal
        let changed = { var p = proposal; p.expected_version += 1; return p }()
        let store = try h.store()
        let interceptor = Interceptor { _, bytes, _ in
            let e = 1_900_000_000
            switch damage {
            case "actionID": return try Self.preparedBody(bytes, expires: e, proposal: proposal, actionID: "a-replacement")
            case "kind": return try Self.preparedBody(bytes, expires: e, proposal: proposal, kind: "reject")
            case "hash": return try Self.preparedBody(bytes, expires: e, proposal: proposal, hash: String(repeating: "0", count: 64))
            case "reference": return try Self.preparedBody(bytes, expires: e, proposal: proposal, reference: "client-made-proof")
            case "bodyExpires": return try Self.preparedBody(bytes, expires: e, proposal: proposal, bodyExpires: e + 1)
            case "beyondProposal": return try Self.preparedBody(bytes, expires: proposal.expires_at + 1, proposal: proposal)
            default: return try Self.preparedBody(bytes, expires: e, proposal: changed)
            }
        }
        let client = try h.client(interceptor, store: store)
        await #expect(throws: TripFailure.invalidResponse) { try await client.prepare(.accept, proposal: proposal, binding: h.binding) }
        #expect(try store.pending().isEmpty)
    }

    @Test func confirmationNearExpiryIsNotSubmitted() async throws {
        let h = try Harness(); defer { h.clean() }
        let proposal = try fixture().proposal
        let expires = 1_900_000_000
        let interceptor = Interceptor { _, bytes, _ in try Self.preparedBody(bytes, expires: expires, proposal: proposal) }
        let client = try h.client(interceptor)
        let prepared = try await client.prepare(.reject, proposal: proposal, binding: h.binding)
        await #expect(throws: TripFailure.invalidInput) { try await client.confirm(prepared, binding: h.binding, now: expires - 30) }
        #expect(await interceptor.calls.map(\.operation) == ["prepareTripConfirmation"])
    }

    @Test func unknownOutcomeBlocksNewActionsUntilTheOriginalIsReconciled() async throws {
        let h = try Harness(); defer { h.clean() }
        let proposal = try fixture().proposal
        let expires = 1_900_000_000
        let store = try h.store()
        let interceptor = Interceptor { _, bytes, operation in
            switch operation {
            case "prepareTripConfirmation": return try Self.preparedBody(bytes, expires: expires, proposal: proposal)
            case "actOnTripProposal": throw URLError(.networkConnectionLost)
            default: return "{\"request_id\":\"\(trace)\",\"receipt\":null}"
            }
        }
        let client = try h.client(interceptor, store: store)
        let prepared = try await client.prepare(.accept, proposal: proposal, binding: h.binding)
        await #expect(throws: TripFailure.exchangeUnknown) { try await client.confirm(prepared, binding: h.binding, now: expires - 120) }
        #expect(try store.pending().map(\.actionID) == [prepared.pending.actionID])
        // No replacement while the original may still commit.
        await #expect(throws: TripFailure.pendingRequiresQuery) { try await client.prepare(.accept, proposal: proposal, binding: h.binding) }
        guard case .notObserved = try await client.query(actionID: prepared.pending.actionID, binding: h.binding, now: expires) else {
            Issue.record("a missing receipt before expiry must stay unknown"); return
        }
        await #expect(throws: TripFailure.pendingRequiresQuery) { try await client.prepare(.reject, proposal: proposal, binding: h.binding) }
        guard case .expiredUncommitted = try await client.query(actionID: prepared.pending.actionID, binding: h.binding,
                                                               now: expires + confirmationClockMargin + 1) else {
            Issue.record("expired signed confirmation without receipt can never commit"); return
        }
        // The same proposal keeps its frozen original record; other proposals are no longer blocked.
        await #expect(throws: TripFailure.pendingRequiresQuery) { try await client.prepare(.reject, proposal: proposal, binding: h.binding) }
        let operations = await interceptor.calls.map(\.operation)
        #expect(operations.filter { $0 == "actOnTripProposal" }.count == 1) // never resent
    }

    @Test func interceptedTestClientDoesNotAdvertiseUserActions() async throws {
        let h = try Harness(); defer { h.clean() }
        let client = try h.client(Interceptor { _, _, _ in "" })
        #expect(!client.acceptsUserActions)
    }
}
