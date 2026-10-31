import Foundation
import Testing
import OpenAPIRuntime
import HTTPTypes
import CJAPI
@testable import CJMessageHTTP

private actor DiscussionExitSpy: ClientTransport {
    var bodies: [Data] = []
    let callback: @Sendable () async -> Void
    init(callback: @escaping @Sendable () async -> Void = {}) { self.callback = callback }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        if let body { bodies.append(try await Data(collecting: body, upTo: 65536)) }
        await callback()
        return (HTTPResponse(status: .ok), HTTPBody("{}".utf8))
    }
}
@MainActor private final class DiscussionLifetime {
    var active = true
    func check() throws { guard active else { throw MessageHTTPFailure.credentialsUnavailable } }
}
@MainActor struct TripDiscussionTransportTests {
    func endpoint(maximum: Int = 65536) throws -> MessageEndpoint {
        try MessageEndpoint(url: #require(URL(string: "http://127.0.0.1:9062")), maximumRequestBytes: maximum, maximumResponseBytes: 65536, allowLoopbackHTTP: true)
    }
    func request(path: String = "/v3/messages", scheme: String? = nil, authority: String? = nil) -> HTTPRequest {
        var request = HTTPRequest(method: .post, scheme: scheme, authority: authority, path: path)
        request.headerFields[.contentType] = "application/octet-stream"
        return request
    }
    @Test func frozenDiscussionCapabilityCannotWriteOtherVersionsOrActions() async throws {
        let spy = DiscussionExitSpy(), endpoint = try endpoint(), raw = try TripDiscussionWireTests().original()
        let cap = NoRedirectTransport(interceptedTransport: spy, tripDiscussionEndpoint: endpoint, validateDiscussion: {})
        _ = try await cap.send(request(), body: HTTPBody(raw), baseURL: endpoint.url, operationID: "receiveTripDiscussionV3")
        let invalid = [("/v1/messages", Operations.receiveMessage.id), ("/v2/messages", Operations.receiveMessageV2.id),
                       ("/v4/messages", "receiveTripDiscussionV3"), ("/v3/messages?owner=x", "receiveTripDiscussionV3"),
                       ("/v3/messages", Operations.receiveMessageV2.id), ("/v1/trip-actions", Operations.actOnTripProposal.id),
                       ("/v2/memories", Operations.saveTypedMemory.id)]
        for (path, operation) in invalid {
            await #expect(throws: (any Error).self) { try await cap.send(request(path: path), body: HTTPBody(raw), baseURL: endpoint.url, operationID: operation) }
        }
        for changed in [request(scheme: "http"), request(authority: "other.invalid")] {
            await #expect(throws: (any Error).self) { try await cap.send(changed, body: HTTPBody(raw), baseURL: endpoint.url, operationID: "receiveTripDiscussionV3") }
        }
        var host = request(); host.headerFields[.init("host")!] = "other.invalid"
        await #expect(throws: (any Error).self) { try await cap.send(host, body: HTTPBody(raw), baseURL: endpoint.url, operationID: "receiveTripDiscussionV3") }
        #expect(await spy.bodies == [raw])
    }
    @Test func oldCapabilitiesRemainClosedToNewDiscussionWire() async throws {
        let spy = DiscussionExitSpy(), endpoint = try endpoint(), raw = try TripDiscussionWireTests().original()
        let closed = try NoRedirectTransport(interceptedTransport: spy, previewEndpoint: nil, validatePreview: nil)
        let legacy = try NoRedirectTransport(interceptedTransport: spy, messageEndpoint: endpoint, validateMessage: {})
        let travel = NoRedirectTransport(interceptedTransport: spy, travelMessageEndpoint: endpoint, validateMessage: {})
        for cap in [closed, legacy, travel] {
            await #expect(throws: (any Error).self) { try await cap.send(request(), body: HTTPBody(raw), baseURL: endpoint.url, operationID: "receiveTripDiscussionV3") }
        }
        #expect(await spy.bodies.isEmpty)
        #if !os(iOS)
        #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
            try NoRedirectTransport.developmentTripDiscussions(endpoint: endpoint, requestTimeout: 1, resourceTimeout: 1, validate: {})
        }
        #endif
    }
    @Test func malformedOrUnboundedOriginalNeverReachesExit() async throws {
        let spy = DiscussionExitSpy(), endpoint = try endpoint(), raw = try TripDiscussionWireTests().original()
        let cap = NoRedirectTransport(interceptedTransport: spy, tripDiscussionEndpoint: endpoint, validateDiscussion: {})
        let short = NoRedirectTransport(interceptedTransport: spy, tripDiscussionEndpoint: try self.endpoint(maximum: raw.count - 1), validateDiscussion: {})
        for bad in [Data("{}".utf8), try TripDiscussionWireTests().original { $0["creation_intent"] = "consider_trip" }, OriginalTravelMessageTests().raw()] {
            await #expect(throws: (any Error).self) { try await cap.send(request(), body: HTTPBody(bad), baseURL: endpoint.url, operationID: "receiveTripDiscussionV3") }
        }
        await #expect(throws: (any Error).self) { try await short.send(request(), body: HTTPBody(raw), baseURL: endpoint.url, operationID: "receiveTripDiscussionV3") }
        var mime = request(); mime.headerFields[.contentType] = "application/json"
        await #expect(throws: (any Error).self) { try await cap.send(mime, body: HTTPBody(raw), baseURL: endpoint.url, operationID: "receiveTripDiscussionV3") }
        #expect(await spy.bodies.isEmpty)
    }
    @Test func identityChangeBeforeOrAfterNetworkWithholdsPrivateOutput() async throws {
        let lifetime = DiscussionLifetime(), endpoint = try endpoint(), raw = try TripDiscussionWireTests().original()
        let spy = DiscussionExitSpy { await MainActor.run { lifetime.active = false } }
        let cap = NoRedirectTransport(interceptedTransport: spy, tripDiscussionEndpoint: endpoint, validateDiscussion: { try lifetime.check() })
        await #expect(throws: MessageHTTPFailure.credentialsUnavailable) { try await cap.send(request(), body: HTTPBody(raw), baseURL: endpoint.url, operationID: "receiveTripDiscussionV3") }
        await #expect(throws: MessageHTTPFailure.credentialsUnavailable) { try await cap.send(request(), body: HTTPBody(raw), baseURL: endpoint.url, operationID: "receiveTripDiscussionV3") }
        #expect(await spy.bodies == [raw])
    }
}
