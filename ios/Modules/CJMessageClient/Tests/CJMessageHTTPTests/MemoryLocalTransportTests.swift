import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
import CJAPI
@testable import CJMessageHTTP

private actor MemoryExitSpy: ClientTransport {
    var calls = 0
    var bodies: [Data] = []
    let status: HTTPResponse.Status
    let after: @Sendable () async -> Void
    init(status: HTTPResponse.Status = .ok, after: @escaping @Sendable () async -> Void = {}) {
        self.status = status; self.after = after
    }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        calls += 1
        if let body { bodies.append(try await Data(collecting: body, upTo: 1000)) }
        await after()
        return (HTTPResponse(status: status), HTTPBody("{}".utf8))
    }
}
@MainActor private final class MemoryExitLease {
    var active = true
    func validate() throws { if !active { throw MessageHTTPFailure.credentialsUnavailable } }
}
@Suite @MainActor struct MemoryLocalTransportTests {
    func endpoint() throws -> MessageEndpoint {
        try MessageEndpoint(url: #require(URL(string: "http://127.0.0.1:9000")), maximumRequestBytes: 32,
                            maximumResponseBytes: 32, allowLoopbackHTTP: true)
    }
    func request(path: String = "/v1/memories") -> HTTPRequest {
        var result = HTTPRequest(method: .post, scheme: nil, authority: nil, path: path)
        result.headerFields[.contentType] = "application/octet-stream"
        return result
    }
    @Test func defaultRejectsManualPostAndMacFactoryCannotActivate() async throws {
        let spy = MemoryExitSpy(), endpoint = try endpoint()
        let transport = try NoRedirectTransport(interceptedTransport: spy, previewEndpoint: nil, validatePreview: nil)
        await #expect(throws: (any Error).self) {
            _ = try await transport.send(request(), body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: Operations.saveMemory.id)
        }
        #expect(await spy.calls == 0)
        #if !os(iOS)
        #expect(throws: (any Error).self) {
            try NoRedirectTransport.developmentMemory(endpoint: endpoint, requestTimeout: 1, resourceTimeout: 1, validate: {})
        }
        #endif
    }
    @Test func exactWireOnlyPreservesBytesAndDoesNotGrantOtherWrites() async throws {
        let spy = MemoryExitSpy(), lease = MemoryExitLease(), endpoint = try endpoint()
        let transport = NoRedirectTransport(interceptedTransport: spy, memoryEndpoint: endpoint, validateMemory: { try lease.validate() })
        let bytes = Data(" {\"x\":\"e\u{301}\"}\n".utf8)
        _ = try await transport.send(request(), body: HTTPBody(bytes), baseURL: endpoint.url, operationID: Operations.saveMemory.id)
        #expect(await spy.bodies == [bytes])
        for (path, operation) in [("/v1/messages", Operations.receiveMessage.id),
                                  ("/v1/memory-management-actions", "applyMemoryManagementAction"),
                                  ("/v1/memories?owner=other", Operations.saveMemory.id),
                                  ("/v1/memories", "receiveMessage")] {
            await #expect(throws: (any Error).self) {
                _ = try await transport.send(request(path: path), body: HTTPBody(bytes), baseURL: endpoint.url, operationID: operation)
            }
        }
        #expect(await spy.calls == 1)
    }
    @Test func staleBeforeOrAfterDispatchWithholdsAndBoundsStayClosed() async throws {
        let endpoint = try endpoint(), lease = MemoryExitLease()
        let spy = MemoryExitSpy(after: { await MainActor.run { lease.active = false } })
        let transport = NoRedirectTransport(interceptedTransport: spy, memoryEndpoint: endpoint, validateMemory: { try lease.validate() })
        await #expect(throws: (any Error).self) {
            _ = try await transport.send(request(), body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: Operations.saveMemory.id)
        }
        #expect(await spy.calls == 1)
        await #expect(throws: (any Error).self) {
            _ = try await transport.send(request(), body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: Operations.saveMemory.id)
        }
        #expect(await spy.calls == 1)
        lease.active = true
        await #expect(throws: (any Error).self) {
            _ = try await transport.send(request(), body: HTTPBody(Data(repeating: 1, count: 33)), baseURL: endpoint.url, operationID: Operations.saveMemory.id)
        }
        #expect(await spy.calls == 1)
    }
}

extension MemoryLocalTransportTests {
    @Test func defaultRejectsEveryLifecyclePostAndNonSimulatorFactory() async throws {
        let spy = MemoryExitSpy(), endpoint = try endpoint()
        let transport = try NoRedirectTransport(interceptedTransport: spy, previewEndpoint: nil, validatePreview: nil)
        for (path, operation) in [("/v1/memory-management-actions", Operations.applyMemoryManagementAction.id),
                                  ("/v1/memory-edit-actions", Operations.applyMemoryEditAction.id),
                                  ("/v1/memory-withdrawal-actions", Operations.applyMemoryStopUseAction.id)] {
            await #expect(throws: (any Error).self) {
                _ = try await transport.send(request(path: path), body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: operation)
            }
        }
        #expect(await spy.calls == 0)
        #if !os(iOS)
        #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
            try NoRedirectTransport.developmentMemoryManagement(endpoint: endpoint, requestTimeout: 1, resourceTimeout: 1, validate: {})
        }
        #endif
    }
    @Test func lifecycleCapabilityIsExactAndDoesNotGrantManualOrMessageSending() async throws {
        let spy = MemoryExitSpy(), lease = MemoryExitLease(), endpoint = try endpoint()
        let transport = NoRedirectTransport(interceptedTransport: spy, memoryManagementEndpoint: endpoint, validateManagement: { try lease.validate() })
        let original = Data(" {\"x\":\"e\u{301}\"}\n".utf8)
        for (path, operation) in [("/v1/memory-management-actions", Operations.applyMemoryManagementAction.id),
                                  ("/v1/memory-edit-actions", Operations.applyMemoryEditAction.id),
                                  ("/v1/memory-withdrawal-actions", Operations.applyMemoryStopUseAction.id)] {
            _ = try await transport.send(request(path: path), body: HTTPBody(original), baseURL: endpoint.url, operationID: operation)
        }
        #expect(await spy.bodies == [original, original, original])
        for (path, operation) in [("/v1/memories", Operations.saveMemory.id), ("/v1/messages", Operations.receiveMessage.id),
                                  ("/v1/trip-manual-previews", Operations.previewManualTripEdit.id),
                                  ("/v1/memory-edit-actions?owner=other", Operations.applyMemoryEditAction.id),
                                  ("/v1/memory-management-actions", Operations.applyMemoryEditAction.id)] {
            await #expect(throws: (any Error).self) {
                _ = try await transport.send(request(path: path), body: HTTPBody(original), baseURL: endpoint.url, operationID: operation)
            }
        }
        #expect(await spy.calls == 3)
    }
    @Test func staleLifecycleLeaseWithholdsBeforeAndAfterActualDispatch() async throws {
        let endpoint = try endpoint(), lease = MemoryExitLease()
        let spy = MemoryExitSpy(after: { await MainActor.run { lease.active = false } })
        let transport = NoRedirectTransport(interceptedTransport: spy, memoryManagementEndpoint: endpoint, validateManagement: { try lease.validate() })
        await #expect(throws: MessageHTTPFailure.credentialsUnavailable) {
            _ = try await transport.send(request(path: "/v1/memory-edit-actions"), body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: Operations.applyMemoryEditAction.id)
        }
        #expect(await spy.calls == 1)
        await #expect(throws: MessageHTTPFailure.credentialsUnavailable) {
            _ = try await transport.send(request(path: "/v1/memory-withdrawal-actions"), body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: Operations.applyMemoryStopUseAction.id)
        }
        #expect(await spy.calls == 1)
    }
    @Test func lifecycleHostAuthorityMediaAndBodyBoundsRemainClosed() async throws {
        let endpoint = try endpoint(), spy = MemoryExitSpy()
        let transport = NoRedirectTransport(interceptedTransport: spy, memoryManagementEndpoint: endpoint, validateManagement: {})
        var wrongMedia = request(path: "/v1/memory-edit-actions"); wrongMedia.headerFields[.contentType] = "application/json"
        var host = request(path: "/v1/memory-edit-actions"); host.headerFields[HTTPField.Name("Host")!] = "other.invalid"
        let authority = HTTPRequest(method: .post, scheme: "http", authority: "other.invalid", path: "/v1/memory-edit-actions")
        for req in [wrongMedia, host, authority] {
            await #expect(throws: (any Error).self) { _ = try await transport.send(req, body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: Operations.applyMemoryEditAction.id) }
        }
        await #expect(throws: (any Error).self) {
            _ = try await transport.send(request(path: "/v1/memory-edit-actions"), body: HTTPBody(Data(repeating: 1, count: 33)), baseURL: endpoint.url, operationID: Operations.applyMemoryEditAction.id)
        }
        #expect(await spy.calls == 0)
    }
}

extension MemoryLocalTransportTests {
    @Test func typedMemoryOnlyGrantsItsThreeExactFrozenWrites() async throws {
        let spy = MemoryExitSpy(),endpoint = try endpoint(),lease = MemoryExitLease()
        let typed = NoRedirectTransport(interceptedTransport:spy,typedMemoryEndpoint:endpoint,validateTypedMemory:{ try lease.validate() })
        let raw = Data(" {\"original\":\"unchanged\"}\n".utf8)
        let allowed = [("/v2/memories",Operations.saveTypedMemory.id),
            ("/v2/memory-management-actions",Operations.applyTypedMemoryManagement.id),
            ("/v2/memory-withdrawal-actions",Operations.applyTypedMemoryStopUse.id)]
        for (path,operation) in allowed {
            _ = try await typed.send(request(path:path),body:HTTPBody(raw),baseURL:endpoint.url,operationID:operation)
            await #expect(throws:(any Error).self) { _ = try await typed.send(request(path:path + "?owner=x"),body:HTTPBody(raw),baseURL:endpoint.url,operationID:operation) }
        }
        #expect(await spy.bodies == [raw,raw,raw])
        let legacy = NoRedirectTransport(interceptedTransport:spy,memoryEndpoint:endpoint,validateMemory:{})
        for (path,operation) in allowed {
            await #expect(throws:(any Error).self) { _ = try await legacy.send(request(path:path),body:HTTPBody(raw),baseURL:endpoint.url,operationID:operation) }
        }
        for (path,operation) in [("/v1/memories",Operations.saveMemory.id),("/v1/memory-management-actions",Operations.applyMemoryManagementAction.id),
                                 ("/v2/messages",Operations.receiveMessageV2.id),("/v1/travel-context-actions",Operations.applyTravelContextAction.id)] {
            await #expect(throws:(any Error).self) { _ = try await typed.send(request(path:path),body:HTTPBody(raw),baseURL:endpoint.url,operationID:operation) }
        }
        lease.active = false
        await #expect(throws:(any Error).self) { _ = try await typed.send(request(path:"/v2/memories"),body:HTTPBody(raw),baseURL:endpoint.url,operationID:Operations.saveTypedMemory.id) }
        #expect(await spy.bodies == [raw,raw,raw])
        #if !os(iOS)
        #expect(throws:MessageHTTPFailure.productionActivationUnavailable) { try NoRedirectTransport.developmentTypedMemory(endpoint:endpoint,requestTimeout:1,resourceTimeout:1,validate:{}) }
        #endif
    }
}
