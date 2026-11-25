import CJCleanupClient
@testable import CJLioUser
import Darwin
import Foundation
import Testing
@testable import CJShell

@MainActor struct LioRoadbookCleanupTests {
    @Test func erasesEveryRoadbookTheStoreWroteForTheSelectedAccountOnly() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let selected = try account("selected", at: root), adjacent = try account("adjacent", at: root)
        let books = LioRoadbookPreview.library(.english)
        #expect(books.count >= 2)
        let store = LioRoadbookStore(directory: LioAccountFolders.roadbooks(inMessageDirectory: selected))
        for book in books { try store.save(book) }
        let other = LioRoadbookStore(directory: LioAccountFolders.roadbooks(inMessageDirectory: adjacent))
        try other.save(books[0])
        let written = try FileManager.default.contentsOfDirectory(atPath: store.directory.path)
        #expect(written.count == books.count && written.allSatisfy(LioAccountFolders.isRoadbookFileName))

        let directory = try DeviceCleanupDirectory(existingPrivateDirectory: selected)
        try LioRoadbookCleanup.erase(in: directory)
        try directory.requireEmpty()
        try LioRoadbookCleanup.erase(in: directory)
        #expect(other.load().count == 1)
    }

    @Test func unknownEntriesKeepCleanupIncompleteAndArePreserved() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let selected = try account("selected", at: root)
        let store = LioRoadbookStore(directory: LioAccountFolders.roadbooks(inMessageDirectory: selected))
        try store.save(LioRoadbookPreview.library(.chinese)[0])
        let unknown = store.directory.appendingPathComponent("notes.txt")
        try Data([7]).write(to: unknown)
        let directory = try DeviceCleanupDirectory(existingPrivateDirectory: selected)
        #expect(throws: CleanupFailure.unavailable) { try LioRoadbookCleanup.erase(in: directory) }
        #expect(store.load().isEmpty)
        #expect(try Data(contentsOf: unknown) == Data([7]))
    }

    @Test func onlyDigestNamedJSONCounts() {
        #expect(LioAccountFolders.isRoadbookFileName(String(repeating: "a", count: 64) + ".json"))
        #expect(!LioAccountFolders.isRoadbookFileName(String(repeating: "A", count: 64) + ".json"))
        #expect(!LioAccountFolders.isRoadbookFileName(String(repeating: "a", count: 63) + ".json"))
        #expect(!LioAccountFolders.isRoadbookFileName(String(repeating: "a", count: 64) + ".txt"))
        #expect(!LioAccountFolders.isRoadbookFileName(String(repeating: "b\u{0301}", count: 64) + ".json"))
        #expect(!LioAccountFolders.isRoadbookFileName(String(repeating: "a", count: 64) + ".JSON"))
    }

    private func temporaryRoot() throws -> URL {
        let physical = try #require(realpath(FileManager.default.temporaryDirectory.path, nil))
        defer { free(physical) }
        let root = URL(fileURLWithPath: String(cString: physical))
            .appendingPathComponent("roadbook-cleanup-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false,
                                               attributes: [.posixPermissions: 0o700])
        return root
    }

    private func account(_ name: String, at root: URL) throws -> URL {
        let account = root.appendingPathComponent(name, isDirectory: true)
        try FileManager.default.createDirectory(at: account, withIntermediateDirectories: false,
                                               attributes: [.posixPermissions: 0o700])
        return account
    }
}
