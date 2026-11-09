import Foundation
import HTTPTypes
import OpenAPIRuntime
import Testing
import CJMessageClient
@testable import CJMessageHTTP

@MainActor private final class EventFixtureStorage: SecureMessageStorage {
    func load(scope: StorageScope) throws -> Snapshot? { nil }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws {}
}

@MainActor private final class EventFixtureCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "fixture-only" }
}

private struct DialogueEventChunks: AsyncSequence, Sendable {
    typealias Element = ArraySlice<UInt8>
    let beforeSecond: @Sendable () async -> Void

    struct AsyncIterator: AsyncIteratorProtocol {
        var index = 0
        let beforeSecond: @Sendable () async -> Void

        mutating func next() async -> Element? {
            index += 1
            if index == 1 { return Array("id: 13\n".utf8)[...] }
            if index == 2 {
                await beforeSecond()
                return Array("data: fixture\n\n".utf8)[...]
            }
            return nil
        }
    }

    func makeAsyncIterator() -> AsyncIterator { .init(beforeSecond: beforeSecond) }
}

private actor DialogueEventFixture: ClientTransport {
    private(set) var paths: [String] = []
    private(set) var cursors: [String] = []
    let beforeSecond: @Sendable () async -> Void
    let needsResync: Bool

    init(needsResync: Bool = false, beforeSecond: @escaping @Sendable () async -> Void = {}) {
        self.beforeSecond = beforeSecond
        self.needsResync = needsResync
    }

    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        guard let path = request.path, body == nil, operationID == DemoDialogueRoute.eventStream else {
            throw MessageHTTPFailure.invalidConfiguration
        }
        paths.append(path)
        cursors.append(request.headerFields[HTTPField.Name("Last-Event-ID")!] ?? "")
        var response = HTTPResponse(status: .init(code: needsResync ? 409 : 200))
        response.headerFields[HTTPField.Name("X-Request-ID")!] = "11111111-1111-4111-8111-111111111111"
        if needsResync {
            response.headerFields[.contentType] = "application/json"
            let raw = #"{"request_id":"11111111-1111-4111-8111-111111111111","error":{"code":"RESYNC_REQUIRED","outcome":"failed","recovery":"retry_safe_read"}}"#
            return (response, HTTPBody(raw.utf8))
        }
        response.headerFields[.contentType] = "text/event-stream"
        response.headerFields[.cacheControl] = "no-store"
        return (response, HTTPBody(DialogueEventChunks(beforeSecond: beforeSecond), length: .unknown, iterationBehavior: .single))
    }
}

@MainActor struct DemoDialogueEventsClientTests {
    @Test func unknownCursorDoesNotConsumeAnEventOrResendAutomatically() async throws {
        let recovery = MessageRecovery(storage: EventFixtureStorage())
        let scope = try StorageScope(environment: UUID().uuidString, account: "one")
        let lease = try recovery.activate(scope)
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://api-beta.go2china.space")),
                                           maximumRequestBytes: 16_384, maximumResponseBytes: 65_536)
        let fixture = DialogueEventFixture(needsResync: true)
        let client = DemoDialogueEventsClient(recovery: recovery, scope: scope, endpoint: endpoint,
            credentials: EventFixtureCredentials(),
            transport: NoRedirectTransport(interceptedTransport: fixture, demoDialogueEndpoint: endpoint, validateDemoDialogue: {}),
            validateSession: {})
        await #expect(throws: DemoDialogueEventsFailure.resyncRequired) {
            try await client.read(messageID: "original", after: "999", lease: lease) { _ in
                Issue.record("A resync error must not be emitted as an event")
            }
        }
        #expect(await fixture.paths == ["/v1/demo-dialogue/events?message_id=original"])
        #expect(await fixture.cursors == ["999"])
    }

    @Test(arguments: [false, true])
    func exactReadCursorAndEveryChunkRespectTheLease(stale: Bool) async throws {
        let recovery = MessageRecovery(storage: EventFixtureStorage())
        let scope = try StorageScope(environment: UUID().uuidString, account: "one")
        let lease = try recovery.activate(scope)
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://api-beta.go2china.space")),
                                           maximumRequestBytes: 16_384, maximumResponseBytes: 65_536)
        let fixture = DialogueEventFixture(beforeSecond: {
            if stale { await MainActor.run { recovery.invalidate() } }
        })
        let client = DemoDialogueEventsClient(recovery: recovery, scope: scope, endpoint: endpoint,
            credentials: EventFixtureCredentials(),
            transport: NoRedirectTransport(interceptedTransport: fixture, demoDialogueEndpoint: endpoint, validateDemoDialogue: {}),
            validateSession: {})
        var observed = Data()
        if stale {
            await #expect(throws: RecoveryError.inactive) {
                try await client.read(messageID: "one+two", after: "12", lease: lease) { observed.append($0) }
            }
            #expect(observed == Data("id: 13\n".utf8))
        } else {
            await #expect(throws: MessageHTTPFailure.invalidConfiguration) {
                try await client.read(messageID: "one+two", after: "012", lease: lease) { observed.append($0) }
            }
            try await client.read(messageID: "one+two", after: "12", lease: lease) { observed.append($0) }
            #expect(observed == Data("id: 13\ndata: fixture\n\n".utf8))
        }
        #expect(await fixture.paths == ["/v1/demo-dialogue/events?message_id=one%2Btwo"])
        #expect(await fixture.cursors == ["12"])
    }
}
