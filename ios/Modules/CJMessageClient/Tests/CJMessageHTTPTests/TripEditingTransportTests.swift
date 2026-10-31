import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
@testable import CJMessageHTTP

private actor TripEditingExit: ClientTransport {
    var requests: [String] = []
    var bodies: [Data] = []
    let after: @Sendable () async -> Void
    init(after: @escaping @Sendable () async -> Void = {}) { self.after = after }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        requests.append(request.path!)
        if let body { bodies.append(try await Data(collecting: body, upTo: 1_000_000)) }
        await after(); return (HTTPResponse(status: .ok), HTTPBody("{}".utf8))
    }
}
@MainActor private final class TripEditingLease {
    var active = true
    func check() throws { guard active else { throw MessageHTTPFailure.credentialsUnavailable } }
}
@MainActor struct TripEditingTransportTests {
    func endpoint(_ bytes: Int = 1_000_000) throws -> MessageEndpoint {
        try MessageEndpoint(url: #require(URL(string: "http://127.0.0.1:9001")), maximumRequestBytes: bytes,
                            maximumResponseBytes: 1_000_000, allowLoopbackHTTP: true)
    }
    func post(_ path: String) -> HTTPRequest {
        var r = HTTPRequest(method: .post, scheme: nil, authority: nil, path: path)
        r.headerFields[.contentType] = "application/octet-stream"; return r
    }
    @Test func exactFrozenRoutesPreserveRawBytesAndDefaultConstructionStaysClosed() async throws {
        let endpoint = try endpoint(), spy = TripEditingExit(), lease = TripEditingLease()
        let ordinary = try NoRedirectTransport(interceptedTransport: spy, previewEndpoint: nil, validatePreview: nil)
        await #expect(throws: (any Error).self) {
            _ = try await ordinary.send(post(LocalTripEditingOperation.prepare.path), body: HTTPBody("{}".utf8), baseURL: endpoint.url,
                                       operationID: LocalTripEditingOperation.prepare.rawValue)
        }
        let transport = NoRedirectTransport(interceptedTransport: spy, tripEditingEndpoint: endpoint, validateTripEditing: { try lease.check() })
        let raw = Data(" {\"original\":\"cafe\u{301}\"}\n".utf8)
        for op in [LocalTripEditingOperation.prepare, .save, .needsPrepare, .needsSave, .initialize, .initializeSave] {
            _ = try await transport.send(post(op.path), body: HTTPBody(raw), baseURL: endpoint.url, operationID: op.rawValue)
        }
        #expect(await spy.bodies == Array(repeating: raw, count: 6))
        for op in [LocalTripEditingOperation.queryPrepare, .queryReceipt, .queryNeedsPrepare, .queryNeedsReceipt, .queryInitialization, .queryInitializationReceipt] {
            let r = HTTPRequest(method: .get, scheme: nil, authority: nil, path: op.path+"?"+op.queryField!+"=original:1")
            _ = try await transport.send(r, body: nil, baseURL: endpoint.url, operationID: op.rawValue)
        }
        #expect(await spy.requests.count == 12)
        #if !DEBUG || !targetEnvironment(simulator)
        #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
            try NoRedirectTransport.developmentTripEditing(endpoint: endpoint, requestTimeout: 1, resourceTimeout: 1, validate: {})
        }
        #endif
    }
    @Test func wrongPurposeHostMediaQueryAndSaveBoundsNeverReachTheUnderlyingExit() async throws {
        let endpoint = try endpoint(), spy = TripEditingExit()
        let transport = NoRedirectTransport(interceptedTransport: spy, tripEditingEndpoint: endpoint, validateTripEditing: {})
        let op = LocalTripEditingOperation.prepare
        for path in ["/v1/messages", op.path+"?owner=x", "/v1/trip-actions"] {
            await #expect(throws: (any Error).self) {
                _ = try await transport.send(post(path), body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: op.rawValue)
            }
        }
        var host = post(op.path); host.headerFields[HTTPField.Name("Host")!] = "other.invalid"
        var authority = post(op.path); authority.authority = "other.invalid"
        var mime = post(op.path); mime.headerFields[.contentType] = "application/json"
        for r in [host, authority, mime] {
            await #expect(throws: (any Error).self) { _ = try await transport.send(r, body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: op.rawValue) }
        }
        let read = LocalTripEditingOperation.queryPrepare
        for path in [read.path+"?request_id=a&request_id=b",read.path+"?owner=a",read.path+"?request_id=a#ignored",
                     "//other.invalid"+read.path+"?request_id=a", "https://other.invalid"+read.path+"?request_id=a"] {
            let r = HTTPRequest(method: .get, scheme: nil, authority: nil, path: path)
            await #expect(throws: (any Error).self) { _ = try await transport.send(r, body: nil, baseURL: endpoint.url, operationID: read.rawValue) }
        }
        await #expect(throws: (any Error).self) {
            let save = LocalTripEditingOperation.save
            _ = try await transport.send(post(save.path), body: HTTPBody(Data(repeating: 1, count: 32769)), baseURL: endpoint.url, operationID: save.rawValue)
        }
        #expect(await spy.requests.isEmpty)
    }
    @Test func lateLifetimeChangesWithholdResultsAndFurtherDispatch() async throws {
        let endpoint = try endpoint(), lease = TripEditingLease()
        let spy = TripEditingExit(after: { await MainActor.run { lease.active = false } })
        let transport = NoRedirectTransport(interceptedTransport: spy, tripEditingEndpoint: endpoint, validateTripEditing: { try lease.check() })
        let op = LocalTripEditingOperation.prepare
        await #expect(throws: (any Error).self) { _ = try await transport.send(post(op.path), body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: op.rawValue) }
        await #expect(throws: (any Error).self) { _ = try await transport.send(post(op.path), body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: op.rawValue) }
        #expect(await spy.requests.count == 1)
    }
}
