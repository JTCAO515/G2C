import Testing
import Foundation
import Darwin
import CJAPI
import CJMessageHTTP
import CJSession
import OpenAPIRuntime
import HTTPTypes
@testable import CJTripClient // only original intercepted-transport test initializer
@testable import CJOfflineTrip

private actor DetailGate {
    private var entered = false
    private var parked: CheckedContinuation<Void,Never>?
    private var waiter: CheckedContinuation<Void,Never>?
    func park() async {
        entered = true; waiter?.resume(); waiter = nil
        await withCheckedContinuation { parked = $0 }
    }
    func waitEntered() async { if !entered { await withCheckedContinuation { waiter = $0 } } }
    func release() { parked?.resume(); parked = nil }
}
private actor DetailWire: ClientTransport {
    let bytes: Data
    let trace: String
    let gate: DetailGate?
    var calls: [String] = []
    init(bytes: Data, gate: DetailGate? = nil) throws {
        self.bytes = bytes; self.gate = gate
        let object = try #require(JSONSerialization.jsonObject(with:bytes) as? [String:Any])
        trace = try #require(object["request_id"] as? String)
    }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse,HTTPBody?) {
        calls.append(operationID)
        #expect(request.method == .get && operationID == "getTrip")
        if let gate { await gate.park() }
        var response = HTTPResponse(status:.ok)
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        response.headerFields[.contentType] = "application/json"
        return (response,HTTPBody(bytes))
    }
}
@MainActor private final class DetailSelection {
    var binding: TripBinding?
    var onCurrent: (() -> Void)?
    init(_ binding: TripBinding) { self.binding = binding }
    func current() -> TripBinding? { onCurrent?(); return binding }
}
@MainActor private struct DetailHarness {
    let h: KeyHarness
    let wire: DetailWire
    let binding: TripBinding
    let selection: DetailSelection
    let client: TripClient
    let originalBytes: Data
    init(_ h: KeyHarness, gate: DetailGate? = nil) throws {
        self.h = h
        // Deliberate whitespace and escaped Unicode: unequal to any encoded record.
        let body = String(decoding:try h.snapshot().responseBytes,as:UTF8.self).replacingOccurrences(of:"北京",with:"\\u5317\\u4eac")
        originalBytes = Data((" \n" + body + "\n ").utf8)
        wire = try DetailWire(bytes:originalBytes,gate:gate)
        binding = TripBinding(environment:h.ns.backend,account:h.ns.account,generation:UUID(),selection:UUID())
        selection = DetailSelection(binding)
        let endpoint = try TripEndpoint(url:URL(string:"https://accepted-trip.invalid")!,maximumRequestBytes:100_000,maximumResponseBytes:100_000)
        client = TripClient(endpoint:endpoint,credentials:{ _ in "synthetic-only" },currentBinding:selection.current,
                            session:h.session,sessionOperation:h.operation,interceptedTransport:wire)
    }
    func capture(_ accepted: AcceptedTripDetailSnapshot) throws -> AcceptedDetailSnapshotCache {
        try AcceptedDetailSnapshotCache(client:client,accepted:accepted,store:h.store,provider:h.provider,
            session:h.session,sessionOperation:h.operation,expectedKeyID:h.expectedID,
            sync:.init(syncedAt:1000,deadline:1100,boot:UUID(),uptime:50))
    }
}


@Suite @MainActor struct IndependentAcceptedSourceAttemptTests {
    @Test func sourceValidationReentryCannotCommitSameCaptureTwice() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }
        let d = try DetailHarness(h)
        let original = try d.client.prepareDetailSnapshot(id: "trip1", binding: d.binding)
        let accepted = try #require(try await d.client.detailSnapshot(for: original))
        let cache = try d.capture(accepted)
        var successes = 0, commits = 0
        var nestedCiphertext: Data?
        h.store.afterRename = { commits += 1 }
        d.selection.onCurrent = {
            d.selection.onCurrent = nil
            do {
                _ = try cache.writeOnce(); successes += 1
                nestedCiphertext = try h.store.read()
            } catch OfflineFailure.unavailable { }
            catch { Issue.record("Unexpected nested failure: \(type(of: error))") }
        }
        do { _ = try cache.writeOnce(); successes += 1 }
        catch OfflineFailure.unavailable { }
        catch { Issue.record("Unexpected outer failure: \(type(of: error))") }
        #expect(successes == 1, "One accepted capture returned two successful write receipts")
        #expect(commits == 1, "Reentry before attempted=true allowed two atomic replacements")
        if let nestedCiphertext {
            #expect(try h.store.read() == nestedCiphertext, "Old outer write replaced already committed original ciphertext with a new nonce")
        }
        #expect(await d.wire.calls == ["getTrip"])
        #expect(h.storage.adds == 0 && h.storage.removes == 0)
    }
}
