import CJMessageClient
import Foundation
import HTTPTypes
import OpenAPIRuntime
import Testing
@testable import CJMessageHTTP

@MainActor private final class UndoStore: SecureMessageStorage {
    func load(scope: StorageScope) throws -> Snapshot? { nil }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws {}
}

@MainActor private final class UndoCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "synthetic-only" }
}

/// Answers each call from a script and keeps what was sent.
private actor UndoExit: ClientTransport {
    enum Answer: Sendable {
        case json(Int, String)
        case plain(Int, String)
        case fail
    }
    struct Call: Sendable {
        let method: HTTPRequest.Method
        let path: String?
        let body: Data?
        let contentType: String?
        let authorization: String?
    }

    private(set) var calls: [Call] = []
    private var script: [Answer]

    init(_ script: [Answer]) { self.script = script }

    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes = if let body { try await Data(collecting: body, upTo: 16_384) } else { nil as Data? }
        calls.append(Call(method: request.method, path: request.path, body: bytes, contentType: request.headerFields[.contentType],
                          authorization: request.headerFields[.authorization]))
        let answer = script.isEmpty ? Answer.fail : script.removeFirst()
        switch answer {
        case .fail: throw URLError(.networkConnectionLost)
        case .json(let status, let text):
            var response = HTTPResponse(status: .init(code: status))
            response.headerFields[.contentType] = "application/json"
            return (response, HTTPBody(text))
        case .plain(let status, let text):
            var response = HTTPResponse(status: .init(code: status))
            response.headerFields[.contentType] = "text/plain"
            return (response, HTTPBody(text))
        }
    }
}

/// #1994: the undo of an automatic save, as the App sends it (`LIO-trip-undo.4` and `.5`) and what it makes of the answer.
@MainActor
struct LioTripUndoTests {
    typealias Receipt = LioTimelineWire.TripReceipt
    private let conversation = "lio-dialogue-0123456789abcdef0123456789abcdef"
    private let hashA = String(repeating: "a", count: 64)
    private let hashB = String(repeating: "b", count: 64)
    private let until = "2026-11-28T03:04:05.678+00:00"

    private func target(restore: Bool = true, version: Int = 7) -> Receipt.UndoTarget {
        .init(tripID: "trip-9a1b", expectedVersion: restore ? version : 1, originalHash: hashA, contentVersion: "structured.4",
              restore: restore ? .init(version: version - 1, hash: hashB, contentVersion: "structured.3") : nil)
    }

    private func receipt(restore: Bool = true, version: Int = 7, saveID: String = "lio-plan-run-5c1f",
                         undo: Receipt.Undo? = nil) -> Receipt {
        let id = LioTimelineWire.undoActionID(forSave: saveID)
        return Receipt(status: .saved, actionID: saveID, tripID: "trip-9a1b", committedVersion: restore ? version : 1,
                       undo: undo ?? .init(state: .available, kind: restore ? .restore : .withdrawCreated, actionID: id, until: until,
                                           target: target(restore: restore, version: version)))
    }

    private func request(restore: Bool = true, saveID: String = "lio-plan-run-5c1f") throws -> LioTripUndoWire.Request {
        try #require(LioTripUndoWire.Request(receipt: receipt(restore: restore, saveID: saveID), conversationID: conversation))
    }

    private func receiptJSON(_ request: LioTripUndoWire.Request, committed: Bool = true, version: String = "LIO-trip-undo-receipt.4",
                             action: String? = nil, conversation: String? = nil) -> String {
        #"{"version":"\#(version)","conversation_id":"\#(conversation ?? request.conversationID)","action_id":"\#(action ?? request.actionID)","committed":\#(committed)}"#
    }

    private func client(_ exit: UndoExit) throws -> LioTimelineHTTP {
        let scope = try StorageScope(environment: "synthetic-undo", account: "synthetic-owner")
        let lease = try MessageRecovery(storage: UndoStore()).activate(scope)
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")),
                                           maximumRequestBytes: 16_384, maximumResponseBytes: 4_500_000)
        let transport = try NoRedirectTransport(interceptedTransport: exit, messageEndpoint: endpoint, validateMessage: {}, lio: true)
        return LioTimelineHTTP(scope: scope, lease: lease, credentials: UndoCredentials(), transport: transport)
    }

    private func object(_ data: Data) throws -> [String: Any] {
        try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    // MARK: The request

    @Test func aRestoreIsLioTripUndo4WithTheReceiptsOwnTargetAndTheServersActionID() throws {
        let value = try request()
        let body = try object(value.body)
        #expect(Set(body.keys) == ["version", "action_id", "conversation_id", "target"])
        #expect(body["version"] as? String == "LIO-trip-undo.4")
        #expect(body["action_id"] as? String == "undo-114b97123ea4b9ac35e69d3f8fd0ea64056a4c28")
        #expect(body["conversation_id"] as? String == conversation)
        let sent = try #require(body["target"] as? [String: Any])
        #expect(Set(sent.keys) == ["trip_id", "expected_version", "original_hash", "content_version",
                                   "restore_version", "restore_hash", "restore_content_version"])
        #expect(sent["expected_version"] as? Int == 7 && sent["restore_version"] as? Int == 6)
        #expect(value.version == "LIO-trip-undo.4")
        #expect(value.body.count <= LioTripUndoWire.maximumRequestBytes)
    }

    @Test func theBodyMatchesTheContractsOwnUndoExampleInShape() throws {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let examples = try object(Data(contentsOf: root.appendingPathComponent("contracts/message/lio-trip-history-examples.4.json")))
        let example = try #require(examples["undo"] as? [String: Any])
        let body = try object(request().body)
        #expect(Set(body.keys) == Set(example.keys))
        #expect(Set((body["target"] as? [String: Any] ?? [:]).keys) == Set((example["target"] as? [String: Any] ?? [:]).keys))
        #expect(example["version"] as? String == "LIO-trip-undo.4")
    }

    @Test func aWithdrawIsLioTripUndo5WithTheFourFieldTargetOfVersionOne() throws {
        let value = try request(restore: false)
        let body = try object(value.body)
        #expect(body["version"] as? String == "LIO-trip-undo.5" && value.version == "LIO-trip-undo.5")
        let sent = try #require(body["target"] as? [String: Any])
        #expect(Set(sent.keys) == ["trip_id", "expected_version", "original_hash", "content_version"])
        #expect(sent["expected_version"] as? Int == 1)
    }

    @Test func theBodyHoldsNothingButIdsVersionsAndHashes() throws {
        let text = String(decoding: try request().body, as: UTF8.self)
        for word in ["title", "name", "place", "summary", "text", "device", "user", "email", "lat", "lng"] {
            #expect(!text.contains(word), "\(word)")
        }
    }

    @Test func noRequestIsMadeFromAReceiptThatOffersNoUndo() throws {
        let id = LioTimelineWire.undoActionID(forSave: "lio-plan-run-5c1f")
        for state in [Receipt.Undo.State.expired, .superseded, .undone, .unavailable] {
            let value = receipt(undo: .init(state: state, until: until))
            #expect(LioTripUndoWire.Request(receipt: value, conversationID: conversation) == nil, "\(state)")
        }
        #expect(LioTripUndoWire.Request(receipt: Receipt(status: .notSaved, actionID: "a1", reason: .conflict), conversationID: conversation) == nil)
        #expect(LioTripUndoWire.Request(receipt: Receipt(status: .unknown, actionID: "a1"), conversationID: conversation) == nil)
        #expect(LioTripUndoWire.Request(receipt: receipt(undo: .init(state: .available, kind: .restore, actionID: id, until: until)),
                                        conversationID: conversation) == nil, "no target")
        #expect(LioTripUndoWire.Request(receipt: receipt(undo: .init(state: .available, kind: .withdrawCreated, actionID: id, until: until,
                                                                      target: target())), conversationID: conversation) == nil,
                "a withdraw has no restore fields")
        #expect(LioTripUndoWire.Request(receipt: receipt(undo: .init(state: .available, kind: .restore, actionID: id, until: until,
                                                                      target: target(restore: false))), conversationID: conversation) == nil,
                "a restore needs them")
        for bad in ["", "lio-dialogue-short", "lio-dialogue-0123456789ABCDEF0123456789abcdef", "x"] {
            #expect(LioTripUndoWire.Request(receipt: receipt(), conversationID: bad) == nil, "\(bad)")
        }
    }

    // MARK: On the wire

    @Test func theUndoIsOnePostToTheV4RouteWithItsBodyAndNoQuery() async throws {
        let value = try request()
        let exit = UndoExit([.json(200, receiptJSON(value))])
        let reply = try await client(exit).submitTripUndo(value)
        #expect(reply == .committed)
        let call = try #require(await exit.calls.first)
        #expect(await exit.calls.count == 1)
        #expect(call.method == .post && call.path == "/v4/lio/trip-undos")
        #expect(call.body == value.body && call.contentType == "application/octet-stream")
        #expect(call.authorization == "Bearer synthetic-only")
    }

    @Test func theReceiptQueryCarriesTheSameValuesAndVersionOnlyForAWithdraw() async throws {
        let restore = try request(), withdraw = try request(restore: false, saveID: "lio-plan-run-first")
        let exit = UndoExit([.json(200, receiptJSON(restore, committed: false)), .json(200, receiptJSON(withdraw, committed: true))])
        let http = try client(exit)
        #expect(try await http.readTripUndoReceipt(restore) == .notCommitted)
        #expect(try await http.readTripUndoReceipt(withdraw) == .committed)
        let calls = await exit.calls
        #expect(calls.map(\.method) == [.get, .get] && calls.allSatisfy { $0.body == nil })
        func query(_ path: String?) throws -> [String: String] {
            let components = try #require(URLComponents(string: "https://x" + (path ?? "")))
            #expect(components.path == "/v4/lio/trip-undo-receipts")
            return Dictionary(uniqueKeysWithValues: (components.queryItems ?? []).map { ($0.name, $0.value ?? "") })
        }
        let first = try query(calls[0].path), second = try query(calls[1].path)
        #expect(Set(first.keys) == ["action_id", "target", "conversation_id"], "no version: the server reads .4")
        #expect(Set(second.keys) == ["action_id", "target", "conversation_id", "version"])
        #expect(second["version"] == "LIO-trip-undo.5")
        #expect(first["action_id"] == restore.actionID && first["conversation_id"] == conversation)
        // The target is the body's target, as JSON the server parses.
        let sentBody = try object(restore.body)
        #expect(NSDictionary(dictionary: try object(Data(try #require(first["target"]).utf8)))
            .isEqual(to: try #require(sentBody["target"] as? [String: Any])))
        let withdrawBody = try object(withdraw.body)
        #expect(NSDictionary(dictionary: try object(Data(try #require(second["target"]).utf8)))
            .isEqual(to: try #require(withdrawBody["target"] as? [String: Any])))
    }

    @Test(arguments: [(409, LioTripUndoWire.Reply.changed), (403, .refused), (503, .other), (500, .other), (401, .other), (400, .other),
                      (429, .other), (404, .other)])
    func theServersStatusesAreRead(status: Int, reply: LioTripUndoWire.Reply) async throws {
        let value = try request()
        let exit = UndoExit([.json(status, #"{"failure":"unavailable"}"#), .json(status, #"{"failure":"unavailable"}"#)])
        let http = try client(exit)
        #expect(try await http.submitTripUndo(value) == reply)
        #expect(try await http.readTripUndoReceipt(value) == reply)
    }

    @Test func a200ThatIsNotTheContractsReceiptForThisActionIsNotAnAnswer() async throws {
        let value = try request()
        let bodies = [
            receiptJSON(value, version: "LIO-trip-undo-receipt.3"), receiptJSON(value, version: "LIO-trip-undo-receipt.5"),
            receiptJSON(value, action: "undo-" + String(repeating: "0", count: 40)),
            receiptJSON(value, conversation: "lio-dialogue-ffffffffffffffffffffffffffffffff"),
            #"{"version":"LIO-trip-undo-receipt.4","conversation_id":"\#(conversation)","action_id":"\#(value.actionID)"}"#,
            #"{"version":"LIO-trip-undo-receipt.4","conversation_id":"\#(conversation)","action_id":"\#(value.actionID)","committed":true,"x":1}"#,
            #"{"version":"LIO-trip-undo-receipt.4","conversation_id":"\#(conversation)","action_id":"\#(value.actionID)","committed":"true"}"#,
            #"{"version":"LIO-trip-undo-receipt.4","conversation_id":"\#(conversation)","action_id":"\#(value.actionID)","committed":true,"committed":false}"#,
            "{}", "[]", "not json", "",
        ]
        for body in bodies {
            let exit = UndoExit([.json(200, body)])
            #expect(try await client(exit).submitTripUndo(value) == .other, "\(body)")
        }
        #expect(try await client(UndoExit([.plain(200, receiptJSON(value))])).submitTripUndo(value) == .other, "not JSON")
    }

    // MARK: The contract's own examples (main: lio-answer-rich-examples.1.json), both kinds

    private func contractReceipts() throws -> [(name: String, receipt: Receipt, undo: [String: Any])] {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let file = try object(Data(contentsOf: root.appendingPathComponent("contracts/message/lio-answer-rich-examples.1.json")))
        let valid = try #require(file["valid"] as? [[String: Any]])
        var found: [(String, Receipt, [String: Any])] = []
        for example in valid {
            guard let rich = example["rich"] as? [String: Any], let wire = rich["trip_receipt"] as? [String: Any],
                  let undo = wire["undo"] as? [String: Any], undo["state"] as? String == "available" else { continue }
            let json = String(decoding: try JSONSerialization.data(withJSONObject: rich), as: UTF8.self)
            let page = Data("""
                {"version":"LIO-timeline.2","conversation_id":"\(conversation)","messages":[
                {"message_id":"m1","text":"Q","answer":"好的，已经帮你排好了。","status":"completed","sources":[],"rich":\(json)}],"next_before":null}
                """.utf8)
            let row = try #require(try LioTimelineWire.decodePage(page, for: conversation, version: .v2).messages.first)
            found.append((example["name"] as? String ?? "", try #require(row.rich?.tripReceipt, "\(example["name"] ?? "")"), undo))
        }
        return found
    }

    @Test func everyAvailableUndoOfTheContractsExamplesMakesItsRequestWithTheReceiptsOwnTarget() throws {
        let all = try contractReceipts()
        #expect(all.count == 6, "the contract has 6 valid examples with an available undo")
        #expect(all.contains { $0.undo["kind"] as? String == "withdraw_created" }, "and one of them is a withdrawal")
        for (name, receipt, undo) in all {
            let request = try #require(LioTripUndoWire.Request(receipt: receipt, conversationID: conversation), "\(name)")
            let body = try object(request.body)
            let kind = undo["kind"] as? String ?? "restore"
            #expect(body["version"] as? String == (kind == "restore" ? "LIO-trip-undo.4" : "LIO-trip-undo.5"), "\(name)")
            #expect(body["action_id"] as? String == undo["action_id"] as? String, "\(name)")
            #expect(body["conversation_id"] as? String == conversation, "\(name)")
            // The target is copied as it is in the receipt: the same fields, the same values.
            #expect(NSDictionary(dictionary: try #require(body["target"] as? [String: Any]))
                .isEqual(to: try #require(undo["target"] as? [String: Any])), "\(name)")
            #expect(Set(body.keys) == ["version", "action_id", "conversation_id", "target"], "\(name)")
        }
    }

    @Test func aWithdrawalGoesToTheSameRoutesWithVersion5AndAnswersWithReceipt4() async throws {
        let all = try contractReceipts()
        let created = try #require(all.first { $0.undo["kind"] as? String == "withdraw_created" })
        let request = try #require(LioTripUndoWire.Request(receipt: created.receipt, conversationID: conversation))
        #expect(request.kind == .withdrawCreated && created.receipt.committedVersion == 1)
        let exit = UndoExit([.json(200, receiptJSON(request)), .json(200, receiptJSON(request))])
        let http = try client(exit)
        #expect(try await http.submitTripUndo(request) == .committed)
        #expect(try await http.readTripUndoReceipt(request) == .committed)
        let calls = await exit.calls
        #expect(calls[0].method == .post && calls[0].path == "/v4/lio/trip-undos" && calls[0].body == request.body)
        let query = try #require(URLComponents(string: "https://x" + (calls[1].path ?? ""))).queryItems ?? []
        #expect(calls[1].method == .get && query.contains(URLQueryItem(name: "version", value: "LIO-trip-undo.5")))
        #expect(query.contains(URLQueryItem(name: "action_id", value: request.actionID)))
        // A server that answered with receipt 5 would not be the contract's: no answer.
        let other = UndoExit([.json(200, receiptJSON(request, version: "LIO-trip-undo-receipt.5"))])
        #expect(try await client(other).submitTripUndo(request) == .other)
    }

    // MARK: What the App makes of it

    private func tripClient(_ send: [LioTripUndoWire.Reply?], read: [LioTripUndoWire.Reply?] = []) -> (LioTripUndoClient, Counter) {
        let counter = Counter(send: send, read: read)
        return (LioTripUndoClient(send: { try counter.sent($0) }, read: { try counter.asked($0) }), counter)
    }

    @Test(arguments: [(LioTripUndoWire.Reply.committed, LioTripUndoClient.Outcome.undone), (.changed, .superseded), (.refused, .expired),
                      (.notCommitted, .notDone)])
    func anAnswerThatIsKnownIsNotAskedAboutAgain(reply: LioTripUndoWire.Reply, outcome: LioTripUndoClient.Outcome) async throws {
        let (client, counter) = tripClient([reply])
        #expect(await client.undo(try request()) == outcome)
        #expect(counter.posts.count == 1 && counter.gets.isEmpty)
    }

    @Test func anAnswerThatIsNotKnownIsAskedAboutWithTheSameActionIDAndNeverASecondPost() async throws {
        let value = try request()
        for (first, read, outcome) in [(nil as LioTripUndoWire.Reply?, LioTripUndoWire.Reply.committed as LioTripUndoWire.Reply?, LioTripUndoClient.Outcome.undone),
                                       (.other, .notCommitted, .notDone), (nil, .changed, .superseded), (.other, .refused, .expired),
                                       (nil, nil, .unknown), (.other, .other, .unknown)] {
            let (client, counter) = tripClient([first], read: [read])
            #expect(await client.undo(value) == outcome)
            #expect(counter.posts.map(\.actionID) == [value.actionID] && counter.gets.map(\.actionID) == [value.actionID])
            #expect(counter.posts.map(\.body) == [value.body], "the same bytes")
        }
    }

    @Test func aSecondTapWhileTheFirstIsBeingSentSendsNothing() async throws {
        let value = try request()
        let gate = Gate()
        let counter = Counter(send: [.committed], read: [])
        let client = LioTripUndoClient(send: { request in
            await gate.wait()
            return try counter.sent(request)
        }, read: { try counter.asked($0) })
        async let first = client.undo(value)
        for _ in 0..<50 where !client.isSending(value.actionID) { await Task.yield() }
        #expect(client.isSending(value.actionID))
        #expect(await client.undo(value) == .inFlight)
        #expect(await client.confirm(value) == .inFlight)
        await gate.open()
        #expect(await first == .undone)
        #expect(counter.posts.count == 1 && counter.gets.isEmpty)
        #expect(!client.isSending(value.actionID), "free again once it ended")
    }

    @Test func aRetryAfterNothingWasKnownUsesTheSameActionAndCanSucceed() async throws {
        let value = try request()
        let (client, counter) = tripClient([nil, .committed], read: [nil])
        #expect(await client.undo(value) == .unknown)
        #expect(await client.undo(value) == .undone)
        #expect(counter.posts.map(\.actionID) == [value.actionID, value.actionID])
        #expect(counter.gets.count == 1)
    }

    @Test func confirmOnlyAsks() async throws {
        let value = try request()
        let (client, counter) = tripClient([], read: [.committed, nil, .notCommitted])
        #expect(await client.confirm(value) == .undone)
        #expect(await client.confirm(value) == .unknown)
        #expect(await client.confirm(value) == .notDone)
        #expect(counter.posts.isEmpty && counter.gets.count == 3)
    }

    @Test func twoActionsAreIndependent() async throws {
        let one = try request(), two = try request(restore: false, saveID: "lio-plan-run-first")
        let gate = Gate()
        let counter = Counter(send: [.committed, .committed], read: [])
        let client = LioTripUndoClient(send: { request in
            if request.actionID == one.actionID { await gate.wait() }
            return try counter.sent(request)
        }, read: { try counter.asked($0) })
        async let first = client.undo(one)
        for _ in 0..<50 where !client.isSending(one.actionID) { await Task.yield() }
        #expect(await client.undo(two) == .undone)
        await gate.open()
        #expect(await first == .undone)
        #expect(counter.posts.count == 2)
    }

    @MainActor private final class Counter {
        var send: [LioTripUndoWire.Reply?]
        var read: [LioTripUndoWire.Reply?]
        private(set) var posts: [LioTripUndoWire.Request] = []
        private(set) var gets: [LioTripUndoWire.Request] = []
        init(send: [LioTripUndoWire.Reply?], read: [LioTripUndoWire.Reply?]) { self.send = send; self.read = read }
        func sent(_ request: LioTripUndoWire.Request) throws -> LioTripUndoWire.Reply {
            posts.append(request)
            guard !send.isEmpty, let reply = send.removeFirst() else { throw URLError(.networkConnectionLost) }
            return reply
        }
        func asked(_ request: LioTripUndoWire.Request) throws -> LioTripUndoWire.Reply {
            gets.append(request)
            guard !read.isEmpty, let reply = read.removeFirst() else { throw URLError(.notConnectedToInternet) }
            return reply
        }
    }

    private actor Gate {
        private var opened = false
        private var waiting: [CheckedContinuation<Void, Never>] = []
        func wait() async { if opened { return }; await withCheckedContinuation { waiting.append($0) } }
        func open() { opened = true; waiting.forEach { $0.resume() }; waiting = [] }
    }
}
