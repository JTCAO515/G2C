import Foundation
import HTTPTypes
import OpenAPIRuntime
import Testing
import CJMessageClient
@testable import CJMessageHTTP

@MainActor
struct LioNative4ClientTests {
    private let cid = "lio-dialogue-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

    @Test(arguments: [LioTimelineWire.Version.v2, .v4])
    func firstOriginalRestoresWithoutChangingItsProtocol(_ version: LioTimelineWire.Version) async throws {
        let store = Native4Store()
        let scope = try StorageScope(environment: "synthetic", account: UUID().uuidString)
        let recovery = MessageRecovery(storage: store)
        let lease = try recovery.activate(scope)
        let exit = Native4Exit(page: try page(), losesReceipt: true)
        let client = try makeClient(recovery, scope: scope, lease: lease, exit: exit)
        let original = try LioTimelineWire.Send(messageID: "first", text: "Se\u{301}jour 北京", locale: .english,
                                                destination: .newChat, version: version)
        await #expect(throws: URLError.self) { _ = try await client.submit(original) }
        #expect(try recovery.action(messageID: "first", lease: lease)?.originalUTF8 == original.originalUTF8)
        recovery.invalidate()
        let restored = MessageRecovery(storage: store)
        let restoredLease = try restored.activate(scope)
        let reopened = try makeClient(restored, scope: scope, lease: restoredLease, exit: exit)
        let next = try LioTimelineWire.Send(messageID: "next", text: "Another trip", locale: .english,
                                           destination: .newChat, version: .v4)
        await #expect(throws: RecoveryError.queryOnly) { _ = try await reopened.submit(next) }
        #expect(try await reopened.reconcileFirstChat(messageID: "first") == cid)
        let record = try #require(try restored.action(messageID: "first", lease: restoredLease))
        #expect(record.phase == .accepted && record.originalUTF8 == original.originalUTF8)
        let calls = await exit.calls
        #expect(calls.map(\.path).first == "/v\(version.rawValue)/lio/messages")
        #expect(calls.count == 2 && calls[0].body == original.originalUTF8 && calls[1].body == nil)
        let lookup = try #require(URLComponents(string: calls[1].path))
        #expect(lookup.path == "/v\(version.rawValue)/lio/messages")
        #expect(lookup.queryItems?.first(where: { $0.name == "input_sha256" })?.value == record.inputSHA256)
        #expect(try reopened.savedChats().map(\.id) == [cid])
    }

    @Test func lookupPreservesTheActualNestedReceiptBytes() throws {
        let original = try LioTimelineWire.Send(messageID: "first", text: "Trip", locale: .english,
                                                destination: .newChat, version: .v4)
        let raw = #"{ "conversation_id" : "li\u006f-dialogue-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "version" : "LIO-message-receipt.4", "message_id":"first" }"#
        let lookup = Data("{\n \"receipt\" : \(raw), \"version\":\"LIO-message-lookup.4\"\n}".utf8)
        let confirmed = try original.confirmLookup(lookup)
        let result = try #require(confirmed)
        #expect(result.id == cid && result.receipt == Data(raw.utf8))
        #expect(try original.confirmLookup(Data(#"{"version":"LIO-message-lookup.4","receipt":null}"#.utf8)) == nil)
    }

    @Test func native4ReceiptsRejectDowngradesAndOpenShapes() throws {
        let original = try LioTimelineWire.Send(messageID: "first", text: "Trip", locale: .english,
                                                destination: .existing(cid), version: .v4)
        let good = #"{"version":"LIO-message-receipt.4","message_id":"first","conversation_id":"lio-dialogue-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}"#
        #expect(try original.confirm(Data(good.utf8)) == cid)
        for bad in [good.replacingOccurrences(of: ".4", with: ".2"),
                    good.replacingOccurrences(of: "first", with: "different"),
                    good.replacingOccurrences(of: String(repeating: "a", count: 32), with: String(repeating: "b", count: 32)),
                    good.replacingOccurrences(of: "{", with: #"{"extra":true,"#),
                    good.replacingOccurrences(of: #""message_id":"first""#, with: #""message_id":"first","message_id":"first""#)] {
            #expect(throws: Error.self) { try original.confirm(Data(bad.utf8)) }
        }
        #expect(throws: Error.self) { try original.confirm(Data(repeating: 32, count: 65_537)) }
        #expect(throws: Error.self) { try original.confirmLookup(Data(#"{"version":"LIO-message-lookup.4","receipt":null,"extra":true}"#.utf8)) }
        #expect(throws: Error.self) { try LioTimelineWire.Send(messageID: "first", text: "Trip", locale: .english,
                                                             destination: .newChat, version: .v1) }
    }

    @Test func restoredNative4FirstQuestionRequiresItsClosedShapeAndOriginalID() throws {
        let original = try LioTimelineWire.Send(messageID: "first", text: "Trip", locale: .english,
                                                destination: .newChat, version: .v4)
        let decoded = try #require(try LioTimelineWire.Send.recordedFirst(original.originalUTF8, messageID: "first"))
        #expect(decoded.original.originalUTF8 == original.originalUTF8 && decoded.original.version == .v4)
        var fields = try #require(JSONSerialization.jsonObject(with: original.originalUTF8) as? [String: Any])
        fields["extra"] = true
        let extra = try JSONSerialization.data(withJSONObject: fields)
        #expect(throws: Error.self) { try LioTimelineWire.Send.recordedFirst(extra, messageID: "first") }
        #expect(throws: Error.self) { try LioTimelineWire.Send.recordedFirst(original.originalUTF8, messageID: "another") }
    }

    @Test func explicitNative4ReadRetainsFieldsAndLegacyDecoderCannotFlattenIt() async throws {
        let bytes = try page()
        let recovery = MessageRecovery(storage: Native4Store())
        let scope = try StorageScope(environment: "synthetic", account: UUID().uuidString)
        let lease = try recovery.activate(scope)
        let exit = Native4Exit(page: bytes)
        let client = try makeClient(recovery, scope: scope, lease: lease, exit: exit)
        let result = try await client.exploration(conversationID: cid)
        #expect(result.inputUTF8 == bytes && result.conversationID == cid)
        #expect(result.messages[0].segments.first?.purpose == .direction)
        #expect(result.messages[0].questions[0].options.map(\.id) == ["interests.history", "interests.food", "interests.nature"])
        #expect(result.messages[0].exits.count == 2)
        #expect(throws: Error.self) { try LioTimelineWire.decodePage(bytes, version: .v4) }
        await #expect(throws: Error.self) { _ = try await client.exploration(conversationID: cid, before: result.messages[0].id) }
        #expect(await exit.calls.allSatisfy { $0.path.hasPrefix("/v4/lio/timeline?") && $0.body == nil })
        recovery.invalidate()
        await #expect(throws: Error.self) { _ = try await client.exploration(conversationID: cid) }
        #expect(await exit.calls.count == 2)
    }

    @Test(arguments: [String(repeating: "m", count: 128), String(repeating: "m", count: 129),
                      String(repeating: "m", count: 256), String(repeating: "界", count: 85) + "a", "e\u{301}", "  m  "])
    func native4KeepsTheExistingMessageIDByteDomain(_ mid: String) throws {
        let original = try LioTimelineWire.Send(messageID: mid, text: "Trip", locale: .english,
                                                destination: .newChat, version: .v4)
        let restored = try LioTimelineWire.Send.recordedFirst(original.originalUTF8, messageID: mid)
        #expect(restored?.original.originalUTF8 == original.originalUTF8)
        let fields = ["version":"LIO-message-receipt.4", "message_id":mid, "conversation_id":cid]
        let response = try JSONSerialization.data(withJSONObject: fields)
        #expect(try original.confirm(response) == cid)
        if mid == "e\u{301}" {
            var different = fields; different["message_id"] = "\u{e9}"
            let normalized = try JSONSerialization.data(withJSONObject: different)
            #expect(throws: Error.self) { try original.confirm(normalized) }
        }
        #expect(throws: MessageHTTPFailure.invalidConfiguration) {
            try LioTimelineWire.Send(messageID: String(repeating: "m", count: 257), text: "Trip", locale: .english,
                                     destination: .newChat, version: .v4)
        }
    }

    @Test func successfulNative4SubmissionStoresItsVerifiedReceipt() async throws {
        let scope = try StorageScope(environment: "synthetic", account: UUID().uuidString)
        let recovery = MessageRecovery(storage: Native4Store())
        let lease = try recovery.activate(scope)
        let exit = Native4Exit(page: try page())
        let client = try makeClient(recovery, scope: scope, lease: lease, exit: exit)
        let original = try LioTimelineWire.Send(messageID: "first", text: "Trip", locale: .english,
                                                destination: .newChat, version: .v4)
        guard case .accepted(let id) = try await client.submit(original) else { Issue.record("No verified receipt"); return }
        #expect(id == cid)
        #expect(try recovery.action(messageID: "first", lease: lease)?.phase == .accepted)
        #expect(try client.savedChats().map(\.id) == [cid])
        #expect(await exit.calls.count == 1)
    }

    @Test(arguments: [400, 429, 503])
    func rejectionsAndUnknownResponsesNeverSelectAnOlderProtocol(_ status: Int) async throws {
        let scope = try StorageScope(environment: "synthetic", account: UUID().uuidString)
        let recovery = MessageRecovery(storage: Native4Store())
        let lease = try recovery.activate(scope)
        let exit = Native4Exit(page: try page(), postStatus: status)
        let client = try makeClient(recovery, scope: scope, lease: lease, exit: exit)
        let original = try LioTimelineWire.Send(messageID: "first", text: "Trip", locale: .english,
                                                destination: .newChat, version: .v4)
        if status == 503 {
            await #expect(throws: MessageHTTPFailure.exchangeUnknown) { _ = try await client.submit(original) }
            #expect(try recovery.action(messageID: "first", lease: lease)?.phase == .queryRequired)
        } else {
            let result = try await client.submit(original)
            if status == 429 { guard case .dailyLimit = result else { Issue.record("Expected this request's quota rejection"); return } }
            else { guard case .rejected = result else { Issue.record("Expected rejection"); return } }
            #expect(try client.firstChatCanReturnToDraft(messageID: "first"))
        }
        #expect(await exit.calls.map(\.path) == ["/v4/lio/messages"])
        #expect(await exit.calls.first?.body == original.originalUTF8)
        #expect(throws: Error.self) { try LioNative4Envelope.rejection(Data(#"{"failure":"quota","committed":true}"#.utf8), expected: "quota") }
    }

    @Test(arguments: [false, true])
    func ownerChangeOrCancellationWhileReadingCannotReturnAnOldPage(_ cancelled: Bool) async throws {
        let scope = try StorageScope(environment: "synthetic", account: UUID().uuidString)
        let recovery = MessageRecovery(storage: Native4Store())
        let lease = try recovery.activate(scope)
        let exit = Native4Exit(page: try page(), holdsPage: true)
        let client = try makeClient(recovery, scope: scope, lease: lease, exit: exit)
        let operation = Task { try await client.exploration(conversationID: cid) }
        await exit.waitForPage()
        if cancelled { operation.cancel() }
        else { _ = try recovery.activate(StorageScope(environment: "synthetic", account: UUID().uuidString)) }
        await exit.releasePage()
        if cancelled { await #expect(throws: CancellationError.self) { _ = try await operation.value } }
        else { await #expect(throws: RecoveryError.inactive) { _ = try await operation.value } }
        #expect(await exit.calls.count == 1)
    }

    private func page() throws -> Data {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let data = try Data(contentsOf: root.appendingPathComponent("contracts/message/lio-exploration-examples.4.json"))
        let fields = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let value = try #require(fields["en"])
        return try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes])
    }

    private func makeClient(_ recovery: MessageRecovery, scope: StorageScope, lease: Lease,
                        exit: Native4Exit) throws -> LioTimelineHTTP {
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")),
                                           maximumRequestBytes: 16_384, maximumResponseBytes: 4_500_000)
        let transport = try NoRedirectTransport(interceptedTransport: exit, messageEndpoint: endpoint,
            validateMessage: { _ = try recovery.localProjection(scope: scope, lease: lease) }, lio: true)
        return LioTimelineHTTP(scope: scope, lease: lease, credentials: Native4Credentials(),
                               transport: transport, firstChatRecovery: recovery)
    }
}

@MainActor private final class Native4Store: SecureMessageStorage {
    private var values: [String: Snapshot] = [:]
    func load(scope: StorageScope) throws -> Snapshot? { values[scope.environment + "\0" + scope.account] }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { values[scope.environment + "\0" + scope.account] = snapshot }
}
@MainActor private final class Native4Credentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "synthetic-only" }
}
private actor Native4Exit: ClientTransport {
    struct Call: Sendable { let path: String; let body: Data? }
    private let page: Data
    private let losesReceipt: Bool
    private let postStatus: Int?
    private let holdsPage: Bool
    private var pageEntered = false
    private var pageWaiters: [CheckedContinuation<Void, Never>] = []
    private var heldPage: CheckedContinuation<Void, Never>?
    private var original: [String: Any]?
    private(set) var calls: [Call] = []
    init(page: Data, losesReceipt: Bool = false, postStatus: Int? = nil, holdsPage: Bool = false) {
        self.page = page; self.losesReceipt = losesReceipt; self.postStatus = postStatus; self.holdsPage = holdsPage
    }
    func waitForPage() async {
        if pageEntered { return }
        await withCheckedContinuation { pageWaiters.append($0) }
    }
    func releasePage() { heldPage?.resume(); heldPage = nil }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let path = try #require(request.path)
        let bytes: Data?
        if let body { bytes = try await Data(collecting: body, upTo: 16_384) } else { bytes = nil }
        calls.append(Call(path: path, body: bytes))
        var response = HTTPResponse(status: .ok); response.headerFields[.contentType] = "application/json"
        if path.hasPrefix("/v4/lio/timeline") {
            pageEntered = true
            if holdsPage {
                await withCheckedContinuation { continuation in
                    heldPage = continuation
                    for waiter in pageWaiters { waiter.resume() }
                    pageWaiters = []
                }
            }
            return (response, HTTPBody(page))
        }
        if let bytes {
            original = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
            if let postStatus {
                response.status = .init(code: postStatus)
                return (response, HTTPBody(postStatus == 429 ? #"{"failure":"quota"}"# : #"{"failure":"unavailable"}"#))
            }
            if losesReceipt { throw URLError(.networkConnectionLost) }
        }
        let fields = try #require(original), protocolName = try #require(fields["version"] as? String)
        let version = String(try #require(protocolName.last))
        let receipt = "{\"version\":\"LIO-message-receipt.\(version)\",\"message_id\":\"first\",\"conversation_id\":\"lio-dialogue-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"}"
        return (response, HTTPBody(bytes == nil ? "{\"version\":\"LIO-message-lookup.\(version)\",\"receipt\":\(receipt)}" : receipt))
    }
}
