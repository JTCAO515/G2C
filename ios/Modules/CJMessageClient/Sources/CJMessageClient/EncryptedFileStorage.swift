import Foundation
import CryptoKit
import Darwin

/// Storage material supplied by a trusted external provider, not an AUTH assertion.
public struct MessageStorageKey: CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    public let id: UUID
    fileprivate let key: SymmetricKey
    public init(id: UUID, key: SymmetricKey) { self.id = id; self.key = key }
    public var description: String { "<redacted message storage key>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
}

@MainActor public protocol MessageEncryptionKeyProvider: AnyObject {
    /// Read existing material only. Missing/unknown must never auto-create a replacement.
    func existing(for scope: StorageScope, expectedID: UUID?) throws -> MessageStorageKey?
}

@MainActor public final class EncryptedFileStorage: SecureMessageStorage {
    private let directory: URL
    private let keys: any MessageEncryptionKeyProvider
    private let directoryIdentity: stat
    private let prefix = Data("CJMKEY02".utf8)
    private let headerSize = 44 // 8-byte version + canonical 36-byte UUID; both authenticated.

    public init(directory: URL, keys: any MessageEncryptionKeyProvider) throws {
        guard directory.isFileURL, directory.standardizedFileURL.path == directory.resolvingSymlinksInPath().path else {
            throw RecoveryError.unsafeDirectory
        }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                               attributes: [.posixPermissions: 0o700])
        let attributes = try FileManager.default.attributesOfItem(atPath: directory.path)
        guard attributes[.type] as? FileAttributeType == .typeDirectory,
              let permissions = attributes[.posixPermissions] as? NSNumber,
              permissions.intValue & 0o077 == 0 else { throw RecoveryError.unsafeDirectory }
        var identity = stat()
        guard lstat(directory.path, &identity) == 0 else { throw RecoveryError.unsafeDirectory }
        self.directory = directory; self.keys = keys; directoryIdentity = identity
    }

    /// Local physical removal only. A trusted cleanup host must retire all consumers first.
    /// No key lookup, server deletion or device-wide completion is implied.
    public func clearLocalSnapshot(scope: StorageScope) throws {
        guard directory.standardizedFileURL.path == directory.resolvingSymlinksInPath().path else {
            throw RecoveryError.unsafeDirectory
        }
        let fd = open(directory.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { throw RecoveryError.unsafeDirectory }
        defer { close(fd) }
        var current = stat()
        guard fstat(fd, &current) == 0, current.st_dev == directoryIdentity.st_dev,
              current.st_ino == directoryIdentity.st_ino, current.st_uid == getuid(),
              current.st_mode & 0o077 == 0 else { throw RecoveryError.unsafeDirectory }
        let name = file(scope).lastPathComponent
        var entry = stat()
        if fstatat(fd, name, &entry, AT_SYMLINK_NOFOLLOW) == 0 {
            guard entry.st_mode & S_IFMT == S_IFREG, entry.st_nlink == 1,
                  entry.st_uid == getuid() else { throw RecoveryError.unsafeDirectory }
            guard unlinkat(fd, name, 0) == 0 else { throw RecoveryError.persistenceUnknown }
        } else if errno != ENOENT { throw RecoveryError.persistenceUnknown }
        guard fsync(fd) == 0, fstatat(fd, name, &entry, AT_SYMLINK_NOFOLLOW) != 0,
              errno == ENOENT else { throw RecoveryError.persistenceUnknown }
        var named = stat()
        guard lstat(directory.path, &named) == 0, named.st_dev == current.st_dev,
              named.st_ino == current.st_ino, named.st_mode & S_IFMT == S_IFDIR else {
            throw RecoveryError.unsafeDirectory
        }
    }

    public func load(scope: StorageScope) throws -> Snapshot? {
        guard let bytes = try read(scope) else {
            // Missing file is not permission to create a key or infer remote absence.
            _ = try requireKey(scope, expectedID: nil)
            return nil
        }
        let (id, header, ciphertext) = try envelope(bytes)
        let material = try requireKey(scope, expectedID: id)
        let clear = try AES.GCM.open(AES.GCM.SealedBox(combined: ciphertext), using: material.key,
                                     authenticating: scope.binding + header)
        return try JSONDecoder().decode(Snapshot.self, from: clear)
    }

    public func save(_ snapshot: Snapshot, scope: StorageScope) throws {
        let old = try read(scope)
        let expectedID = try old.map { try envelope($0).0 }
        let material = try requireKey(scope, expectedID: expectedID)
        if let old {
            let (_, header, ciphertext) = try envelope(old)
            // Never overwrite corrupt/legacy/key-mismatched existing ciphertext.
            _ = try AES.GCM.open(AES.GCM.SealedBox(combined: ciphertext), using: material.key,
                                  authenticating: scope.binding + header)
        }
        let header = prefix + Data(material.id.uuidString.utf8)
        let clear = try JSONEncoder().encode(snapshot)
        let sealed = try AES.GCM.seal(clear, using: material.key, authenticating: scope.binding + header)
        guard let combined = sealed.combined else { throw RecoveryError.invalidSnapshot }
        #if os(iOS)
        try (header + combined).write(to: file(scope), options: [.atomic, .completeFileProtection])
        #else
        try (header + combined).write(to: file(scope), options: .atomic)
        #endif
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file(scope).path)
    }

    private func read(_ scope: StorageScope) throws -> Data? {
        let path = file(scope)
        do {
            let attributes = try FileManager.default.attributesOfItem(atPath: path.path)
            guard attributes[.type] as? FileAttributeType == .typeRegular else { throw RecoveryError.unsafeDirectory }
        } catch let error as NSError where error.domain == NSCocoaErrorDomain && error.code == NSFileReadNoSuchFileError { return nil }
        return try Data(contentsOf: path)
    }
    private func envelope(_ bytes: Data) throws -> (UUID, Data, Data) {
        guard bytes.starts(with: prefix) else { throw RecoveryError.legacyStorageFormat }
        guard bytes.count > headerSize,
              let text = String(data: bytes[8..<headerSize], encoding: .utf8),
              let id = UUID(uuidString: text), id.uuidString == text else { throw RecoveryError.invalidSnapshot }
        return (id, Data(bytes.prefix(headerSize)), Data(bytes.dropFirst(headerSize)))
    }
    private func requireKey(_ scope: StorageScope, expectedID: UUID?) throws -> MessageStorageKey {
        guard let material = try keys.existing(for: scope, expectedID: expectedID), material.key.bitCount == 256 else {
            throw RecoveryError.keyUnavailable
        }
        guard expectedID == nil || expectedID == material.id else { throw RecoveryError.keyMismatch }
        return material
    }
    private func file(_ scope: StorageScope) -> URL {
        let name = SHA256.hash(data: scope.binding).map { String(format: "%02x", $0) }.joined()
        return directory.appendingPathComponent(name + ".sealed")
    }
}
