import Testing
import Foundation
import CryptoKit
import CJSession
import CJMessageHTTP
@testable import CJMessageKeys
@testable import CJFeedbackClient

@MainActor final class KeyPersistence: MessageKeyPersistence {
    var value: MessageKeyRecord?
    var readFailure = false
    var unknownAdd = false
    var adds = 0
    var deletes = 0
    func read() throws -> MessageKeyRecord? { if readFailure { throw MessageKeyFailure.storageUnavailable }; return value }
    func add(_ record: MessageKeyRecord) throws {
        adds += 1; value = record
        if unknownAdd { throw MessageKeyFailure.storageUnavailable }
    }
    func remove(expectedID: UUID) throws { deletes += 1; value = nil }
}
@MainActor struct SyntheticSessionPersistence: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ material: SessionMaterial) throws { }
    func clearAndBlock() throws { }
}

@MainActor struct StoreAndGateTests {
    @Test func canonicalProviderOriginalPurposeAndEncryptedReopen() throws {
        let h = try Harness(); defer { h.clean() }; let persistence = KeyPersistence()
        let provider = ScopedMessageKeyProvider(namespace: h.namespace, persistence: persistence, randomBytes: { Data(repeating: 19, count: 32) })
        let key = try provider.create(storageState: .confirmedEmpty, for: provider.begin(.create))
        let store = try FeedbackPendingStore(directory: h.root, maximumBytes: 100_000, maximumRecords: 10, binding: h.binding, expectedKeyID: key.id, provider: provider)
        let original = try pending(); try store.append(original)
        let ciphertext = try Data(contentsOf: h.root.appendingPathComponent(digest(Data(original.actionID.utf8)) + ".feedback"))
        #expect(ciphertext.range(of: original.originalUTF8) == nil)
        #expect(ciphertext.range(of: Data("自愿问题".utf8)) == nil)
        let reopened = try FeedbackPendingStore(directory: h.root, maximumBytes: 100_000, maximumRecords: 10, binding: h.binding, expectedKeyID: key.id, provider: provider)
        #expect(try reopened.pending().first?.originalUTF8 == original.originalUTF8)
        #expect(persistence.adds == 1 && persistence.deletes == 0)
    }
    @Test(arguments: ["missing", "unknown", "wrongID", "unknownCreation"]) func noKeyNeverCreatesRetriesOrSends(kind: String) async throws {
        let h = try Harness(); defer { h.clean() }; let persistence = KeyPersistence()
        let provider = ScopedMessageKeyProvider(namespace: h.namespace, persistence: persistence, randomBytes: { Data(repeating: 7, count: 32) })
        var expectedID = UUID()
        if kind == "wrongID" { _ = try provider.create(storageState: .confirmedEmpty, for: provider.begin(.create)) }
        if kind == "unknown" { persistence.readFailure = true }
        if kind == "unknownCreation" {
            persistence.unknownAdd = true
            #expect(throws: MessageKeyFailure.storageUnavailable) { try provider.create(storageState: .confirmedEmpty, for: provider.begin(.create)) }
            expectedID = try #require(persistence.value?.id)
        }
        let beforeAdds = persistence.adds
        let store = try FeedbackPendingStore(directory: h.root, maximumBytes: 100_000, maximumRecords: 10, binding: h.binding, expectedKeyID: expectedID, provider: provider)
        let wire = Interceptor { _, _, _ in Reply(text: nullResponse) }; let client = try h.client(wire, store: store); let op = try client.begin(binding: h.binding)
        await #expect(throws: (any Error).self) { try await client.submit(pending(), operation: op) }
        await #expect(throws: FeedbackFailure.pendingRequiresQuery) { try await client.submit(pending(actionID: "another"), operation: op) }
        #expect(persistence.adds == beforeAdds && persistence.deletes == 0); #expect(await wire.calls.isEmpty)
    }
    @Test(arguments: ["account", "environment", "purpose"]) func wrongNamespaceRejected(kind: String) throws {
        let h = try Harness(); defer { h.clean() }; let ns = MessageKeyNamespace(environment: kind == "environment" ? UUID() : h.binding.environment,
            account: kind == "account" ? UUID() : h.binding.account, purpose: kind == "purpose" ? .localMessageStorageV1 : .localFeedbackPendingV1)
        let provider = ScopedMessageKeyProvider(namespace: ns, persistence: KeyPersistence())
        #expect(throws: FeedbackFailure.keyUnavailable) {
            try FeedbackPendingStore(directory: h.root, maximumBytes: 100_000, maximumRecords: 10, binding: h.binding, expectedKeyID: UUID(), provider: provider)
        }
    }
    @Test func wrongOriginalKeyAndDirectorySymlinkFailClosed() throws {
        let h = try Harness(); defer { h.clean() }; let original = try pending(); try h.store().append(original)
        let wrong = try h.store { SymmetricKey(size: .bits256) }
        #expect(throws: (any Error).self) { try wrong.pending() }
        let link = h.root.appendingPathExtension("link")
        defer { try? FileManager.default.removeItem(at: link) }
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: h.root)
        #expect(throws: FeedbackFailure.storageUnavailable) {
            try FeedbackPendingStore(directory: link, maximumBytes: 100_000, maximumRecords: 10, namespace: h.namespace, keyID: h.keyID, key: { h.key })
        }
    }
    @Test func exclusiveAppendRetainsBytesAndNeverDeletes() throws {
        let h = try Harness(); defer { h.clean() }; let store = try h.store(); let original = try pending(); try store.append(original)
        #expect(throws: FeedbackFailure.storageUnavailable) { try store.append(original) }
        #expect(try store.pending().first?.originalUTF8 == original.originalUTF8)
        let file = h.root.appendingPathComponent(digest(Data(original.actionID.utf8)) + ".feedback")
        let hardlink = h.root.appendingPathComponent("extra")
        try FileManager.default.linkItem(at: file, to: hardlink)
        #expect(throws: (any Error).self) { try store.pending() }
    }
    @Test func publicClientCannotPostEvenWithTrustedSessionAndResources() async throws {
        let h = try Harness(); defer { h.clean() }; var credentialCalls = 0
        let session = SessionLifecycle(persistence: SyntheticSessionPersistence(), restorePolicy: .userInitiatedOnly)
        let client = FeedbackClient(endpoint: h.endpoint, credentials: { _ in credentialCalls += 1; return "synthetic" }, currentBinding: { h.binding },
            session: session, sessionOperation: try session.beginUserRestore(), pendingStore: try h.store(),
            liveReadTransport: try NoRedirectTransport(requestTimeout: 1, resourceTimeout: 1))
        #expect(!client.acceptsSubmissions)
        await #expect(throws: FeedbackFailure.liveWriteUnavailable) { try await client.submit(pending(), operation: client.begin(binding: h.binding)) }
        #expect(credentialCalls == 0); #expect(try h.store().pending().isEmpty)
        let model = FeedbackPresentation(client: client); model.replace(binding: h.binding); model.edit(problem: "draft", expectation: "")
        #expect(model.state == .unavailable); #expect(model.prepareSubmit() == nil); #expect(model.problem == "draft")
    }
    @Test func privateTransportExceptionIsSanitized() async throws {
        let h = try Harness(); defer { h.clean() }
        let privateError = NSError(domain: "PRIVATE_BODY_TOKEN_URL", code: 1, userInfo: [NSLocalizedDescriptionKey:"private secret"])
        let client = try h.client(Interceptor { _, _, _ in throw privateError })
        do { _ = try await client.submit(pending(), operation: client.begin(binding: h.binding)); Issue.record("unexpected success") }
        catch {
            #expect(error as? FeedbackFailure == .exchangeUnknown)
            #expect(!String(describing: error).contains("PRIVATE_BODY")); #expect(!String(describing: error).contains("secret"))
        }
    }
}
