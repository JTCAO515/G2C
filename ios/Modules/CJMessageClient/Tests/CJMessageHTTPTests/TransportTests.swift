import Foundation
import CryptoKit
import Testing
import HTTPTypes
import OpenAPIRuntime
import CJMessageClient
@testable import CJMessageHTTP

@MainActor private final class Memory: SecureMessageStorage {
    var value: Snapshot?
    func load(scope: StorageScope) throws -> Snapshot? { value }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { value = snapshot }
}
@MainActor private final class Credentials: MessageCredentialsProvider {
    var token: String? = "synthetic-only"
    var beforeReturn: (() -> Void)?
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { beforeReturn?(); return token }
}
private actor Interceptor: ClientTransport {
    let response: HTTPResponse
    let data: Data
    let beforeReturn: (@Sendable () async -> Void)?
    var sent: [Data] = []
    var contentTypes: [String?] = []
    init(response: HTTPResponse, data: Data, beforeReturn: (@Sendable () async -> Void)? = nil) {
        self.response = response; self.data = data; self.beforeReturn = beforeReturn
    }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        sent.append(try await body.mapAsync { try await Data(collecting: $0, upTo: 10000) } ?? Data())
        contentTypes.append(request.headerFields[.contentType])
        await beforeReturn?()
        return (response, HTTPBody(data))
    }
}
private extension Optional where Wrapped == HTTPBody {
    func mapAsync(_ work: (HTTPBody) async throws -> Data) async rethrows -> Data? {
        switch self { case .some(let value): return try await work(value); case .none: return nil }
    }
}
@Suite @MainActor struct TransportTests {
    let trace = "b8131f98-bbc8-4109-90d6-031199c00a10"
    var raw: Data { Data(" {\"version\":\"MESSAGE-draft.1\",\"message_id\":\"m1\",\"conversation_id\":\"chat\",\"text\":\"你好\",\"trip_id\":null,\"creation_intent\":\"none\"} \n".utf8) }
    func response(_ trace: String? = nil, status: HTTPResponse.Status = .ok) -> HTTPResponse {
        var value = HTTPResponse(status: status)
        value.headerFields[HTTPField.Name("X-Request-ID")!] = trace ?? self.trace
        value.headerFields[.contentType] = "application/json"
        return value
    }
    func body(sequence: Int = 1, conversation: String = "chat") throws -> Data {
        let digest = SHA256.hash(data: raw).map { String(format: "%02x", $0) }.joined()
        return try JSONSerialization.data(withJSONObject: ["request_id": trace, "receipt": [
            "message_id":"m1", "conversation_id": conversation, "generation":"g1", "run_id":"r1",
            "sequence":sequence, "input_sha256":digest]])
    }
    private func setup(_ transport: Interceptor, credentials: Credentials = Credentials()) throws -> (MessageRecovery, Lease, MessageHTTPClient) {
        let state = MessageRecovery(storage: Memory())
        let scope = try StorageScope(environment:"synthetic",account:"a")
        let lease = try state.activate(scope)
        try state.stage(messageID:"m1",originalUTF8:raw,lease:lease)
        let endpoint = try MessageEndpoint(url: #require(URL(string:"https://synthetic.invalid")), maximumRequestBytes:10000, maximumResponseBytes:10000)
        return (state, lease, MessageHTTPClient(recovery:state,scope:scope,endpoint:endpoint,credentials:credentials,interceptedTestTransport:transport))
    }
    @Test func officialClientSendsOriginalOctetsOnce() async throws {
        let interceptor = Interceptor(response:response(),data:try body())
        let (state,lease,client) = try setup(interceptor)
        _ = try await client.submit(messageID:"m1",lease:lease)
        #expect(await interceptor.sent == [raw])
        #expect(await interceptor.contentTypes == ["application/octet-stream"])
        #expect(try state.action(messageID:"m1",lease:lease)?.phase == .accepted)
        await #expect(throws: (any Error).self) { try await client.submit(messageID:"m1",lease:lease) }
        #expect(await interceptor.sent.count == 1)
    }
    @Test func invalidReceiptTraceAndRedirectRemainQueryOnly() async throws {
        var duplicate = response()
        duplicate.headerFields.append(HTTPField(name: HTTPField.Name("X-Request-ID")!, value: trace))
        let cases: [(HTTPResponse,Data)] = [
            (response("b8131f98-bbc8-4109-90d6-031199c00a11"),try body()),
            (duplicate,try body()), (response(),try body(sequence:0)),
            (response(),try body(conversation:"wrong-chat")),
            (response(status:.found),try body()),
            (response(),Data("{\"request_id\":\"\(trace)\",\"request_id\":\"\(trace)\"}".utf8))]
        for (response,data) in cases {
            let transport = Interceptor(response:response,data:data)
            let (state,lease,client) = try setup(transport)
            await #expect(throws: (any Error).self) { try await client.submit(messageID:"m1",lease:lease) }
            #expect(try state.action(messageID:"m1",lease:lease)?.phase == .queryRequired)
            #expect(await transport.sent.count == 1)
        }
    }
    @Test func credentialsAwaitCannotSendAfterSwitch() async throws {
        let transport = Interceptor(response:response(),data:try body())
        let credentials = Credentials()
        let (state,lease,client) = try setup(transport,credentials:credentials)
        credentials.beforeReturn = { state.invalidate() }
        await #expect(throws: (any Error).self) { try await client.submit(messageID:"m1",lease:lease) }
        #expect(await transport.sent.isEmpty)
    }
    @Test func responseAfterSwitchCannotPersist() async throws {
        let state = MessageRecovery(storage:Memory())
        let scope = try StorageScope(environment:"synthetic",account:"a")
        let lease = try state.activate(scope)
        try state.stage(messageID:"m1",originalUTF8:raw,lease:lease)
        let transport = Interceptor(response:response(),data:try body(),beforeReturn:{ await state.invalidate() })
        let client = MessageHTTPClient(recovery:state,scope:scope,endpoint:try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:10000, maximumResponseBytes:10000),credentials:Credentials(),interceptedTestTransport:transport)
        await #expect(throws: (any Error).self) { try await client.submit(messageID:"m1",lease:lease) }
        let next = try state.activate(scope)
        #expect(try state.action(messageID:"m1",lease:next)?.phase == .queryRequired)
    }
    @Test func safeReadErrorNeverRetriesPost() async throws {
        let error = try JSONSerialization.data(withJSONObject: ["request_id":trace,"error":[
            "code":"synthetic","category":"dependency","message_en":"Unknown","message_zh":"未知",
            "outcome":"unknown","recovery":"retry_safe_read"]])
        let transport = Interceptor(response:response(status:.serviceUnavailable),data:error)
        let (state,lease,client) = try setup(transport)
        let result = try await client.submit(messageID:"m1",lease:lease)
        if case .rejected(let status, let body) = result {
            #expect(status == 503); #expect(body.error.recovery == .retry_safe_read)
        } else { Issue.record("expected BASE error") }
        #expect(try state.action(messageID:"m1",lease:lease)?.phase == .queryRequired)
        await #expect(throws: (any Error).self) { try await client.submit(messageID:"m1",lease:lease) }
        #expect(await transport.sent.count == 1)
    }

    @Test func explicitEndpointAndMissingCredentialsRejectBeforeSend() async throws {
        #expect(throws: MessageHTTPFailure.self) { try MessageEndpoint(url:#require(URL(string:"http://example.invalid")),maximumRequestBytes:100,maximumResponseBytes:100) }
        #expect(throws: MessageHTTPFailure.self) { try MessageEndpoint(url:#require(URL(string:"https://user:pass@example.invalid")),maximumRequestBytes:100,maximumResponseBytes:100) }
        let credentials = Credentials(); credentials.token = nil
        let transport = Interceptor(response:response(),data:try body())
        let (state,lease,client) = try setup(transport,credentials:credentials)
        await #expect(throws: MessageHTTPFailure.self) { try await client.submit(messageID:"m1",lease:lease) }
        #expect(await transport.sent.isEmpty)
        #expect(try state.action(messageID:"m1",lease:lease)?.phase == .staged)
    }

    @Test func livePostDisabledEvenIfWholeSnapshotIsMissing() async throws {
        let state = MessageRecovery(storage:Memory())
        let scope = try StorageScope(environment:"synthetic",account:"a")
        let lease = try state.activate(scope)
        try state.stage(messageID:"m1",originalUTF8:raw,lease:lease)
        let credentials = Credentials()
        credentials.beforeReturn = { Issue.record("live POST must reject before fetching credentials") }
        let live = try NoRedirectTransport(requestTimeout:1,resourceTimeout:1)
        let client = MessageHTTPClient(recovery:state,scope:scope,
            endpoint:try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:10000,maximumResponseBytes:10000),
            credentials:credentials,liveReadTransport:live)
        await #expect(throws:MessageHTTPFailure.self) { try await client.submit(messageID:"m1",lease:lease) }
        #expect(try state.action(messageID:"m1",lease:lease)?.phase == .staged)
        await #expect(throws:MessageHTTPFailure.self) {
            try await live.send(HTTPRequest(method:.post,scheme:"https",authority:"synthetic.invalid",path:"/v1/messages"),body:HTTPBody(raw),baseURL:#require(URL(string:"https://synthetic.invalid")),operationID:"receiveMessage")
        }
    }

    @Test func missingGeneratedQueryReceiptFailsExplicitlyWithoutRequest() async throws {
        let transport = Interceptor(response:response(),data:try body())
        let (_,lease,client) = try setup(transport)
        await #expect(throws: MessageHTTPFailure.self) { try await client.query(messageID:"m1",lease:lease) }
        #expect(await transport.sent.isEmpty)
    }
}
