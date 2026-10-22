import Testing
import Foundation
import Darwin
@testable import CJMessageKeys
import CJSession
@testable import CJOfflineTrip

@MainActor final class KeyStorage: MessageKeyPersistence {
    var value: MessageKeyRecord?
    var failure: MessageKeyFailure?
    var onRead: (() throws -> Void)?
    var adds = 0
    var removes = 0
    func read() throws -> MessageKeyRecord? {
        try onRead?()
        if let failure { throw failure }
        return value
    }
    func add(_ record: MessageKeyRecord) throws { adds += 1; throw MessageKeyFailure.storageUnavailable }
    func remove(expectedID: UUID) throws { removes += 1; throw MessageKeyFailure.storageUnavailable }
}
@MainActor struct InMemorySession: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ material: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
@MainActor final class SourceState {
    var token: UUID? = UUID()
    var onCurrent: (() -> Void)?
    func current() -> UUID? { onCurrent?(); return token }
}
@MainActor final class KeyHarness {
    let ns: OfflineNamespace
    let expectedID = UUID()
    let source = SourceState()
    let storage = KeyStorage()
    let provider: ScopedMessageKeyProvider
    let session = SessionLifecycle(persistence: InMemorySession(), restorePolicy: .userInitiatedOnly)
    let operation: SessionOperation
    let root: URL
    let store: AtomicSnapshotStore
    let access: CanonicalSnapshotAccess
    init(purpose: MessageKeyPurpose = .localOfflineTripSnapshotV1, environment: UUID? = nil, account: UUID? = nil) throws {
        ns = try OfflineNamespace(account: UUID(), backend: UUID(), trip: "trip1")
        let physical = try #require(realpath(FileManager.default.temporaryDirectory.path, nil))
        defer { free(physical) }
        root = URL(fileURLWithPath: String(cString:physical)).appendingPathComponent("cj022-canonical-test-"+UUID().uuidString)
        try FileManager.default.createDirectory(at:root,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
        store = try AtomicSnapshotStore(existingPrivateDirectory:root)
        storage.value = MessageKeyRecord(id:expectedID, bytes:Data(repeating:37,count:32)) // isolated fixture only
        provider = ScopedMessageKeyProvider(namespace:.init(environment:environment ?? ns.backend,account:account ?? ns.account,purpose:purpose),
                                            persistence:storage, randomBytes:{ throw MessageKeyFailure.random(-1) })
        operation = try session.beginUserRestore()
        let token = try #require(source.token)
        do {
            access = try CanonicalSnapshotAccess(store:store,provider:provider,session:session,sessionOperation:operation,
                                                namespace:ns,expectedKeyID:expectedID,sourceToken:token,currentSource:source.current)
        } catch { try? FileManager.default.removeItem(at:root); throw error }
    }
    func snapshot(version: Int = 2) throws -> OfflineSnapshot {
        let doc: [String:Any] = ["title":"北京 Beijing", "items":[["id":"item1","text":"中文地点 / Place", "verification":"pending","evidence":[]]]]
        let content = try JSONSerialization.data(withJSONObject:doc,options:[.sortedKeys])
        let raw = try JSONSerialization.data(withJSONObject:["request_id":UUID().uuidString,"trip":["trip_id":"trip1","version":version,"document":doc,"content_utf8_base64":content.base64EncodedString()]])
        return try SnapshotCodec.capture(response:raw,namespace:ns,syncedAt:1000,deadline:1100,boot:UUID(),uptime:50,keyID:expectedID)
    }
    func cleanup() { try? FileManager.default.removeItem(at:root) }
}

@Suite @MainActor struct CanonicalKeyTests {
    @Test func actualProviderRoundTripExactBytesNoMutation() throws {
        let h = try KeyHarness(); defer { h.cleanup() }
        let snapshot = try h.snapshot()
        try h.access.write(snapshot)
        let originalCiphertext = try #require(try h.store.read())
        let actual = try #require(try h.access.read(minimumVersion:2))
        #expect(actual.responseBytes == snapshot.responseBytes)
        #expect(actual.metadata == snapshot.metadata)
        #expect(try h.store.read() == originalCiphertext)
        #expect(h.provider.namespace.purpose == .localOfflineTripSnapshotV1)
        #expect(h.storage.adds == 0 && h.storage.removes == 0)
        #expect(!SnapshotCodec.appFactoryAvailable)
    }
    @Test func wrongPurposeAccountAndBackendRejected() throws {
        for purpose in [MessageKeyPurpose.localTripPendingV1,.localMessageStorageV1,.localMemoryPendingV1] {
            #expect(throws:OfflineFailure.unavailable) { try KeyHarness(purpose:purpose) }
        }
        #expect(throws:OfflineFailure.unavailable) { try KeyHarness(environment:UUID()) }
        #expect(throws:OfflineFailure.unavailable) { try KeyHarness(account:UUID()) }
    }
    @Test func missingUnknownAndChangedIDNeverCreates() throws {
        let h = try KeyHarness(); defer { h.cleanup() }
        try h.access.write(h.snapshot())
        let original = try h.store.read(), saved = h.storage.value
        h.storage.value = nil
        #expect(throws:OfflineFailure.keyUnavailable) { try h.access.read(minimumVersion:1) }
        #expect(throws:OfflineFailure.keyUnavailable) { try h.access.write(h.snapshot()) }
        h.storage.value = saved; h.storage.failure = .creationUnconfirmed
        #expect(throws:OfflineFailure.keyUnavailable) { try h.access.read(minimumVersion:1) }
        h.storage.failure = .clearUnconfirmed
        #expect(throws:OfflineFailure.keyUnavailable) { try h.access.write(h.snapshot()) }
        h.storage.failure = nil; h.storage.value = .init(id:UUID(),bytes:Data(repeating:37,count:32))
        #expect(throws:OfflineFailure.keyUnavailable) { try h.access.read(minimumVersion:1) }
        #expect(try h.store.read() == original)
        #expect(h.storage.adds == 0 && h.storage.removes == 0)
    }
    @Test func lookupCallbackInvalidationCannotReadOrWrite() throws {
        let h = try KeyHarness(); defer { h.cleanup() }
        try h.access.write(h.snapshot()); let original = try h.store.read()
        h.storage.onRead = { _ = try h.session.beginUserRestore() }
        #expect(throws:OfflineFailure.unavailable) { try h.access.read(minimumVersion:1) }
        #expect(throws:OfflineFailure.unavailable) { try h.access.write(h.snapshot()) }
        #expect(try h.store.read() == original)
    }
    @Test func lastHostCallbackRechecksProviderSessionAndSource() throws {
        for kind in 0..<4 {
            let h = try KeyHarness(); defer { h.cleanup() }
            try h.access.write(h.snapshot()); let original = try h.store.read()
            h.source.onCurrent = {
                switch kind {
                case 0: h.provider.invalidate()
                case 1: _ = try? h.session.beginUserRestore()
                case 2: h.source.token = UUID()
                default: h.access.invalidate()
                }
            }
            #expect(throws:(any Error).self) { try h.access.read(minimumVersion:1) }
            #expect(try h.store.read() == original)
        }
    }
    @Test func lastHostCallbackCannotReplaceCiphertextOrWriteOverIt() throws {
        let h = try KeyHarness(); defer { h.cleanup() }
        try h.access.write(h.snapshot())
        let changed = Data([1,2,3])
        h.source.onCurrent = { try? changed.write(to:h.root.appendingPathComponent("snapshot.aesgcm")) }
        #expect(throws:OfflineFailure.corrupt) { try h.access.read(minimumVersion:1) }
        #expect(try h.store.read() == changed)
        h.source.onCurrent = nil
        // No fallback to the earlier decryptable snapshot.
        #expect(throws:(any Error).self) { try h.access.read(minimumVersion:1) }
    }
    @Test func canonicalUnknownWriteUsesOriginalCiphertextOnly() throws {
        let h = try KeyHarness(); defer { h.cleanup() }
        h.store.afterRename = { throw OfflineFailure.storageFailure }
        #expect(throws:OfflineFailure.writeUnknown) { try h.access.write(h.snapshot()) }
        let attempted = try h.store.read()
        h.storage.failure = .creationUnconfirmed
        #expect(throws:OfflineFailure.keyUnavailable) { try h.access.reconcileOriginalWrite() }
        #expect(throws:OfflineFailure.writeUnknown) { try h.access.write(h.snapshot()) }
        #expect(throws:OfflineFailure.writeUnknown) { try h.access.read(minimumVersion:1) }
        h.storage.failure = nil
        #expect(try h.access.reconcileOriginalWrite() == .committed)
        #expect(try h.store.read() == attempted)
        #expect(h.storage.adds == 0 && h.storage.removes == 0)
    }
    @Test func callbackReentrancyAndLookupGenerationAreFenced() throws {
        let h = try KeyHarness(); defer { h.cleanup() }
        try h.access.write(h.snapshot())
        var nestedDenied = false
        h.source.onCurrent = {
            do { _ = try h.access.read(minimumVersion:1) }
            catch OfflineFailure.unavailable { nestedDenied = true }
            catch {}
        }
        #expect(try h.access.read(minimumVersion:1) != nil)
        #expect(nestedDenied)
        h.source.onCurrent = { _ = try? h.provider.begin(.lookup) }
        #expect(throws:OfflineFailure.keyUnavailable) { try h.access.read(minimumVersion:1) }
    }
    @Test func wrongKeyMaterialAndPostCallbackFileMutationCannotSucceed() throws {
        let h = try KeyHarness(); defer { h.cleanup() }
        try h.access.write(h.snapshot())
        let original = try h.store.read()
        h.storage.value = .init(id:h.expectedID,bytes:Data(repeating:38,count:32))
        #expect(throws:OfflineFailure.corrupt) { try h.access.read(minimumVersion:1) }
        #expect(try h.store.read() == original)
        h.storage.value = .init(id:h.expectedID,bytes:Data(repeating:37,count:32))
        h.source.onCurrent = { h.access.invalidate() }
        #expect(throws:OfflineFailure.unavailable) { try h.access.write(h.snapshot()) }
        #expect(try h.store.read() == original)
    }

}
