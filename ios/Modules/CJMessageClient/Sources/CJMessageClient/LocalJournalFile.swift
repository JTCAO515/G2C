import Foundation
import Darwin

/// Crash-safe exclusive creation of one immutable journal record. Bytes go to a
/// hidden temporary entry, are written in full and synced, then renamed without
/// replacing an existing name, so a crash or short write never leaves a partial
/// record under its final name. Readers skip the temporary entries; cleanup erases them.
public enum LocalJournalFile {
    private static let temporaryPrefix = ".write-"

    /// Exactly the names this writer creates. Any other entry stays the caller's to reject.
    public static func isTemporary(_ name: String) -> Bool {
        guard name.hasPrefix(temporaryPrefix) else { return false }
        let suffix = String(name.dropFirst(temporaryPrefix.count))
        return UUID(uuidString: suffix)?.uuidString == suffix
    }
    /// Directory entries other than this writer's temporary names.
    public static func recordNames(atPath path: String) throws -> [String] {
        try FileManager.default.contentsOfDirectory(atPath: path).filter { !isTemporary($0) }
    }
    /// False on any failure. Before the rename the temporary entry is removed; an
    /// existing `name` is never replaced. Only the final directory sync can fail after
    /// the rename, which leaves the record in place like an unsynced exclusive create.
    public static func createExclusive(_ name: String, in directory: Int32, bytes: Data) -> Bool {
        createExclusive(name, in: directory, bytes: bytes) { Darwin.write($0, $1, $2) }
    }
    // Short-write fault injection for isolated tests only.
    static func createExclusive(_ name: String, in directory: Int32, bytes: Data,
                                write: (Int32, UnsafeRawPointer, Int) -> Int) -> Bool {
        let temporary = temporaryPrefix + UUID().uuidString
        let fd = openat(directory, temporary, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600)
        guard fd >= 0 else { return false }
        var renamed = false
        defer { close(fd); if !renamed { unlinkat(directory, temporary, 0) } }
        let count = bytes.withUnsafeBytes { buffer -> Int in
            var offset = 0
            while offset < buffer.count {
                let n = write(fd, buffer.baseAddress!.advanced(by: offset), buffer.count - offset)
                if n < 0 && errno == EINTR { continue }
                if n <= 0 { return -1 }; offset += n
            }
            return offset
        }
        guard count == bytes.count, fsync(fd) == 0,
              renameatx_np(directory, temporary, directory, name, UInt32(RENAME_EXCL)) == 0 else { return false }
        renamed = true
        return fsync(directory) == 0
    }
}
