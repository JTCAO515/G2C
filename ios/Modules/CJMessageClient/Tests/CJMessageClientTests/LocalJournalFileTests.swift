import Foundation
import Darwin
import Testing
@testable import CJMessageClient

@MainActor private final class Directory {
    let root = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
    let fd: Int32
    init() throws {
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        fd = open(root.path, O_RDONLY | O_DIRECTORY | O_CLOEXEC)
    }
    deinit { close(fd); try? FileManager.default.removeItem(at: root) }
    func names() throws -> [String] { try FileManager.default.contentsOfDirectory(atPath: root.path).sorted() }
    func bytes(_ name: String) throws -> Data { try Data(contentsOf: root.appendingPathComponent(name)) }
}

private let record = String(repeating: "a1", count: 32) + ".rec"
private let sealed = Data((0..<200).map { UInt8($0 % 251) })

@MainActor @Suite struct LocalJournalFileTests {
    @Test func publishesExactBytesUnderTheFinalNameOnly() throws {
        let d = try Directory()
        #expect(LocalJournalFile.createExclusive(record, in: d.fd, bytes: sealed))
        #expect(try d.names() == [record])
        #expect(try d.bytes(record) == sealed)
        var entry = stat()
        #expect(fstatat(d.fd, record, &entry, AT_SYMLINK_NOFOLLOW) == 0)
        #expect(entry.st_mode & 0o777 == 0o600)
        #expect(entry.st_nlink == 1)
    }

    @Test func neverReplacesAnExistingNameAndRemovesItsTemporary() throws {
        let d = try Directory()
        try Data("keep".utf8).write(to: d.root.appendingPathComponent(record))
        #expect(!LocalJournalFile.createExclusive(record, in: d.fd, bytes: sealed))
        #expect(try d.names() == [record])
        #expect(try d.bytes(record) == Data("keep".utf8))
    }

    @Test func completesShortAndInterruptedWrites() throws {
        let d = try Directory()
        var calls = 0
        let published = LocalJournalFile.createExclusive(record, in: d.fd, bytes: sealed) { fd, buffer, count in
            calls += 1
            if calls == 1 { errno = EINTR; return -1 }
            return Darwin.write(fd, buffer, min(count, 7))
        }
        #expect(published)
        #expect(calls > sealed.count / 7)
        #expect(try d.names() == [record])
        #expect(try d.bytes(record) == sealed)
    }

    @Test(arguments: [0, -1])
    func failedWriteLeavesNeitherARecordNorATemporary(result: Int) throws {
        let d = try Directory()
        var calls = 0
        let published = LocalJournalFile.createExclusive(record, in: d.fd, bytes: sealed) { fd, buffer, count in
            calls += 1
            if calls == 1 { return Darwin.write(fd, buffer, count / 2) }
            errno = EIO; return result
        }
        #expect(!published)
        #expect(try d.names().isEmpty)
    }

    @Test func temporaryNamesAreExactlyThisWritersOwn() throws {
        let id = UUID().uuidString
        #expect(LocalJournalFile.isTemporary(".write-" + id))
        for name in [".write-" + id.lowercased(), "write-" + id, ".write-" + id + ".rec", ".write-", ".write-x", record, ".tmp-" + id] {
            #expect(!LocalJournalFile.isTemporary(name), "\(name)")
        }
        let d = try Directory()
        try Data().write(to: d.root.appendingPathComponent(".write-" + id))
        try Data().write(to: d.root.appendingPathComponent(".write-x"))
        try Data().write(to: d.root.appendingPathComponent(record))
        #expect(try LocalJournalFile.recordNames(atPath: d.root.path).sorted() == [".write-x", record])
    }
}
