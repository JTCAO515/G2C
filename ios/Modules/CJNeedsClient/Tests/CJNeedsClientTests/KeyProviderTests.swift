import Testing
import Foundation
import CryptoKit
@testable import CJMessageKeys
@testable import CJNeedsClient

@MainActor final class KeyPersistenceFixture: MessageKeyPersistence {
    var record: MessageKeyRecord?
    var reads = 0
    var additions = 0
    var removals = 0
    var onRead: (() -> Void)?
    init(_ record: MessageKeyRecord?) { self.record = record }
    func read() throws -> MessageKeyRecord? { reads += 1; onRead?(); return record }
    func add(_ value: MessageKeyRecord) throws { additions += 1; record = value }
    func remove(expectedID: UUID) throws { removals += 1; record = nil }
}
@MainActor @Suite struct KeyProviderTests {
    @Test func publicStoreConsumesOnlyOriginalScopedLookupAcrossReopen() throws {
        let h = try Harness(); defer { h.clean() }
        let persistence = KeyPersistenceFixture(.init(id: h.keyID, bytes: Data(repeating: 7, count: 32)))
        var randomCalls = 0
        let provider = ScopedMessageKeyProvider(namespace: h.namespace, persistence: persistence, randomBytes: { randomCalls += 1; throw NeedsFailure.keyUnavailable })
        let store = try NeedsPendingStore(directory: h.root, maximumBytes: 524_288, maximumRecords: 20, binding: h.binding, expectedKeyID: h.keyID, provider: provider)
        let action = try original(); try store.append(action)
        let reopened = try NeedsPendingStore(directory: h.root, maximumBytes: 524_288, maximumRecords: 20, binding: h.binding, expectedKeyID: h.keyID, provider: provider)
        #expect(try reopened.pending().first?.originalUTF8 == action.originalUTF8)
        #expect(persistence.reads > 0 && persistence.additions == 0 && persistence.removals == 0 && randomCalls == 0)
        persistence.record = nil
        #expect(throws: NeedsFailure.keyUnavailable) { try reopened.pending() }
        #expect(persistence.additions == 0 && persistence.removals == 0 && randomCalls == 0)
        #expect(try FileManager.default.contentsOfDirectory(atPath: h.root.path).count == 1)
    }
    @Test func providerInvalidatedInsideLookupCannotAuthorizePersistence() throws {
        let h = try Harness(); defer { h.clean() }
        let persistence = KeyPersistenceFixture(.init(id: h.keyID, bytes: Data(repeating: 8, count: 32)))
        let provider = ScopedMessageKeyProvider(namespace: h.namespace, persistence: persistence, randomBytes: { throw NeedsFailure.keyUnavailable })
        let store = try NeedsPendingStore(directory: h.root, maximumBytes: 524_288, maximumRecords: 20, binding: h.binding, expectedKeyID: h.keyID, provider: provider)
        persistence.onRead = { provider.invalidate() }
        #expect(throws: NeedsFailure.keyUnavailable) { try store.append(try original()) }
        #expect(try FileManager.default.contentsOfDirectory(atPath: h.root.path).isEmpty)
        #expect(persistence.additions == 0 && persistence.removals == 0)
    }
    @Test func publicStoreRejectsOtherDomainBeforeLookup() throws {
        let h = try Harness(); defer { h.clean() }
        let persistence = KeyPersistenceFixture(.init(id: h.keyID, bytes: Data(repeating: 9, count: 32)))
        let namespace = MessageKeyNamespace(environment: h.binding.environment, account: h.binding.account, purpose: .localMemoryPendingV1)
        let provider = ScopedMessageKeyProvider(namespace: namespace, persistence: persistence, randomBytes: { throw NeedsFailure.keyUnavailable })
        #expect(throws: NeedsFailure.keyUnavailable) {
            try NeedsPendingStore(directory: h.root, maximumBytes: 524_288, maximumRecords: 20, binding: h.binding, expectedKeyID: h.keyID, provider: provider)
        }
        #expect(persistence.reads == 0 && persistence.additions == 0 && persistence.removals == 0)
    }
}
