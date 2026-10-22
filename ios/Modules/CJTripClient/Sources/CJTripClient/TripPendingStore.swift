// Adapted from fixed CJMemoryClient 884a070 append-only encrypted pending pattern.
import Foundation
import CryptoKit
import Darwin
import CJMessageKeys

func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }

/// Immutable, exclusive encrypted records. Reopening grants query only; no resend/delete API.
@MainActor public final class TripPendingStore {
    private let root: URL
    private let directory: Int32
    private let maximumBytes: Int
    private let maximumRecords: Int
    private let namespace: MessageKeyNamespace
    private let keyID: UUID
    private let key: () throws -> SymmetricKey
    private var ad: Data { Data("CJTripPending|1|\(namespace.environment.uuidString)|\(namespace.account.uuidString)|\(namespace.purpose.rawValue)|\(keyID.uuidString)".utf8) }
    public convenience init(directory: URL, maximumBytes: Int, maximumRecords: Int, binding: TripBinding,
                            expectedKeyID: UUID, provider: any MessageEncryptionKeyProvider) throws {
        let namespace = MessageKeyNamespace(environment: binding.environment, account: binding.account, purpose: .localTripPendingV1)
        guard provider.namespace == namespace else { throw TripFailure.keyUnavailable }
        try self.init(directory: directory, maximumBytes: maximumBytes, maximumRecords: maximumRecords, namespace: namespace, keyID: expectedKeyID) {
            guard provider.namespace == namespace else { throw TripFailure.keyUnavailable }
            let op = try provider.begin(.lookup)
            guard let key = try provider.existing(expectedID: expectedKeyID, for: op), provider.isCurrent(op),
                  key.namespace == namespace, key.id == expectedKeyID else { throw TripFailure.keyUnavailable }
            return key.withSymmetricKey { $0 }
        }
    }
    // Package-only test seam; no public raw key initializer and no platform key calls in tests.
    init(directory: URL, maximumBytes: Int, maximumRecords: Int, namespace: MessageKeyNamespace, keyID: UUID,
         key: @escaping () throws -> SymmetricKey) throws {
        guard maximumBytes > 0, maximumBytes <= Int.max - 28, maximumRecords > 0, directory.isFileURL,
              directory.standardizedFileURL.path == directory.resolvingSymlinksInPath().path else { throw TripFailure.storageUnavailable }
        let fd = open(directory.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { throw TripFailure.storageUnavailable }
        var st = stat()
        guard fstat(fd, &st) == 0, st.st_uid == getuid(), st.st_mode & 0o077 == 0 else { close(fd); throw TripFailure.storageUnavailable }
        root = directory; self.directory = fd; self.maximumBytes = maximumBytes; self.maximumRecords = maximumRecords
        self.namespace = namespace; self.keyID = keyID; self.key = key
    }
    deinit { close(directory) }
    func validate(_ binding: TripBinding) throws {
        guard namespace.environment == binding.environment, namespace.account == binding.account,
              namespace.purpose == .localTripPendingV1 else { throw TripFailure.staleBinding }
    }
    private func name(_ id: String) throws -> String {
        guard tripID(id) else { throw TripFailure.invalidInput }
        return digest(Data(id.utf8)) + ".trip"
    }
    func append(_ pending: TripPending, validateBinding: () throws -> Void = {}) throws {
        let existing = try self.pending()
        guard existing.count < maximumRecords, !existing.contains(where: { same($0.actionID, pending.actionID) }) else { throw TripFailure.storageUnavailable }
        try pending.validate()
        let plain = try JSONEncoder().encode(pending)
        guard plain.count <= maximumBytes else { throw TripFailure.invalidInput }
        let encrypted = try AES.GCM.seal(plain, using: key(), authenticating: ad)
        guard let bytes = encrypted.combined else { throw TripFailure.storageUnavailable }
        try validateDirectory()
        try validateBinding()
        try validateDirectory()
        let fd = openat(directory, try name(pending.actionID), O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600)
        guard fd >= 0 else { throw TripFailure.storageUnavailable }
        defer { close(fd) }
        let count = bytes.withUnsafeBytes { write(fd, $0.baseAddress, $0.count) }
        guard count == bytes.count, fsync(fd) == 0, fsync(directory) == 0 else { throw TripFailure.storageUnavailable }
        try validateDirectory()
    }
    func validateDirectory() throws {
        // Callback/await boundary checks, not a claim of protection against arbitrary same-UID races.
        var current = stat(); var original = stat()
        guard lstat(root.path, &current) == 0, fstat(directory, &original) == 0,
              current.st_ino == original.st_ino, current.st_dev == original.st_dev,
              current.st_mode & S_IFMT == S_IFDIR, current.st_uid == getuid(), current.st_mode & 0o077 == 0,
              root.path == root.resolvingSymlinksInPath().path else { throw TripFailure.storageUnavailable }
    }
    struct Durability {
        fileprivate let filename: String
        fileprivate let ciphertext: Data
    }
    /// Captures the exact ciphertext whose plaintext was checked, before the last host callback.
    func requireOriginal(_ expected: TripPending) throws -> Durability {
        try validateDirectory()
        let filename = try name(expected.actionID)
        let bytes = try readCiphertext(filename)
        let material = try key()
        try validateDirectory()
        let plain = try AES.GCM.open(AES.GCM.SealedBox(combined: bytes), using: material, authenticating: ad)
        let observed = try JSONDecoder().decode(TripPending.self, from: plain)
        try observed.validate()
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        guard try encoder.encode(observed) == encoder.encode(expected) else { throw TripFailure.storageUnavailable }
        let proof = Durability(filename: filename, ciphertext: bytes)
        try validateDurability(proof)
        return proof
    }
    /// No provider, binding, caller callback or await. Must be last before outflow/settlement.
    func validateDurability(_ proof: Durability) throws {
        try validateDirectory()
        guard try readCiphertext(proof.filename) == proof.ciphertext else { throw TripFailure.storageUnavailable }
        try validateDirectory()
    }
    private func readCiphertext(_ filename: String) throws -> Data {
        let fd = openat(directory, filename, O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { throw TripFailure.storageUnavailable }
        defer { close(fd) }
        var st = stat()
        guard fstat(fd, &st) == 0, st.st_mode & S_IFMT == S_IFREG, st.st_nlink == 1,
              st.st_uid == getuid(), st.st_mode & 0o077 == 0, st.st_size > 28,
              st.st_size <= maximumBytes + 28 else { throw TripFailure.storageUnavailable }
        var bytes = Data(count: Int(st.st_size))
        let count = bytes.withUnsafeMutableBytes { read(fd, $0.baseAddress, $0.count) }
        guard count == bytes.count else { throw TripFailure.storageUnavailable }
        return bytes
    }
    public func pending() throws -> [TripPending] {
        try validateDirectory()
        let names = try FileManager.default.contentsOfDirectory(atPath: root.path)
        guard names.count <= maximumRecords else { throw TripFailure.storageUnavailable }
        let result = try names.sorted().map { filename in
            let stem = String(filename.dropLast(5))
            guard filename.hasSuffix(".trip"), (stem.count == 64 && stem.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) })) else { throw TripFailure.storageUnavailable }
            let bytes = try readCiphertext(filename)
            let material = try key()
            try validateDirectory()
            let plain = try AES.GCM.open(AES.GCM.SealedBox(combined: bytes), using: material, authenticating: ad)
            let pending = try JSONDecoder().decode(TripPending.self, from: plain)
            try pending.validate()
            guard try name(pending.actionID) == filename else { throw TripFailure.storageUnavailable }
            return pending
        }
        try validateDirectory()
        guard Set(result.map { Data($0.actionID.utf8) }).count == result.count else { throw TripFailure.storageUnavailable }
        return result
    }
}
