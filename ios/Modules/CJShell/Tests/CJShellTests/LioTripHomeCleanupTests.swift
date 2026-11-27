import CJCleanupClient
import CJLioUser
import CJMessageClient
import CJTripClient
import Darwin
import Foundation
import Testing
@testable import CJShell

@MainActor struct LioTripHomeCleanupTests {
    @Test func erasesOnlyTheSelectedAccountsTripHome() throws {
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
        try LioTripHomeCleanup.erase(in: account)
        try account.requireEmpty()
        try TripPendingStore.requireEmptyNamespace(directory: tripRoot)
        try LioTripHomeCleanup.erase(in: account)
        #expect(try Data(contentsOf: tripHomeFile(in: adjacent)) == Data([2]))
    }

    /// #1995: the trip canvas lives in the trip home's folder and goes with it, with no other file left behind.
    @Test func erasesTheTripCanvasTogetherWithTheTripHome() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let selected = try seedAccount("selected", at: root, bytes: Data([1]))
        let canvas = tripHomeFile(in: selected).deletingLastPathComponent().appendingPathComponent(LioTripCanvasStore.fileName)
        try Data([4]).write(to: canvas)
        let account = try DeviceCleanupDirectory(existingPrivateDirectory: selected)
        try LioTripHomeCleanup.erase(in: account)
        try account.requireEmpty()
        #expect(!FileManager.default.fileExists(atPath: canvas.path))
        // With only a canvas (the trip home never started) it is removed too, and again is a no-op.
        let other = try seedAccount("other", at: root, bytes: Data([1]))
        let otherHome = tripHomeFile(in: other)
        try FileManager.default.removeItem(at: otherHome)
        try Data([5]).write(to: otherHome.deletingLastPathComponent().appendingPathComponent(LioTripCanvasStore.fileName))
        let otherAccount = try DeviceCleanupDirectory(existingPrivateDirectory: other)
        try LioTripHomeCleanup.erase(in: otherAccount)
        try otherAccount.requireEmpty()
        try LioTripHomeCleanup.erase(in: otherAccount)
    }

    /// The copies kept of a damaged canvas file are part of the canvas: they go with the account's trip home.
    @Test func erasesTheCopiesKeptOfADamagedCanvasFileToo() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let selected = try seedAccount("selected", at: root, bytes: Data([1]))
        let folder = tripHomeFile(in: selected).deletingLastPathComponent()
        let copies = LioTripCanvasStore.damagedCopyNames.map { folder.appendingPathComponent($0) }
        for (index, copy) in copies.enumerated() { try Data([UInt8(10 + index)]).write(to: copy) }
        let account = try DeviceCleanupDirectory(existingPrivateDirectory: selected)
        try LioTripHomeCleanup.erase(in: account)
        try account.requireEmpty()
        #expect(copies.allSatisfy { !FileManager.default.fileExists(atPath: $0.path) })
        try LioTripHomeCleanup.erase(in: account)          // and again is a no-op
    }

    /// #1994: the one-time autosave notice's record lives in the trip home's folder and goes with it on account cleanup.
    @Test func erasesTheAutosaveNoticeRecordTogetherWithTheTripHome() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let selected = try seedAccount("selected", at: root, bytes: Data([1]))
        let adjacent = try seedAccount("adjacent", at: root, bytes: Data([2]))
        let folder = tripHomeFile(in: selected).deletingLastPathComponent()
        let record = folder.appendingPathComponent(LioAutosaveNoticeStore.fileName)
        try Data([6]).write(to: record)
        let account = try DeviceCleanupDirectory(existingPrivateDirectory: selected)
        try LioTripHomeCleanup.erase(in: account)
        try account.requireEmpty()
        #expect(!FileManager.default.fileExists(atPath: record.path))
        try LioTripHomeCleanup.erase(in: account)
        #expect(try Data(contentsOf: tripHomeFile(in: adjacent)) == Data([2]), "another account keeps its own")
        // With only the record (the trip home never started) it is removed too.
        let other = try seedAccount("other", at: root, bytes: Data([1]))
        try FileManager.default.removeItem(at: tripHomeFile(in: other))
        try Data([7]).write(to: tripHomeFile(in: other).deletingLastPathComponent().appendingPathComponent(LioAutosaveNoticeStore.fileName))
        let otherAccount = try DeviceCleanupDirectory(existingPrivateDirectory: other)
        try LioTripHomeCleanup.erase(in: otherAccount)
        try otherAccount.requireEmpty()
    }

    @Test func unknownRecordsKeepCleanupIncompleteAndArePreserved() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let selected = try seedAccount("selected", at: root, bytes: Data([1]))
        let known = tripHomeFile(in: selected)
        let unknown = known.deletingLastPathComponent().appendingPathComponent("unknown")
        try Data([3]).write(to: unknown)
        let account = try DeviceCleanupDirectory(existingPrivateDirectory: selected)
        #expect(throws: CleanupFailure.unavailable) { try LioTripHomeCleanup.erase(in: account) }
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
            .appendingPathComponent("trip-home-cleanup-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false,
                                               attributes: [.posixPermissions: 0o700])
        return root
    }

    private func seedAccount(_ name: String, at root: URL, bytes: Data) throws -> URL {
        let account = root.appendingPathComponent(name, isDirectory: true)
        try FileManager.default.createDirectory(at: account, withIntermediateDirectories: false,
                                               attributes: [.posixPermissions: 0o700])
        let file = tripHomeFile(in: account)
        try FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: false,
                                               attributes: [.posixPermissions: 0o700])
        try bytes.write(to: file)
        return account
    }

    private func tripHomeFile(in account: URL) -> URL {
        LioTripHomeStore.storageDirectory(inMessageDirectory: account)
            .appendingPathComponent(LioTripHomeStore.fileName)
    }
}
