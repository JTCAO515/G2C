import Foundation
import Testing
import CJAPI
import CJSession
import CJMessageHTTP
import HTTPTypes
import OpenAPIRuntime
@testable import CJTripClient
@testable import CJManualPreviewClient

let trace = "00000000-0000-0000-0000-000000000017"
func originalRecord() throws -> Components.Schemas.TripRecord {
    let document = Components.Schemas.TripDocument(title: "Cafe\u{301}", items: [
        .init(id: "a", text: "Original A", verification: .verified, evidence: ["source-a"]),
        .init(id: "b", text: "Original B", verification: .pending, evidence: []),
        .init(id: "c", text: "Original C", verification: .pending, evidence: [])])
    return .init(trip_id: "trip17", version: 7, content_utf8_base64: try encoded(document).base64EncodedString(), document: document)
}
func preview(_ original: Components.Schemas.TripRecord, after: Components.Schemas.TripDocument? = nil,
             selected: [String] = [], titleSelected: Bool = false,
             diff: [Components.Schemas.ManualPreviewChange] = []) throws -> Components.Schemas.ManualPreview {
    let document = after ?? original.document
    return .init(preview_status: .LOCAL, original: original, content_utf8_base64: try encoded(document).base64EncodedString(),
                 document: document, selected_ids: selected, title_selected: titleSelected, protection_status: .UNKNOWN, can_save: false, diff: diff)
}
func change<T: Encodable>(_ path: [String], _ before: T, _ after: T) throws -> Components.Schemas.ManualPreviewChange {
    .init(path: path, before_utf8_base64: try encoded(before).base64EncodedString(), after_utf8_base64: try encoded(after).base64EncodedString())
}
func response(_ p: Components.Schemas.ManualPreview) throws -> Data {
    try encoded(Components.Schemas.ManualPreviewResponse(request_id: trace, preview: p))
}
struct Persistence: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ material: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
actor Gate {
    private var parked: CheckedContinuation<Void, Never>?
    private var entered = false
    private var waiter: CheckedContinuation<Void, Never>?
    func park() async { entered = true; waiter?.resume(); waiter = nil; await withCheckedContinuation { parked = $0 } }
    func wait() async { if entered { return }; await withCheckedContinuation { waiter = $0 } }
    func release() { parked?.resume(); parked = nil }
}
struct SuspendedBody: AsyncSequence, Sendable {
    typealias Element = ArraySlice<UInt8>
    let bytes: Data
    let gate: Gate
    struct AsyncIterator: AsyncIteratorProtocol {
        let bytes: Data; let gate: Gate; var done = false
        mutating func next() async -> Element? {
            guard !done else { return nil }; done = true; await gate.park(); return ArraySlice(bytes)
        }
    }
    func makeAsyncIterator() -> AsyncIterator { .init(bytes: bytes, gate: gate) }
}
actor Wire: ClientTransport {
    var calls: [Data] = []
    let bytes: Data
    let code: Int
    let headerTrace: String
    let cache: String?
    let gate: Gate?
    let bodyGate: Gate?
    init(_ bytes: Data, code: Int = 200, trace: String = trace, cache: String? = "no-store", gate: Gate? = nil, bodyGate: Gate? = nil) {
        self.bytes = bytes; self.code = code; headerTrace = trace; self.cache = cache; self.gate = gate; self.bodyGate = bodyGate
    }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let input: Data
        if let body { input = try await Data(collecting: body, upTo: 100_000) } else { input = Data() }
        calls.append(input)
        if let gate { await gate.park() }
        var response = HTTPResponse(status: .init(code: code))
        response.headerFields[.contentType] = "application/json"
        response.headerFields[HTTPField.Name("X-Request-ID")!] = headerTrace
        if let cache { response.headerFields[.cacheControl] = cache }
        if let bodyGate { return (response, HTTPBody(SuspendedBody(bytes: bytes, gate: bodyGate), length: .unknown, iterationBehavior: .single)) }
        return (response, HTTPBody(bytes))
    }
}
@MainActor final class Harness {
    let original: Components.Schemas.TripRecord
    let session = SessionLifecycle(persistence: Persistence(), restorePolicy: .userInitiatedOnly)
    let operation: SessionOperation
    let binding = TripBinding(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID())
    var current: TripBinding?
    var callback: (() -> Void)?
    let endpoint = try! MessageEndpoint(url: URL(string: "https://preview.invalid")!, maximumRequestBytes: 100_000, maximumResponseBytes: 100_000)
    var trip: TripClient!
    var snapshot: AcceptedTripDetailSnapshot!
    init() throws { original = try originalRecord(); operation = try session.beginTrustedSDKSave(); current = binding }
    func load() async throws {
        let data = Data(("{\"request_id\":\"" + trace + "\",\"trip\":" + String(decoding: try encoded(original), as: UTF8.self) + "}").utf8)
        let wire = Wire(data)
        trip = TripClient(endpoint: endpoint, credentials: { _ in "synthetic" }, currentBinding: { [self] in callback?(); return current },
                          session: session, sessionOperation: operation, interceptedTransport: wire)
        let request = try trip.prepareDetailSnapshot(id: original.trip_id, binding: binding)
        snapshot = try #require(try await trip.detailSnapshot(for: request))
    }
    func editor(_ wire: Wire, credentials: TripCredentialCallback? = nil) throws -> PreviewEditor {
        try PreviewEditor(trip: trip, source: snapshot, endpoint: endpoint, session: session, operation: operation,
                          credentials: credentials ?? { _ in "synthetic" }, interceptedTransport: wire)
    }
}
