import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
@testable import CJTripClient

private actor StructuredReadWire: ClientTransport {
    struct Call: Sendable { let path: String?; let operation: String }
    var calls: [Call] = []
    let handler: @Sendable (HTTPRequest, String) async throws -> Data
    let noStore: Bool
    init(noStore: Bool = true, handler: @escaping @Sendable (HTTPRequest, String) async throws -> Data) {
        self.noStore = noStore; self.handler = handler
    }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        #expect(request.method == .get && body == nil)
        #expect(request.headerFields[.authorization] == "Bearer synthetic-test-token")
        calls.append(.init(path: request.path, operation: operationID))
        let bytes = try await handler(request, operationID)
        var response = HTTPResponse(status: .ok)
        response.headerFields[.contentType] = "application/json"
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        if noStore { response.headerFields[HTTPField.Name("Cache-Control")!] = "no-store" }
        return (response, HTTPBody(bytes))
    }
}

@Suite @MainActor struct StructuredReadClientTests {
    func detail(_ version: Int = 2, id: String = "trip1") throws -> Data {
        let fixture = try StructuredTripTests().fixture("minute"), content = String(decoding: fixture.bytes, as: UTF8.self)
        return Data("{\"version\":\"TRIP-structured-read.1\",\"request_id\":\"\(trace)\",\"trip\":{\"trip_id\":\"\(id)\",\"version\":\(version),\"content_sha256\":\"\(fixture.sha256)\",\"content\":\(content)}}".utf8)
    }
    private func client(_ h: Harness, _ wire: StructuredReadWire, credentials: TripCredentialCallback? = nil) -> TripClient {
        TripClient(endpoint: h.endpoint, credentials: credentials ?? { _ in "synthetic-test-token" },
            currentBinding: { h.current }, interceptedTransport: wire)
    }
    @Test func acceptedSourceIsOpaqueAndBelongsToOneClientAndRead() async throws {
        let h = try Harness(); defer { h.clean() }
        let data = try detail(), wire = StructuredReadWire { _, _ in data }
        let owner = client(h, wire), other = client(h, wire)
        let request = try owner.prepareStructuredDetail(id: "trip1", binding: h.binding)
        let value = try await owner.structuredDetail(for: request), source = try #require(value)
        #expect(Mirror(reflecting: source).children.isEmpty)
        #expect(try owner.withCurrentStructuredSnapshot(source) { _, record, _, _ in record.version } == 2)
        #expect(throws: TripFailure.staleBinding) { try other.validateStructuredSnapshot(source) }
        #expect(throws: TripFailure.staleBinding) { try owner.withCurrentStructuredSnapshot(source) { _, _, _, _ in owner.invalidate() } }
        #expect(await wire.calls.count == 1)
    }
    @Test func newerObservationDoesNotReplaceTheEditorsOriginalBasis() async throws {
        let h = try Harness(); defer { h.clean() }
        let second = try detail(3)
        actor ReplyIndex { var n = 0; func next() -> Int { n += 1; return n } }
        let index = ReplyIndex(), first = try detail(2)
        let wire = StructuredReadWire { _, _ in await index.next() == 1 ? first : second }
        let owner = client(h, wire), request = try owner.prepareStructuredDetail(id: "trip1", binding: h.binding)
        let value = try await owner.structuredDetail(for: request), source = try #require(value)
        #expect(try await owner.readCurrentStructuredRecord(for: source)?.version == 3)
        #expect(try owner.withCurrentStructuredSnapshot(source) { _, record, _, _ in record.version } == 2)
        _ = try owner.prepareStructuredDetail(id: "trip1", binding: h.binding)
        #expect(throws: TripFailure.staleBinding) { try owner.validateStructuredSnapshot(source) }
    }
    @Test func replacementSelectionDiscardsLatePrivateSource() async throws {
        let h = try Harness(); defer { h.clean() }
        let gate = Gate(), data = try detail()
        let wire = StructuredReadWire { _, _ in await gate.park(); return data }, owner = client(h, wire)
        let old = try owner.prepareStructuredDetail(id: "trip1", binding: h.binding)
        let task = Task { try await owner.structuredDetail(for: old) }
        await gate.waitForEntry()
        _ = try owner.prepareStructuredDetail(id: "trip2", binding: h.binding)
        await gate.release()
        do { _ = try await task.value; Issue.record("late source escaped") }
        catch { #expect(error as? TripFailure == .staleBinding) }
    }
    @Test func changedCredentialsLifetimePreventsAnyRequest() async throws {
        let h = try Harness(); defer { h.clean() }
        let data = try detail(), wire = StructuredReadWire { _, _ in data }
        let owner = client(h, wire, credentials: { _ in h.current = nil; return "synthetic-test-token" })
        let request = try owner.prepareStructuredDetail(id: "trip1", binding: h.binding)
        do { _ = try await owner.structuredDetail(for: request); Issue.record("retired credentials dispatched") }
        catch { #expect(error as? TripFailure == .staleBinding) }
        #expect(await wire.calls.isEmpty)
    }
    @Test func emptyPageCursorProgressesAndCannotSurviveRefresh() async throws {
        let h = try Harness(); defer { h.clean() }
        let first = Data("{\"version\":\"TRIP-structured-read.1\",\"request_id\":\"\(trace)\",\"trips\":[],\"next_after\":\"legacy1\"}".utf8)
        let last = Data("{\"version\":\"TRIP-structured-read.1\",\"request_id\":\"\(trace)\",\"trips\":[],\"next_after\":null}".utf8)
        let wire = StructuredReadWire { request, operation in
            #expect(operation == "listStructuredTripsV1")
            return request.path!.contains("after=legacy1") ? last : first
        }, owner = client(h, wire)
        let request = try owner.prepareStructuredPage(limit: 1, binding: h.binding)
        let page = try await owner.structuredPage(for: request), cursor = try #require(page.next)
        #expect(page.trips.isEmpty)
        let next = try owner.prepareStructuredPage(limit: 1, after: cursor, binding: h.binding)
        #expect(try await owner.structuredPage(for: next).next == nil)
        _ = try owner.prepareStructuredPage(limit: 1, binding: h.binding)
        #expect(throws: TripFailure.staleBinding) { try owner.prepareStructuredPage(limit: 1, after: cursor, binding: h.binding) }
    }
    @Test func pageRefreshRetiresAlreadyQueuedWorkAndMissingNoStoreIsRefused() async throws {
        let h = try Harness(); defer { h.clean() }
        let empty = Data("{\"version\":\"TRIP-structured-read.1\",\"request_id\":\"\(trace)\",\"trips\":[],\"next_after\":null}".utf8)
        let wire = StructuredReadWire { _, _ in empty }, owner = client(h, wire)
        let old = try owner.prepareStructuredPage(limit: 20, binding: h.binding)
        _ = try owner.prepareStructuredPage(limit: 20, binding: h.binding)
        do { _ = try await owner.structuredPage(for: old); Issue.record("stale page sent") }
        catch { #expect(error as? TripFailure == .staleBinding) }
        #expect(await wire.calls.isEmpty)
        let unsafe = StructuredReadWire(noStore: false) { _, _ in empty }, reader = client(h, unsafe)
        let request = try reader.prepareStructuredPage(limit: 20, binding: h.binding)
        do { _ = try await reader.structuredPage(for: request); Issue.record("cacheable private bytes accepted") }
        catch { #expect(error as? TripFailure == .invalidResponse) }
    }
}
