import CJCleanupClient
import CJLioUser
import Darwin
import Foundation
import Testing
@testable import CJShell

@MainActor struct LioLocalAddressCleanupTests {
    @Test func retiresOnlyTheSelectedAccountsAddressMarkerAndDirectory() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let selected = try seed("selected", under: root, marker: true)
        let adjacent = try seed("adjacent", under: root, marker: true)
        let adjacentFile = marker(in: adjacent)
        let adjacentBytes = try Data(contentsOf: adjacentFile)

        let captured = try DeviceCleanupDirectory(existingPrivateDirectory: selected)
        try LioLocalAddressCleanup.erase(in: captured)
        try captured.requireEmpty()
        try LioLocalAddressCleanup.erase(in: captured)
        #expect(try Data(contentsOf: adjacentFile) == adjacentBytes)
    }

    @Test func emptyDirectoryIsRetiredAndUnknownFilesKeepCleanupIncomplete() throws {
        let root = try temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let empty = try seed("empty", under: root, marker: false)
        let emptyCapture = try DeviceCleanupDirectory(existingPrivateDirectory: empty)
        try LioLocalAddressCleanup.erase(in: emptyCapture)
        try emptyCapture.requireEmpty()

        let other = try seed("other", under: root, marker: true)
        let unknown = marker(in: other).deletingLastPathComponent().appending(path: "unrecognized")
        let contents = Data([7])
        try contents.write(to: unknown)
        let captured = try DeviceCleanupDirectory(existingPrivateDirectory: other)
        #expect(throws: CleanupFailure.unavailable) { try LioLocalAddressCleanup.erase(in: captured) }
        #expect(try Data(contentsOf: unknown) == contents)
    }

    private func temporaryRoot() throws -> URL {
        let physical = try #require(realpath(FileManager.default.temporaryDirectory.path, nil))
        defer { free(physical) }
        let root = URL(fileURLWithPath: String(cString: physical))
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false,
                                                attributes: [.posixPermissions: 0o700])
        return root
    }

    private func seed(_ name: String, under root: URL, marker includeMarker: Bool) throws -> URL {
        let account = root.appending(path: name, directoryHint: .isDirectory)
        try FileManager.default.createDirectory(at: account, withIntermediateDirectories: false,
                                                attributes: [.posixPermissions: 0o700])
        let file = marker(in: account)
        try FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: false,
                                                attributes: [.posixPermissions: 0o700])
        if includeMarker { try Data(UUID().uuidString.utf8).write(to: file) }
        return account
    }

    private func marker(in account: URL) -> URL {
        account.appending(path: LioLocalAddressRelayClient.pendingDirectoryName, directoryHint: .isDirectory)
            .appending(path: LioLocalAddressRelayClient.pendingFileName)
    }
}
