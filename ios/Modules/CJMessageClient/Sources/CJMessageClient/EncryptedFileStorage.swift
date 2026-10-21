import Foundation
import CryptoKit

/// The future Keychain/session owner supplies the key. No key generation/persistence,
/// credential lookup, UserDefaults fallback or AUTH interpretation occurs here.
@MainActor public protocol MessageEncryptionKeyProvider: AnyObject {
    func key(for scope: StorageScope) throws -> SymmetricKey?
}

@MainActor public final class EncryptedFileStorage: SecureMessageStorage {
    private let directory: URL
    private let keys: any MessageEncryptionKeyProvider

    /// Host must supply an app-private resolved directory and enforce single-writer ownership.
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
        self.directory = directory; self.keys = keys
    }

    public func load(scope: StorageScope) throws -> Snapshot? {
        let key = try requireKey(scope)
        let path = file(scope)
        do {
            let attributes = try FileManager.default.attributesOfItem(atPath: path.path)
            guard attributes[.type] as? FileAttributeType == .typeRegular else { throw RecoveryError.unsafeDirectory }
        } catch let error as NSError where error.domain == NSCocoaErrorDomain && error.code == NSFileReadNoSuchFileError {
            return nil
        }
        let ciphertext = try Data(contentsOf: path)
        let clear = try AES.GCM.open(AES.GCM.SealedBox(combined: ciphertext), using: key, authenticating: scope.binding)
        return try JSONDecoder().decode(Snapshot.self, from: clear)
    }

    public func save(_ snapshot: Snapshot, scope: StorageScope) throws {
        let key = try requireKey(scope)
        let path = file(scope)
        if let attributes = try? FileManager.default.attributesOfItem(atPath: path.path),
           attributes[.type] as? FileAttributeType != .typeRegular { throw RecoveryError.unsafeDirectory }
        let clear = try JSONEncoder().encode(snapshot)
        let sealed = try AES.GCM.seal(clear, using: key, authenticating: scope.binding)
        guard let combined = sealed.combined else { throw RecoveryError.invalidSnapshot }
        #if os(iOS)
        try combined.write(to: path, options: [.atomic, .completeFileProtection])
        #else
        try combined.write(to: path, options: .atomic)
        #endif
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: path.path)
    }

    private func requireKey(_ scope: StorageScope) throws -> SymmetricKey {
        guard let key = try keys.key(for: scope), key.bitCount == 256 else { throw RecoveryError.keyUnavailable }
        return key
    }
    private func file(_ scope: StorageScope) -> URL {
        let name = SHA256.hash(data: scope.binding).map { String(format: "%02x", $0) }.joined()
        return directory.appendingPathComponent(name + ".sealed")
    }
}
