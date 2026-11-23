import CJCleanupClient
import CJLioUser
import CJMessageClient
import CJTripClient
import Darwin
import Foundation
import Testing
@testable import CJShell

@MainActor struct LioTaxiRecentsCleanupTests {
    @Test func erasesOnlyTheSelectedAccountsKnownTaxiFile() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let selected = try seedAccount("selected", at: root, bytes: Data([1]))
        let adjacent = try seedAccount("adjacent", at: root, bytes: Data([2]))
        let tripRoot = root.appendingPathComponent("trip-journal", isDirectory: true)
        try FileManager.default.createDirectory(at: tripRoot, withIntermediateDirectories: false,
                                                attributes: [.posixPermissions: 0o700])
        try TripPendingStore.requireEmptyNamespace(directory: tripRoot)
        let scope = try StorageScope(environment: UUID().uuidString, account: UUID().uuidString)
        try EncryptedFileStorage(directory: selected, keys: NoKeys()).clearLocalSnapshot(scope: scope)
        let account = try DeviceCleanupDirectory(existingPrivateDirectory: selected)
        try LioTaxiRecentsCleanup.erase(in: account)
        try account.requireEmpty()
        try TripPendingStore.requireEmptyNamespace(directory: tripRoot)
        try LioTaxiRecentsCleanup.erase(in: account)
        #expect(try Data(contentsOf: recentFile(in: adjacent)) == Data([2]))
    }

    @Test func unknownRecordsKeepCleanupIncompleteAndArePreserved() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let selected = try seedAccount("selected", at: root, bytes: Data([1]))
        let known = recentFile(in: selected)
        let unknown = known.deletingLastPathComponent().appendingPathComponent("unknown")
        try Data([3]).write(to: unknown)
        let account = try DeviceCleanupDirectory(existingPrivateDirectory: selected)
        #expect(throws: CleanupFailure.unavailable) { try LioTaxiRecentsCleanup.erase(in: account) }
        #expect(!FileManager.default.fileExists(atPath: known.path))
        #expect(try Data(contentsOf: unknown) == Data([3]))
    }

    private final class NoKeys: MessageEncryptionKeyProvider {
        func existing(for scope: StorageScope, expectedID: UUID?) throws -> MessageStorageKey? {
            Issue.record("Local cleanup requested a key")
            return nil
        }
    }

    private func temporaryRoot() throws -> URL {
        let physical = try #require(realpath(FileManager.default.temporaryDirectory.path, nil))
        defer { free(physical) }
        let root = URL(fileURLWithPath: String(cString: physical))
            .appendingPathComponent("taxi-cleanup-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false,
                                               attributes: [.posixPermissions: 0o700])
        return root
    }

    private func seedAccount(_ name: String, at root: URL, bytes: Data) throws -> URL {
        let account = root.appendingPathComponent(name, isDirectory: true)
        try FileManager.default.createDirectory(at: account, withIntermediateDirectories: false,
                                               attributes: [.posixPermissions: 0o700])
        let file = recentFile(in: account)
        try FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: false,
                                               attributes: [.posixPermissions: 0o700])
        try bytes.write(to: file)
        return account
    }

    private func recentFile(in account: URL) -> URL {
        LioTaxiRecentPlaces.storageDirectory(inMessageDirectory: account)
            .appendingPathComponent(LioTaxiRecentPlaces.fileName)
    }
}
