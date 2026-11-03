import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
@testable import CJMessageHTTP

@MainActor private final class CurrentDeviceLease {
    var active = true
    func validate() throws { guard active else { throw MessageHTTPFailure.credentialsUnavailable } }
}
private struct CurrentDeviceBody: AsyncSequence, Sendable {
    typealias Element = ArraySlice<UInt8>
    let callback: @Sendable () async -> Void
    struct AsyncIterator: AsyncIteratorProtocol {
        let callback: @Sendable () async -> Void
        var sent = false
        mutating func next() async throws -> ArraySlice<UInt8>? {
            guard !sent else { return nil };sent=true;await callback();return Array("{}".utf8)[...]
        }
    }
    func makeAsyncIterator() -> AsyncIterator { .init(callback:callback) }
}
private actor CurrentDeviceSpy: ClientTransport {
    var requests: [(String,String,Data?)] = []
    let after: @Sendable () async -> Void
    let body: @Sendable () async -> Void
    init(after: @escaping @Sendable () async -> Void = {}, body: @escaping @Sendable () async -> Void = {}) { self.after=after;self.body=body }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes: Data?
        if let body { bytes = try await Data(collecting:body,upTo:16384) } else { bytes=nil }
        requests.append((request.path!,operationID,bytes));await after()
        return (HTTPResponse(status:.ok),HTTPBody(CurrentDeviceBody(callback:self.body),length:.unknown,iterationBehavior:.single))
    }
}
@MainActor struct DeviceCurrentTransportTests {
    func endpoint() throws -> MessageEndpoint {
        try MessageEndpoint(url:URL(string:"http://127.0.0.1:1234")!,maximumRequestBytes:16384,maximumResponseBytes:65536,allowLoopbackHTTP:true)
    }
    func request(_ path: String, post: Bool = false) -> HTTPRequest {
        var r=HTTPRequest(method:post ? .post : .get,scheme:nil,authority:nil,path:path)
        if post { r.headerFields[.contentType]="application/octet-stream" };return r
    }
    @Test func currentSixExitsPreserveExactBytesAndRejectOtherVersionsAndPurposes() async throws {
        let endpoint=try endpoint(),spy=CurrentDeviceSpy()
        let transport=NoRedirectTransport(interceptedTransport:spy,deviceCleanupEndpoint:endpoint,validateDeviceCleanup:{},version:.v4)
        let hash=String(repeating:"a",count:64),raw=Data(" {\"version\":\"CLEANUP-DEVICE@4\"}\n".utf8)
        let accepted=[("/v4/cleanup-devices","registerCleanupDeviceV4",true),
            ("/v4/cleanup-device-registrations?action_id=original&input_sha256="+hash,"queryCleanupDeviceRegistrationV4",false),
            ("/v4/cleanup-device-calls","createCleanupDeviceCallV4",true),
            ("/v4/cleanup-device-call-actions?action_id=original&input_sha256="+hash,"queryCleanupDeviceCallActionV4",false),
            ("/v4/cleanup-device-calls/original","queryCleanupDeviceInvocationV4",false),
            ("/v4/cleanup-device-receipts","reportCleanupDeviceReceiptV4",true)]
        for (path,operation,post) in accepted {
            _ = try await transport.send(request(path,post:post),body:post ? HTTPBody(raw) : nil,baseURL:endpoint.url,operationID:operation)
        }
        #expect(await spy.requests.count == 6)
        #expect(await spy.requests.compactMap(\.2) == [raw,raw,raw])
        let denied=[("/v3/cleanup-device-calls","createCleanupDeviceCallV3",true),
            ("/v4/cleanup-devices?owner=other","registerCleanupDeviceV4",true),
            ("/v1/memory-erasures","eraseMemoryV1",true),
            ("/v3/memory-candidate-actions","applyMemoryCandidateActionV1",true),
            ("/v2/cleanup-device-completions/original?request_digest="+hash,"readCleanupDeviceCompletionV2",false)]
        for (path,operation,post) in denied {
            await #expect(throws:MessageHTTPFailure.productionActivationUnavailable) {
                _ = try await transport.send(request(path,post:post),body:post ? HTTPBody(raw) : nil,baseURL:endpoint.url,operationID:operation)
            }
        }
        #expect(await spy.requests.count == 6)
    }
    @Test func completion2IsReadOnlyAndCannotReadCompletion1OrDeviceControl() async throws {
        let endpoint=try endpoint(),spy=CurrentDeviceSpy()
        let transport=NoRedirectTransport(interceptedTransport:spy,deviceCompletionEndpoint:endpoint,validateDeviceCompletion:{},version:.v4)
        let hash=String(repeating:"a",count:64),path="/v2/cleanup-device-completions/original?request_digest="+hash
        _ = try await transport.send(request(path),body:nil,baseURL:endpoint.url,operationID:"readCleanupDeviceCompletionV2")
        for (url,operation) in [("/v1/cleanup-device-completions/original?request_digest="+hash,"readCleanupDeviceCompletionV1"),
            ("/v4/cleanup-device-calls/original","queryCleanupDeviceInvocationV4"),
            (path+"&owner=other","readCleanupDeviceCompletionV2")] {
            await #expect(throws:MessageHTTPFailure.productionActivationUnavailable) {
                _ = try await transport.send(request(url),body:nil,baseURL:endpoint.url,operationID:operation)
            }
        }
        await #expect(throws:MessageHTTPFailure.productionActivationUnavailable) {
            _ = try await transport.send(request(path),body:HTTPBody("{}".utf8),baseURL:endpoint.url,operationID:"readCleanupDeviceCompletionV2")
        }
        #expect(await spy.requests.count == 1)
    }
    @Test(arguments:["before","response","body"],[false,true])
    func currentExitsRetireAtEveryBoundary(phase: String, completion: Bool) async throws {
        let endpoint=try endpoint(),lease=CurrentDeviceLease()
        let revoke: @Sendable () async -> Void = { await MainActor.run { lease.active=false } }
        let noop: @Sendable () async -> Void = {}
        let spy=CurrentDeviceSpy(after:phase == "response" ? revoke : noop,body:phase == "body" ? revoke : noop)
        let transport=completion
            ? NoRedirectTransport(interceptedTransport:spy,deviceCompletionEndpoint:endpoint,validateDeviceCompletion:{try lease.validate()},version:.v4)
            : NoRedirectTransport(interceptedTransport:spy,deviceCleanupEndpoint:endpoint,validateDeviceCleanup:{try lease.validate()},version:.v4)
        if phase == "before" { lease.active=false }
        let path=completion ? "/v2/cleanup-device-completions/original?request_digest="+String(repeating:"a",count:64) : "/v4/cleanup-device-calls/original"
        await #expect(throws:MessageHTTPFailure.credentialsUnavailable) {
            _ = try await transport.send(request(path),body:nil,baseURL:endpoint.url,operationID:completion ? "readCleanupDeviceCompletionV2" : "queryCleanupDeviceInvocationV4")
        }
        #expect(await spy.requests.count == (phase == "before" ? 0 : 1))
    }
}
