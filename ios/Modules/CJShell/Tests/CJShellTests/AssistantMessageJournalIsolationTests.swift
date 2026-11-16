import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
import CJMessageClient
import CJMessageHTTP
@testable import CJShell

@MainActor private final class JournalIsolationStore: SecureMessageStorage {
    var snapshot: Snapshot?
    func load(scope: StorageScope) throws -> Snapshot? { snapshot }
    func save(_ value: Snapshot, scope: StorageScope) throws { snapshot = value }
}
@MainActor private final class JournalIsolationCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "synthetic-only" }
}
@MainActor private final class JournalIsolationLifetime { var active = true }
private actor JournalIsolationServer: ClientTransport {
    var calls = 0
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        calls += 1
        #expect(request.method == .get)
        let trace = UUID().uuidString
        var response = HTTPResponse(status: .ok)
        response.headerFields[.contentType] = "application/json"
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        let bytes = try JSONSerialization.data(withJSONObject: ["request_id": trace, "receipt": NSNull(),
            "head": ["conversation_id": "synthetic-legacy-chat", "generation": "g1", "last_sequence": 0]])
        return (response, HTTPBody(bytes))
    }
}
@MainActor struct AssistantMessageJournalIsolationTests {
    @Test(arguments: [LioTimelineWire.Version.v2, .v3, .v4])
    func unresolvedLioFirstSendDoesNotRetireSharedClientWhenLegacyConversationIsSelected(version: LioTimelineWire.Version) async throws {
        let store = JournalIsolationStore()
        let recovery = MessageRecovery(storage: store)
        let scope = try StorageScope(environment: UUID().uuidString, account: "journal-synthetic")
        let lease = try recovery.activate(scope)
        let original = try LioTimelineWire.Send(messageID: UUID().uuidString, text: "Synthetic journal question", locale: .english,
                                                destination: .newChat, version: version)
        try recovery.stage(messageID: original.messageID, originalUTF8: original.originalUTF8, lease: lease)
        let submission = try recovery.beginSubmission(messageID: original.messageID, lease: lease)
        try recovery.observeUnknown(submission.operation)
        let before = try #require(try recovery.action(messageID: original.messageID, lease: lease))
        #expect(before.phase == .queryRequired)
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")),
                                           maximumRequestBytes: 16384, maximumResponseBytes: 1000000)
        let server = JournalIsolationServer()
        let client = MessageHTTPClient(recovery: recovery, scope: scope, endpoint: endpoint,
                                        credentials: JournalIsolationCredentials(), interceptedTestTransport: server)
        let shell = ShellState(preferences: try #require(UserDefaults(suiteName: "journal-isolation-" + UUID().uuidString)))
        let lifetime = JournalIsolationLifetime()
        let host = AssistantMessageHost(shell: shell)
        #expect(host.bind(.init(recovery: recovery, scope: scope, lease: lease, generation: shell.generation,
                               synthetic: true, isCurrent: { lifetime.active },
                               invalidateResources: { lifetime.active = false }, sendClient: client)))
        let projection = try #require(host.visibleProjection)
        let lioReference = try #require(projection.actions.first { $0.messageID == original.messageID })
        #expect(!host.selectAction(lioReference, from: projection))
        #expect(host.visibleRecord == nil && host.isConfigured && lifetime.active)
        #expect(host.selectConversationForSending("synthetic-legacy-chat"))
        #expect(host.isConfigured && lifetime.active)
        try recovery.validateScope(scope, lease: lease)
        for _ in 0..<2000 { if !host.isBusy { break }; await Task.yield() }
        #expect(!host.isBusy && host.selectedConversation == "synthetic-legacy-chat")
        let retained = try #require(try recovery.action(messageID: original.messageID, lease: lease))
        #expect(retained.originalUTF8 == before.originalUTF8 && retained.phase == .queryRequired)
        #expect(host.visibleRecord == nil)
        // Reopening keeps the same unknown original; isolation never clears or resends it.
        #expect(store.snapshot != nil)
        let reopened = MessageRecovery(storage: store)
        let reopenedLease = try reopened.activate(scope)
        let after = try #require(try reopened.action(messageID: original.messageID, lease: reopenedLease))
        #expect(after.originalUTF8 == before.originalUTF8 && after.phase == .queryRequired)
    }
}
