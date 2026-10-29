import Foundation
import CryptoKit
import Testing
import HTTPTypes
import OpenAPIRuntime
import CJMessageClient
@testable import CJMessageHTTP

@MainActor private final class PermitMemory: SecureMessageStorage {
    private struct Key: Hashable { let environment: Data; let account: Data }
    private var snapshots: [Key: Snapshot] = [:]
    var onSave: (() -> Void)?
    func load(scope: StorageScope) throws -> Snapshot? { snapshots[Key(environment: Data(scope.environment.utf8), account: Data(scope.account.utf8))] }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws {
        snapshots[Key(environment: Data(scope.environment.utf8), account: Data(scope.account.utf8))] = snapshot
        onSave?()
    }
}
@MainActor private final class PermitCredentials: MessageCredentialsProvider {
    var calls = 0
    var beforeReturn: (() -> Void)?
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? {
        calls += 1
        beforeReturn?()
        return "synthetic-only"
    }
}
private actor PermitServer: ClientTransport {
    var sequence = 0
    var posted: [Data] = []
    var generation = "g1"
    var headPresent = true
    var receiptDigest: String?
    var failPost = false
    var statusBody: String?
    var responseCode = 200
    var postConflict: String?
    func rejectPost(_ code: String?) { postConflict = code }
    func loseNextPost() { failPost = true }
    func overrideStatus(_ body: String?, code: Int = 200) { statusBody = body; responseCode = code }
    func status(sequence: Int, generation: String = "g1", head: Bool = true, digest: String? = nil) {
        self.sequence = sequence; self.generation = generation; headPresent = head; receiptDigest = digest
    }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let trace = UUID().uuidString
        let value: [String: Any]
        if request.method == .get {
            let receipt: Any = receiptDigest.map { ["message_id": "m1", "conversation_id": "chat", "generation": "g1", "sequence": 2, "run_id": "run1", "input_sha256": $0] as [String: Any] } ?? NSNull()
            let head: Any = headPresent ? ["conversation_id": "chat", "generation": generation, "last_sequence": sequence] as [String: Any] : NSNull()
            value = ["request_id": trace, "receipt": receipt, "head": head]
        } else {
            let raw = try await Data(collecting: body!, upTo: 10000)
            posted.append(raw)
            if failPost { failPost = false; throw URLError(.networkConnectionLost) }
            if let postConflict {
                value = ["request_id": trace, "error": ["code": postConflict, "category": "conflict", "message_en": "Conflict", "message_zh": "冲突", "outcome": "failed", "recovery": postConflict == "INPUT_CONFLICT" ? "do_not_retry" : "reconcile_original"]]
            } else {
                let input = try JSONSerialization.jsonObject(with: raw) as! [String: Any]
                sequence += 1
                value = ["request_id": trace, "receipt": ["message_id": input["message_id"]!, "conversation_id": "chat", "generation": "g1", "sequence": sequence, "run_id": "run1", "input_sha256": SHA256.hash(data: raw).map { String(format: "%02x", $0) }.joined()]]
            }
        }
        var response = HTTPResponse(status: .init(code: request.method == .post && postConflict != nil ? 409 : responseCode))
        response.headerFields[.contentType] = "application/json"
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        let data = request.method == .get ? statusBody.map { Data($0.replacingOccurrences(of: "$TRACE", with: trace).utf8) } : nil
        return (response, HTTPBody(try data ?? JSONSerialization.data(withJSONObject: value)))
    }
}

@MainActor private final class PermitLifetime {
    var current = true
    func validate() throws {
        guard current else { throw RecoveryError.inactive }
    }
}

@MainActor private final class PermitDiskKeys: MessageEncryptionKeyProvider {
    var available = true
    var material = MessageStorageKey(id: UUID(), key: SymmetricKey(size: .bits256))
    func existing(for scope: StorageScope, expectedID: UUID?) throws -> MessageStorageKey? {
        available ? material : nil
    }
}

@Suite @MainActor struct SendPermitTests {
    @Test func occupiedSequenceRequiresValidatedFreshHistoryIncludingAfterReopen() async throws {
        let memory = PermitMemory(), server = PermitServer()
        let state = MessageRecovery(storage: memory)
        let scope = try StorageScope(environment: UUID().uuidString, account: "a")
        let lease = try state.activate(scope)
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 10000, maximumResponseBytes: 10000)
        let client = MessageHTTPClient(recovery: state, scope: scope, endpoint: endpoint, credentials: PermitCredentials(), interceptedTestTransport: server)
        let limits = try MessageReadLimits(maximumPageItems: 20, maximumCursorBytes: 2048, maximumDecodedBytes: 10000, maximumPages: 10)
        _ = try await client.readSendHead(conversationID: "chat", lease: lease)
        try client.stageSend(messageID: "m1", conversationID: "chat", text: "original", lease: lease)
        _ = try state.beginSubmission(messageID: "m1", lease: lease)
        let other = try JSONSerialization.data(withJSONObject: ["version": "MESSAGE-send.1", "conversation_id": "chat", "message_id": "other", "text": "occupying message", "trip_id": NSNull(), "creation_intent": "none", "expected_generation": "g1", "expected_sequence": 0])
        let row: [String: Any] = ["receipt": ["message_id": "other", "conversation_id": "chat", "generation": "g1", "sequence": 1, "run_id": "r", "input_sha256": SHA256.hash(data: other).map { String(format: "%02x", $0) }.joined()], "original_utf8_base64": other.base64EncodedString(), "text": "occupying message"]
        let page = String(decoding: try JSONSerialization.data(withJSONObject: ["request_id": "$TRACE", "messages": [row], "next_cursor": NSNull()]), as: UTF8.self)
        // A page read before the verdict cannot satisfy the subsequent refresh.
        await server.overrideStatus(page)
        _ = try await client.history(conversationID: "chat", limit: 20, limits: limits, lease: lease)
        await server.overrideStatus(nil); await server.status(sequence: 1)
        #expect(try await client.reconcileSend(messageID: "m1", lease: lease) == .notAccepted)
        #expect(try !client.canStartSend(conversationID: "chat", lease: lease))
        _ = try await client.readSendHead(conversationID: "chat", lease: lease)
        #expect(throws: (any Error).self) { try client.stageSend(messageID: "new", conversationID: "chat", text: "blocked", lease: lease) }
        await server.overrideStatus("{}")
        await #expect(throws: (any Error).self) { try await client.history(conversationID: "chat", limit: 20, limits: limits, lease: lease) }
        #expect(try !client.canStartSend(conversationID: "chat", lease: lease))
        await server.overrideStatus(page)
        _ = try await client.history(conversationID: "chat", limit: 20, limits: limits, lease: lease)
        #expect(try client.canStartSend(conversationID: "chat", lease: lease))
        state.invalidate()
        let restored = MessageRecovery(storage: memory), next = try restored.activate(scope)
        let reopened = MessageHTTPClient(recovery: restored, scope: scope, endpoint: endpoint, credentials: PermitCredentials(), interceptedTestTransport: server)
        await server.overrideStatus(nil)
        _ = try await reopened.readSendHead(conversationID: "chat", lease: next)
        #expect(try !reopened.canStartSend(conversationID: "chat", lease: next))
        await server.overrideStatus(page)
        _ = try await reopened.history(conversationID: "chat", limit: 20, limits: limits, lease: next)
        try reopened.stageSend(messageID: "new", conversationID: "chat", text: "user chooses after refresh", lease: next)
        #expect(await server.posted.isEmpty)
    }

    @Test func sequenceConflictRequiresOriginalStatusBeforeResubmission() async throws {
        let state = MessageRecovery(storage: PermitMemory())
        let scope = try StorageScope(environment: UUID().uuidString, account: "a")
        let lease = try state.activate(scope), server = PermitServer()
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 10000, maximumResponseBytes: 10000)
        let client = MessageHTTPClient(recovery: state, scope: scope, endpoint: endpoint, credentials: PermitCredentials(), interceptedTestTransport: server)
        _ = try await client.readSendHead(conversationID: "chat", lease: lease)
        let original = try client.stageSend(messageID: "m1", conversationID: "chat", text: "original", lease: lease)
        await server.rejectPost("SEQUENCE_CONFLICT")
        _ = try await client.submitPrepared(messageID: "m1", lease: lease)
        #expect(try !client.hasSendHead(conversationID: "chat", lease: lease))
        await #expect(throws: (any Error).self) { try await client.submitPrepared(messageID: "m1", lease: lease, confirmRestored: true) }
        #expect(throws: (any Error).self) { try client.stageSend(messageID: "m2", conversationID: "chat", text: "replacement", lease: lease) }
        #expect(await server.posted == [original.originalUTF8])
        await server.status(sequence: 1)
        #expect(try await client.reconcileSend(messageID: "m1", lease: lease) == .notAccepted)
        await #expect(throws: (any Error).self) { try await client.submitPrepared(messageID: "m1", lease: lease, confirmRestored: true) }
        #expect(await server.posted == [original.originalUTF8])
    }

    @Test func encryptedRollbackRequiresStatusAndConfirmationAndRejectsUnreadableStorage() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let keys = PermitDiskKeys()
        let storage = try EncryptedFileStorage(directory: directory, keys: keys)
        let scope = try StorageScope(environment: UUID().uuidString, account: "a")
        let state = MessageRecovery(storage: storage), server = PermitServer()
        let lease = try state.activate(scope)
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 10000, maximumResponseBytes: 10000)
        let client = MessageHTTPClient(recovery: state, scope: scope, endpoint: endpoint, credentials: PermitCredentials(), interceptedTestTransport: server)
        _ = try await client.readSendHead(conversationID: "chat", lease: lease)
        let original = try client.stageSend(messageID: "m1", conversationID: "chat", text: "encrypted original", lease: lease)
        let file = try #require(FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil).first)
        let oldCiphertext = try Data(contentsOf: file)
        await server.loseNextPost()
        await #expect(throws: (any Error).self) { try await client.submitPrepared(messageID: "m1", lease: lease) }
        state.invalidate()
        try oldCiphertext.write(to: file, options: .atomic)
        let reopened = MessageRecovery(storage: try EncryptedFileStorage(directory: directory, keys: keys))
        let next = try reopened.activate(scope)
        let restored = MessageHTTPClient(recovery: reopened, scope: scope, endpoint: endpoint, credentials: PermitCredentials(), interceptedTestTransport: server)
        #expect(try reopened.action(messageID: "m1", lease: next)?.phase == .queryRequired)
        await #expect(throws: (any Error).self) { try await restored.submitPrepared(messageID: "m1", lease: next, confirmRestored: true) }
        #expect(try await restored.reconcileSend(messageID: "m1", lease: next) == .resubmitOriginal)
        await #expect(throws: (any Error).self) { try await restored.submitPrepared(messageID: "m1", lease: next) }
        #expect(await server.posted == [original.originalUTF8])
        _ = try await restored.submitPrepared(messageID: "m1", lease: next, confirmRestored: true)
        #expect(await server.posted == [original.originalUTF8, original.originalUTF8])
        reopened.invalidate()
        let saved = keys.material
        keys.available = false
        #expect(throws: (any Error).self) { try reopened.activate(scope) }
        keys.available = true
        keys.material = MessageStorageKey(id: saved.id, key: SymmetricKey(size: .bits256))
        #expect(throws: (any Error).self) { try reopened.activate(scope) }
        keys.material = saved
        var corrupt = try Data(contentsOf: file); corrupt[corrupt.count - 1] ^= 1
        try corrupt.write(to: file)
        #expect(throws: (any Error).self) { try reopened.activate(scope) }
        #expect(try Data(contentsOf: file) == corrupt)
        #expect(await server.posted.count == 2)
    }

    @Test func originalInputConflictStopsConversationInsteadOfRetrying() async throws {
        let state = MessageRecovery(storage: PermitMemory())
        let scope = try StorageScope(environment: UUID().uuidString, account: "a")
        let lease = try state.activate(scope), server = PermitServer()
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 10000, maximumResponseBytes: 10000)
        let client = MessageHTTPClient(recovery: state, scope: scope, endpoint: endpoint, credentials: PermitCredentials(), interceptedTestTransport: server)
        _ = try await client.readSendHead(conversationID: "chat", lease: lease)
        try client.stageSend(messageID: "m1", conversationID: "chat", text: "original", lease: lease)
        await server.loseNextPost()
        await #expect(throws: (any Error).self) { try await client.submitPrepared(messageID: "m1", lease: lease) }
        #expect(try await client.reconcileSend(messageID: "m1", lease: lease) == .resubmitOriginal)
        await server.rejectPost("INPUT_CONFLICT")
        _ = try await client.submitPrepared(messageID: "m1", lease: lease)
        #expect(try state.action(messageID: "m1", lease: lease)?.phase == .integrityError)
        _ = try await client.readSendHead(conversationID: "chat", lease: lease)
        #expect(throws: (any Error).self) { try client.stageSend(messageID: "m2", conversationID: "chat", text: "blocked", lease: lease) }
        await #expect(throws: (any Error).self) { try await client.submitPrepared(messageID: "m1", lease: lease, confirmRestored: true) }
        #expect(await server.posted.count == 2)
    }

    @Test func credentialReentryCannotSendOrReuseAnotherLeaseHead() async throws {
        let memory = PermitMemory(), credentials = PermitCredentials()
        let state = MessageRecovery(storage: memory)
        let scope = try StorageScope(environment: UUID().uuidString, account: "a")
        let other = try StorageScope(environment: scope.environment, account: "b")
        let lease = try state.activate(scope), server = PermitServer()
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 10000, maximumResponseBytes: 10000)
        let client = MessageHTTPClient(recovery: state, scope: scope, endpoint: endpoint, credentials: credentials, interceptedTestTransport: server)
        _ = try await client.readSendHead(conversationID: "chat", lease: lease)
        try client.stageSend(messageID: "m1", conversationID: "chat", text: "private", lease: lease)
        var otherLease: Lease?
        credentials.beforeReturn = { otherLease = try? state.activate(other) }
        await #expect(throws: (any Error).self) { try await client.submitPrepared(messageID: "m1", lease: lease) }
        #expect(await server.posted.isEmpty)
        #expect(try state.action(messageID: "m1", lease: #require(otherLease)) == nil)
        credentials.beforeReturn = nil
        let next = try state.activate(scope)
        #expect(try state.action(messageID: "m1", lease: next)?.phase == .queryRequired)
        #expect(try !client.hasSendHead(conversationID: "chat", lease: next))
        #expect(throws: (any Error).self) { try client.stageSend(messageID: "m2", conversationID: "chat", text: "blocked", lease: next) }
    }

    @Test func twoGatesRestrictPathBodyAndCurrentDevelopmentSession() async throws {
        let state = MessageRecovery(storage: PermitMemory())
        let scope = try StorageScope(environment: UUID().uuidString, account: "a")
        let lease = try state.activate(scope), server = PermitServer()
        let credentials = PermitCredentials(), lifetime = PermitLifetime()
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 10000, maximumResponseBytes: 10000)
        let transport = try NoRedirectTransport(interceptedTransport: server, messageEndpoint: endpoint, validateMessage: { try lifetime.validate() })
        let client = MessageHTTPClient(recovery: state, scope: scope, endpoint: endpoint, credentials: credentials, liveReadTransport: transport)
        _ = try await client.readSendHead(conversationID: "chat", lease: lease)
        let original = try client.stageSend(messageID: "m1", conversationID: "chat", text: "original", lease: lease)
        var request = HTTPRequest(method: .post, scheme: nil, authority: nil, path: "/v1/messages")
        request.headerFields[.contentType] = "application/octet-stream"
        for (method, path, operation) in [(HTTPRequest.Method.put, "/v1/messages", "receiveMessage"),
            (.put, "/v1/message-drafts?conversation_id=chat", "saveMessageDraft"),
            (.post, "/v1/run-cancellations", "cancelOriginalRun"),
            (.post, "/v1/trip-actions", "receiveMessage"), (.post, "/v1/messages?extra=1", "receiveMessage"),
            (.post, "/v1/messages", "otherOperation")] {
            var wrong = request; wrong.method = method; wrong.path = path
            await #expect(throws: (any Error).self) { try await transport.send(wrong, body: HTTPBody(original.originalUTF8), baseURL: endpoint.url, operationID: operation) }
        }
        let old = Data(String(decoding: original.originalUTF8, as: UTF8.self).replacingOccurrences(of: "MESSAGE-send.1", with: "MESSAGE-draft.1").utf8)
        await #expect(throws: (any Error).self) { try await transport.send(request, body: HTTPBody(old), baseURL: endpoint.url, operationID: "receiveMessage") }
        #expect(await server.posted.isEmpty)
        _ = try await client.submitPrepared(messageID: "m1", lease: lease)
        #expect(await server.posted == [original.originalUTF8])
        try client.stageSend(messageID: "m2", conversationID: "chat", text: "blocked", lease: lease)
        lifetime.current = false
        let before = credentials.calls
        await #expect(throws: (any Error).self) { try await client.submitPrepared(messageID: "m2", lease: lease) }
        #expect(credentials.calls == before)
        #expect(await server.posted.count == 1)
    }

    @Test func actualFactoryRejectsNonSimulatorBuild() throws {
        #if !DEBUG || !targetEnvironment(simulator)
        let endpoint = try MessageEndpoint(url: #require(URL(string: "http://127.0.0.1:12345")), maximumRequestBytes: 1000, maximumResponseBytes: 1000, allowLoopbackHTTP: true)
        #expect(throws: (any Error).self) {
            try NoRedirectTransport.developmentMessages(endpoint: endpoint, requestTimeout: 1, resourceTimeout: 2, validate: {})
        }
        #endif
    }

    @Test func currentProcessUnknownCanOnlyResubmitOriginalAfterStatus() async throws {
        let memory = PermitMemory()
        let state = MessageRecovery(storage: memory)
        let scope = try StorageScope(environment: UUID().uuidString, account: "a")
        let lease = try state.activate(scope), server = PermitServer()
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 10000, maximumResponseBytes: 10000)
        let client = MessageHTTPClient(recovery: state, scope: scope, endpoint: endpoint, credentials: PermitCredentials(), interceptedTestTransport: server)
        _ = try await client.readSendHead(conversationID: "chat", lease: lease)
        let original = try client.stageSend(messageID: "m1", conversationID: "chat", text: "original", lease: lease)
        await server.loseNextPost()
        await #expect(throws: (any Error).self) { try await client.submitPrepared(messageID: "m1", lease: lease) }
        #expect(try state.action(messageID: "m1", lease: lease)?.phase == .queryRequired)
        await #expect(throws: (any Error).self) { try await client.submitPrepared(messageID: "m1", lease: lease, confirmRestored: true) }
        #expect(try await client.reconcileSend(messageID: "m1", lease: lease) == .resubmitOriginal)
        #expect(try !client.requiresResubmissionConfirmation(messageID: "m1", lease: lease))
        var reentryDenied = false
        memory.onSave = {
            memory.onSave = nil
            do { try state.authorizeOriginalResubmission(messageID: "m1", lease: lease) }
            catch { reentryDenied = true }
        }
        _ = try await client.submitPrepared(messageID: "m1", lease: lease)
        #expect(reentryDenied)
        #expect(await server.posted == [original.originalUTF8, original.originalUTF8])
    }

    @Test func invalidStatusNeverBecomesTerminalAbsenceOrPermission() async throws {
        let state = MessageRecovery(storage: PermitMemory())
        let scope = try StorageScope(environment: UUID().uuidString, account: "a")
        let lease = try state.activate(scope), server = PermitServer()
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 10000, maximumResponseBytes: 10000)
        let client = MessageHTTPClient(recovery: state, scope: scope, endpoint: endpoint, credentials: PermitCredentials(), interceptedTestTransport: server)
        _ = try await client.readSendHead(conversationID: "chat", lease: lease)
        try client.stageSend(messageID: "m1", conversationID: "chat", text: "original", lease: lease)
        _ = try state.beginSubmission(messageID: "m1", lease: lease)
        for body in [
            #"{"request_id":"$TRACE","receipt":null}"#,
            #"{"request_id":"$TRACE","receipt":null,"head":{"unknown":1}}"#,
            #"{"request_id":"$TRACE","receipt":{},"head":null}"#,
            #"{"request_id":"$TRACE","receipt":null,"head":null,"head":null}"#,
            #"{"request_id":"$TRACE","receipt":null,"head":{"conversation_id":"foreign","generation":"g1","last_sequence":0}}"#
        ] {
            await server.overrideStatus(body)
            await #expect(throws: (any Error).self) { try await client.reconcileSend(messageID: "m1", lease: lease) }
            #expect(try state.action(messageID: "m1", lease: lease)?.phase == .queryRequired)
            await #expect(throws: (any Error).self) { try await client.submitPrepared(messageID: "m1", lease: lease, confirmRestored: true) }
        }
        await server.overrideStatus(#"{"request_id":"$TRACE","error":{"code":"MESSAGE_UNAVAILABLE","category":"dependency","message_en":"Unavailable","message_zh":"不可用","outcome":"unknown","recovery":"retry_safe_read"}}"#, code: 503)
        await #expect(throws: (any Error).self) { try await client.reconcileSend(messageID: "m1", lease: lease) }
        #expect(try state.action(messageID: "m1", lease: lease)?.phase == .queryRequired)
        #expect(await server.posted.isEmpty)
    }

    @Test func allSevenStatusRowsPersistTerminalDecisions() async throws {
        let rows: [(Bool, String?, String, Int, MessageSendDecision, ActionPhase)] = [
            (false, "matching", "g1", 1, .accepted, .accepted),
            (true, "wrong", "g1", 1, .integrityError, .integrityError),
            (false, nil, "g1", 1, .notAccepted, .notAccepted),
            (true, nil, "g2", 1, .notAccepted, .notAccepted),
            (true, nil, "g1", 2, .notAccepted, .notAccepted),
            (true, nil, "g1", 1, .resubmitOriginal, .notObserved),
            (true, nil, "g1", 0, .resyncRequired, .resyncRequired)
        ]
        for (hasHead, digestMode, generation, sequence, expected, phase) in rows {
            let directory = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
            defer { try? FileManager.default.removeItem(at: directory) }
            let keys = PermitDiskKeys()
            let memory = try EncryptedFileStorage(directory: directory, keys: keys)
            let scope = try StorageScope(environment: UUID().uuidString, account: "a")
            let state = MessageRecovery(storage: memory)
            let lease = try state.activate(scope)
            let server = PermitServer()
            await server.status(sequence: 1)
            let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 10000, maximumResponseBytes: 10000)
            let client = MessageHTTPClient(recovery: state, scope: scope, endpoint: endpoint, credentials: PermitCredentials(), interceptedTestTransport: server)
            _ = try await client.readSendHead(conversationID: "chat", lease: lease)
            let original = try client.stageSend(messageID: "m1", conversationID: "chat", text: "decide original", lease: lease)
            _ = try state.beginSubmission(messageID: "m1", lease: lease)
            let digest = digestMode.map { $0 == "matching" ? original.inputSHA256 : String(repeating: "0", count: 64) }
            await server.status(sequence: sequence, generation: generation, head: hasHead, digest: digest)
            #expect(try await client.reconcileSend(messageID: "m1", lease: lease) == expected)
            #expect(try state.action(messageID: "m1", lease: lease)?.phase == phase)
            #expect(await server.posted.isEmpty)
            let restored = MessageRecovery(storage: try EncryptedFileStorage(directory: directory, keys: keys))
            let restoredLease = try restored.activate(scope)
            #expect(try restored.action(messageID: "m1", lease: restoredLease)?.phase == phase)
            if expected == .integrityError || expected == .resyncRequired {
                let reopenedClient = MessageHTTPClient(recovery: restored, scope: scope, endpoint: endpoint, credentials: PermitCredentials(), interceptedTestTransport: server)
                await server.status(sequence: 2)
                _ = try await reopenedClient.readSendHead(conversationID: "chat", lease: restoredLease)
                #expect(throws: (any Error).self) { try reopenedClient.stageSend(messageID: "new", conversationID: "chat", text: "blocked", lease: restoredLease) }
                await #expect(throws: (any Error).self) { try await reopenedClient.submitPrepared(messageID: "m1", lease: restoredLease, confirmRestored: true) }
                #expect(await server.posted.isEmpty)
            }
        }
    }

    @Test func storedOriginalNeedsStatusAndExplicitConfirmation() async throws {
        let memory = PermitMemory()
        let scope = try StorageScope(environment: UUID().uuidString, account: "a")
        let old = MessageRecovery(storage: memory)
        let oldLease = try old.activate(scope)
        let server = PermitServer()
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 10000, maximumResponseBytes: 10000)
        let first = MessageHTTPClient(recovery: old, scope: scope, endpoint: endpoint, credentials: PermitCredentials(), interceptedTestTransport: server)
        _ = try await first.readSendHead(conversationID: "chat", lease: oldLease)
        let original = try first.stageSend(messageID: "m1", conversationID: "chat", text: "restore me", lease: oldLease)
        old.invalidate()
        let restored = MessageRecovery(storage: memory)
        let lease = try restored.activate(scope)
        let client = MessageHTTPClient(recovery: restored, scope: scope, endpoint: endpoint, credentials: PermitCredentials(), interceptedTestTransport: server)
        await #expect(throws: (any Error).self) { try await client.submitPrepared(messageID: "m1", lease: lease, confirmRestored: true) }
        #expect(try await client.reconcileSend(messageID: "m1", lease: lease) == .resubmitOriginal)
        #expect(try client.requiresResubmissionConfirmation(messageID: "m1", lease: lease))
        await #expect(throws: (any Error).self) { try await client.submitPrepared(messageID: "m1", lease: lease) }
        #expect(await server.posted.isEmpty)
        _ = try await client.submitPrepared(messageID: "m1", lease: lease, confirmRestored: true)
        #expect(await server.posted == [original.originalUTF8])
        #expect(try restored.action(messageID: "m1", lease: lease)?.phase == .accepted)
    }

    @Test func freshSendRequiresCurrentHeadAndConsumesOnce() async throws {
        let state = MessageRecovery(storage: PermitMemory())
        let scope = try StorageScope(environment: UUID().uuidString, account: "a")
        let lease = try state.activate(scope)
        let server = PermitServer()
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 10000, maximumResponseBytes: 10000)
        let client = MessageHTTPClient(recovery: state, scope: scope, endpoint: endpoint, credentials: PermitCredentials(), interceptedTestTransport: server)
        #expect(throws: (any Error).self) {
            try client.stageSend(messageID: "m1", conversationID: "chat", text: "你好", lease: lease)
        }
        _ = try await client.readSendHead(conversationID: "chat", lease: lease)
        let original = try client.stageSend(messageID: "m1", conversationID: "chat", text: "你好", lease: lease)
        #expect(throws: (any Error).self) {
            try client.stageSend(messageID: "m2", conversationID: "chat", text: "second", lease: lease)
        }
        _ = try await client.submitPrepared(messageID: "m1", lease: lease)
        #expect(await server.posted == [original.originalUTF8])
        #expect(try state.action(messageID: "m1", lease: lease)?.phase == .accepted)
        await #expect(throws: (any Error).self) { try await client.submitPrepared(messageID: "m1", lease: lease) }
        #expect(await server.posted.count == 1)
        state.invalidate()
        await #expect(throws: (any Error).self) { try await client.readSendHead(conversationID: "chat", lease: lease) }
    }
}
