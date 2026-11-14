import CJMessageClient
import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
@testable import CJMessageHTTP

@MainActor
struct LioTripHistoryTests {
    @Test func defaultCalendarHistoryWaitsForObservedIdentityAndRejectsAReplacement() async throws {
        let store = UndoFixtureStore()
        let scope = try StorageScope(environment: "synthetic", account: UUID().uuidString)
        let recovery = MessageRecovery(storage: store), lease = try recovery.activate(scope)
        let exit = DefaultCalendarExit(), timeline = try defaultTimeline(scope, lease, recovery, exit)
        let history = LioTripHistoryClient(timeline: timeline, recovery: recovery, scope: scope, lease: lease, version: .v3)
        await #expect(throws: MessageHTTPFailure.exchangeUnknown) { try await history.history() }
        #expect(await exit.paths.isEmpty)
        _ = try await timeline.timeline(version: .v3)
        #expect(try await history.history().current == nil)
        #expect(await exit.paths == ["/v3/lio/timeline", "/v3/lio/trip?conversation_id=\(DefaultCalendarExit.conversation)"])
        await exit.replaceIdentity()
        await #expect(throws: MessageHTTPFailure.invalidResponse) { try await timeline.timeline(version: .v3) }
    }

    @Test func defaultCalendarSendReceiptCanBindBeforeTheFirstReadCompletes() async throws {
        let scope = try StorageScope(environment: "synthetic", account: UUID().uuidString)
        let recovery = MessageRecovery(storage: UndoFixtureStore()), lease = try recovery.activate(scope)
        let exit = DefaultCalendarExit(), timeline = try defaultTimeline(scope, lease, recovery, exit)
        let original = try LioTimelineWire.Send(messageID: "default-first", text: "Plan", locale: .english,
                                               destination: .defaultChat, version: .v3)
        guard case .accepted = try await timeline.submit(original) else { Issue.record("default not accepted"); return }
        let history = LioTripHistoryClient(timeline: timeline, recovery: recovery, scope: scope, lease: lease, version: .v3)
        #expect(try await history.history().current == nil)
        #expect(await exit.paths == ["/v3/lio/messages", "/v3/lio/trip?conversation_id=\(DefaultCalendarExit.conversation)"])
    }

    @Test func upgradedDefaultClientCanOnlyReadTheOldUnknownUndoOriginal() async throws {
        let page = try history(), target = try #require(page.undoTarget)
        let store = UndoFixtureStore()
        let scope = try StorageScope(environment: "synthetic", account: UUID().uuidString)
        let first = MessageRecovery(storage: store), firstLease = try first.activate(scope)
        let originalClient = LioTripHistoryClient(recovery: first, scope: scope, lease: firstLease,
            readHistory: { _ in page }, submit: { _ in throw URLError(.networkConnectionLost) }, readReceipt: { _ in nil })
        #expect(try await originalClient.undo(target) == .pending)
        let next = MessageRecovery(storage: store), nextLease = try next.activate(scope)
        let exit = DefaultCalendarExit(), timeline = try defaultTimeline(scope, nextLease, next, exit)
        let upgraded = LioTripHistoryClient(timeline: timeline, recovery: next, scope: scope, lease: nextLease, version: .v3)
        #expect(try upgraded.hasPendingUndo())
        #expect(try await upgraded.reconcileUndo() == .committed)
        #expect(try !upgraded.hasPendingUndo())
        let paths = await exit.paths
        #expect(paths.count == 1)
        #expect(paths[0].hasPrefix("/v1/lio/trip/undo?"))
        #expect(await exit.posts == 0)
    }

    private func defaultTimeline(_ scope: StorageScope, _ lease: Lease, _ recovery: MessageRecovery,
                                 _ exit: DefaultCalendarExit) throws -> LioTimelineHTTP {
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")),
                                           maximumRequestBytes: 16_384, maximumResponseBytes: 4_500_000)
        let transport = try NoRedirectTransport(interceptedTransport: exit, messageEndpoint: endpoint, validateMessage: {}, lio: true)
        return LioTimelineHTTP(scope: scope, lease: lease, credentials: DefaultCalendarCredentials(),
                               transport: transport, firstChatRecovery: recovery)
    }
    @Test func uncertainUndoSurvivesReactivationAndIsOnlyRead() async throws {
        let page = try history()
        let target = try #require(page.undoTarget)
        let store = UndoFixtureStore()
        let scope = try StorageScope(environment: "synthetic", account: UUID().uuidString)
        let firstRecovery = MessageRecovery(storage: store)
        let firstLease = try firstRecovery.activate(scope)
        var submissions: [Data] = []
        let first = LioTripHistoryClient(recovery: firstRecovery, scope: scope, lease: firstLease,
            readHistory: { _ in page }, submit: { undo in
                submissions.append(undo.originalUTF8)
                throw URLError(.networkConnectionLost)
            }, readReceipt: { _ in nil })

        #expect(try await first.undo(target) == .pending)
        #expect(try first.hasPendingUndo())
        let original = try #require(submissions.first)

        let restoredRecovery = MessageRecovery(storage: store)
        let restoredLease = try restoredRecovery.activate(scope)
        var observed: [Data] = []
        let restored = LioTripHistoryClient(recovery: restoredRecovery, scope: scope, lease: restoredLease,
            readHistory: { _ in page }, submit: { undo in
                submissions.append(undo.originalUTF8)
                throw URLError(.networkConnectionLost)
            }, readReceipt: { undo in
                observed.append(undo.originalUTF8)
                if observed.count == 1 { return nil }
                return Data("""
                    {"version":"LIO-trip-undo-receipt.1","action_id":"\(undo.actionID)","committed":true}
                    """.utf8)
            })

        #expect(try restored.hasPendingUndo())
        #expect(try await restored.undo(target) == .pending)
        #expect(try await restored.reconcileUndo() == .pending)
        #expect(try restored.hasPendingUndo())
        #expect(try await restored.reconcileUndo() == .committed)
        #expect(try !restored.hasPendingUndo())
        #expect(submissions == [original])
        #expect(observed == [original, original])
    }

    @Test func refusesHistoryForMoreThanOneItinerary() throws {
        let data = historyJSON(historyTripID: "trip:other")
        #expect(throws: MessageHTTPFailure.invalidResponse) { try LioTripHistoryWire.decodePage(data) }
    }

    @Test func v2UndoStaysWithItsOriginalConversation() async throws {
        let conversation = "lio-dialogue-0123456789abcdef0123456789abcdef"
        let other = "lio-dialogue-00000000000000000000000000000000"
        let data = Data(String(decoding: historyJSON(historyTripID: "trip:synthetic"), as: UTF8.self)
            .replacingOccurrences(of: "\"LIO-trip-history.1\"", with: "\"LIO-trip-history.2\",\"conversation_id\":\"\(conversation)\"").utf8)
        let page = try LioTripHistoryWire.decodePage(data, conversationID: conversation)
        #expect(throws: MessageHTTPFailure.invalidResponse) { try LioTripHistoryWire.decodePage(data, conversationID: other) }
        let target = try #require(page.undoTarget)
        let scope = try StorageScope(environment: "synthetic", account: UUID().uuidString)
        let recovery = MessageRecovery(storage: UndoFixtureStore())
        let lease = try recovery.activate(scope)
        var written: [Data] = []
        var queried: [Data] = []
        let original = LioTripHistoryClient(recovery: recovery, scope: scope, lease: lease, conversationID: conversation,
            readHistory: { _ in page }, submit: { undo in
                written.append(undo.originalUTF8)
                throw URLError(.networkConnectionLost)
            }, readReceipt: { undo in
                queried.append(undo.originalUTF8)
                let wrong = Data("""
                    {"version":"LIO-trip-undo-receipt.2","action_id":"\(undo.actionID)","conversation_id":"\(other)","committed":true}
                    """.utf8)
                #expect(throws: MessageHTTPFailure.invalidResponse) { try undo.committed(wrong) }
                return Data("""
                    {"version":"LIO-trip-undo-receipt.2","action_id":"\(undo.actionID)","conversation_id":"\(conversation)","committed":true}
                    """.utf8)
            })
        let alternate = LioTripHistoryClient(recovery: recovery, scope: scope, lease: lease, conversationID: other,
            readHistory: { _ in page }, submit: { _ in Issue.record("Wrong conversation submitted"); return .conflict(Data()) },
            readReceipt: { _ in Issue.record("Wrong conversation reconciled"); return nil })

        await #expect(throws: MessageHTTPFailure.invalidConfiguration) { _ = try await alternate.undo(target) }
        #expect(try await original.undo(target) == .pending)
        #expect(try !alternate.hasPendingUndo())
        #expect(try await alternate.reconcileUndo() == nil)
        #expect(try await original.reconcileUndo() == .committed)
        #expect(written.count == 1 && queried == written)
        let bytes = try #require(written.first)
        let payload = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: String])
        #expect(payload["conversation_id"] == conversation && payload["version"] == "LIO-trip-undo.2")
    }

    @Test func aRefusedTargetDoesNotAuthorizeAnAutomaticNewUndo() async throws {
        let page = try history()
        let target = try #require(page.undoTarget)
        let store = UndoFixtureStore()
        let scope = try StorageScope(environment: "synthetic", account: UUID().uuidString)
        let recovery = MessageRecovery(storage: store)
        let lease = try recovery.activate(scope)
        var sends = 0
        let client = LioTripHistoryClient(recovery: recovery, scope: scope, lease: lease,
            readHistory: { _ in page }, submit: { _ in
                sends += 1
                return .conflict(Data(#"{"failure":"unavailable"}"#.utf8))
            }, readReceipt: { _ in Issue.record("A rejected undo needs a fresh trip read, not a receipt"); return nil })

        #expect(try await client.undo(target) == .changed)
        #expect(try !client.hasPendingUndo())
        #expect(try await client.reconcileUndo() == nil)
        #expect(sends == 1)
    }

    private func history() throws -> LioTripHistoryWire.Page {
        try LioTripHistoryWire.decodePage(historyJSON(historyTripID: "trip:synthetic"))
    }

    private func historyJSON(historyTripID: String) -> Data {
        Data("""
            {"version":"LIO-trip-history.1",
             "current":{"trip_id":"trip:synthetic","title":"Current plan","days":[
               {"date":"2026-11-10","items":[{"item_id":"walk","label":"Park walk","start_time":null,"end_time":null,"fixed":null}]}
             ]},
             "history":[{"trip_id":"\(historyTripID)","title":"Previous plan","days":[
               {"date":"2026-11-10","items":[{"item_id":"walk","label":"River walk","start_time":null,"end_time":null,"fixed":null}]}
             ]}],
             "undo_target":"fixture_target","next_before":null}
            """.utf8)
    }
}

@MainActor private final class DefaultCalendarCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "fixture" }
}

private actor DefaultCalendarExit: ClientTransport {
    static let conversation = "lio-dialogue-0123456789abcdef0123456789abcdef"
    private var alternate = false
    private(set) var paths: [String] = []
    private(set) var posts = 0
    func replaceIdentity() { alternate = true }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let path = try #require(request.path)
        paths.append(path)
        let cid = alternate ? "lio-dialogue-00000000000000000000000000000000" : Self.conversation
        let json: String
        if request.method == .post {
            posts += 1
            let bytes = try await Data(collecting: #require(body), upTo: 16_384)
            let input = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
            let id = try #require(input["message_id"] as? String)
            json = "{\"version\":\"LIO-message-receipt.3\",\"message_id\":\"\(id)\",\"conversation_id\":\"\(cid)\"}"
        } else if path.hasPrefix("/v1/lio/trip/undo?") {
            let query = try #require(URLComponents(string: path)?.queryItems)
            let id = try #require(query.first { $0.name == "action_id" }?.value)
            json = "{\"version\":\"LIO-trip-undo-receipt.1\",\"action_id\":\"\(id)\",\"committed\":true}"
        } else if path.hasPrefix("/v3/lio/trip?") {
            json = "{\"version\":\"LIO-trip-history.3\",\"conversation_id\":\"\(cid)\",\"current\":null,\"history\":[],\"undo_target\":null,\"next_before\":null}"
        } else {
            json = "{\"version\":\"LIO-timeline.3\",\"conversation_id\":\"\(cid)\",\"messages\":[],\"next_before\":null}"
        }
        var response = HTTPResponse(status: .ok)
        response.headerFields[.contentType] = "application/json"
        return (response, HTTPBody(json))
    }
}

@MainActor
private final class UndoFixtureStore: SecureMessageStorage {
    private var snapshot: Snapshot?

    func load(scope: StorageScope) throws -> Snapshot? { snapshot }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { self.snapshot = snapshot }
}
