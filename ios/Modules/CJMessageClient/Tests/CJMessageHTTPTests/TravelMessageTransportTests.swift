import Foundation
import Testing
import OpenAPIRuntime
import HTTPTypes
import CJAPI
@testable import CJMessageHTTP

private actor TravelExitSpy: ClientTransport {
    var bodies: [Data] = []
    let returned: @Sendable () async -> Void
    init(returned: @escaping @Sendable () async -> Void = {}) { self.returned = returned }
    func send(_ request: HTTPRequest,body: HTTPBody?,baseURL: URL,operationID: String) async throws -> (HTTPResponse,HTTPBody?) {
        if let body { bodies.append(try await Data(collecting:body,upTo:65536)) }
        await returned()
        return (HTTPResponse(status:.ok),HTTPBody("{}".utf8))
    }
}
@MainActor private final class TravelExitLifetime {
    var active = true
    func check() throws { guard active else { throw MessageHTTPFailure.credentialsUnavailable } }
}
@MainActor struct TravelMessageTransportTests {
    private func endpoint() throws -> MessageEndpoint {
        try MessageEndpoint(url:#require(URL(string:"http://127.0.0.1:9062")),maximumRequestBytes:65536,maximumResponseBytes:65536,allowLoopbackHTTP:true)
    }
    private func request(path: String = "/v2/messages") -> HTTPRequest {
        var value = HTTPRequest(method:.post,scheme:nil,authority:nil,path:path)
        value.headerFields[.contentType] = "application/octet-stream"
        return value
    }
    @Test func typedCapabilityKeepsOriginalBytesAndRejectsLegacyEndpoint() async throws {
        let spy = TravelExitSpy();let endpoint = try endpoint()
        let cap = NoRedirectTransport(interceptedTransport:spy,travelMessageEndpoint:endpoint,validateMessage:{})
        let original = OriginalTravelMessageTests().raw()
        _ = try await cap.send(request(),body:HTTPBody(original),baseURL:endpoint.url,operationID:Operations.receiveMessageV2.id)
        #expect(await spy.bodies == [original])
        for (path,operation) in [("/v1/messages",Operations.receiveMessage.id),("/v2/messages",Operations.receiveMessage.id),
                                 ("/v2/messages?owner=x",Operations.receiveMessageV2.id),("/v1/travel-context-actions",Operations.applyTravelContextAction.id),
                                 ("/v2/memories",Operations.saveTypedMemory.id)] {
            await #expect(throws:(any Error).self) { _ = try await cap.send(request(path:path),body:HTTPBody(original),baseURL:endpoint.url,operationID:operation) }
        }
        #expect(await spy.bodies.count == 1)
    }
    @Test func defaultAndLegacyCapabilitiesNeverGainTypedWrites() async throws {
        let spy = TravelExitSpy();let endpoint = try endpoint();let raw = OriginalTravelMessageTests().raw()
        let closed = try NoRedirectTransport(interceptedTransport:spy,previewEndpoint:nil,validatePreview:nil)
        let legacy = try NoRedirectTransport(interceptedTransport:spy,messageEndpoint:endpoint,validateMessage:{})
        for cap in [closed,legacy] {
            await #expect(throws:(any Error).self) { _ = try await cap.send(request(),body:HTTPBody(raw),baseURL:endpoint.url,operationID:Operations.receiveMessageV2.id) }
        }
        #expect(await spy.bodies.isEmpty)
        #if !os(iOS)
        #expect(throws:MessageHTTPFailure.productionActivationUnavailable) {
            try NoRedirectTransport.developmentTravelMessages(endpoint:endpoint,requestTimeout:1,resourceTimeout:1,validate:{})
        }
        #endif
    }
    @Test func invalidTypedOriginalNeverDispatches() async throws {
        let spy = TravelExitSpy();let endpoint = try endpoint()
        let cap = NoRedirectTransport(interceptedTransport:spy,travelMessageEndpoint:endpoint,validateMessage:{})
        let good = String(decoding:OriginalTravelMessageTests().raw(),as:UTF8.self)
        for value in [good.replacingOccurrences(of:",\"travel_context\":null",with:""),good.replacingOccurrences(of:"MESSAGE-send.2",with:"MESSAGE-send.1"),"{}"] {
            await #expect(throws:(any Error).self) { _ = try await cap.send(request(),body:HTTPBody(value.utf8),baseURL:endpoint.url,operationID:Operations.receiveMessageV2.id) }
        }
        #expect(await spy.bodies.isEmpty)
    }
    @Test func invalidationBeforeOrAfterNetworkWithholdsOutput() async throws {
        let lifetime = TravelExitLifetime();let endpoint = try endpoint()
        let spy = TravelExitSpy(returned:{ await MainActor.run { lifetime.active = false } })
        let cap = NoRedirectTransport(interceptedTransport:spy,travelMessageEndpoint:endpoint,validateMessage:{ try lifetime.check() })
        let raw = OriginalTravelMessageTests().raw()
        await #expect(throws:MessageHTTPFailure.credentialsUnavailable) { _ = try await cap.send(request(),body:HTTPBody(raw),baseURL:endpoint.url,operationID:Operations.receiveMessageV2.id) }
        #expect(await spy.bodies == [raw])
        await #expect(throws:MessageHTTPFailure.credentialsUnavailable) { _ = try await cap.send(request(),body:HTTPBody(raw),baseURL:endpoint.url,operationID:Operations.receiveMessageV2.id) }
        #expect(await spy.bodies.count == 1)
    }
}
