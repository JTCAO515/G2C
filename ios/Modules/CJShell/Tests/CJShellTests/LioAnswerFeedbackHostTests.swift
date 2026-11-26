import Foundation
import CryptoKit
import Testing
import CJLioUser
import OpenAPIRuntime
import HTTPTypes
@testable import CJFeedbackClient
@testable import CJShell

private let lioFeedbackTrace = "00000000-0000-4000-8000-000000000002"

/// A stand-in server: keeps what arrived by action ID and answers look-ups from it.
private actor LioFeedbackServer: ClientTransport {
    enum Submission { case accept, arriveWithoutReply, refuse }
    var submission = Submission.accept
    private(set) var arrived: [String: Data] = [:]
    private(set) var submitted: [Data] = []
    private(set) var lookUps: [String] = []

    func set(_ value: Submission) { submission = value }
    func receive(_ original: FeedbackPending) { arrived[original.actionID] = original.originalUTF8 }

    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        if operationID == "submitFeedback" {
            let bytes = try await Data(collecting: try #require(body), upTo: 16384)
            submitted.append(bytes)
            let id = try #require(try JSONSerialization.jsonObject(with: bytes) as? [String: Any])["action_id"] as? String ?? ""
            switch submission {
            case .refuse: throw FeedbackFailure.exchangeUnknown
            case .arriveWithoutReply: arrived[id] = bytes; throw FeedbackFailure.exchangeUnknown
            case .accept: arrived[id] = bytes; return try reply(receipt(id: id, bytes: bytes))
            }
        }
        let path = try #require(request.path)
        let id = try #require(URLComponents(string: path)?.queryItems?.first { $0.name == "action_id" }?.value)
        lookUps.append(id)
        guard let bytes = arrived[id] else { return try reply(NSNull()) }
        return try reply(receipt(id: id, bytes: bytes))
    }

    private func receipt(id: String, bytes: Data) throws -> [String: Any] {
        let action = try #require(try JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        let message = (action["references"] as? [[String: Any]])?.first { $0["kind"] as? String == "message" }?["id"] as? String
        let source: Any = message.map {
            ["message_id": $0, "run_id": "run-A", "conversation_id": "synthetic-conversation", "generation": "synthetic-generation",
             "message_sequence": 1, "message_input_sha256": String(repeating: "b", count: 64), "run_status_at_read": "running",
             "event_highwater_at_read": 4] as [String: Any]
        } ?? NSNull()
        return ["action_id": id, "input_sha256": SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined(),
                "submitted_at": "2026-11-26T10:00:00Z", "status": "submitted", "message_en": "Feedback submitted.",
                "message_zh": "反馈已提交。", "source": source]
    }

    private func reply(_ receipt: Any) throws -> (HTTPResponse, HTTPBody?) {
        var response = HTTPResponse(status: .ok)
        response.headerFields[HTTPField.Name("X-Request-ID")!] = lioFeedbackTrace
        response.headerFields[.contentType] = "application/json"
        let data = try JSONSerialization.data(withJSONObject: ["request_id": lioFeedbackTrace, "receipt": receipt])
        return (response, HTTPBody(data))
    }
}

@MainActor private final class LioFeedbackFixture {
    let binding: FeedbackBinding
    let server = LioFeedbackServer()
    let directory: URL
    let store: FeedbackPendingStore
    let host: LioAnswerFeedbackHost
    private let client: FeedbackClient
    private let current: @MainActor () -> FeedbackBinding?
    private let maximumRecords: Int
    private let session: Session
    var signedIn: Bool {
        get { session.signedIn }
        set { session.signedIn = newValue }
    }
    @MainActor private final class Session { var signedIn = true }

    init(maximumRecords: Int = 100) throws {
        let session = Session(), binding = FeedbackBinding(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID())
        self.binding = binding
        self.session = session
        directory = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        let key = SymmetricKey(size: .bits256)
        store = try FeedbackPendingStore(directory: directory, maximumBytes: 32768, maximumRecords: maximumRecords,
            namespace: .init(environment: binding.environment, account: binding.account, purpose: .localFeedbackPendingV1),
            keyID: UUID(), key: { key })
        let current: @MainActor () -> FeedbackBinding? = { session.signedIn ? binding : nil }
        let client = FeedbackClient(endpoint: try FeedbackEndpoint(url: #require(URL(string: "https://synthetic.invalid")),
                                                                   maximumRequestBytes: 16384, maximumResponseBytes: 100_000),
            credentials: { _ in "SYNTHETIC" }, currentBinding: current, pendingStore: store, interceptedTransport: server)
        host = LioAnswerFeedbackHost(client: client, currentBinding: current, maximumRecords: maximumRecords)
        self.client = client; self.current = current; self.maximumRecords = maximumRecords
    }

    /// The host the app makes when it comes back from the background: same client and store, no attempts.
    func rebuiltHost() -> LioAnswerFeedbackHost {
        host.invalidate()
        return LioAnswerFeedbackHost(client: client, currentBinding: current, maximumRecords: maximumRecords)
    }
    deinit { try? FileManager.default.removeItem(at: directory) }

    /// A line an earlier session saved and maybe sent.
    func seed(_ id: String, arrived: Bool) async throws -> FeedbackPending {
        let original = try FeedbackPending(problem: "Earlier line", expectation: "", context: FeedbackContext(messageID: "message-old"), actionID: id)
        try store.append(original)
        if arrived { await server.receive(original) }
        return original
    }

    func actions() async throws -> [[String: Any]] {
        try await server.submitted.map { try #require(try JSONSerialization.jsonObject(with: $0) as? [String: Any]) }
    }
}

@Suite @MainActor struct LioAnswerFeedbackHostTests {
    private let problem = "This answer didn't help."

    @Test func oneTapSendsTheFixedLineAboutThisMessageOnly() async throws {
        let f = try LioFeedbackFixture()
        #expect(await f.host.notHelpful(messageID: "message-A", problem: problem) == .sent)
        let actions = try await f.actions()
        #expect(actions.count == 1)
        let action = try #require(actions.first)
        #expect(Set(action.keys) == ["action_id", "problem", "expectation", "references"])
        #expect(action["problem"] as? String == problem && action["expectation"] as? String == "")
        let references = try #require(action["references"] as? [[String: String]])
        #expect(references == [["kind": "message", "id": "message-A"]], "no run, no chat text")
        #expect(try f.store.pending().isEmpty, "confirmed by its receipt, so the device's copy is removed (#1855)")
        // The same answer again reuses the line that arrived; nothing new goes out.
        #expect(await f.host.notHelpful(messageID: "message-A", problem: problem) == .sent)
        #expect(await f.server.submitted.count == 1)
    }

    @Test func detailsGoAsASecondLineAfterTheFirstArrived() async throws {
        let f = try LioFeedbackFixture()
        #expect(await f.host.notHelpful(messageID: "message-A", problem: problem) == .sent)
        #expect(await f.host.addDetails(messageID: "message-A", text: "The station name was wrong") == .sent)
        let actions = try await f.actions()
        #expect(actions.map { $0["problem"] as? String } == [problem, "The station name was wrong"])
        #expect(actions.allSatisfy { ($0["references"] as? [[String: String]]) == [["kind": "message", "id": "message-A"]] })
        #expect(actions.allSatisfy { $0["expectation"] as? String == "" })
        #expect(Set(actions.compactMap { $0["action_id"] as? String }).count == 2)
        #expect(await f.server.lookUps.isEmpty, "both arrived in this session; nothing to look up")
    }

    @Test func unknownResultRetryOnlyLooksTheSameLineUp() async throws {
        let f = try LioFeedbackFixture()
        await f.server.set(.arriveWithoutReply)
        #expect(await f.host.notHelpful(messageID: "message-A", problem: problem) == .notSent)
        let saved = try #require(try f.store.pending().first)
        await f.server.set(.accept)
        #expect(await f.host.retry(.notHelpful, messageID: "message-A", text: problem) == .sent)
        #expect(await f.server.submitted.count == 1, "never sent again under a new ID")
        #expect(await f.server.lookUps == [saved.actionID])
        #expect(try f.store.pending().isEmpty, "confirmed, so removed")
    }

    @Test func lineThatNeverArrivedIsOnlyEverSentAgainUnderItsOwnIDOnTheTravellersRetry() async throws {
        let f = try LioFeedbackFixture()
        await f.server.set(.refuse)
        #expect(await f.host.notHelpful(messageID: "message-A", problem: problem) == .notSent)
        let saved = try #require(try f.store.pending().first)
        // A first tap on another answer looks the line up and sends nothing: not new lines, not a resend.
        #expect(await f.host.notHelpful(messageID: "message-B", problem: problem) == .notSent)
        #expect(await f.server.submitted.count == 1)
        // The traveller's retry: the server has no such line, so the same line goes out again, same ID and bytes.
        #expect(await f.host.retry(.notHelpful, messageID: "message-A", text: problem) == .notSent)
        let submitted = await f.server.submitted
        #expect(submitted.count == 2 && submitted[0] == submitted[1], "same ID, same bytes; never a new line")
        #expect(try f.store.pending().map(\.actionID) == [saved.actionID])
        // Now the server takes it: the line settles under its own ID and nothing else is made.
        await f.server.set(.accept)
        #expect(await f.host.retry(.notHelpful, messageID: "message-A", text: problem) == .sent)
        let all = await f.server.submitted
        #expect(all.count == 3 && Set(all).count == 1)
        #expect(try f.store.pending().isEmpty)
    }

    @Test func olderSavedLinesAreLookedUpBeforeAnythingNew() async throws {
        let f = try LioFeedbackFixture()
        let first = try await f.seed("old-1", arrived: true), second = try await f.seed("old-2", arrived: false)
        #expect(await f.host.notHelpful(messageID: "message-A", problem: problem) == .notSent)
        #expect(await f.server.submitted.isEmpty, "nothing new while an older line is unsettled")
        #expect(Set(await f.server.lookUps) == [first.actionID, second.actionID])
        await f.server.receive(second)
        #expect(await f.host.retry(.notHelpful, messageID: "message-A", text: problem) == .sent)
        #expect(await f.server.submitted.count == 1)
        // old-1 arrived on the first pass and is not asked about again.
        #expect(await f.server.lookUps.filter { $0 == first.actionID }.count == 1)
        #expect(await f.server.lookUps.filter { $0 == second.actionID }.count == 2)
    }

    @Test func confirmedLinesAreRemovedSoTheCapRollsButUnremovableOnesStillCount() async throws {
        let f = try LioFeedbackFixture(maximumRecords: 2)
        _ = try await f.seed("old-1", arrived: true)
        _ = try await f.seed("old-2", arrived: true)
        // Both arrived: they are removed from the device, so there is room again (#1855).
        #expect(await f.host.notHelpful(messageID: "message-A", problem: problem) == .sent)
        #expect(await f.server.submitted.count == 1)
        #expect(try f.store.pending().isEmpty)
        // Lines that cannot be removed (the folder is read-only) keep their place; nothing new is sent.
        let g = try LioFeedbackFixture(maximumRecords: 2)
        _ = try await g.seed("old-1", arrived: true)
        _ = try await g.seed("old-2", arrived: true)
        try FileManager.default.setAttributes([.posixPermissions: 0o500], ofItemAtPath: g.directory.path)
        defer { try? FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: g.directory.path) }
        #expect(await g.host.notHelpful(messageID: "message-A", problem: problem) == .full)
        #expect(await g.host.retry(.notHelpful, messageID: "message-A", text: problem) == .full)
        #expect(await g.server.submitted.isEmpty)
        #expect(try g.store.pending().count == 2)
    }

    @Test func signedOutSendsNothing() async throws {
        let f = try LioFeedbackFixture()
        f.signedIn = false
        #expect(await f.host.notHelpful(messageID: "message-A", problem: problem) == .unavailable)
        #expect(await f.server.submitted.isEmpty)
        #expect(await f.server.lookUps.isEmpty)
        #expect(try f.store.pending().isEmpty)
        #expect(await f.host.retry(.details, messageID: "message-A", text: "Late") == .unavailable)
        #expect(await f.server.submitted.isEmpty)
    }

    @Test func hostMadeAfterComingBackFindsTheSavedLineInsteadOfMakingAnother() async throws {
        let f = try LioFeedbackFixture()
        await f.server.set(.arriveWithoutReply)
        #expect(await f.host.notHelpful(messageID: "message-A", problem: problem) == .notSent)
        let saved = try #require(try f.store.pending().first)
        await f.server.set(.accept)
        let host = f.rebuiltHost()
        #expect(await host.retry(.notHelpful, messageID: "message-A", text: problem) == .sent)
        #expect(await f.server.submitted.count == 1, "the line that arrived is adopted, not sent again")
        #expect(await f.server.lookUps == [saved.actionID])
        // Details typed before the app went away are retried with the same text and go as their own line.
        await f.server.set(.refuse)
        #expect(await host.addDetails(messageID: "message-A", text: "Wrong exit") == .notSent)
        // The store lists lines by a hash of their ID, not by when they were saved.
        let details = try #require(try f.store.pending().first { $0.actionID != saved.actionID })
        await f.server.receive(details)
        await f.server.set(.accept)
        let again = f.rebuiltHost()
        #expect(await again.retry(.details, messageID: "message-A", text: "Wrong exit") == .sent)
        #expect(await f.server.submitted.count == 2)
        #expect(try f.store.pending().isEmpty, "both lines confirmed, so both removed (#1855)")
    }

    @Test func linesFoundConfirmedWhileHandlingAnotherCallAreReportedSoARetryNeverResendsThem() async throws {
        let f = try LioFeedbackFixture()
        var confirmed: [String] = []
        f.host.onLineConfirmed = { message, text in confirmed.append(message + "|" + text) }
        // Answer A's result is unknown: the line arrived, the reply did not.
        await f.server.set(.arriveWithoutReply)
        #expect(await f.host.notHelpful(messageID: "message-A", problem: problem) == .notSent)
        #expect(confirmed.isEmpty)
        // A tap on answer B looks A's line up, finds it, and the device's copy is removed.
        await f.server.set(.accept)
        #expect(await f.host.notHelpful(messageID: "message-B", problem: problem) == .sent)
        // The host reports the older line it found; B's own line is reported by LioHome from the outcome.
        #expect(confirmed == ["message-A|" + problem])
        #expect(try f.store.pending().isEmpty)
        // A host made after the app came back cannot see A's line any more; LioHome's ledger now holds it, so the
        // retry for A never reaches a host.
    }

    @Test func aLineConfirmedAndRemovedByAnotherSurfaceIsNeverSentAgainUnderANewID() async throws {
        let f = try LioFeedbackFixture()
        var confirmed: [String] = []
        f.host.onLineConfirmed = { message, text in confirmed.append(message + "|" + text) }
        await f.server.set(.arriveWithoutReply)
        #expect(await f.host.notHelpful(messageID: "message-A", problem: problem) == .notSent)
        // The engineering feedback surface shares the folder: it looks the line up, finds it and removes it.
        let saved = try #require(try f.store.pending().first)
        try f.store.remove(saved)
        await f.server.set(.accept)
        #expect(await f.host.retry(.notHelpful, messageID: "message-A", text: problem) == .sent)
        #expect(await f.server.submitted.count == 1, "no new line for words that already arrived")
        #expect(confirmed == ["message-A|" + problem])
    }

    @Test func aLineThatWasNeverSavedStillGetsANewLineOnRetry() async throws {
        let f = try LioFeedbackFixture()
        f.signedIn = false
        #expect(await f.host.notHelpful(messageID: "message-A", problem: problem) == .unavailable)
        f.signedIn = true
        #expect(await f.host.retry(.notHelpful, messageID: "message-A", text: problem) == .sent)
        #expect(await f.server.submitted.count == 1)
    }

    @Test func savedLineIsAdoptedOnlyForTheSameMessageAndText() async throws {
        let f = try LioFeedbackFixture()
        #expect(await f.host.notHelpful(messageID: "message-A", problem: problem) == .sent)
        let host = f.rebuiltHost()
        #expect(await host.retry(.notHelpful, messageID: "message-B", text: problem) == .sent)
        #expect(await host.retry(.details, messageID: "message-A", text: "Something else") == .sent)
        let actions = try await f.actions()
        #expect(actions.count == 3, "another message, or other text, is a line of its own")
    }

    @Test func onlyALineShapedLikeLiosOwnIsAdopted() async throws {
        let f = try LioFeedbackFixture()
        let withExpectation = try FeedbackPending(problem: problem, expectation: "Something else",
                                                  context: FeedbackContext(messageID: "message-A"), actionID: "other-1")
        let withRun = try FeedbackPending(problem: problem, expectation: "",
                                          context: FeedbackContext(messageID: "message-A", runID: "run-A"), actionID: "other-2")
        for line in [withExpectation, withRun] {
            try f.store.append(line)
            await f.server.receive(line)
        }
        #expect(await f.host.notHelpful(messageID: "message-A", problem: problem) == .sent)
        #expect(await f.server.submitted.count == 1, "neither saved line is Lio's, so a line of its own goes out")
    }

    @Test func invalidatedHostSendsNothing() async throws {
        let f = try LioFeedbackFixture()
        f.host.invalidate()
        f.signedIn = false
        #expect(await f.host.addDetails(messageID: "message-A", text: "Late") == .unavailable)
        #expect(await f.server.submitted.isEmpty)
    }
}
