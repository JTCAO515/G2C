import Foundation
import Testing
import CJAPI
@testable import CJTripClient

@Suite @MainActor struct BoundaryTests {
    @Test(arguments: Components.Schemas.TripProposalSnapshot.statusPayload.allCases)
    func terminalProposalReadableWithoutGrantingWrite(_ status: Components.Schemas.TripProposalSnapshot.statusPayload) async throws {
        let h = try Harness(); defer { h.clean() }
        let transport = Interceptor { _, _, _ in
            var p = try fixture().proposal; p.status = status; return try response("proposal", p)
        }
        let client = try h.client(transport)
        let p = try await client.proposal(id: "proposal1", binding: h.binding)
        #expect(p.status.rawValue == status.rawValue && !client.acceptsUserActions)
        #expect(p.content_utf8_base64 == (try fixture().proposal.content_utf8_base64))
        #expect(p.document.displayItems.first?.verification == .pending)
    }
    @Test func expiredOrTerminalTestCandidateCannotDispatch() async throws {
        let h = try Harness(); defer { h.clean() }
        let transport = Interceptor { _, _, _ in "{}" }; let client = try h.client(transport)
        let original = try pending()
        await #expect(throws: TripFailure.invalidInput) { try await client.submitFixture(original, binding: h.binding, now: original.proposal.expires_at) }
        var p = original.proposal; p.status = .superseded
        let replaced = try TripPending(actionID: "replacement", kind: .accept, proposal: p, confirmationReference: "test-proof")
        await #expect(throws: TripFailure.invalidInput) { try await client.submitFixture(replaced, binding: h.binding, now: 1) }
        #expect(await transport.calls.isEmpty)
        #expect(try h.store().pending().isEmpty)
    }
    @Test func proposalProjectionMismatchAndDuplicateItemFail() async throws {
        let h = try Harness(); defer { h.clean() }
        let mismatched = Interceptor { _, _, _ in
            var p = try fixture().proposal; p.document.items[0].text = "different display"; return try response("proposal", p)
        }
        await #expect(throws: TripFailure.invalidResponse) { try await h.client(mismatched).proposal(id: "proposal1", binding: h.binding) }
        var p = try fixture().proposal
        p.document.items.append(p.document.items[0]); p.content_utf8_base64 = try JSONEncoder().encode(p.document).base64EncodedString()
        #expect(throws: TripFailure.invalidResponse) { try validateProposal(p) }
    }
    @Test func duplicateJSONAndTraceMismatchRejectedBeforeDecode() async throws {
        let h = try Harness(); defer { h.clean() }
        let duplicate = Interceptor { _, _, _ in
            "{\"request_id\":\"\(trace)\",\"trip\":null,\"trip\":\(try json(record()))}"
        }
        await #expect(throws: TripFailure.exchangeUnknown) { try await h.client(duplicate).detail(id: "trip1", binding: h.binding) }
        let traceMismatch = Interceptor { _, _, _ in "{\"request_id\":\"00000000-0000-0000-0000-000000000002\",\"trip\":null}" }
        await #expect(throws: TripFailure.exchangeUnknown) { try await h.client(traceMismatch).detail(id: "trip1", binding: h.binding) }
    }
    @Test func illegalRejectVersionFallbackAndWrongAcceptVersionFail() throws {
        let original = try pending(.reject)
        let base = try response("receipt", actionReceipt(original))
        let invalid = base.replacingOccurrences(of: "\"committed_version\":null", with: "\"committed_version\":{}")
        let decoded = try JSONDecoder().decode(Components.Schemas.TripActionResponse.self, from: Data(invalid.utf8))
        #expect(throws: TripFailure.invalidResponse) { try validateReceipt(decoded.receipt, original: original) }
        let accepted = try pending()
        #expect(throws: TripFailure.invalidResponse) { try validateReceipt(actionReceipt(accepted, version: 9), original: accepted) }
    }
    @Test func latePageCannotAppendAfterRefresh() async throws {
        let h = try Harness(); defer { h.clean() }
        let gate = Gate()
        let transport = Interceptor { request, _, _ in
            if request.path?.contains("after=trip1") == true {
                await gate.park()
                return "{\"request_id\":\"\(trace)\",\"trips\":[\(try json(record("trip2")))],\"next_after\":\"trip2\"}"
            }
            return "{\"request_id\":\"\(trace)\",\"trips\":[\(try json(record()))],\"next_after\":\"trip1\"}"
        }
        let state = TripPresentation(client: try h.client(transport)); state.replace(binding: h.binding)
        await state.perform(try #require(state.prepareTrips(limit: 1)))
        let moreWork = try #require(state.prepareTrips(limit: 1, more: true))
        let more = Task { await state.perform(moreWork) }; await gate.waitForEntry()
        await state.perform(try #require(state.prepareTrips(limit: 1))); await gate.release(); await more.value
        #expect(state.trips.map(\.trip_id) == ["trip1"] && state.listState == .loaded)
    }
}
