import Foundation
import Darwin

/// What one domain's local journal family may differ on.
public protocol LocalJournalCleanupPolicy {
    associatedtype Failure: Error
    static var unavailable: Failure { get }
    static var outcomeUnknown: Failure { get }
    /// Record file extension without the dot.
    static var recordExtension: String { get }
    /// Whether a record stem may be a UUID as well as a lowercase SHA-256 digest.
    static var acceptsUUIDStem: Bool { get }
}

public extension LocalJournalCleanupPolicy {
    static var acceptsUUIDStem: Bool { false }
}

/// Domain-local exact-target erasure. Retained descriptors prevent a replaced
/// directory (including an inode reused after unlink) from becoming the target.
/// No key lookup, plaintext, caller callback, await, recursion or wildcard scope.
@MainActor public final class LocalJournalCleanup<Policy: LocalJournalCleanupPolicy> {
    private let targets: [URL]
    private var handles: [String: Int32] = [:]
    public private(set) var started = false

    public init(root: URL, suffixes: [String]) throws {
        targets = [root] + suffixes.map { root.appendingPathExtension($0) }
        do {
            for target in targets {
                var entry = stat()
                if lstat(target.path, &entry) == 0 {
                    try retain(target)
                } else if errno != ENOENT {
                    throw Policy.unavailable
                }
            }
            try validateRegistered(root)
        } catch {
            for handle in handles.values { close(handle) }
            handles.removeAll()
            throw error
        }
    }
    deinit { for handle in handles.values { close(handle) } }

    public func checkReadable() throws {
        guard !started else { throw Policy.unavailable }
    }
    private func retain(_ target: URL) throws {
        guard target.isFileURL, target.standardizedFileURL.path == target.resolvingSymlinksInPath().path else {
            throw Policy.unavailable
        }
        let fd = open(target.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { throw Policy.unavailable }
        do { try validate(target, fd: fd) } catch { close(fd); throw error }
        handles[target.path] = fd
    }
    private func validate(_ target: URL, fd: Int32) throws {
        var entry = stat(); var held = stat()
        guard lstat(target.path, &entry) == 0, fstat(fd, &held) == 0,
              entry.st_dev == held.st_dev, entry.st_ino == held.st_ino,
              entry.st_mode & S_IFMT == S_IFDIR, entry.st_uid == getuid(), entry.st_mode & 0o077 == 0,
              target.path == target.resolvingSymlinksInPath().path else { throw Policy.unavailable }
    }
    public func validateRegistered(_ target: URL) throws {
        guard let fd = handles[target.path] else { throw Policy.unavailable }
        try validate(target, fd: fd)
    }
    /// Only creation through this original journal may add an initially absent
    /// known sidecar. A sidecar appearing independently is never adopted.
    public func openAdjacent(_ target: URL, create: Bool) throws -> Bool {
        try checkReadable()
        guard targets.contains(target) else { throw Policy.unavailable }
        if handles[target.path] != nil { try validateRegistered(target); return true }
        var entry = stat()
        guard lstat(target.path, &entry) != 0, errno == ENOENT else { throw Policy.unavailable }
        guard create else { return false }
        try FileManager.default.createDirectory(at: target, withIntermediateDirectories: false,
                                               attributes: [.posixPermissions: 0o700])
        try retain(target)
        return true
    }
    public func clear() throws {
        // Revoke this store family even when preflight or physical deletion fails.
        // Retry stays on these same held targets and never needs a business key.
        started = true
        var entries: [(fd: Int32, name: String, device: dev_t, inode: ino_t)] = []
        for target in targets {
            guard let fd = handles[target.path] else {
                var entry = stat()
                guard lstat(target.path, &entry) != 0, errno == ENOENT else { throw Policy.unavailable }
                continue
            }
            try validate(target, fd: fd)
            let names = try FileManager.default.contentsOfDirectory(atPath: target.path)
            for name in names {
                let stem = name.dropLast(Policy.recordExtension.utf8.count + 1)
                var entry = stat()
                let hash = stem.count == 64 && stem.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
                guard name.hasSuffix("." + Policy.recordExtension),
                      hash || (Policy.acceptsUUIDStem && UUID(uuidString: String(stem)) != nil),
                      fstatat(fd, name, &entry, AT_SYMLINK_NOFOLLOW) == 0,
                      entry.st_mode & S_IFMT == S_IFREG, entry.st_nlink == 1, entry.st_uid == getuid() else {
                    throw Policy.unavailable
                }
                entries.append((fd, name, entry.st_dev, entry.st_ino))
            }
        }
        // Complete preflight precedes the first unlink. Recheck each name against
        // its original inode; no externally supplied code executes in this phase.
        for target in targets where handles[target.path] != nil { try validateRegistered(target) }
        for item in entries {
            var current = stat()
            guard fstatat(item.fd, item.name, &current, AT_SYMLINK_NOFOLLOW) == 0,
                  current.st_dev == item.device, current.st_ino == item.inode,
                  current.st_mode & S_IFMT == S_IFREG, current.st_nlink == 1, current.st_uid == getuid() else {
                throw Policy.outcomeUnknown
            }
            guard unlinkat(item.fd, item.name, 0) == 0 else { throw Policy.outcomeUnknown }
        }
        for target in targets {
            guard let fd = handles[target.path] else { continue }
            guard fsync(fd) == 0 else { throw Policy.outcomeUnknown }
            try validateRegistered(target)
            guard try FileManager.default.contentsOfDirectory(atPath: target.path).isEmpty else {
                throw Policy.outcomeUnknown
            }
        }
    }
}
