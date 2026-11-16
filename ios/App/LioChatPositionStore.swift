import CJMessageClient
import CJMessageKeys
import CryptoKit
import Darwin
import Foundation

/// App-owned encrypted navigation/draft state; never a message or write receipt.
@MainActor final class LioChatPositionStore {
    static let filename = "lio-position.cjlio"
    private static let prefix = Data("CJLIOP01".utf8)
    private static let headerSize = 44
    private static let maximumBytes = 1_048_576
    private let directory: URL
    private let identity: stat
    private let namespace: MessageKeyNamespace
    private let keys: any CJMessageKeys.MessageEncryptionKeyProvider
    private let validate: @MainActor () throws -> Void

    init(directory: URL, namespace: MessageKeyNamespace, keys: any CJMessageKeys.MessageEncryptionKeyProvider,
         validate: @escaping @MainActor () throws -> Void) throws {
        guard namespace.purpose == .localMessageStorageV1, keys.namespace == namespace else {
            throw MessageKeyFailure.invalidConfiguration
        }
        guard directory.isFileURL,
              directory.standardizedFileURL.path == directory.resolvingSymlinksInPath().path else {
            throw RecoveryError.unsafeDirectory
        }
        var identity = stat()
        guard lstat(directory.path, &identity) == 0, identity.st_mode & S_IFMT == S_IFDIR,
              identity.st_uid == getuid(), identity.st_mode & 0o077 == 0 else { throw RecoveryError.unsafeDirectory }
        self.directory = directory; self.identity = identity; self.namespace = namespace
        self.keys = keys; self.validate = validate
    }

    /// Only the existing authorized cleanup host may call this after retiring consumers.
    /// It removes this file alone; no key lookup or message-journal deletion occurs here.
    func clearRetiredPosition() throws {
        let fd = try directoryHandle(); defer { close(fd) }
        var entry = stat()
        if fstatat(fd, Self.filename, &entry, AT_SYMLINK_NOFOLLOW) == 0 {
            guard entry.st_mode & S_IFMT == S_IFREG, entry.st_nlink == 1,
                  entry.st_uid == getuid(), entry.st_mode & 0o077 == 0 else { throw RecoveryError.unsafeDirectory }
            guard unlinkat(fd, Self.filename, 0) == 0 else { throw RecoveryError.persistenceUnknown }
        } else if errno != ENOENT { throw RecoveryError.persistenceUnknown }
        guard fsync(fd) == 0, fstatat(fd, Self.filename, &entry, AT_SYMLINK_NOFOLLOW) != 0,
              errno == ENOENT else { throw RecoveryError.persistenceUnknown }
        try validateDirectory()
    }

    func load() throws -> Data? {
        try validate()
        let fd = try directoryHandle(); defer { close(fd) }
        guard let bytes = try read(fd) else {
            _ = try existingKey(expectedID: nil)
            return nil
        }
        let envelope = try envelope(bytes)
        let key = try existingKey(expectedID: envelope.id)
        let plain = try open(envelope, key: key)
        try validate(); try validateDirectory()
        return plain
    }

    func save(_ bytes: Data) throws {
        guard bytes.count <= Self.maximumBytes else { throw RecoveryError.invalidSnapshot }
        try validate()
        let fd = try directoryHandle(); defer { close(fd) }
        let previous = try read(fd).map(envelope)
        let key = try existingKey(expectedID: previous?.id)
        // An unreadable old draft is evidence, never permission to replace it.
        if let previous { _ = try open(previous, key: key) }
        let header = Self.prefix + Data(key.id.uuidString.utf8)
        let cipher = try key.withSymmetricKey {
            try AES.GCM.seal(bytes, using: $0, authenticating: binding + header)
        }
        guard let combined = cipher.combined else { throw RecoveryError.invalidSnapshot }
        try validate(); try validateDirectory()
        let path = directory.appendingPathComponent(Self.filename)
        #if os(iOS)
        try (header + combined).write(to: path, options: [.atomic, .completeFileProtection])
        #else
        try (header + combined).write(to: path, options: .atomic)
        #endif
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: path.path)
        try validate(); try validateDirectory()
    }

    private var binding: Data {
        Data(("CJLIO-position.1\u{0}" + namespace.environment.uuidString + "\u{0}" + namespace.account.uuidString
              + "\u{0}" + namespace.purpose.rawValue).utf8)
    }

    private func existingKey(expectedID: UUID?) throws -> MessageEncryptionKey {
        guard keys.namespace == namespace else { throw MessageKeyFailure.inactiveNamespace }
        let operation = try keys.begin(.lookup)
        guard keys.isCurrent(operation) else { throw MessageKeyFailure.staleOperation }
        guard let key = try keys.existing(expectedID: expectedID, for: operation) else { throw RecoveryError.keyUnavailable }
        guard keys.isCurrent(operation), key.namespace == namespace,
              expectedID == nil || key.id == expectedID else { throw MessageKeyFailure.staleOperation }
        try validate()
        return key
    }

    private struct Envelope { let id: UUID; let header: Data; let ciphertext: Data }
    private func envelope(_ bytes: Data) throws -> Envelope {
        guard bytes.starts(with: Self.prefix), bytes.count > Self.headerSize,
              let value = String(data: bytes[8..<Self.headerSize], encoding: .utf8),
              let id = UUID(uuidString: value), id.uuidString == value else { throw RecoveryError.invalidSnapshot }
        return .init(id: id, header: Data(bytes.prefix(Self.headerSize)), ciphertext: Data(bytes.dropFirst(Self.headerSize)))
    }
    private func open(_ envelope: Envelope, key: MessageEncryptionKey) throws -> Data {
        try key.withSymmetricKey {
            try AES.GCM.open(AES.GCM.SealedBox(combined: envelope.ciphertext), using: $0,
                             authenticating: binding + envelope.header)
        }
    }
    private func validateDirectory() throws {
        var current = stat()
        guard lstat(directory.path, &current) == 0, current.st_dev == identity.st_dev,
              current.st_ino == identity.st_ino, current.st_uid == getuid(),
              current.st_mode & S_IFMT == S_IFDIR, current.st_mode & 0o077 == 0 else { throw RecoveryError.unsafeDirectory }
    }
    private func directoryHandle() throws -> Int32 {
        try validateDirectory()
        let fd = Darwin.open(directory.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { throw RecoveryError.unsafeDirectory }
        var current = stat()
        guard fstat(fd, &current) == 0, current.st_dev == identity.st_dev, current.st_ino == identity.st_ino else {
            close(fd); throw RecoveryError.unsafeDirectory
        }
        return fd
    }
    private func read(_ directory: Int32) throws -> Data? {
        let fd = openat(directory, Self.filename, O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else {
            if errno == ENOENT { return nil }
            throw RecoveryError.unsafeDirectory
        }
        defer { close(fd) }
        var entry = stat()
        let maximum = Self.maximumBytes + Self.headerSize + 28
        guard fstat(fd, &entry) == 0, entry.st_mode & S_IFMT == S_IFREG, entry.st_nlink == 1,
              entry.st_uid == getuid(), entry.st_mode & 0o077 == 0,
              entry.st_size <= maximum else { throw RecoveryError.unsafeDirectory }
        let handle = FileHandle(fileDescriptor: fd, closeOnDealloc: false)
        var bytes = Data()
        while let chunk = try handle.read(upToCount: maximum + 1 - bytes.count), !chunk.isEmpty {
            bytes.append(chunk)
            guard bytes.count <= maximum else { throw RecoveryError.invalidSnapshot }
        }
        return bytes
    }
}
