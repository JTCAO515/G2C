import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
@testable import CJMessageHTTP

@MainActor private final class DeviceExitLease {
    var active = true
    func validate() throws { guard active else { throw MessageHTTPFailure.credentialsUnavailable } }
}
private actor DeviceExitSpy: ClientTransport {
    var requests: [(String, Data?)] = []
    let after: @Sendable () async -> Void
    init(after: @escaping @Sendable () async -> Void = {}) { self.after = after }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes: Data?
        if let body { bytes = try await Data(collecting: body, upTo: 1024) } else { bytes = nil }
        requests.append((request.path!, bytes)); await after()
        return (HTTPResponse(status: .ok), HTTPBody("{}".utf8))
    }
}
@MainActor struct DeviceCleanupLocalTransportTests {
    func endpoint() throws -> MessageEndpoint {
        try MessageEndpoint(url: #require(URL(string: "http://127.0.0.1:9000")), maximumRequestBytes: 1024, maximumResponseBytes: 1024, allowLoopbackHTTP: true)
    }
    func request(_ path: String, get: Bool = false) -> HTTPRequest {
        var request = HTTPRequest(method: get ? .get : .post, scheme: nil, authority: nil, path: path)
        if !get { request.headerFields[.contentType] = "application/octet-stream" }
        return request
    }
    @Test func ordinaryAndNonSimulatorDeviceWritersRemainClosed() async throws {
        let spy = DeviceExitSpy(), endpoint = try endpoint()
        let ordinary = try NoRedirectTransport(interceptedTransport: spy, previewEndpoint: nil, validatePreview: nil)
        await #expect(throws: (any Error).self) {
            _ = try await ordinary.send(request("/v3/cleanup-devices"), body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: "registerCleanupDeviceV3")
        }
        #expect(await spy.requests.isEmpty)
        #if !DEBUG || !targetEnvironment(simulator)
        #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
            try NoRedirectTransport.developmentDeviceCleanup(endpoint: endpoint, requestTimeout: 1, resourceTimeout: 1, validate: {})
        }
        #endif
    }
    @Test func sixExactExitsPreserveOriginalBytesAndRejectOtherVersions() async throws {
        let spy = DeviceExitSpy(), lease = DeviceExitLease(), endpoint = try endpoint()
        let transport = NoRedirectTransport(interceptedTransport: spy, deviceCleanupEndpoint: endpoint, validateDeviceCleanup: { try lease.validate() })
        let original = Data(" {\"version\":\"CLEANUP-DEVICE@3\"}\n".utf8)
        for (path, operation) in [("/v3/cleanup-devices","registerCleanupDeviceV3"), ("/v3/cleanup-device-calls","createCleanupDeviceCallV3"), ("/v3/cleanup-device-receipts","reportCleanupDeviceReceiptV3")] {
            _ = try await transport.send(request(path), body: HTTPBody(original), baseURL: endpoint.url, operationID: operation)
        }
        let hash = String(repeating: "a", count: 64)
        for (path, operation) in [("/v3/cleanup-device-registrations?action_id=original&input_sha256="+hash,"queryCleanupDeviceRegistrationV3"),
            ("/v3/cleanup-device-call-actions?input_sha256="+hash+"&action_id=original","queryCleanupDeviceCallActionV3"),
            ("/v3/cleanup-device-calls/original-invocation","queryCleanupDeviceInvocationV3")] {
            _ = try await transport.send(request(path, get: true), body: nil, baseURL: endpoint.url, operationID: operation)
        }
        #expect(await spy.requests.compactMap(\.1) == [original, original, original])
        for (path, operation) in [("/v1/cleanup-devices","registerCleanupDeviceV3"), ("/v2/cleanup-device-calls","createCleanupDeviceCallV3"),
            ("/v1/account-cleanup-operations","registerCleanupDeviceV3"), ("/v1/messages","reportCleanupDeviceReceiptV3"),
            ("/v3/cleanup-device-calls?owner=other","createCleanupDeviceCallV3")] {
            await #expect(throws: (any Error).self) {
                _ = try await transport.send(request(path), body: HTTPBody(original), baseURL: endpoint.url, operationID: operation)
            }
        }
        #expect(await spy.requests.count == 6)
    }
    @Test(arguments: ["registration","action","invocation"])
    func readonlyOriginalExitRechecksLiveLeaseAndWithholdsLateResponse(kind: String) async throws {
        let lease = DeviceExitLease(), endpoint = try endpoint()
        let spy = DeviceExitSpy(after: { await MainActor.run { lease.active = false } })
        let transport = NoRedirectTransport(interceptedTransport: spy, deviceCleanupEndpoint: endpoint, validateDeviceCleanup: { try lease.validate() })
        let hash = String(repeating: "a", count: 64)
        let path: String, operation: String
        switch kind {
        case "registration": path = "/v3/cleanup-device-registrations?action_id=original&input_sha256="+hash; operation = "queryCleanupDeviceRegistrationV3"
        case "action": path = "/v3/cleanup-device-call-actions?action_id=original&input_sha256="+hash; operation = "queryCleanupDeviceCallActionV3"
        default: path = "/v3/cleanup-device-calls/original"; operation = "queryCleanupDeviceInvocationV3"
        }
        lease.active = false
        await #expect(throws: MessageHTTPFailure.credentialsUnavailable) { _ = try await transport.send(request(path, get: true), body: nil, baseURL: endpoint.url, operationID: operation) }
        #expect(await spy.requests.isEmpty)
        lease.active = true
        await #expect(throws: MessageHTTPFailure.credentialsUnavailable) { _ = try await transport.send(request(path, get: true), body: nil, baseURL: endpoint.url, operationID: operation) }
        #expect(await spy.requests.count == 1)
    }
    @Test func ownerSelectorsWrongHashesAndHostNeverReachLiveExit() async throws {
        let spy = DeviceExitSpy(), endpoint = try endpoint()
        let transport = NoRedirectTransport(interceptedTransport: spy, deviceCleanupEndpoint: endpoint, validateDeviceCleanup: {})
        let hash = String(repeating: "a", count: 64)
        for path in ["/v3/cleanup-device-registrations?action_id=original", "/v3/cleanup-device-registrations?action_id=original&input_sha256=bad",
            "/v3/cleanup-device-registrations?action_id=original&input_sha256="+hash+"&owner=other",
            "/v3/cleanup-device-registrations?action_id=original&action_id=other&input_sha256="+hash] {
            await #expect(throws: (any Error).self) { _ = try await transport.send(request(path, get: true), body: nil, baseURL: endpoint.url, operationID: "queryCleanupDeviceRegistrationV3") }
        }
        var host = request("/v3/cleanup-devices"); host.headerFields[HTTPField.Name("Host")!] = "other.invalid"
        await #expect(throws: (any Error).self) { _ = try await transport.send(host, body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: "registerCleanupDeviceV3") }
        #expect(await spy.requests.isEmpty)
    }
    @Test func identityVerificationOnlyPermitsFreshUnknownReceiptAndChecksLease() async throws {
        let endpoint=try endpoint(),spy=DeviceExitSpy(),lease=DeviceExitLease()
        let transport=NoRedirectTransport(interceptedTransport:spy,deviceCleanupEndpoint:endpoint,validateDeviceCleanup:{try lease.validate()})
        let path="/v1/message-receipts?message_id=cleanup-check-"+UUID().uuidString
        _ = try await transport.send(request(path,get:true),body:nil,baseURL:endpoint.url,operationID:"verifyDeviceCleanupIdentityV3")
        for bad in ["/v1/message-receipts?message_id=existing-business-message",path+"&owner=other",path+"&message_id=other"] {
            await #expect(throws:(any Error).self) {
                _ = try await transport.send(request(bad,get:true),body:nil,baseURL:endpoint.url,operationID:"verifyDeviceCleanupIdentityV3")
            }
        }
        lease.active=false
        await #expect(throws:MessageHTTPFailure.credentialsUnavailable) {
            _ = try await transport.send(request(path,get:true),body:nil,baseURL:endpoint.url,operationID:"verifyDeviceCleanupIdentityV3")
        }
        #expect(await spy.requests.count==1)
    }

}
