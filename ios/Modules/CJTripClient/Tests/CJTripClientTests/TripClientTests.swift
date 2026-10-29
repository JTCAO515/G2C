import Testing
import Foundation
import CJAPI
import CJMessageHTTP
import CJSession
@testable import CJTripClient

@Suite @MainActor struct TripClientTests {
    @Test func officialRawBytesFreezeBeforeAwaitAndSurviveReopen() async throws {
        let h = try Harness(); defer { h.clean() }
        let original = try pending()
        #expect(original.originalUTF8 == Data(try fixture().accept_raw.utf8))
        #expect(try pending(.reject).originalUTF8 == Data(fixture().reject_raw.utf8))
        let transport = Interceptor { _, _, _ in try response("receipt", actionReceipt(original)) }
        let client = try h.client(transport, credentials: { _ in
            let persisted = try h.store().pending().first?.originalUTF8
            #expect(persisted == original.originalUTF8)
            return "synthetic-test-token"
        })
        guard case .confirmed(let receipt) = try await client.submitFixture(original, binding: h.binding, now: 1) else { Issue.record("missing receipt"); return }
        #expect(receipt.committed_version == .case1(1))
        let calls = await transport.calls
        #expect(calls.count == 1 && calls[0].bytes == original.originalUTF8)
        #expect(try h.store().pending().first?.originalUTF8 == calls[0].bytes)
        let disk = try Data(contentsOf: h.root.appendingPathComponent(digest(Data(original.actionID.utf8)) + ".trip"))
        #expect(disk.range(of: original.originalUTF8) == nil)
        #expect(disk.range(of: Data("Synthetic".utf8)) == nil)
        await #expect(throws: TripFailure.pendingRequiresQuery) { try await client.submitFixture(original, binding: h.binding, now: 1) }
        #expect(await transport.calls.count == 1)
    }
    @Test func lostReceiptReopenNullOnlyQueriesOriginalAndNeverResends() async throws {
        let h = try Harness(); defer { h.clean() }
        let original = try pending()
        let transport = Interceptor { _, _, op in
            if op == "actOnTripProposal" { throw TripFailure.exchangeUnknown }
            return "{\"request_id\":\"\(trace)\",\"receipt\":null}"
        }
        let client = try h.client(transport)
        await #expect(throws: TripFailure.exchangeUnknown) { try await client.submitFixture(original, binding: h.binding, now: 1) }
        let reopened = try h.client(transport)
        guard case .notObserved = try await reopened.query(actionID: original.actionID, binding: h.binding) else { Issue.record("not null"); return }
        await #expect(throws: TripFailure.pendingRequiresQuery) { try await reopened.submitFixture(pending(.reject), binding: h.binding, now: 1) }
        #expect(await transport.calls.map(\.operation) == ["actOnTripProposal", "queryTripAction"])
        #expect(await transport.calls.last?.path?.contains("action_id=accept1") == true)
    }
    @Test func receiptIsHistoricalAndFormalEntrancesReadCurrentVersion() async throws {
        let h = try Harness(); defer { h.clean() }
        let original = try pending(); try h.store().append(original)
        let transport = Interceptor { _, _, op in
            switch op {
            case "queryTripAction": return try response("receipt", actionReceipt(original))
            case "getTrip": return try response("trip", record(version: 9))
            default: return "{\"request_id\":\"\(trace)\",\"trips\":[\(try json(record(version: 9)))],\"next_after\":\"trip1\"}"
            }
        }
        let client = try h.client(transport)
        guard case .confirmed(let receipt) = try await client.query(actionID: original.actionID, binding: h.binding) else { Issue.record("missing receipt"); return }
        #expect(receipt.committed_version == .case1(1))
        let detail = try await client.detail(id: "trip1", binding: h.binding)
        let list = try await client.list(limit: 20, binding: h.binding)
        #expect(detail?.version == 9 && list.trips.first == detail)
        #expect(detail?.document.displayItems.first?.verification == .pending)
        #expect(list.next != nil) // Short page is not completeness.
    }
    @Test(arguments: ["{}", "false", "7", "\"bad\""])
    func nonNullOneOfFallbackNeverMeansAbsent(_ invalid: String) async throws {
        let h = try Harness(); defer { h.clean() }
        try h.store().append(pending())
        let transport = Interceptor { _, _, op in
            "{\"request_id\":\"\(trace)\",\"\(op == "getTrip" ? "trip" : "receipt")\":\(invalid)}"
        }
        let client = try h.client(transport)
        await #expect(throws: TripFailure.invalidResponse) { try await client.query(actionID: "accept1", binding: h.binding) }
        await #expect(throws: TripFailure.invalidResponse) { try await client.detail(id: "trip1", binding: h.binding) }
    }
    @Test func rejectRequiresNullAndMismatchedReceiptCannotSettle() async throws {
        let h = try Harness(); defer { h.clean() }
        let original = try pending(.reject); try h.store().append(original)
        let invalid = Interceptor { _, _, _ in
            var r = actionReceipt(original); r.committed_version = .case1(1); return try response("receipt", r)
        }
        await #expect(throws: TripFailure.invalidResponse) { try await h.client(invalid).query(actionID: original.actionID, binding: h.binding) }
        let correct = Interceptor { _, _, _ in try response("receipt", actionReceipt(original)) }
        guard case .confirmed(let r) = try await h.client(correct).query(actionID: original.actionID, binding: h.binding) else { Issue.record("reject not settled"); return }
        #expect(r.committed_version == .case2(nil))
        let bad = Interceptor { _, _, _ in
            var r = actionReceipt(original); r.candidate_hash = String(repeating: "0", count: 64); return try response("receipt", r)
        }
        await #expect(throws: TripFailure.invalidResponse) { try await h.client(bad).query(actionID: original.actionID, binding: h.binding) }
    }
    @Test func publicReadAndCallerViewedCannotEnablePost() async throws {
        let h = try Harness(); defer { h.clean() }
        let transport = Interceptor { _, _, _ in try response("proposal", fixture().proposal) }
        let client = try h.client(transport)
        let displayed = try await client.proposal(id: "proposal1", binding: h.binding)
        await #expect(throws: TripFailure.liveWriteUnavailable) { try await client.choose(.accept, proposal: displayed, binding: h.binding) }
        #expect(await transport.calls.map(\.operation) == ["getTripProposal"])
        #expect(try h.store().pending().isEmpty)
        let session = SessionLifecycle(persistence: SyntheticSessionPersistence(), restorePolicy: .userInitiatedOnly)
        let operation = try session.beginTrustedSDKSave()
        let live = TripClient(endpoint: h.endpoint, credentials: { _ in "synthetic" }, currentBinding: { h.current }, session: session, sessionOperation: operation, pendingStore: try h.store(),
                              liveReadTransport: try NoRedirectTransport(requestTimeout: 1, resourceTimeout: 1))
        await #expect(throws: TripFailure.liveWriteUnavailable) { try await live.submitFixture(pending(), binding: h.binding, now: 1) }
    }
    @Test func keysetUsesCOrderAndEmptyPageEndsTraversal() async throws {
        let h = try Harness(); defer { h.clean() }
        let transport = Interceptor { request, _, _ in
            if request.path?.contains("after=a") == true { return "{\"request_id\":\"\(trace)\",\"trips\":[],\"next_after\":null}" }
            return "{\"request_id\":\"\(trace)\",\"trips\":[\(try json(record("Z"))),\(try json(record("a")))],\"next_after\":\"a\"}"
        }
        let client = try h.client(transport)
        let page = try await client.list(limit: 20, binding: h.binding)
        #expect(page.trips.map(\.trip_id) == ["Z", "a"] && page.next != nil)
        let final = try await client.list(limit: 20, after: page.next, binding: h.binding)
        #expect(final.trips.isEmpty && final.next == nil)
        let other = try h.client(transport)
        await #expect(throws: TripFailure.staleBinding) { try await other.list(limit: 20, after: page.next, binding: h.binding) }
    }
    @Test(arguments: ["null", "{}", "\"other\""])
    func nonemptyPageNeedsExactLastID(_ cursor: String) async throws {
        let h = try Harness(); defer { h.clean() }
        let transport = Interceptor { _, _, _ in "{\"request_id\":\"\(trace)\",\"trips\":[\(try json(record()))],\"next_after\":\(cursor)}" }
        await #expect(throws: TripFailure.invalidResponse) { try await h.client(transport).list(limit: 20, binding: h.binding) }
    }
}
