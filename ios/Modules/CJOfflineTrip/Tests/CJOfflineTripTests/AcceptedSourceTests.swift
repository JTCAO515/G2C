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

@Suite @MainActor struct AcceptedSourceTests {
    @Test func exactPublicHookToCanonicalKeyToEncryptedFile() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }; let d = try DetailHarness(h)
        let request = try d.client.prepareDetailSnapshot(id:"trip1",binding:d.binding) // synchronous original event
        let accepted = try #require(try await d.client.detailSnapshot(for:request)) // one existing GET
        try d.client.validateDetailSnapshot(accepted) // after consumer await
        let cache = try d.capture(accepted)
        let receipt = try cache.writeOnce()
        let cipher = try #require(try h.store.read())
        let actual = try #require(try h.access.read(minimumVersion:2))
        #expect(actual.responseBytes == d.originalBytes)
        #expect(actual.metadata.namespace == h.ns)
        #expect(receipt.responseHash == CJOfflineTrip.digest(d.originalBytes) && receipt.version == 2)
        #expect(!String(decoding:cipher,as:UTF8.self).contains("中文地点"))
        #expect(throws:OfflineFailure.unavailable) { try cache.writeOnce() }
        #expect(try h.store.read() == cipher)
        #expect(await d.wire.calls == ["getTrip"])
        #expect(h.storage.adds == 0 && h.storage.removes == 0 && !SnapshotCodec.appFactoryAvailable)
    }
    @Test func originalHandleRetiredAcrossAwaitCannotCapture() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }; let d = try DetailHarness(h)
        let request = try d.client.prepareDetailSnapshot(id:"trip1",binding:d.binding)
        let accepted = try #require(try await d.client.detailSnapshot(for:request))
        await Task.yield()
        d.client.invalidateDetailSnapshots()
        #expect(throws:(any Error).self) { try d.capture(accepted) }
        #expect(try h.store.read() == nil)
        #expect(await d.wire.calls == ["getTrip"])
    }
    @Test func networkAwaitSelectionChangeYieldsNoSourceOrCache() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }; let gate = DetailGate(); let d = try DetailHarness(h,gate:gate)
        let request = try d.client.prepareDetailSnapshot(id:"trip1",binding:d.binding)
        let task = Task { try await d.client.detailSnapshot(for:request) }
        await gate.waitEntered()
        d.selection.binding = TripBinding(environment:d.binding.environment,account:d.binding.account,generation:d.binding.generation,selection:UUID())
        d.client.invalidateDetailSnapshots()
        await gate.release()
        await #expect(throws:(any Error).self) { try await task.value }
        #expect(try h.store.read() == nil)
        #expect(await d.wire.calls == ["getTrip"])
    }
    @Test func providerCallbackRetiresOriginalAndCannotPolluteNewSource() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }; let d = try DetailHarness(h)
        let original = try d.client.prepareDetailSnapshot(id:"trip1",binding:d.binding)
        let accepted = try #require(try await d.client.detailSnapshot(for:original))
        let cache = try d.capture(accepted)
        var newer: TripDetailSnapshotRequest?
        h.storage.onRead = {
            h.storage.onRead = nil
            d.selection.onCurrent = {
                d.selection.onCurrent = nil
                newer = try? d.client.prepareDetailSnapshot(id:"trip1",binding:d.binding)
            }
        }
        #expect(throws:OfflineFailure.unavailable) { try cache.writeOnce() }
        #expect(try h.store.read() == nil)
        let replacement = try #require(newer)
        let current = try #require(try await d.client.detailSnapshot(for:replacement))
        let fresh = try d.capture(current); _ = try fresh.writeOnce()
        let bytes = try h.store.read()
        #expect(throws:OfflineFailure.unavailable) { try cache.writeOnce() }
        #expect(try h.store.read() == bytes)
        #expect(await d.wire.calls == ["getTrip","getTrip"])
    }
    @Test func providerCallbackSessionChangeCannotWrite() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }; let d = try DetailHarness(h)
        let request = try d.client.prepareDetailSnapshot(id:"trip1",binding:d.binding)
        let accepted = try #require(try await d.client.detailSnapshot(for:request)); let cache = try d.capture(accepted)
        h.storage.onRead = { _ = try h.session.beginUserRestore() }
        #expect(throws:OfflineFailure.unavailable) { try cache.writeOnce() }
        #expect(try h.store.read() == nil)
    }
    @Test func finalSourceCallbackFileReplacementCannotBeOverwritten() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }; let d = try DetailHarness(h)
        let request = try d.client.prepareDetailSnapshot(id:"trip1",binding:d.binding)
        let accepted = try #require(try await d.client.detailSnapshot(for:request)); let cache = try d.capture(accepted)
        let changed = Data([4,3,2,1])
        h.storage.onRead = {
            h.storage.onRead = nil
            d.selection.onCurrent = {
                d.selection.onCurrent = nil
                try? changed.write(to:h.root.appendingPathComponent("snapshot.aesgcm"),options:[])
                _ = chmod(h.root.appendingPathComponent("snapshot.aesgcm").path,0o600)
            }
        }
        #expect(throws:OfflineFailure.corrupt) { try cache.writeOnce() }
        #expect(try h.store.read() == changed)
    }
    @Test func unknownWriteBlocksNewCaptureAndReconcilesExactOriginal() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }; let d = try DetailHarness(h)
        let request = try d.client.prepareDetailSnapshot(id:"trip1",binding:d.binding)
        let accepted = try #require(try await d.client.detailSnapshot(for:request)); let cache = try d.capture(accepted)
        h.store.afterRename = { throw OfflineFailure.storageFailure }
        #expect(throws:OfflineFailure.writeUnknown) { try cache.writeOnce() }
        let attempted = try h.store.read()
        var lookups = 0; h.storage.onRead = { lookups += 1 }
        #expect(throws:OfflineFailure.writeUnknown) { try cache.writeOnce() }
        #expect(throws:OfflineFailure.writeUnknown) { try d.capture(accepted) }
        #expect(lookups == 0)
        #expect(try h.store.read() == attempted)
        #expect(try cache.reconcileOriginalWrite() == .committed)
        #expect(try h.store.read() == attempted)
        #expect(h.storage.adds == 0 && h.storage.removes == 0)
    }
    @Test func retiredBetweenConstructionAndWriteNeverLooksUpKey() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }; let d = try DetailHarness(h)
        let request = try d.client.prepareDetailSnapshot(id:"trip1",binding:d.binding)
        let accepted = try #require(try await d.client.detailSnapshot(for:request)); let cache = try d.capture(accepted)
        await Task.yield()
        d.client.invalidateDetailSnapshots()
        var lookups = 0; h.storage.onRead = { lookups += 1 }
        #expect(throws:(any Error).self) { try cache.writeOnce() }
        #expect(lookups == 0)
        #expect(try h.store.read() == nil)
    }
    @Test func fileCallbackRetiresSourceWithoutSuccessOrResend() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }; let d = try DetailHarness(h)
        let request = try d.client.prepareDetailSnapshot(id:"trip1",binding:d.binding)
        let accepted = try #require(try await d.client.detailSnapshot(for:request)); let cache = try d.capture(accepted)
        h.store.afterRename = { d.client.invalidateDetailSnapshots() }
        #expect(throws:OfflineFailure.unavailable) { try cache.writeOnce() }
        let original = try #require(try h.store.read()) // write may exist, but no successful-source receipt
        #expect(throws:OfflineFailure.unavailable) { try cache.writeOnce() }
        #expect(try h.store.read() == original)
        #expect(await d.wire.calls == ["getTrip"])
    }

    @Test func failedSourceValidationKeepsReservationAcrossReentry() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }; let d = try DetailHarness(h)
        let request = try d.client.prepareDetailSnapshot(id:"trip1",binding:d.binding)
        let accepted = try #require(try await d.client.detailSnapshot(for:request)); let cache = try d.capture(accepted)
        var nestedDenied = 0, lookups = 0, commits = 0
        h.storage.onRead = { lookups += 1 }
        h.store.afterRename = { commits += 1 }
        d.selection.onCurrent = {
            d.selection.onCurrent = nil
            do { _ = try cache.writeOnce(); Issue.record("Nested write must not own reserved attempt") }
            catch OfflineFailure.unavailable { nestedDenied += 1 }
            catch { Issue.record("Unexpected nested error: \(type(of:error))") }
            d.client.invalidateDetailSnapshots()
        }
        #expect(throws:TripFailure.staleBinding) { try cache.writeOnce() }
        #expect(throws:OfflineFailure.unavailable) { try cache.writeOnce() }
        #expect(nestedDenied == 1 && lookups == 0 && commits == 0)
        #expect(try h.store.read() == nil)
        #expect(await d.wire.calls == ["getTrip"])
    }

}
