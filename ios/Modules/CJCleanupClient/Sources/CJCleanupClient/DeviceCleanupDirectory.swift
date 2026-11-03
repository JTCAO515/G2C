import Foundation
import Darwin

/// A trusted App root supplies its own fixed native path. This type never accepts
/// a server target/path as authority and never creates, recursively erases or
/// adopts a directory which appears later. Held descriptors pin original inodes.
@MainActor public final class DeviceCleanupDirectory {
    private let path: URL
    private let descriptor: Int32?
    private let parent: DeviceCleanupDirectory?
    private let absentName: String?
    private let requiresPrivate: Bool

    public convenience init(existingPrivateDirectory path: URL) throws {
        try self.init(path: path, requiresPrivate: true)
    }
    /// Read-only ancestor pin for an absent private child inside the App container.
    public convenience init(existingOwnedAncestor path: URL) throws {
        try self.init(path: path, requiresPrivate: false)
    }
    private init(path: URL, requiresPrivate: Bool) throws {
        guard path.isFileURL, path.path.hasPrefix("/") else { throw CleanupFailure.unavailable }
        // The physical O_NOFOLLOW walk below is authoritative. Foundation may
        // normalize /private/var back to /var and is not a physical-path proof.
        let fd = try Self.openPhysical(path.path)
        do { try Self.validateOwned(fd, requiresPrivate: requiresPrivate) } catch { close(fd); throw error }
        self.path = path; descriptor = fd; parent = nil; absentName = nil; self.requiresPrivate = requiresPrivate
    }
    /// Missing account roots are represented by their original held private parent
    /// and exact missing child. They are not synthesized on behalf of a cleanup.
    public init(absentChild name: String, of parent: DeviceCleanupDirectory) throws {
        guard !name.isEmpty, ![".",".."].contains(name), !name.contains("/"), !name.contains("\0") else { throw CleanupFailure.unavailable }
        try parent.validateIdentity()
        if let fd = parent.descriptor {
            var entry = stat()
            guard fstatat(fd, name, &entry, AT_SYMLINK_NOFOLLOW) != 0, errno == ENOENT else { throw CleanupFailure.unavailable }
        }
        path = parent.path.appendingPathComponent(name, isDirectory: true)
        descriptor = nil; self.parent = parent; absentName = name; requiresPrivate = true
    }
    private init(path: URL, descriptor: Int32, parent: DeviceCleanupDirectory) {
        self.path = path; self.descriptor = descriptor; self.parent = parent
        absentName = nil; requiresPrivate = true
    }
    /// Fixed App layout traversal from an already captured trusted OS base.
    /// Missing descendants are proved absent without making directories.
    public func child(_ name: String) throws -> DeviceCleanupDirectory {
        guard !name.isEmpty, ![".",".."].contains(name), !name.contains("/"), !name.contains("\0") else { throw CleanupFailure.unavailable }
        try validateIdentity()
        guard let descriptor else { return try DeviceCleanupDirectory(absentChild: name, of: self) }
        var entry = stat()
        if fstatat(descriptor, name, &entry, AT_SYMLINK_NOFOLLOW) != 0 {
            guard errno == ENOENT else { throw CleanupFailure.unavailable }
            return try DeviceCleanupDirectory(absentChild: name, of: self)
        }
        let fd = openat(descriptor, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { throw CleanupFailure.unavailable }
        do { try Self.validateOwned(fd, requiresPrivate: true) } catch { close(fd); throw error }
        let child = DeviceCleanupDirectory(path: path.appendingPathComponent(name, isDirectory: true), descriptor: fd, parent: self)
        try child.validateIdentity()
        return child
    }
    /// For domain-owned primitives only; callers must keep this identity proof
    /// and revalidate around construction/use. No directory is created here.
    public func existingURLForTrustedHost() throws -> URL? {
        try validateIdentity()
        return descriptor == nil ? nil : path
    }
    public var existsInOriginalCapture: Bool { descriptor != nil }
    deinit { if let descriptor { close(descriptor) } }
    private static func openPhysical(_ path: String) throws -> Int32 {
        var fd = open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC)
        guard fd >= 0 else { throw CleanupFailure.unavailable }
        for part in path.split(separator: "/") {
            guard part != ".", part != ".." else { close(fd); throw CleanupFailure.unavailable }
            let next = openat(fd, String(part), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
            close(fd)
            guard next >= 0 else { throw CleanupFailure.unavailable }
            fd = next
        }
        return fd
    }
    private static func validateOwned(_ fd: Int32, requiresPrivate: Bool) throws {
        var entry = stat()
        guard fstat(fd, &entry) == 0, entry.st_mode & S_IFMT == S_IFDIR,
              entry.st_uid == getuid(), !requiresPrivate || entry.st_mode & 0o077 == 0 else { throw CleanupFailure.unavailable }
    }
    public func validateIdentity() throws {
        if let descriptor {
            try parent?.validateIdentity()
            let current = try Self.openPhysical(path.path); defer { close(current) }
            try Self.validateOwned(current, requiresPrivate: requiresPrivate); try Self.validateOwned(descriptor, requiresPrivate: requiresPrivate)
            var before = stat(), now = stat()
            guard fstat(descriptor, &before) == 0, fstat(current, &now) == 0,
                  before.st_dev == now.st_dev, before.st_ino == now.st_ino else { throw CleanupFailure.stale }
        } else {
            guard let parent, let absentName else { throw CleanupFailure.unavailable }
            try parent.validateIdentity()
            if let fd = parent.descriptor {
                var entry = stat()
                guard fstatat(fd, absentName, &entry, AT_SYMLINK_NOFOLLOW) != 0, errno == ENOENT else { throw CleanupFailure.stale }
            }
        }
    }
    /// Callback-free emptiness evidence for shared-key erasure. An unknown entry,
    /// late-created child or replaced root never counts as confirmed empty.
    public func requireEmpty() throws {
        try validateIdentity()
        guard descriptor != nil else { return }
        guard try FileManager.default.contentsOfDirectory(atPath: path.path).isEmpty else { throw CleanupFailure.unavailable }
        try validateIdentity()
    }
    /// Minimal manifest identity only; no file content, key or plaintext exposure.
    public func identityReference() throws -> String {
        try validateIdentity()
        if let descriptor {
            var entry = stat()
            guard fstat(descriptor, &entry) == 0 else { throw CleanupFailure.unavailable }
            return "directory:" + String(entry.st_dev) + ":" + String(entry.st_ino)
        }
        guard let parent, let absentName else { throw CleanupFailure.unavailable }
        return try "absent:" + parent.identityReference() + ":" + absentName
    }
}
