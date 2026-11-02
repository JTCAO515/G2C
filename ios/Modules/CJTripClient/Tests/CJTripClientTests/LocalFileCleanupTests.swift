import Foundation
import CryptoKit
import Darwin
import Testing
import CJMessageKeys
@testable import CJTripClient

@Suite @MainActor struct LocalFileCleanupTests {
    private func directory() throws -> URL {
        let root = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent("cj-trip-cleanup-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        return root
    }
    @Test func physicallyClearsEncryptedTripAndManualJournalsWithoutAnotherAccount() throws {
        let root = try directory(), other = try directory()
        defer {
            for url in [root, other] + TripPendingStore.manualNamespaceDirectories(at: root) { try? FileManager.default.removeItem(at: url) }
        }
        let ns = MessageKeyNamespace(environment: UUID(), account: UUID(), purpose: .localTripPendingV1)
        let key = SymmetricKey(size: .bits256), id = UUID()
        var lookups = 0
        let store = try TripPendingStore(directory: root, maximumBytes: 100_000, maximumRecords: 10,
            namespace: ns, keyID: id, key: { lookups += 1; return key })
        try store.append(pending())
        let otherNS = MessageKeyNamespace(environment: ns.environment, account: UUID(), purpose: .localTripPendingV1)
        let retained = try TripPendingStore(directory: other, maximumBytes: 100_000, maximumRecords: 10,
            namespace: otherNS, keyID: id, key: { key })
        try retained.append(pending())
        let manual: TripEncryptedRecords<TripPending> = try #require(try store.manualRecords(maximumBytes: 100_000, maximumRecords: 10, create: true))
        try manual.append(pending())
        let rejections: TripEncryptedRecords<TripPending> = try #require(try manual.adjacent(suffix: "CJTripManualRejections", domain: "CJTripManualRejections", maximumBytes: 100_000, maximumRecords: 10, create: true))
        try rejections.append(pending(.reject))
        let before = lookups
        try store.clearLocalFiles(); try store.clearLocalFiles()
        #expect(lookups == before)
        for url in [root] + TripPendingStore.manualNamespaceDirectories(at: root) {
            #expect(try FileManager.default.contentsOfDirectory(atPath: url.path).isEmpty)
        }
        #expect(try retained.pending().count == 1)
        let reopened = try TripPendingStore(directory: root, maximumBytes: 100_000, maximumRecords: 10,
            namespace: ns, keyID: id, key: { key })
        #expect(try reopened.pending().isEmpty)
    }
    @Test func unknownEntriesAndLinksRefuseCompletionAndPreserveTargets() throws {
        let root = try directory()
        defer { try? FileManager.default.removeItem(at: root) }
        let ns = MessageKeyNamespace(environment: UUID(), account: UUID(), purpose: .localTripPendingV1)
        let store = try TripPendingStore(directory: root, maximumBytes: 100_000, maximumRecords: 10,
            namespace: ns, keyID: UUID(), key: { SymmetricKey(size: .bits256) })
        let keep = root.appendingPathExtension("keep")
        defer { try? FileManager.default.removeItem(at: keep) }
        try Data("keep".utf8).write(to: keep)
        let unknown = root.appendingPathComponent("unknown.txt")
        try Data("unknown".utf8).write(to: unknown)
        #expect(throws: TripFailure.storageUnavailable) { try store.clearLocalFiles() }
        try FileManager.default.removeItem(at: unknown)
        let named = root.appendingPathComponent(String(repeating: "a", count: 64) + ".trip")
        try FileManager.default.createSymbolicLink(at: named, withDestinationURL: keep)
        #expect(throws: TripFailure.storageUnavailable) { try store.clearLocalFiles() }
        try FileManager.default.removeItem(at: named)
        #expect(link(keep.path, named.path) == 0)
        #expect(throws: TripFailure.storageUnavailable) { try store.clearLocalFiles() }
        #expect(try Data(contentsOf: keep) == Data("keep".utf8))
    }
}
