import Foundation
import Testing
import CJAPI
import CJSession
import OpenAPIRuntime
import HTTPTypes
@testable import CJTripClient

private func spacedDetail(_ trip: Components.Schemas.TripRecord) throws -> String {
    let encoded = try json(trip).replacingOccurrences(of: "Synthetic", with: "\\u0053ynthetic")
    return " \n{ \"trip\" : \(encoded),  \"request_id\" : \"\(trace)\" }\n"
}

private struct SnapshotBody: AsyncSequence, Sendable {
    typealias Element = ArraySlice<UInt8>
    let bytes: Data
    let gate: Gate
    struct AsyncIterator: AsyncIteratorProtocol {
        let bytes: Data
        let gate: Gate
        var emitted = false
        mutating func next() async throws -> Element? {
            guard !emitted else { return nil }; emitted = true
            await gate.park()
            return ArraySlice(bytes)
        }
    }
    func makeAsyncIterator() -> AsyncIterator { .init(bytes: bytes, gate: gate) }
}
private actor SnapshotWire: ClientTransport {
    let payload: Data
    let status: HTTPResponse.Status
    let gate: Gate?
    var calls = 0
    init(_ payload: String, status: HTTPResponse.Status = .ok, gate: Gate? = nil) {
        self.payload = Data(payload.utf8); self.status = status; self.gate = gate
    }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        calls += 1
        var response = HTTPResponse(status: status)
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        response.headerFields[.contentType] = "application/json"
        let body: HTTPBody
        if let gate { body = HTTPBody(SnapshotBody(bytes: payload, gate: gate), length: .unknown, iterationBehavior: .single) }
        else { body = HTTPBody(payload) }
        return (response, body)
    }
}

@Suite @MainActor struct AcceptedDetailSnapshotTests {
    @Test func exactReceivedBytesRecordTraceAndRedaction() async throws {
        let h = try Harness(); defer { h.clean() }
        let trip = try record(version: 7); let raw = try spacedDetail(trip)
        let rebuilt = Data(try response("trip", trip).utf8)
        let wire = Interceptor { _, _, _ in raw }; let client = try h.client(wire)
        let original = try client.prepareDetailSnapshot(id: "trip1", binding: h.binding)
        let snapshot = try #require(try await client.detailSnapshot(for: original))
        try client.withCurrentDetailSnapshot(snapshot) { bytes, accepted, requestID, binding in
            #expect(bytes == Data(raw.utf8))
            #expect(accepted == trip && accepted.version == 7 && requestID == trace)
            #expect(binding == h.binding)
            #expect(bytes != rebuilt)
        }
        #expect(AcceptedTripDetailSnapshot.apiSourceCommit == "c02cf08e52a0d8ffc2fefac99226654a7e01539c")
        #expect(String(reflecting: snapshot) == "<accepted formal Trip detail snapshot>")
        #expect(Mirror(reflecting: snapshot).children.isEmpty)
        #expect(await wire.calls.map(\.operation) == ["getTrip"])
        #expect(await wire.calls.first?.path?.contains("trip_id=trip1") == true)
        await #expect(throws: TripFailure.staleBinding) { try await client.detailSnapshot(for: original) }
        #expect(await wire.calls.count == 1)
        let other = try h.client(wire)
        #expect(throws: TripFailure.staleBinding) { try other.validateDetailSnapshot(snapshot) }
    }

    @Test(arguments: ["false", "{}", "7", "\"not-a-record\""])
    func invalidNonNullFallbackCannotBecomeSnapshot(_ value: String) async throws {
        let h = try Harness(); defer { h.clean() }
        let wire = Interceptor { _, _, _ in "{\"request_id\":\"\(trace)\",\"trip\":\(value)}" }
        let client = try h.client(wire); let request = try client.prepareDetailSnapshot(id: "trip1", binding: h.binding)
        await #expect(throws: TripFailure.invalidResponse) { try await client.detailSnapshot(for: request) }
    }
    @Test func actualNullRemainsAbsenceAndOldDetailStillWorks() async throws {
        let h = try Harness(); defer { h.clean() }
        let wire = Interceptor { _, _, _ in "{\"request_id\":\"\(trace)\",\"trip\":null}" }
        let client = try h.client(wire)
        let request = try client.prepareDetailSnapshot(id: "trip1", binding: h.binding)
        #expect(try await client.detailSnapshot(for: request) == nil)
        #expect(try await client.detail(id: "trip1", binding: h.binding) == nil)
        #expect(await wire.calls.map(\.operation) == ["getTrip", "getTrip"])
    }
    @Test(arguments: ["receipt", "proposal"])
    func otherDomainBodyCannotBecomeFormalSource(_ key: String) async throws {
        let h = try Harness(); defer { h.clean() }
        let wire = Interceptor { _, _, _ in
            key == "proposal" ? try response("proposal", fixture().proposal) : try response("receipt", actionReceipt(pending()))
        }
        let client = try h.client(wire); let request = try client.prepareDetailSnapshot(id: "trip1", binding: h.binding)
        await #expect(throws: TripFailure.exchangeUnknown) { try await client.detailSnapshot(for: request) }
    }
    @Test(arguments: ["wrong-id", "zero-version", "projection", "extra-response", "extra-record", "extra-content"])
    func invalidRecordOrIgnoredFieldsCannotBecomeAccepted(_ fault: String) async throws {
        let h = try Harness(); defer { h.clean() }
        var trip = try record()
        if fault == "wrong-id" { trip.trip_id = "another-trip" }
        if fault == "zero-version" { trip.version = 0 }
        if fault == "projection" { trip.document.title = "different projected title" }
        if fault == "extra-content" {
            let content = try #require(Data(base64Encoded: trip.content_utf8_base64))
            var object = try #require(try JSONSerialization.jsonObject(with: content) as? [String: Any])
            object["unrecognized"] = "not formal schema"
            trip.content_utf8_base64 = try JSONSerialization.data(withJSONObject: object).base64EncodedString()
        }
        var raw = try response("trip", trip)
        if fault == "extra-response" {
            var object = try #require(try JSONSerialization.jsonObject(with: Data(raw.utf8)) as? [String: Any])
            object["extra"] = true; raw = String(decoding: try JSONSerialization.data(withJSONObject: object), as: UTF8.self)
        }
        if fault == "extra-record" {
            var object = try #require(try JSONSerialization.jsonObject(with: Data(raw.utf8)) as? [String: Any])
            var item = try #require(object["trip"] as? [String: Any]); item["extra"] = true; object["trip"] = item
            raw = String(decoding: try JSONSerialization.data(withJSONObject: object), as: UTF8.self)
        }
        let payload = raw
        let client = try h.client(Interceptor { _, _, _ in payload })
        let request = try client.prepareDetailSnapshot(id: "trip1", binding: h.binding)
        let expected: TripFailure = fault == "extra-response" ? .exchangeUnknown : .invalidResponse
        await #expect(throws: expected) { try await client.detailSnapshot(for: request) }
    }
    @Test(arguments: ["trace", "duplicate"])
    func invalidTransportEnvelopeCannotBecomeAccepted(_ fault: String) async throws {
        let h = try Harness(); defer { h.clean() }
        let raw = fault == "trace"
            ? "{\"request_id\":\"00000000-0000-0000-0000-000000000002\",\"trip\":\(try json(record()))}"
            : "{\"request_id\":\"\(trace)\",\"trip\":null,\"trip\":\(try json(record()))}"
        let client = try h.client(Interceptor { _, _, _ in raw })
        let request = try client.prepareDetailSnapshot(id: "trip1", binding: h.binding)
        await #expect(throws: TripFailure.exchangeUnknown) { try await client.detailSnapshot(for: request) }
    }
    @Test func queuedRequestCannotAdoptLaterSameBindingSelection() async throws {
        let h = try Harness(); defer { h.clean() }
        let wire = Interceptor { _, _, _ in try response("trip", record("B")) }; let client = try h.client(wire)
        let a = try client.prepareDetailSnapshot(id: "A", binding: h.binding)
        let task = Task { try await client.detailSnapshot(for: a) }
        let b = try client.prepareDetailSnapshot(id: "B", binding: h.binding)
        do { _ = try await task.value; Issue.record("queued old source accepted") } catch TripFailure.staleBinding { }
        #expect(await wire.calls.isEmpty)
        let accepted = try #require(try await client.detailSnapshot(for: b))
        try client.withCurrentDetailSnapshot(accepted) { _, trip, _, _ in #expect(trip.trip_id == "B") }
        #expect(await wire.calls.count == 1)
    }
    @Test func accountSwitchAcrossAwaitWithholdsSource() async throws {
        let h = try Harness(); defer { h.clean() }; let gate = Gate()
        let wire = Interceptor { _, _, _ in await gate.park(); return try response("trip", record()) }
        let client = try h.client(wire); let request = try client.prepareDetailSnapshot(id: "trip1", binding: h.binding)
        let task = Task { try await client.detailSnapshot(for: request) }; await gate.waitForEntry()
        h.current = nil; await gate.release()
        do { _ = try await task.value; Issue.record("retired account source accepted") } catch TripFailure.staleBinding { }
        #expect(await wire.calls.count == 1)
    }
    @Test func sourceChangeAcrossAwaitWithholdsSource() async throws {
        let h = try Harness(); defer { h.clean() }; let gate = Gate()
        let wire = Interceptor { _, _, _ in await gate.park(); return try response("trip", record()) }
        let client = try h.client(wire); let request = try client.prepareDetailSnapshot(id: "trip1", binding: h.binding)
        let task = Task { try await client.detailSnapshot(for: request) }; await gate.waitForEntry()
        client.invalidateDetailSnapshots(); await gate.release()
        do { _ = try await task.value; Issue.record("retired selection source accepted") } catch TripFailure.staleBinding { }
    }
    @Test func finalBindingCallbackCannotReturnRetiredSnapshot() async throws {
        let h = try Harness(); defer { h.clean() }
        var armed = false; var reads = 0; var retire: (() -> Void)?
        let wire = Interceptor { _, _, _ in
            await MainActor.run { armed = true }
            return try response("trip", record())
        }
        let client = TripClient(endpoint: h.endpoint, credentials: { _ in "synthetic" }, currentBinding: {
            if armed { reads += 1; if reads == 6 { retire?() } }
            return h.binding
        }, interceptedTransport: wire)
        retire = { client.invalidateDetailSnapshots() }
        let request = try client.prepareDetailSnapshot(id: "trip1", binding: h.binding)
        await #expect(throws: TripFailure.staleBinding) { try await client.detailSnapshot(for: request) }
        #expect(reads == 6)
    }
    @Test func consumerCallbackAndLaterAwaitMustRecheckSource() async throws {
        let h = try Harness(); defer { h.clean() }
        let client = try h.client(Interceptor { _, _, _ in try response("trip", record()) })
        let request = try client.prepareDetailSnapshot(id: "trip1", binding: h.binding)
        let snapshot = try #require(try await client.detailSnapshot(for: request))
        #expect(throws: TripFailure.staleBinding) {
            try client.withCurrentDetailSnapshot(snapshot) { bytes, _, _, _ in
                client.invalidateDetailSnapshots()
                return bytes.count
            }
        }
        let next = try client.prepareDetailSnapshot(id: "trip1", binding: h.binding)
        let current = try #require(try await client.detailSnapshot(for: next))
        let gate = Gate()
        let consumer = Task {
            await gate.park()
            try client.validateDetailSnapshot(current)
        }
        await gate.waitForEntry(); h.current = nil; await gate.release()
        do { try await consumer.value; Issue.record("consumer accepted after account switch") } catch TripFailure.staleBinding { }
    }
    @Test func formalSelectionOrLegacyDetailRetiresPreviousSnapshot() async throws {
        let h = try Harness(); defer { h.clean() }
        let wire = Interceptor { _, _, _ in try response("trip", record()) }; let client = try h.client(wire)
        let state = TripPresentation(client: client); state.replace(binding: h.binding)
        let request = try client.prepareDetailSnapshot(id: "trip1", binding: h.binding)
        let snapshot = try #require(try await client.detailSnapshot(for: request))
        _ = state.prepareTrip(id: "B")
        #expect(throws: TripFailure.staleBinding) { try client.validateDetailSnapshot(snapshot) }
        let next = try client.prepareDetailSnapshot(id: "trip1", binding: h.binding)
        let newer = try #require(try await client.detailSnapshot(for: next))
        #expect(try await client.detail(id: "trip1", binding: h.binding)?.version == 1)
        #expect(throws: TripFailure.staleBinding) { try client.validateDetailSnapshot(newer) }
        #expect(await wire.calls.count == 3)
    }
    @Test func requestIsBoundToClientAndInvalidationAndNeverAddsPost() async throws {
        let h = try Harness(); defer { h.clean() }
        let wire = Interceptor { _, _, _ in try response("trip", record()) }
        let client = try h.client(wire); let other = try h.client(wire)
        let request = try client.prepareDetailSnapshot(id: "trip1", binding: h.binding)
        await #expect(throws: TripFailure.staleBinding) { try await other.detailSnapshot(for: request) }
        client.invalidate()
        await #expect(throws: TripFailure.staleBinding) { try await client.detailSnapshot(for: request) }
        #expect(await wire.calls.isEmpty && !client.acceptsUserActions)
    }
    @Test(arguments: [false, true])
    func bodyCollectionAwaitCannotAcceptRetiredSource(_ switchAccount: Bool) async throws {
        let h = try Harness(); defer { h.clean() }; let gate = Gate()
        let wire = SnapshotWire(try spacedDetail(record()), gate: gate)
        let client = TripClient(endpoint: h.endpoint, credentials: { _ in "synthetic" },
                                currentBinding: { h.current }, interceptedTransport: wire)
        let request = try client.prepareDetailSnapshot(id: "trip1", binding: h.binding)
        let read = Task { try await client.detailSnapshot(for: request) }; await gate.waitForEntry()
        if switchAccount { h.current = nil } else { client.invalidateDetailSnapshots() }
        await gate.release()
        do { _ = try await read.value; Issue.record("retired source escaped body collection") } catch TripFailure.staleBinding { }
        #expect(await wire.calls == 1)
    }
    @Test func knownErrorAndRedirectCannotIssueAcceptedSnapshotOrRetry() async throws {
        let h = try Harness(); defer { h.clean() }
        let failure = Components.Schemas.ErrorResponse(request_id: trace, error: .init(
            code: "TRIP_ACCESS_UNAVAILABLE", category: "access", message_en: "Unavailable", message_zh: "不可用",
            outcome: .unknown, recovery: .retry_safe_read))
        let wire = SnapshotWire(try json(failure), status: .serviceUnavailable)
        let client = TripClient(endpoint: h.endpoint, credentials: { _ in "synthetic" }, currentBinding: { h.current }, interceptedTransport: wire)
        let request = try client.prepareDetailSnapshot(id: "trip1", binding: h.binding)
        await #expect(throws: TripFailure.rejected(503, "TRIP_ACCESS_UNAVAILABLE")) { try await client.detailSnapshot(for: request) }
        await #expect(throws: TripFailure.staleBinding) { try await client.detailSnapshot(for: request) }
        #expect(await wire.calls == 1)
        let redirect = SnapshotWire(try spacedDetail(record()), status: .found)
        let other = TripClient(endpoint: h.endpoint, credentials: { _ in "synthetic" }, currentBinding: { h.current }, interceptedTransport: redirect)
        let redirectRequest = try other.prepareDetailSnapshot(id: "trip1", binding: h.binding)
        await #expect(throws: TripFailure.exchangeUnknown) { try await other.detailSnapshot(for: redirectRequest) }
        #expect(await redirect.calls == 1)
    }
    @Test func canceledOriginalReadCannotReturnSnapshotOrDispatchAgain() async throws {
        let h = try Harness(); defer { h.clean() }; let gate = Gate()
        let wire = Interceptor { _, _, _ in await gate.park(); return try response("trip", record()) }
        let client = try h.client(wire); let request = try client.prepareDetailSnapshot(id: "trip1", binding: h.binding)
        let read = Task { try await client.detailSnapshot(for: request) }; await gate.waitForEntry()
        read.cancel(); await gate.release()
        do { _ = try await read.value; Issue.record("canceled snapshot returned") } catch is CancellationError { }
        await #expect(throws: TripFailure.staleBinding) { try await client.detailSnapshot(for: request) }
        #expect(await wire.calls.count == 1)
        #expect(try FileManager.default.contentsOfDirectory(atPath: h.root.path).isEmpty)
    }
    @Test func originalSessionOperationMustRemainCurrentWhenReadingSnapshot() async throws {
        let h = try Harness(); defer { h.clean() }
        let session = SessionLifecycle(persistence: SyntheticSessionPersistence(), restorePolicy: .userInitiatedOnly)
        let operation = try session.beginTrustedSDKSave()
        let wire = Interceptor { _, _, _ in try response("trip", record()) }
        let client = TripClient(endpoint: h.endpoint, credentials: { _ in "synthetic" }, currentBinding: { h.current },
                                session: session, sessionOperation: operation, interceptedTransport: wire)
        let request = try client.prepareDetailSnapshot(id: "trip1", binding: h.binding)
        let snapshot = try #require(try await client.detailSnapshot(for: request))
        _ = try session.beginTrustedSDKSave()
        #expect(throws: TripFailure.staleBinding) { try client.validateDetailSnapshot(snapshot) }
        var called = false
        #expect(throws: TripFailure.staleBinding) {
            try client.withCurrentDetailSnapshot(snapshot) { _, _, _, _ in called = true }
        }
        #expect(!called)
    }
    @Test func credentialCallbackNewSelectionPreventsOldSourceOutflow() async throws {
        let h = try Harness(); defer { h.clean() }
        let wire = Interceptor { _, _, _ in try response("trip", record("B")) }
        var client: TripClient!
        var newer: TripDetailSnapshotRequest?
        var switchOnce = true
        client = try h.client(wire, credentials: { _ in
            if switchOnce { switchOnce = false; newer = try client.prepareDetailSnapshot(id: "B", binding: h.binding) }
            return "synthetic"
        })
        let old = try client.prepareDetailSnapshot(id: "A", binding: h.binding)
        await #expect(throws: TripFailure.staleBinding) { try await client.detailSnapshot(for: old) }
        #expect(await wire.calls.isEmpty)
        let fresh = try #require(newer)
        let snapshot = try #require(try await client.detailSnapshot(for: fresh))
        try client.withCurrentDetailSnapshot(snapshot) { _, record, _, _ in #expect(record.trip_id == "B") }
        #expect(await wire.calls.count == 1)
    }

    @Test func staleOldReadCannotRetireNewIdentitySnapshot() async throws {
        let h = try Harness(); defer { h.clean() }
        let wire = Interceptor { _, _, _ in try response("trip", record()) }; let client = try h.client(wire)
        let request = try client.prepareDetailSnapshot(id: "trip1", binding: h.binding)
        let snapshot = try #require(try await client.detailSnapshot(for: request))
        let old = TripBinding(environment: h.binding.environment, account: UUID(), generation: UUID(), selection: UUID())
        #expect(throws: TripFailure.staleBinding) { try client.prepareDetailSnapshot(id: "old-trip", binding: old) }
        try client.validateDetailSnapshot(snapshot)
        await #expect(throws: TripFailure.staleBinding) { try await client.detail(id: "old-trip", binding: old) }
        try client.validateDetailSnapshot(snapshot)
        let staleUI = TripPresentation(client: client)
        _ = staleUI.prepareTrip(id: "old-trip")
        try client.validateDetailSnapshot(snapshot)
        #expect(await wire.calls.count == 1)
    }
    @Test func bindingCallbackNewSelectionCannotBeRetiredByOuterPrepare() async throws {
        let h = try Harness(); defer { h.clean() }
        let wire = Interceptor { _, _, _ in try response("trip", record("B")) }
        var hook: (() -> Void)?; var newRequest: TripDetailSnapshotRequest?
        let client = TripClient(endpoint: h.endpoint, credentials: { _ in "synthetic" }, currentBinding: {
            let callback = hook; hook = nil; callback?(); return h.binding
        }, interceptedTransport: wire)
        hook = { newRequest = try! client.prepareDetailSnapshot(id: "B", binding: h.binding) }
        #expect(throws: TripFailure.staleBinding) { try client.prepareDetailSnapshot(id: "A", binding: h.binding) }
        let originalB = try #require(newRequest)
        let snapshot = try #require(try await client.detailSnapshot(for: originalB))
        try client.withCurrentDetailSnapshot(snapshot) { _, record, _, _ in #expect(record.trip_id == "B") }
    }

    @Test func olderPreparedUIWorkCannotRetireNewSnapshotSource() async throws {
        let h = try Harness(); defer { h.clean() }
        let wire = Interceptor { _, _, _ in try response("trip", record("B")) }; let client = try h.client(wire)
        let state = TripPresentation(client: client); state.replace(binding: h.binding)
        let oldUI = try #require(state.prepareTrip(id: "A"))
        let b = try client.prepareDetailSnapshot(id: "B", binding: h.binding)
        let snapshot = try #require(try await client.detailSnapshot(for: b))
        await state.perform(oldUI)
        try client.validateDetailSnapshot(snapshot)
        #expect(await wire.calls.count == 1)
        #expect(state.trip == nil)
    }

    @Test func inFlightUIReadCannotApplyAfterNewSnapshotSelection() async throws {
        let h = try Harness(); defer { h.clean() }; let gate = Gate()
        let wire = Interceptor { request, _, _ in
            if request.path?.contains("trip_id=A") == true { await gate.park(); return try response("trip", record("A")) }
            return try response("trip", record("B"))
        }
        let client = try h.client(wire)
        let state = TripPresentation(client: client); state.replace(binding: h.binding)
        let old = try #require(state.prepareTrip(id: "A"))
        let oldUI = Task { await state.perform(old) }; await gate.waitForEntry()
        let current = try client.prepareDetailSnapshot(id: "B", binding: h.binding)
        let snapshot = try #require(try await client.detailSnapshot(for: current))
        await gate.release(); await oldUI.value
        #expect(state.trip == nil)
        try client.validateDetailSnapshot(snapshot)
        #expect(await wire.calls.count == 2)
    }

}
