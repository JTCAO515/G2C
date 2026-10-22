import Foundation
import Darwin

/// Isolated file primitive, intentionally module-internal until key/session/CLEANUP are fixed.
/// One synchronous owner; no automatic retry, migration, key creation, or old-version fallback.
final class AtomicSnapshotStore {
    enum Settlement: Equatable { case committed, originalRetained, unknown }
    private let root: String
    private let directory: Int32
    private let identity: stat
    private let name = "snapshot.aesgcm"
    private var pending: (original: Data?, attempted: Data)?
    // Fault injection for isolated tests only. Called after rename, before directory fsync.
    var afterRename: (() throws -> Void)?

    init(existingPrivateDirectory url: URL) throws {
        guard url.isFileURL, url.path.hasPrefix("/"), !url.path.contains("/../") else { throw OfflineFailure.invalidPath }
        root = url.path
        directory = try Self.walk(root)
        var info = stat()
        guard fstat(directory, &info) == 0, info.st_uid == getuid(), info.st_mode & 0o777 == 0o700 else {
            close(directory); throw OfflineFailure.invalidPath
        }
        identity = info
    }
    deinit { close(directory) }

    private static func walk(_ path: String) throws -> Int32 {
        var fd = Darwin.open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC)
        guard fd >= 0 else { throw OfflineFailure.invalidPath }
        for part in path.split(separator: "/") {
            guard part != ".", part != ".." else { close(fd); throw OfflineFailure.invalidPath }
            let next = openat(fd, String(part), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
            close(fd)
            guard next >= 0 else { throw OfflineFailure.invalidPath }
            fd = next
        }
        return fd
    }
    private func checkRoot() throws {
        let fd = try Self.walk(root); defer { close(fd) }
        var info = stat()
        guard fstat(fd, &info) == 0, info.st_dev == identity.st_dev, info.st_ino == identity.st_ino,
              info.st_uid == getuid(), info.st_mode & 0o777 == 0o700 else { throw OfflineFailure.invalidPath }
    }
    func read() throws -> Data? {
        try checkRoot()
        let fd = openat(directory, name, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC)
        if fd < 0 {
            if errno == ENOENT { return nil }
            throw OfflineFailure.invalidPath
        }
        defer { close(fd) }
        var info = stat()
        guard fstat(fd, &info) == 0, info.st_mode & S_IFMT == S_IFREG, info.st_mode & 0o777 == 0o600,
              info.st_uid == getuid(), info.st_nlink == 1,
              info.st_size > 0, info.st_size <= SnapshotCodec.maximumBytes else { throw OfflineFailure.corrupt }
        var data = Data(count: Int(info.st_size))
        let expected = data.count
        let count = data.withUnsafeMutableBytes { buffer -> Int in
            var offset = 0
            while offset < expected {
                let n = Darwin.read(fd, buffer.baseAddress!.advanced(by: offset), expected - offset)
                if n < 0 && errno == EINTR { continue }
                if n <= 0 { return -1 }; offset += n
            }
            return offset
        }
        var after = stat(); var named = stat()
        guard count == expected, fstat(fd, &after) == 0,
              fstatat(directory, name, &named, AT_SYMLINK_NOFOLLOW) == 0,
              after.st_dev == named.st_dev, after.st_ino == named.st_ino,
              after.st_size == info.st_size,
              after.st_mtimespec.tv_sec == info.st_mtimespec.tv_sec,
              after.st_mtimespec.tv_nsec == info.st_mtimespec.tv_nsec,
              after.st_ctimespec.tv_sec == info.st_ctimespec.tv_sec,
              after.st_ctimespec.tv_nsec == info.st_ctimespec.tv_nsec else { throw OfflineFailure.corrupt }
        try checkRoot()
        return data
    }
    func requireNoPendingWrite() throws {
        guard pending == nil else { throw OfflineFailure.writeUnknown }
    }
    func write(_ sealed: Data) throws {
        try requireNoPendingWrite()
        guard !sealed.isEmpty, sealed.count <= SnapshotCodec.maximumBytes else { throw OfflineFailure.invalidSnapshot }
        let previous = try read()
        let temporary = ".write-" + UUID().uuidString
        let fd = openat(directory, temporary, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600)
        guard fd >= 0 else { throw OfflineFailure.storageFailure }
        defer { close(fd); unlinkat(directory, temporary, 0) }
        guard fchmod(fd, 0o600) == 0 else { throw OfflineFailure.storageFailure }
        let count = sealed.withUnsafeBytes { buffer -> Int in
            var offset = 0
            while offset < buffer.count {
                let n = Darwin.write(fd, buffer.baseAddress!.advanced(by: offset), buffer.count - offset)
                if n < 0 && errno == EINTR { continue }
                if n <= 0 { return -1 }; offset += n
            }
            return offset
        }
        guard count == sealed.count, fsync(fd) == 0 else { throw OfflineFailure.storageFailure }
        try checkRoot()
        // Verify no unobserved replacement before committing. No callbacks in this interval.
        guard try read() == previous else { throw OfflineFailure.storageFailure }
        pending = (previous, sealed)
        guard renameat(directory, temporary, directory, name) == 0 else { throw OfflineFailure.writeUnknown }
        do {
            try afterRename?()
            guard fsync(directory) == 0, try read() == sealed else { throw OfflineFailure.writeUnknown }
            pending = nil
        } catch { throw OfflineFailure.writeUnknown }
    }
    /// Only compare ORIGINAL attempted ciphertext; never reseal (which creates a new nonce).
    func reconcileOriginalWrite() -> Settlement {
        guard let pending else { return .unknown }
        do {
            let found = try read()
            if found == pending.attempted {
                guard fsync(directory) == 0 else { return .unknown }
                self.pending = nil; return .committed
            }
            if found == pending.original { self.pending = nil; return .originalRetained }
        } catch { return .unknown }
        return .unknown
    }
    /// Only this directory's fixed cache entry; no recursive or device-wide cleanup claim.
    func clearLocalEntry() throws {
        guard pending == nil else { throw OfflineFailure.writeUnknown }
        _ = try read(); try checkRoot()
        guard unlinkat(directory, name, 0) == 0 || errno == ENOENT, fsync(directory) == 0 else {
            throw OfflineFailure.storageFailure
        }
    }
}
