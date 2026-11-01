import Foundation
import CryptoKit
import Testing
import CJTripClient
import CJMessageHTTP
import CJMessageKeys
import OpenAPIRuntime
import HTTPTypes
@testable import CJManualPreviewClient

private actor ScopedWire: ClientTransport {
    var requests: [(String, Data?)] = []
    var original: Data?
    var discoveryOverride: Data?
    var loseACK = false
    var emptyReceipt = false
    var callback: (@MainActor @Sendable () -> Void)?
    func useDiscovery(_ bytes: Data) { discoveryOverride = bytes }
    func configure(loseACK: Bool = false, emptyReceipt: Bool = false, callback: (@MainActor @Sendable () -> Void)? = nil) {
        self.loseACK = loseACK; self.emptyReceipt = emptyReceipt; self.callback = callback
    }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes: Data?
        if let body { bytes = try await Data(collecting: body, upTo: 32768) } else { bytes = nil }
        requests.append((request.path!, bytes))
        let output: Data
        if operationID == "discoverScopedTripV1" { output = try discoveryOverride ?? scopedFixture() }
        else {
            if let bytes { original = bytes }
            if loseACK, bytes != nil { throw PreviewFailure.unknown }
            let action = try ScopedAction(originalUTF8: #require(original))
            let receipt: Any = emptyReceipt ? NSNull() : ["action_id": action.actionID, "kind": action.kind.rawValue,
                "proposal_id": action.proposalID, "candidate_hash": action.candidateHash, "trip_id": "trip-518cedd7-dfe0-4efe-bdad-bd6d997748aa", "committed_version": action.kind == .accept ? 3 as Any : NSNull()]
            output = try canonical(["version": "TRIP-scoped-result.1", "request_id": "00000000-0000-4000-8000-000000000337", "receipt": receipt])
        }
        if let callback { await callback() }
        var response = HTTPResponse(status: .ok)
        response.headerFields[.init("x-request-id")!] = "00000000-0000-4000-8000-000000000337"
        response.headerFields[.cacheControl] = "no-store"
        return (response, HTTPBody(output))
    }
}
@MainActor private final class ScopedHarness {
    let root: URL
    let binding = TripBinding(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID())
    let wire = ScopedWire()
    let originals: ScopedJournal<ScopedOriginal>
    let settlements: ScopedJournal<ScopedSettlement>
    var current = true
    var sourceCurrent = true
    init() throws {
        root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        let a = root.appendingPathComponent("originals"), b = root.appendingPathComponent("settlements")
        for p in [a, b] { try FileManager.default.createDirectory(at: p, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700]) }
        let key = SymmetricKey(size: .bits256), kid = UUID()
        let namespace = MessageKeyNamespace(environment: binding.environment, account: binding.account, purpose: .localTripPendingV1)
        originals = try .init(directory: a, maximumBytes: 6_000_000, maximumRecords: 20, namespace: namespace, keyID: kid, domain: "CJScopedOriginal.1", key: { key })
        settlements = try .init(directory: b, maximumBytes: 7_000_000, maximumRecords: 20, namespace: namespace, keyID: kid, domain: "CJScopedSettlement.1", key: { key })
    }
    func client() throws -> ScopedTripClient {
        try .init(endpoint: MessageEndpoint(url: URL(string: "http://127.0.0.1:1234")!, maximumRequestBytes: 32768, maximumResponseBytes: 4_000_000, allowLoopbackHTTP: true),
            binding: binding, credentials: { [self] _ in guard current else { throw PreviewFailure.retired }; return "synthetic-bearer" },
            validate: { [self] in guard current else { throw PreviewFailure.retired } }, transport: wire, originals: originals, settlements: settlements)
    }
    func read(_ client: ScopedTripClient) async throws -> ScopedCandidateRead {
        try await client.discover(original: scopedReference(scopedFixture())) { [self] in guard sourceCurrent else { throw PreviewFailure.retired } }
    }
}
@MainActor struct ScopedRuntimeTests {
    @Test func originalUnicodeAndQueryPunctuationSurviveTheCQueryBoundary() async throws {
        let h = try ScopedHarness(), client = try h.client()
        let message = "原消息-e\u{301} +/?&%", run = "原运行-+ &%/?"
        var root = try #require(JSONSerialization.jsonObject(with: scopedFixture()) as? [String: Any])
        var d = root["discovery"] as! [String: Any], ref = d["reference"] as! [String: Any]
        ref["message_id"] = message; ref["run_id"] = run; d["reference"] = ref
        var proposal = d["proposal"] as! [String: Any], scope = proposal["scope"] as! [String: Any]
        scope["reference"] = ref; proposal["scope"] = scope; d["proposal"] = proposal; root["discovery"] = d
        let bytes = try canonical(root), original = try scopedReference(bytes)
        await h.wire.useDiscovery(bytes)
        let read = try await client.discover(original: original, validateOriginal: {})
        #expect(Data(read.value.reference.messageID.utf8) == Data(message.utf8))
        let path = try #require(await h.wire.requests.first?.0)
        let query = try #require(URLComponents(string: "http://127.0.0.1" + path)?.percentEncodedQuery)
        let decoded = try query.split(separator: "&").reduce(into: [String: String]()) { result, part in
            let pair = part.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
            let key = try #require(String(pair[0]).removingPercentEncoding)
            // The owning C parse_qsl decodes form-query plus as a space.
            result[key] = try #require(String(pair[1]).replacingOccurrences(of: "+", with: " ").removingPercentEncoding)
        }
        #expect(Data(try #require(decoded["message_id"]).utf8) == Data(message.utf8))
        #expect(Data(try #require(decoded["run_id"]).utf8) == Data(run.utf8))
    }
    @Test func originalBytesAreDurableBeforeOnePostAndReopeningQueriesOnly() async throws {
        let h = try ScopedHarness(), client = try h.client(), read = try await h.read(client)
        let work = try client.stage(.accept, read: read)
        let retained = try #require(h.originals.pending().first)
        #expect(retained.actionID == work.actionID)
        let result = try await client.perform(work)
        guard case .confirmed(let receipt) = result else { Issue.record("expected original receipt"); return }
        #expect(receipt.committedVersion == 3 && receipt.actionID == work.actionID)
        await #expect(throws: (any Error).self) { try await client.perform(work) }
        let restored = try h.client()
        #expect(try restored.originalActions().map(\.actionID) == [work.actionID])
        guard case .confirmed = try await restored.queryOriginal(work.actionID) else { Issue.record("expected restored receipt"); return }
        let requests = await h.wire.requests
        #expect(requests.filter { $0.0 == "/v1/trip-scoped-actions" }.map(\.1) == [retained.actionUTF8])
        #expect(requests.last?.0.contains("action_id=" + work.actionID) == true)
        #expect(throws: (any Error).self) { try client.stage(.reject, read: read) }
    }
    @Test func ACKLossAndNullStayUnknownAndDoNotMintReplacement() async throws {
        let h = try ScopedHarness(), client = try h.client(), read = try await h.read(client)
        let work = try client.stage(.accept, read: read)
        await h.wire.configure(loseACK: true)
        await #expect(throws: (any Error).self) { try await client.perform(work) }
        let reopened = try h.client()
        await h.wire.configure(emptyReceipt: true)
        guard case .unknown = try await reopened.queryOriginal(work.actionID) else { Issue.record("null must remain unknown"); return }
        #expect(try h.settlements.pending().isEmpty)
        #expect(throws: (any Error).self) { try client.stage(.accept, read: read) }
        await h.wire.configure()
        guard case .confirmed(let receipt) = try await reopened.queryOriginal(work.actionID) else { Issue.record("expected reconciliation"); return }
        #expect(receipt.actionID == work.actionID && receipt.committedVersion == 3)
        #expect(await h.wire.requests.filter { $0.0 == "/v1/trip-scoped-actions" }.count == 1)
    }
    @Test func lateDiscoveryAndRetiredDecisionCannotEscapeSourceOrAccount() async throws {
        let h = try ScopedHarness(), client = try h.client()
        await h.wire.configure(callback: { h.sourceCurrent = false })
        await #expect(throws: (any Error).self) { try await h.read(client) }
        h.sourceCurrent = true; await h.wire.configure()
        let read = try await h.read(client), work = try client.stage(.reject, read: read)
        h.current = false
        await #expect(throws: (any Error).self) { try await client.perform(work) }
        #expect(throws: (any Error).self) { try client.originalActions() }
        #expect(await h.wire.requests.allSatisfy { !$0.0.hasPrefix("/v1/trip-scoped-actions") })
    }
}
