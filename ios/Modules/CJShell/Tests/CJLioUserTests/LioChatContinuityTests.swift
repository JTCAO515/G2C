import CJMessageClient
@testable import CJMessageHTTP
import CryptoKit
import Foundation
import HTTPTypes
import OpenAPIRuntime
import Testing
@testable import CJLioUser

@MainActor struct LioChatContinuityTests {
    @Test func reauthenticatedClientReturnsToTheSameChatAndDraftWithoutSendingAgain() async throws {
        let fixture = try ChatContinuityFixture()
        let old = try fixture.library()
        let selected = old.newChat()
        let position = try #require(old.continuity)
        position.selectedID = selected.id
        let model = LioConversation(service: selected.service)
        model.send("A synthetic question", language: .english)
        await model.receive(try #require(model.pending))
        position.draft = "My unsent follow-up"
        let renewedPosition = LioChatContinuity()
        renewedPosition.inherit(position)
        let renewed = try fixture.library(continuity: renewedPosition)
        let restored = try #require(try await renewed.restore?())
        #expect(restored.id == selected.id && renewedPosition.draft == "My unsent follow-up")
        let restoredModel = LioConversation(service: restored.service)
        await restoredModel.refreshTimeline()
        #expect(restoredModel.turns.last?.answer == "A synthetic answer")
        #expect(await fixture.transport.posts == 1)
        // A new presentation starts empty unless the verified root transfers it.
        let other = try fixture.library()
        #expect(other.continuity?.selectedID == nil && other.continuity?.draft == "")
    }

    @Test func acceptedChatRestoresWithoutLookingUpAnUnrelatedUncertainFirstSend() async throws {
        let fixture = try ChatContinuityFixture()
        let library = try fixture.library()
        let accepted = library.newChat()
        let position = try #require(library.continuity)
        let first = LioConversation(service: accepted.service)
        first.send("A synthetic saved question", language: .english)
        await first.receive(try #require(first.pending))
        let unrelated = library.newChat()
        let uncertain = try LioTimelineWire.Send(messageID: UUID().uuidString, text: "Another synthetic question",
                                                 locale: .english, destination: .newChat)
        position.firstQuestions[unrelated.id] = LioQuestion(messageID: uncertain.messageID,
                                                         text: "Another synthetic question", language: .english)
        await fixture.transport.loseNextReceipt()
        do {
            _ = try await fixture.client().submit(uncertain)
            Issue.record("The second synthetic receipt must be lost")
        } catch let error as URLError { #expect(error.code == .networkConnectionLost) }
        position.selectedID = accepted.id
        position.draft = "An unsent synthetic follow-up"
        await fixture.transport.failLookups(true)
        let transferred = LioChatContinuity()
        transferred.inherit(position)
        let renewed = try fixture.library(continuity: transferred)
        let restored = try #require(try await renewed.restore?())
        #expect(restored.id == accepted.id)
        #expect(transferred.draft == position.draft)
        #expect(transferred.firstQuestions[unrelated.id]?.messageID == uncertain.messageID)
        #expect(await fixture.transport.lookups == 0)
        #expect(await fixture.transport.posts == 2)
        let retained = try #require(try fixture.recovery.action(messageID: uncertain.messageID, lease: fixture.lease))
        #expect(retained.phase == .queryRequired)
        #expect(retained.originalUTF8 == uncertain.originalUTF8)
        let anotherFirst = try LioTimelineWire.Send(messageID: UUID().uuidString, text: "A third synthetic question",
                                                   locale: .english, destination: .newChat)
        await #expect(throws: RecoveryError.queryOnly) { _ = try await fixture.client().submit(anotherFirst) }
        #expect(await fixture.transport.posts == 2)
    }

    @Test func selectedUncertainFirstSendStillRequiresItsOwnReceiptLookup() async throws {
        let fixture = try ChatContinuityFixture()
        let library = try fixture.library()
        let selected = library.newChat()
        let position = try #require(library.continuity)
        let first = try LioTimelineWire.Send(messageID: UUID().uuidString, text: "An uncertain synthetic question",
                                            locale: .english, destination: .newChat)
        position.selectedID = selected.id
        position.firstQuestions[selected.id] = LioQuestion(messageID: first.messageID,
                                                         text: "An uncertain synthetic question", language: .english)
        await fixture.transport.loseNextReceipt()
        do {
            _ = try await fixture.client().submit(first)
            Issue.record("The selected synthetic receipt must be lost")
        } catch let error as URLError { #expect(error.code == .networkConnectionLost) }
        await fixture.transport.failLookups(true)
        await #expect(throws: MessageHTTPFailure.exchangeUnknown) { _ = try await library.restore?() }
        #expect(position.selectedID == selected.id)
        #expect(position.firstQuestions[selected.id]?.messageID == first.messageID)
        let retained = try #require(try fixture.recovery.action(messageID: first.messageID, lease: fixture.lease))
        #expect(retained.originalUTF8 == first.originalUTF8 && retained.phase == .queryRequired)
        #expect(await fixture.transport.posts == 1)
        #expect(await fixture.transport.lookups == 1)
    }

    @Test func lostFirstReceiptIsReadByItsOriginalIDBeforeReturningToTheChat() async throws {
        let fixture = try ChatContinuityFixture()
        let old = try fixture.library()
        let selected = old.newChat()
        let position = try #require(old.continuity)
        position.selectedID = selected.id
        let original = try LioTimelineWire.Send(messageID: UUID().uuidString, text: "A synthetic question",
                                               locale: .english, destination: .newChat)
        position.firstQuestions[selected.id] = LioQuestion(messageID: original.messageID, text: "A synthetic question", language: .english)
        await fixture.transport.loseNextReceipt()
        do {
            _ = try await fixture.client().submit(original)
            Issue.record("The synthetic first receipt must be lost")
        } catch let error as URLError { #expect(error.code == .networkConnectionLost) }
        let renewedPosition = LioChatContinuity()
        renewedPosition.inherit(position)
        let renewed = try fixture.library(continuity: renewedPosition)
        await fixture.transport.holdLookup(true)
        await #expect(throws: MessageHTTPFailure.exchangeUnknown) { _ = try await renewed.restore?() }
        #expect(renewedPosition.firstQuestions[selected.id]?.messageID == original.messageID)
        await fixture.transport.holdLookup(false)
        let restored = try #require(try await renewed.restore?())
        #expect(restored.id == selected.id && renewedPosition.firstQuestions.isEmpty)
        let model = LioConversation(service: restored.service)
        await model.refreshTimeline()
        #expect(model.turns.last?.question.messageID == original.messageID)
        #expect(await fixture.transport.posts == 1)
        #expect(await fixture.transport.lookups == 2)
    }

    @Test func backgroundBeforeTheFirstActionIsStagedRestoresTheQuestionAsAnUnsentDraft() async throws {
        let fixture = try ChatContinuityFixture()
        let old = try fixture.library()
        let selected = old.newChat()
        let position = try #require(old.continuity)
        position.selectedID = selected.id
        let question = LioQuestion(messageID: UUID().uuidString, text: "An unsent synthetic question", language: .english)
        position.firstQuestions[selected.id] = question // Background before the send task stages an action.
        let restoredPosition = LioChatContinuity()
        restoredPosition.inherit(position)
        let restored = try fixture.library(continuity: restoredPosition)
        #expect(try await restored.restore?()?.id == selected.id)
        #expect(restoredPosition.draft == question.text && restoredPosition.firstQuestions.isEmpty)
        #expect(await fixture.transport.posts == 0)
        #expect(await fixture.transport.lookups == 0)
    }

    // MARK: - Failure stages (#1036 follow-up). Each keeps the original error, record and draft.

    private func selectedUncertainFirstSend(_ fixture: ChatContinuityFixture) async throws
        -> (library: LioChatLibrary, position: LioChatContinuity, selected: LioChatSession, original: LioTimelineWire.Send) {
        let library = try fixture.library()
        let selected = library.newChat()
        let position = try #require(library.continuity)
        let original = try LioTimelineWire.Send(messageID: UUID().uuidString, text: "A synthetic stage question",
                                               locale: .english, destination: .newChat)
        position.selectedID = selected.id
        position.draft = "A synthetic unsent draft"
        position.firstQuestions[selected.id] = LioQuestion(messageID: original.messageID,
                                                         text: "A synthetic stage question", language: .english)
        await fixture.transport.loseNextReceipt()
        do {
            _ = try await fixture.client().submit(original)
            Issue.record("The synthetic first receipt must be lost")
        } catch let error as URLError { #expect(error.code == .networkConnectionLost) }
        return (library, position, selected, original)
    }

    private func expectRetained(_ fixture: ChatContinuityFixture, _ position: LioChatContinuity,
                                _ selected: LioChatSession, _ original: LioTimelineWire.Send,
                                phase: ActionPhase = .queryRequired) async throws {
        #expect(position.selectedID == selected.id && position.draft == "A synthetic unsent draft")
        #expect(position.firstQuestions[selected.id]?.messageID == original.messageID)
        let retained = try #require(try fixture.recovery.action(messageID: original.messageID, lease: fixture.lease))
        #expect(retained.originalUTF8 == original.originalUTF8 && retained.phase == phase)
        #expect(await fixture.transport.posts == 1)
    }

    @Test(arguments: [(HTTPResponse.Status.serviceUnavailable, LioFailureDiagnosis.Category.service, 503),
                      (.internalServerError, .service, 500),
                      (.unauthorized, .signIn, 401),
                      (.forbidden, .signIn, 403)])
    func firstSendLookupFailureIsNamedByItsStatus(status: HTTPResponse.Status, category: LioFailureDiagnosis.Category,
                                                  code: Int) async throws {
        let fixture = try ChatContinuityFixture()
        let (library, position, selected, original) = try await selectedUncertainFirstSend(fixture)
        await fixture.transport.failLookups(status: status)
        await #expect(throws: MessageHTTPFailure.exchangeUnknown) { _ = try await library.restore?() }
        let diagnosis = try #require(library.diagnose?(MessageHTTPFailure.exchangeUnknown))
        #expect(diagnosis == LioFailureDiagnosis(category: category, stage: .firstSendLookup,
                                                 request: .firstLookup, httpStatus: code,
                                                 serverReference: ChatContinuityTransport.trace))
        #expect(fixture.notes.entries.map(\.category) == [category])
        #expect(fixture.notes.entries.first?.reference == ChatContinuityTransport.trace)
        #expect(fixture.notes.entries.first?.stage == .firstSendLookup && fixture.notes.entries.first?.httpStatus == code)
        #expect(await fixture.transport.lookups == 1)
        try await expectRetained(fixture, position, selected, original)
    }

    @Test func firstSendLookupWithoutAConnectionIsANetworkProblem() async throws {
        let fixture = try ChatContinuityFixture()
        let (library, position, selected, original) = try await selectedUncertainFirstSend(fixture)
        await fixture.transport.dropLookups()
        var thrown: (any Error)?
        do { _ = try await library.restore?() } catch { thrown = error }
        let error = try #require(thrown as? URLError)
        #expect(error.code == .notConnectedToInternet)
        let diagnosis = try #require(library.diagnose?(error))
        #expect(diagnosis == LioFailureDiagnosis(category: .network, stage: .firstSendLookup,
                                                 request: .firstLookup, httpStatus: nil))
        try await expectRetained(fixture, position, selected, original)
    }

    @Test func unansweredFirstSendLookupStaysUnclear() async throws {
        let fixture = try ChatContinuityFixture()
        let (library, position, selected, original) = try await selectedUncertainFirstSend(fixture)
        await fixture.transport.holdLookup(true)
        await #expect(throws: MessageHTTPFailure.exchangeUnknown) { _ = try await library.restore?() }
        let diagnosis = try #require(library.diagnose?(MessageHTTPFailure.exchangeUnknown))
        #expect(diagnosis == LioFailureDiagnosis(category: .unclear, stage: .firstSendLookup,
                                                 request: .firstLookup, httpStatus: 200,
                                                 serverReference: ChatContinuityTransport.trace))
        // The lookup proved nothing either way; the original action stays for its own later lookup.
        try await expectRetained(fixture, position, selected, original, phase: .notObserved)
    }

    @Test func unavailableSignInIsASessionCheckWithoutAnyRequest() async throws {
        let fixture = try ChatContinuityFixture()
        let (_, position, selected, original) = try await selectedUncertainFirstSend(fixture)
        let transferred = LioChatContinuity()
        transferred.inherit(position)
        let signedOut = try fixture.library(continuity: transferred, signedIn: false)
        await #expect(throws: MessageHTTPFailure.credentialsUnavailable) { _ = try await signedOut.restore?() }
        let diagnosis = try #require(signedOut.diagnose?(MessageHTTPFailure.credentialsUnavailable))
        #expect(diagnosis.stage == .sessionCheck && diagnosis.category == .unclear && diagnosis.httpStatus == nil)
        #expect(await fixture.transport.lookups == 0)
        try await expectRetained(fixture, transferred, selected, original)
    }

    @Test func damagedLocalRecordIsNotReportedAsANetworkProblem() async throws {
        let fixture = try ChatContinuityFixture()
        let library = try fixture.library()
        let selected = library.newChat()
        let position = try #require(library.continuity)
        let messageID = UUID().uuidString
        let unreadable = Data(#"{"version":"synthetic-unrecognized"}"#.utf8)
        try fixture.recovery.stage(messageID: messageID, originalUTF8: unreadable, lease: fixture.lease)
        position.selectedID = selected.id
        position.draft = "A synthetic unsent draft"
        position.firstQuestions[selected.id] = LioQuestion(messageID: messageID, text: "A synthetic question", language: .english)
        await #expect(throws: RecoveryError.invalidSnapshot) { _ = try await library.restore?() }
        let diagnosis = try #require(library.diagnose?(RecoveryError.invalidSnapshot))
        #expect(diagnosis == LioFailureDiagnosis(category: .localRecord, stage: .localRecord, request: nil, httpStatus: nil))
        #expect(fixture.notes.entries.first?.category == .localRecord)
        // Nothing is cleared to make the error go away.
        #expect(try fixture.recovery.action(messageID: messageID, lease: fixture.lease)?.originalUTF8 == unreadable)
        #expect(position.selectedID == selected.id && position.draft == "A synthetic unsent draft")
        #expect(position.firstQuestions[selected.id]?.messageID == messageID)
        #expect(await fixture.transport.lookups == 0)
        #expect(await fixture.transport.posts == 0)
    }

    @Test func missingSelectedChatIsUnclearAndNeverStartsABlankChat() async throws {
        let fixture = try ChatContinuityFixture()
        let library = try fixture.library()
        let position = try #require(library.continuity)
        position.selectedID = Data("synthetic-missing-chat".utf8)
        position.draft = "A synthetic unsent draft"
        await #expect(throws: MessageHTTPFailure.exchangeUnknown) { _ = try await library.restore?() }
        let diagnosis = try #require(library.diagnose?(MessageHTTPFailure.exchangeUnknown))
        #expect(diagnosis == LioFailureDiagnosis(category: .unclear, stage: .selectedChat, request: nil, httpStatus: nil))
        #expect(position.selectedID == Data("synthetic-missing-chat".utf8) && position.draft == "A synthetic unsent draft")
        #expect(position.blankIDs.isEmpty)
        #expect(await fixture.transport.posts == 0)
        #expect(await fixture.transport.lookups == 0)
    }

    @Test func timelineReadFailureIsNotedAsItsOwnStage() async throws {
        let fixture = try ChatContinuityFixture()
        let library = try fixture.library()
        let accepted = library.newChat()
        let first = LioConversation(service: accepted.service)
        first.send("A synthetic saved question", language: .english)
        await first.receive(try #require(first.pending))
        let position = try #require(library.continuity)
        position.selectedID = accepted.id
        let restored = try #require(try await library.restore?())
        #expect(fixture.notes.entries.isEmpty)
        await fixture.transport.failTimeline(status: .internalServerError)
        let model = LioConversation(service: restored.service)
        // The read keeps its existing retry window; stop once the first failure is noted.
        let refresh = Task { await model.refreshTimeline() }
        for _ in 0..<300 where fixture.notes.entries.isEmpty { try await Task.sleep(for: .milliseconds(10)) }
        refresh.cancel()
        await refresh.value
        #expect(model.turns.isEmpty)
        #expect(await fixture.transport.timelineReads >= 1)
        let note = try #require(fixture.notes.entries.first)
        #expect(note.stage == .timeline && note.category == .service && note.httpStatus == 500 && note.request == "timeline")
        #expect(await fixture.transport.posts == 1)
    }
}

@MainActor private struct ChatContinuityFixture {
    let transport = ChatContinuityTransport()
    let storage = ChatContinuityStorage()
    let recovery: MessageRecovery
    let notes = LioDiagnosticLog(defaults: UserDefaults(suiteName: "synthetic-notes-" + UUID().uuidString)!, build: "45")
    let scope: StorageScope
    let lease: Lease

    init() throws {
        recovery = MessageRecovery(storage: storage)
        scope = try StorageScope(environment: "synthetic", account: "continuity")
        lease = try recovery.activate(scope)
    }

    func client(signedIn: Bool = true) throws -> LioTimelineHTTP {
        let endpoint = try MessageEndpoint(url: URL(string: "https://synthetic.invalid")!,
            maximumRequestBytes: 16_384, maximumResponseBytes: 65_536)
        let transport = try NoRedirectTransport(interceptedTransport: transport, messageEndpoint: endpoint,
                                               validateMessage: {}, lio: true)
        return LioTimelineHTTP(scope: scope, lease: lease, credentials: ChatContinuityCredentials(signedIn: signedIn),
                               transport: transport, firstChatRecovery: recovery)
    }

    func library(continuity: LioChatContinuity? = nil, signedIn: Bool = true) throws -> LioChatLibrary {
        let client = try client(signedIn: signedIn)
        return .signed(client: client, defaultService: .signedTimeline(client), language: { .english },
            continuity: continuity, notes: notes) { id in
            LioTripHistoryClient(timeline: client, recovery: recovery, scope: scope, lease: lease, conversationID: id)
        }
    }
}

@MainActor private final class ChatContinuityStorage: SecureMessageStorage {
    private var snapshot: Snapshot?
    func load(scope: StorageScope) throws -> Snapshot? { snapshot }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { self.snapshot = snapshot }
}

@MainActor private final class ChatContinuityCredentials: MessageCredentialsProvider {
    let signedIn: Bool
    init(signedIn: Bool = true) { self.signedIn = signedIn }
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { signedIn ? "SYNTHETIC" : nil }
}

private actor ChatContinuityTransport: ClientTransport {
    static let trace = "6F9619FF-8B86-D011-B42D-00C04FC964FF"
    private let id = "lio-dialogue-0123456789abcdef0123456789abcdef"
    private var original: LioTimelineWire.Send?
    private var originalDigest: String?
    private var loseReceipt = false
    private var lookupHeld = false
    private var lookupFailure: HTTPResponse.Status?
    private var lookupOffline = false
    private var timelineFailure: HTTPResponse.Status?
    private(set) var posts = 0
    private(set) var lookups = 0
    private(set) var timelineReads = 0
    func loseNextReceipt() { loseReceipt = true }
    func holdLookup(_ held: Bool) { lookupHeld = held }
    func failLookups(_ value: Bool) { lookupFailure = value ? .serviceUnavailable : nil }
    func failLookups(status: HTTPResponse.Status) { lookupFailure = status }
    func dropLookups() { lookupOffline = true }
    func failTimeline(status: HTTPResponse.Status?) { timelineFailure = status }

    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let route = try #require(URLComponents(string: request.path ?? ""))
        switch (request.method, route.path) {
        case (.post, "/v2/lio/messages"):
            posts += 1
            let body = try #require(body)
            let bytes = try await Data(collecting: body, upTo: 16_384)
            originalDigest = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
            let fields = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
            original = try LioTimelineWire.Send(messageID: #require(fields["message_id"] as? String),
                text: #require(fields["text"] as? String), locale: .english, destination: .newChat)
            if loseReceipt { throw URLError(.networkConnectionLost) }
            return try reply(["version": "LIO-message-receipt.2", "message_id": #require(original?.messageID), "conversation_id": id])
        case (.get, "/v2/lio/messages"):
            lookups += 1
            if lookupOffline { throw URLError(.notConnectedToInternet) }
            if let lookupFailure { return try reply(["failure": "unavailable"], status: lookupFailure) }
            let original = try #require(original)
            #expect(route.queryItems?.contains(.init(name: "message_id", value: original.messageID)) == true)
            let digest = try #require(originalDigest)
            #expect(route.queryItems?.contains(.init(name: "input_sha256", value: digest)) == true)
            if lookupHeld { return try reply(["version": "LIO-message-lookup.2", "receipt": NSNull()]) }
            return try reply(["version": "LIO-message-lookup.2", "receipt": ["version": "LIO-message-receipt.2", "message_id": original.messageID, "conversation_id": id]])
        case (.get, "/v2/lio/timeline"):
            timelineReads += 1
            if let timelineFailure { return try reply(["failure": "unavailable"], status: timelineFailure) }
            let original = try #require(original)
            return try reply(["version": "LIO-timeline.2", "conversation_id": id, "next_before": NSNull(),
                "messages": [["message_id": original.messageID, "text": "A synthetic question", "answer": "A synthetic answer", "status": "completed", "sources": []]]])
        default: throw MessageHTTPFailure.invalidConfiguration
        }
    }

    private func reply(_ fields: [String: Any], status: HTTPResponse.Status = .ok) throws -> (HTTPResponse, HTTPBody?) {
        var response = HTTPResponse(status: status)
        response.headerFields[.contentType] = "application/json"
        response.headerFields[HTTPField.Name("X-Request-ID")!] = Self.trace
        return (response, HTTPBody(try JSONSerialization.data(withJSONObject: fields)))
    }

}
